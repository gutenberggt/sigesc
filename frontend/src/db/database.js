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
class SigescDatabase extends Dexie {
  constructor() {
    super('SigescOfflineDB');

    // Schema do banco - versão 1
    this.version(1).stores({
      // Notas dos alunos
      grades: '++localId, id, student_id, course_id, class_id, academic_year, [student_id+course_id+academic_year], syncStatus',
      
      // Frequência/Presenças
      attendance: '++localId, id, class_id, date, academic_year, [class_id+date], syncStatus',
      
      // Dados de referência (somente leitura, sincronizados do servidor)
      students: 'id, class_id, full_name, enrollment_number',
      classes: 'id, school_id, grade_level, academic_year',
      courses: 'id, name, school_id',
      schools: 'id, name',
      
      // Fila de operações pendentes para sincronização
      syncQueue: '++id, collection, operation, recordId, timestamp, status, retries',
      
      // Metadados de sincronização
      syncMeta: 'collection, lastSync, recordCount'
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
  }
}

// Instância única do banco
export const db = new SigescDatabase();

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
 * Adiciona um item à fila de sincronização
 */
export async function addToSyncQueue(collection, operation, recordId, data = null) {
  await db.syncQueue.add({
    collection,
    operation,
    recordId,
    data,
    timestamp: new Date().toISOString(),
    status: 'pending',
    retries: 0
  });
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

export default db;
