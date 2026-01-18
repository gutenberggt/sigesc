import { db, getPendingSyncItems, updateSyncQueueItem, removeSyncQueueItem, SYNC_STATUS, countPendingSyncItems, updateSyncMeta } from '@/db/database';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Serviço de sincronização para processar fila de operações pendentes
 * Fase 4: Usa endpoints de backend /api/sync/push e /api/sync/pull
 */
class SyncService {
  constructor() {
    this.isSyncing = false;
    this.listeners = [];
    this.maxRetries = 3;
  }

  /**
   * Obtém token de autenticação
   */
  getAuthToken() {
    return localStorage.getItem('accessToken');
  }

  /**
   * Adiciona listener para eventos de sincronização
   */
  addListener(callback) {
    this.listeners.push(callback);
    return () => {
      this.listeners = this.listeners.filter(l => l !== callback);
    };
  }

  /**
   * Notifica listeners de eventos
   */
  notify(event, data) {
    this.listeners.forEach(callback => {
      try {
        callback(event, data);
      } catch (err) {
        console.error('[SyncService] Erro no listener:', err);
      }
    });
  }

  /**
   * Processa toda a fila de sincronização usando o endpoint /api/sync/push
   */
  async processQueue() {
    if (this.isSyncing) {
      console.log('[SyncService] Sincronização já em andamento');
      return { success: false, reason: 'already_syncing' };
    }

    if (!navigator.onLine) {
      console.log('[SyncService] Offline - sincronização adiada');
      return { success: false, reason: 'offline' };
    }

    this.isSyncing = true;
    this.notify('sync_start', {});

    const results = {
      processed: 0,
      succeeded: 0,
      failed: 0,
      errors: []
    };

    try {
      const pendingItems = await getPendingSyncItems();
      results.total = pendingItems.length;

      if (pendingItems.length === 0) {
        console.log('[SyncService] Nenhum item pendente para sincronizar');
        this.notify('sync_complete', results);
        return { success: true, results };
      }

      console.log(`[SyncService] Enviando ${pendingItems.length} itens para o servidor`);

      // Converte para formato do endpoint
      const operations = pendingItems.map(item => ({
        collection: item.collection,
        operation: item.operation,
        recordId: item.recordId,
        data: item.data,
        timestamp: item.timestamp
      }));

      // Chama endpoint de push
      const token = this.getAuthToken();
      const response = await axios.post(
        `${API_URL}/api/sync/push`,
        { operations },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const serverResults = response.data;
      results.processed = serverResults.processed;
      results.succeeded = serverResults.succeeded;
      results.failed = serverResults.failed;

      // Processa resultados individuais
      for (const result of serverResults.results) {
        const queueItem = pendingItems.find(item => item.recordId === result.recordId);
        
        if (result.success) {
          // Remove da fila local
          if (queueItem) {
            await removeSyncQueueItem(queueItem.id);
          }
          
          // Atualiza ID local com ID do servidor se necessário
          if (result.serverId && result.serverId !== result.recordId) {
            await this.updateLocalId(queueItem?.collection, result.recordId, result.serverId);
          }
          
          // Atualiza status do registro
          if (queueItem) {
            await this.updateRecordSyncStatus(queueItem.collection, result.serverId || result.recordId, SYNC_STATUS.SYNCED);
          }
        } else {
          // Atualiza tentativas do item com erro
          if (queueItem) {
            await updateSyncQueueItem(
              queueItem.id,
              queueItem.retries >= this.maxRetries ? 'failed' : 'pending',
              result.error
            );
          }
          
          results.errors.push({
            recordId: result.recordId,
            error: result.error
          });
        }
      }

      this.notify('sync_complete', results);
      console.log(`[SyncService] Sincronização concluída:`, results);

      return { success: true, results };

    } catch (err) {
      console.error('[SyncService] Erro na sincronização:', err);
      this.notify('sync_error', { error: err.message });
      return { success: false, error: err.message };

    } finally {
      this.isSyncing = false;
    }
  }

  /**
   * Baixa dados do servidor para o cache local usando /api/sync/pull
   */
  async pullData(collections, options = {}) {
    if (!navigator.onLine) {
      console.log('[SyncService] Offline - pull adiado');
      return { success: false, reason: 'offline' };
    }

    try {
      const token = this.getAuthToken();
      const response = await axios.post(
        `${API_URL}/api/sync/pull`,
        {
          collections,
          classId: options.classId || null,
          academicYear: options.academicYear || null,
          lastSync: options.lastSync || null
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const { data, syncedAt, counts } = response.data;

      // Armazena dados no IndexedDB
      for (const [collection, records] of Object.entries(data)) {
        if (records && records.length > 0) {
          await this.storeCollectionData(collection, records);
          await updateSyncMeta(collection, records.length);
        }
      }

      console.log('[SyncService] Pull concluído:', counts);
      return { success: true, counts, syncedAt };

    } catch (err) {
      console.error('[SyncService] Erro no pull:', err);
      return { success: false, error: err.message };
    }
  }

  /**
   * Armazena dados de uma coleção no IndexedDB
   */
  async storeCollectionData(collection, records) {
    const table = db[collection];
    if (!table) {
      console.warn(`[SyncService] Coleção desconhecida: ${collection}`);
      return;
    }

    await db.transaction('rw', table, async () => {
      for (const record of records) {
        const existing = await table.where('id').equals(record.id).first();
        
        if (existing) {
          // Atualiza registro existente
          await table.update(existing.localId || existing.id, {
            ...record,
            syncStatus: SYNC_STATUS.SYNCED
          });
        } else {
          // Adiciona novo registro
          await table.add({
            ...record,
            syncStatus: SYNC_STATUS.SYNCED
          });
        }
      }
    });
  }

  /**
   * Obtém status de sincronização do servidor
   */
  async getServerStatus() {
    if (!navigator.onLine) {
      return { success: false, reason: 'offline' };
    }

    try {
      const token = this.getAuthToken();
      const response = await axios.get(
        `${API_URL}/api/sync/status`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      return { success: true, data: response.data };
    } catch (err) {
      console.error('[SyncService] Erro ao obter status:', err);
      return { success: false, error: err.message };
    }
  }

  /**
   * Atualiza ID local com ID do servidor após criação
   */
  async updateLocalId(collection, tempId, serverId) {
    if (!collection) return;
    
    const table = db[collection];
    if (!table) return;
    
    const record = await table.where('id').equals(tempId).first();
    if (record) {
      await table.update(record.localId, { id: serverId });
    }
  }

  /**
   * Atualiza status de sincronização de um registro
   */
  async updateRecordSyncStatus(collection, recordId, status) {
    if (!collection) return;
    
    const table = db[collection];
    if (!table) return;
    
    const record = await table.where('id').equals(recordId).first();
    if (record) {
      await table.update(record.localId, { syncStatus: status });
    }
  }

  /**
   * Retorna contagem de itens pendentes
   */
  async getPendingCount() {
    return await countPendingSyncItems();
  }

  /**
   * Verifica se há itens pendentes
   */
  async hasPendingItems() {
    const count = await this.getPendingCount();
    return count > 0;
  }

  /**
   * Limpa itens com falha permanente
   */
  async clearFailedItems() {
    await db.syncQueue.where('status').equals('failed').delete();
  }

  /**
   * Reseta tentativas de itens com erro
   */
  async retryFailedItems() {
    await db.syncQueue
      .where('status').equals('failed')
      .modify({ status: 'pending', retries: 0, lastError: null });
  }
}

// Instância singleton
export const syncService = new SyncService();

export default syncService;
