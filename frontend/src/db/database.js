import Dexie from 'dexie';

/**
 * Banco de dados local do SIGESC usando IndexedDB via Dexie
 * 
 * Armazena dados para funcionamento offline:
 * - Notas (grades)
 * - Frequência (attendance)
 * - Dados de referência (students, classes, courses)
 * - Fila de sincronização (syncQueue)
 */

// Versão atual do schema - incrementar quando houver mudanças
const CURRENT_DB_VERSION = 4;

class SigescDatabase extends Dexie {
  constructor() {
    super('SigescOfflineDB');

    // Schema do banco - versão atual
    this.version(CURRENT_DB_VERSION).stores({
      // Notas dos alunos
      grades: '++localId, id, student_id, course_id, class_id, academic_year, [student_id+course_id+academic_year], syncStatus',
      
      // Frequência/Presenças
      attendance: '++localId, id, class_id, date, academic_year, [class_id+date], syncStatus',
      
      // Alunos - agora com suporte a CRUD offline
      students: '++localId, id, class_id, full_name, enrollment_number, status, syncStatus',
      
      // Dados de referência (somente leitura, sincronizados do servidor)
      classes: 'id, school_id, grade_level, academic_year',
      courses: 'id, name, school_id',
      schools: 'id, name',
      
      // Fila de operações pendentes para sincronização
      syncQueue: '++id, collection, operation, recordId, timestamp, status, retries',
      
      // Metadados de sincronização
      syncMeta: 'collection, lastSync, recordCount',

      // AutoSave (P1): rascunhos de formulários em edição (não salvos no servidor).
      // NUNCA são apagados no logout — sobrevivem para restauração após novo login.
      drafts: 'formId, userId, route, updatedAt'
    });

    // Definir tabelas
    this.grades = this.table('grades');
    this.attendance = this.table('attendance');
    this.students = this.table('students');
    this.classes = this.table('classes');
    this.courses = this.table('courses');
    this.schools = this.table('schools');
    this.syncQueue = this.table('syncQueue');
    this.syncMeta = this.table('syncMeta');
    this.drafts = this.table('drafts');
  }
}

// Instância única do banco
export const db = new SigescDatabase();

/**
 * Tenta abrir o banco de dados, resetando se houver erro de versão
 * Isso resolve o problema de VersionError quando a versão local é maior que a esperada
 */
export async function initializeDatabase() {
  try {
    await db.open();
    console.log('[DB] Banco de dados aberto com sucesso');
    return true;
  } catch (error) {
    if (error.name === 'VersionError') {
      console.warn('[DB] VersionError detectado, resetando banco de dados...');
      try {
        await Dexie.delete('SigescOfflineDB');
        console.log('[DB] Banco de dados antigo removido');
        // Recarrega a página para recriar o banco
        window.location.reload();
        return false;
      } catch (deleteError) {
        console.error('[DB] Erro ao deletar banco:', deleteError);
        return false;
      }
    }
    console.error('[DB] Erro ao abrir banco:', error);
    return false;
  }
}

/**
 * Força o reset completo do banco de dados
 * Útil quando há corrupção ou inconsistências graves
 */
export async function forceResetDatabase() {
  try {
    db.close();
    await Dexie.delete('SigescOfflineDB');
    console.log('[DB] Banco de dados resetado com sucesso');
    return true;
  } catch (error) {
    console.error('[DB] Erro ao resetar banco:', error);
    return false;
  }
}

/**
 * Status de sincronização dos registros
 */
export const SYNC_STATUS = {
  SYNCED: 'synced',           // Sincronizado com servidor
  PENDING: 'pending',          // Aguardando sincronização
  CONFLICT: 'conflict',        // Conflito detectado
  ERROR: 'error'              // Erro na sincronização
};

/**
 * Operações da fila de sincronização
 */
export const SYNC_OPERATIONS = {
  CREATE: 'create',
  UPDATE: 'update',
  DELETE: 'delete'
};

/**
 * Adiciona um item à fila de sincronização e registra Background Sync.
 *
 * `naturalKey` (opcional): chave natural do registro (ex.: turma|data|componente|aula).
 * Quando informada, a fila é IDEMPOTENTE: se já existir um item pendente com a
 * mesma chave natural, ele é ATUALIZADO em vez de criar um novo. Isso garante que
 * N edições offline do mesmo registro convirjam para 1 item de fila (estado final),
 * evitando duplicatas e reenvios redundantes.
 */
export async function addToSyncQueue(collection, operation, recordId, data = null, naturalKey = null) {
  const now = new Date().toISOString();

  if (naturalKey) {
    const pendings = await db.syncQueue.where('status').equals('pending').toArray();
    const existing = pendings.find(
      (it) => it.collection === collection && it.naturalKey === naturalKey
    );
    if (existing) {
      await db.syncQueue.update(existing.id, {
        operation,
        recordId,
        data,
        timestamp: now,
        retries: 0,
        lastError: null,
      });
      await registerBackgroundSync();
      return;
    }
  }

  await db.syncQueue.add({
    collection,
    operation,
    recordId,
    data,
    naturalKey,
    timestamp: now,
    status: 'pending',
    retries: 0
  });

  await registerBackgroundSync();
}

/**
 * Registra Background Sync para sincronizar quando voltar online (quando suportado).
 */
async function registerBackgroundSync() {
  if ('serviceWorker' in navigator && 'sync' in window.SyncManager?.prototype) {
    try {
      const registration = await navigator.serviceWorker.ready;
      await registration.sync.register('sync-pending-data');
      console.log('[DB] Background Sync registrado para sincronização pendente');
    } catch (err) {
      console.log('[DB] Background Sync não disponível:', err.message);
    }
  }
}

/**
 * Obtém itens pendentes da fila de sincronização
 */
export async function getPendingSyncItems() {
  return await db.syncQueue
    .where('status')
    .equals('pending')
    .toArray();
}

/**
 * Conta itens pendentes de sincronização
 */
export async function countPendingSyncItems() {
  return await db.syncQueue
    .where('status')
    .equals('pending')
    .count();
}

/**
 * Conta itens pendentes/com falha agrupados por categoria (coleção).
 * Ex.: { attendance: { pending: 2, failed: 0 }, grades: { pending: 0, failed: 1 } }
 */
export async function countPendingByCollection() {
  const items = await db.syncQueue
    .where('status')
    .anyOf('pending', 'error', 'failed')
    .toArray();
  const result = {};
  for (const it of items) {
    const key = it.collection || 'outros';
    if (!result[key]) result[key] = { pending: 0, failed: 0 };
    if (it.status === 'error' || it.status === 'failed') result[key].failed += 1;
    else result[key].pending += 1;
  }
  return result;
}

/**
 * Retorna itens que falharam na sincronização (para o "Ver detalhes").
 */
export async function getFailedSyncItems() {
  const items = await db.syncQueue.toArray();
  return items.filter((it) => it.status === 'error' || it.status === 'failed');
}

/**
 * Atualiza status de um item na fila
 */
export async function updateSyncQueueItem(id, status, error = null) {
  const updates = { status };
  if (error) {
    updates.lastError = error;
    updates.retries = (await db.syncQueue.get(id))?.retries + 1 || 1;
  }
  await db.syncQueue.update(id, updates);
}

/**
 * Remove item da fila após sincronização bem-sucedida
 */
export async function removeSyncQueueItem(id) {
  await db.syncQueue.delete(id);
}

/**
 * Limpa toda a fila de sincronização
 */
export async function clearSyncQueue() {
  await db.syncQueue.clear();
}

/**
 * Atualiza metadados de sincronização
 */
export async function updateSyncMeta(collection, recordCount = null) {
  const existing = await db.syncMeta.get(collection);
  
  if (existing) {
    await db.syncMeta.update(collection, {
      lastSync: new Date().toISOString(),
      recordCount: recordCount ?? existing.recordCount
    });
  } else {
    await db.syncMeta.add({
      collection,
      lastSync: new Date().toISOString(),
      recordCount: recordCount ?? 0
    });
  }
}

/**
 * Obtém última sincronização de uma coleção
 */
export async function getLastSync(collection) {
  const meta = await db.syncMeta.get(collection);
  return meta?.lastSync || null;
}

/**
 * Limpa todos os dados do banco (para logout ou reset)
 */
export async function clearAllData() {
  await Promise.all([
    db.grades.clear(),
    db.attendance.clear(),
    db.students.clear(),
    db.classes.clear(),
    db.courses.clear(),
    db.schools.clear(),
    db.syncQueue.clear(),
    db.syncMeta.clear()
  ]);
  console.log('[DB] Todos os dados locais foram limpos');
}

/**
 * Exporta dados para backup
 */
export async function exportData() {
  return {
    grades: await db.grades.toArray(),
    attendance: await db.attendance.toArray(),
    syncQueue: await db.syncQueue.toArray(),
    exportedAt: new Date().toISOString()
  };
}

/**
 * Obtém data da última sincronização de uma coleção
 */
export async function getLastSyncTime(collection) {
  try {
    const meta = await db.syncMeta.where('collection').equals(collection).first();
    return meta?.lastSync || null;
  } catch (error) {
    console.error('[DB] Erro ao obter last sync:', error);
    return null;
  }
}

/**
 * Verifica se o banco está disponível
 */
export async function isDatabaseAvailable() {
  try {
    await db.syncMeta.count();
    return true;
  } catch (error) {
    console.error('[DB] Banco de dados não disponível:', error);
    return false;
  }
}

// ===========================================================================
// AutoSave (P1) — rascunhos de formulários em edição
// ===========================================================================

/** Salva/atualiza um rascunho (idempotente por formId). */
export async function saveDraft({ formId, userId, route, data }) {
  if (!formId) return;
  await db.drafts.put({
    formId,
    userId: userId || null,
    route: route || null,
    data,
    updatedAt: new Date().toISOString(),
  });
}

/** Carrega um rascunho pelo formId. */
export async function loadDraft(formId) {
  if (!formId) return null;
  try {
    return (await db.drafts.get(formId)) || null;
  } catch {
    return null;
  }
}

/** Remove um rascunho (após salvar no servidor com sucesso, ou ao descartar). */
export async function deleteDraft(formId) {
  if (!formId) return;
  try {
    await db.drafts.delete(formId);
  } catch {
    /* noop */
  }
}

/** Lista rascunhos do usuário (para o painel de recuperação — P2). */
export async function listDrafts(userId) {
  try {
    const all = await db.drafts.toArray();
    return userId ? all.filter((d) => !d.userId || d.userId === userId) : all;
  } catch {
    return [];
  }
}

export default db;
