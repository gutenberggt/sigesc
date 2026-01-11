import { db, getPendingSyncItems, updateSyncQueueItem, removeSyncQueueItem, SYNC_STATUS, countPendingSyncItems } from '@/db/database';
import { gradesAPI, attendanceAPI } from '@/services/api';

/**
 * Serviço de sincronização para processar fila de operações pendentes
 */
class SyncService {
  constructor() {
    this.isSyncing = false;
    this.listeners = [];
    this.maxRetries = 3;
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
   * Processa toda a fila de sincronização
   */
  async processQueue() {
    if (this.isSyncing) {
      console.log('[SyncService] Sincronização já em andamento');
      return { success: false, reason: 'already_syncing' };
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

      console.log(`[SyncService] Processando ${pendingItems.length} itens pendentes`);

      for (const item of pendingItems) {
        try {
          this.notify('sync_progress', { 
            current: results.processed + 1, 
            total: pendingItems.length,
            item 
          });

          await this.processItem(item);
          
          // Remove da fila após sucesso
          await removeSyncQueueItem(item.id);
          results.succeeded++;

          // Atualiza status do registro original
          await this.updateRecordSyncStatus(item.collection, item.recordId, SYNC_STATUS.SYNCED);

        } catch (err) {
          console.error(`[SyncService] Erro ao processar item ${item.id}:`, err);
          
          // Atualiza tentativas
          await updateSyncQueueItem(item.id, 
            item.retries >= this.maxRetries ? 'failed' : 'pending',
            err.message
          );
          
          results.failed++;
          results.errors.push({
            itemId: item.id,
            collection: item.collection,
            error: err.message
          });
        }

        results.processed++;
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
   * Processa um item individual da fila
   */
  async processItem(item) {
    const { collection, operation, recordId, data } = item;

    switch (collection) {
      case 'grades':
        return await this.syncGrade(operation, recordId, data);
      case 'attendance':
        return await this.syncAttendance(operation, recordId, data);
      default:
        throw new Error(`Coleção desconhecida: ${collection}`);
    }
  }

  /**
   * Sincroniza uma nota
   */
  async syncGrade(operation, recordId, data) {
    // Remove campos de controle local
    const cleanData = this.cleanData(data);

    switch (operation) {
      case 'create':
        // Cria no servidor
        const created = await gradesAPI.create(cleanData);
        
        // Atualiza ID local com ID do servidor
        await this.updateLocalId('grades', recordId, created.id);
        return created;

      case 'update':
        return await gradesAPI.update(recordId, cleanData);

      case 'delete':
        return await gradesAPI.delete(recordId);

      default:
        throw new Error(`Operação desconhecida: ${operation}`);
    }
  }

  /**
   * Sincroniza um registro de frequência
   */
  async syncAttendance(operation, recordId, data) {
    const cleanData = this.cleanData(data);

    switch (operation) {
      case 'create':
        const created = await attendanceAPI.create(cleanData);
        await this.updateLocalId('attendance', recordId, created.id);
        return created;

      case 'update':
        return await attendanceAPI.update(recordId, cleanData);

      case 'delete':
        return await attendanceAPI.delete(recordId);

      default:
        throw new Error(`Operação desconhecida: ${operation}`);
    }
  }

  /**
   * Remove campos de controle local dos dados
   */
  cleanData(data) {
    if (!data) return data;
    
    const { localId, syncStatus, ...cleanData } = data;
    
    // Remove ID temporário se for criar
    if (cleanData.id && cleanData.id.startsWith('temp_')) {
      delete cleanData.id;
    }
    
    return cleanData;
  }

  /**
   * Atualiza ID local com ID do servidor após criação
   */
  async updateLocalId(collection, tempId, serverId) {
    const table = db[collection];
    
    const record = await table.where('id').equals(tempId).first();
    if (record) {
      await table.update(record.localId, { id: serverId });
    }
  }

  /**
   * Atualiza status de sincronização de um registro
   */
  async updateRecordSyncStatus(collection, recordId, status) {
    const table = db[collection];
    
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
