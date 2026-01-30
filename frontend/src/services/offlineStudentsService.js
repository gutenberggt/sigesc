import { db, addToSyncQueue, SYNC_STATUS } from '@/db/database';
import { studentsAPI } from '@/services/api';
import { v4 as uuidv4 } from 'uuid';

/**
 * Serviço para gerenciamento offline de alunos
 * Permite cadastro e edição de alunos mesmo sem conexão
 */
class OfflineStudentsService {
  
  /**
   * Verifica se está online
   */
  isOnline() {
    return navigator.onLine;
  }

  /**
   * Busca alunos - SEMPRE usa servidor quando online
   */
  async getStudents(filters = {}) {
    if (this.isOnline()) {
      try {
        // Online: SEMPRE busca do servidor (dados mais recentes)
        const response = await studentsAPI.getAll(filters);
        const students = response.items || response;
        
        // Atualiza cache local para uso offline futuro
        // Mas NÃO deixa o cache interferir nos dados do servidor
        await this.updateLocalCache(students);
        
        console.log('[OfflineStudents] Dados carregados do servidor:', students.length, 'alunos');
        return { success: true, data: students, source: 'server' };
      } catch (error) {
        console.error('[OfflineStudents] Erro ao buscar do servidor:', error);
        // Fallback para cache local APENAS em caso de erro
        return this.getFromLocalCache(filters);
      }
    } else {
      // Offline: busca do cache local
      console.log('[OfflineStudents] Modo offline - usando cache local');
      return this.getFromLocalCache(filters);
    }
  }

  /**
   * Busca um aluno específico
   */
  async getStudent(studentId) {
    if (this.isOnline()) {
      try {
        const student = await studentsAPI.getById(studentId);
        // Atualiza cache local
        await this.saveToLocalCache(student);
        return { success: true, data: student, source: 'server' };
      } catch (error) {
        console.error('[OfflineStudents] Erro ao buscar aluno:', error);
        return this.getFromLocalCacheById(studentId);
      }
    } else {
      return this.getFromLocalCacheById(studentId);
    }
  }

  /**
   * Cria um novo aluno - funciona offline
   */
  async createStudent(studentData) {
    // Gera ID temporário para uso offline
    const tempId = `temp_${uuidv4()}`;
    const studentWithId = {
      ...studentData,
      id: tempId,
      syncStatus: SYNC_STATUS.PENDING,
      createdAt: new Date().toISOString(),
      createdOffline: true
    };

    if (this.isOnline()) {
      try {
        // Online: cria no servidor
        const response = await studentsAPI.create(studentData);
        const serverStudent = response;
        
        // Salva no cache com ID do servidor
        await this.saveToLocalCache({
          ...serverStudent,
          syncStatus: SYNC_STATUS.SYNCED
        });
        
        return { success: true, data: serverStudent, source: 'server' };
      } catch (error) {
        console.error('[OfflineStudents] Erro ao criar no servidor, salvando localmente:', error);
        // Fallback: salva localmente para sincronização posterior
        return this.createOffline(studentWithId);
      }
    } else {
      // Offline: salva localmente
      return this.createOffline(studentWithId);
    }
  }

  /**
   * Cria aluno offline
   */
  async createOffline(studentData) {
    try {
      // Salva no IndexedDB
      await db.students.add(studentData);
      
      // Adiciona à fila de sincronização
      await addToSyncQueue('students', 'create', studentData.id, studentData);
      
      console.log('[OfflineStudents] Aluno salvo localmente para sincronização:', studentData.id);
      
      return { 
        success: true, 
        data: studentData, 
        source: 'local',
        pendingSync: true,
        message: 'Aluno salvo localmente. Será sincronizado quando a conexão for restaurada.'
      };
    } catch (error) {
      console.error('[OfflineStudents] Erro ao salvar localmente:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Atualiza um aluno - funciona offline
   */
  async updateStudent(studentId, studentData) {
    const updatedData = {
      ...studentData,
      id: studentId,
      updatedAt: new Date().toISOString()
    };

    if (this.isOnline()) {
      try {
        // Online: atualiza no servidor DIRETAMENTE
        console.log('[OfflineStudents] Atualizando aluno no servidor:', studentId);
        const response = await studentsAPI.update(studentId, studentData);
        
        // Atualiza cache local com dados do servidor
        await this.updateInLocalCache(studentId, {
          ...response,
          syncStatus: SYNC_STATUS.SYNCED
        });
        
        console.log('[OfflineStudents] Aluno atualizado com sucesso no servidor');
        return { success: true, data: response, source: 'server' };
      } catch (error) {
        console.error('[OfflineStudents] Erro ao atualizar no servidor:', error);
        // Retorna o erro para o usuário VER, não salva offline silenciosamente
        throw error;
      }
    } else {
      // Offline: salva localmente
      console.log('[OfflineStudents] Modo offline - salvando localmente');
      return this.updateOffline(studentId, updatedData);
    }
  }

  /**
   * Atualiza aluno offline
   */
  async updateOffline(studentId, studentData) {
    try {
      // Atualiza no IndexedDB
      await this.updateInLocalCache(studentId, {
        ...studentData,
        syncStatus: SYNC_STATUS.PENDING,
        updatedOffline: true
      });
      
      // Adiciona à fila de sincronização
      await addToSyncQueue('students', 'update', studentId, studentData);
      
      console.log('[OfflineStudents] Atualização salva localmente:', studentId);
      
      return { 
        success: true, 
        data: studentData, 
        source: 'local',
        pendingSync: true,
        message: 'Alterações salvas localmente. Serão sincronizadas quando a conexão for restaurada.'
      };
    } catch (error) {
      console.error('[OfflineStudents] Erro ao atualizar localmente:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Atualiza cache local com lista de alunos do servidor
   */
  async updateLocalCache(students) {
    try {
      await db.transaction('rw', db.students, async () => {
        for (const student of students) {
          const existing = await db.students.where('id').equals(student.id).first();
          
          if (existing) {
            // Não sobrescreve dados pendentes de sincronização
            if (existing.syncStatus !== SYNC_STATUS.PENDING) {
              await db.students.update(existing.localId, {
                ...student,
                syncStatus: SYNC_STATUS.SYNCED
              });
            }
          } else {
            await db.students.add({
              ...student,
              syncStatus: SYNC_STATUS.SYNCED
            });
          }
        }
      });
    } catch (error) {
      console.error('[OfflineStudents] Erro ao atualizar cache:', error);
    }
  }

  /**
   * Salva um aluno no cache local
   */
  async saveToLocalCache(student) {
    try {
      const existing = await db.students.where('id').equals(student.id).first();
      
      if (existing) {
        await db.students.update(existing.localId, student);
      } else {
        await db.students.add(student);
      }
    } catch (error) {
      console.error('[OfflineStudents] Erro ao salvar no cache:', error);
    }
  }

  /**
   * Atualiza um aluno no cache local
   */
  async updateInLocalCache(studentId, data) {
    try {
      const existing = await db.students.where('id').equals(studentId).first();
      
      if (existing) {
        await db.students.update(existing.localId, data);
      } else {
        await db.students.add({ ...data, id: studentId });
      }
    } catch (error) {
      console.error('[OfflineStudents] Erro ao atualizar cache:', error);
    }
  }

  /**
   * Busca alunos do cache local
   */
  async getFromLocalCache(filters = {}) {
    try {
      let query = db.students.toCollection();
      
      // Aplica filtros básicos
      if (filters.status) {
        query = db.students.where('status').equals(filters.status);
      }
      
      const students = await query.toArray();
      
      // Filtra por escola se necessário
      let filtered = students;
      if (filters.school_id) {
        // Precisa buscar matrículas para filtrar por escola
        // Por simplicidade, retorna todos e deixa o componente filtrar
      }
      
      return { 
        success: true, 
        data: filtered, 
        source: 'local',
        message: 'Dados carregados do cache local (modo offline)'
      };
    } catch (error) {
      console.error('[OfflineStudents] Erro ao buscar do cache:', error);
      return { success: false, data: [], error: error.message };
    }
  }

  /**
   * Busca um aluno do cache local por ID
   */
  async getFromLocalCacheById(studentId) {
    try {
      const student = await db.students.where('id').equals(studentId).first();
      
      if (student) {
        return { success: true, data: student, source: 'local' };
      } else {
        return { success: false, error: 'Aluno não encontrado no cache local' };
      }
    } catch (error) {
      console.error('[OfflineStudents] Erro ao buscar do cache:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Retorna alunos pendentes de sincronização
   */
  async getPendingStudents() {
    try {
      return await db.students
        .where('syncStatus')
        .equals(SYNC_STATUS.PENDING)
        .toArray();
    } catch (error) {
      console.error('[OfflineStudents] Erro ao buscar pendentes:', error);
      return [];
    }
  }

  /**
   * Conta alunos pendentes de sincronização
   */
  async countPendingStudents() {
    try {
      return await db.students
        .where('syncStatus')
        .equals(SYNC_STATUS.PENDING)
        .count();
    } catch (error) {
      return 0;
    }
  }

  /**
   * Limpa cache local de alunos
   */
  async clearCache() {
    try {
      // Mantém apenas alunos pendentes de sincronização
      const pending = await this.getPendingStudents();
      await db.students.clear();
      
      // Restaura pendentes
      for (const student of pending) {
        await db.students.add(student);
      }
      
      console.log('[OfflineStudents] Cache limpo (pendentes mantidos)');
    } catch (error) {
      console.error('[OfflineStudents] Erro ao limpar cache:', error);
    }
  }
}

// Exporta instância singleton
export const offlineStudentsService = new OfflineStudentsService();
export default offlineStudentsService;
