import { useState, useCallback, useEffect } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { db, updateSyncMeta, getLastSync } from '@/db/database';
import { useOffline } from '@/contexts/OfflineContext';
import { studentsAPI, classesAPI, coursesAPI, schoolsAPI } from '@/services/api';

/**
 * Hook para sincronizar dados de referência para uso offline
 * 
 * Sincroniza:
 * - Alunos (students)
 * - Turmas (classes)
 * - Componentes curriculares (courses)
 * - Escolas (schools)
 */
export function useOfflineSync() {
  const { isOnline, updatePendingCount } = useOffline();
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0, collection: '' });
  const [error, setError] = useState(null);
  const [lastSyncTime, setLastSyncTime] = useState(null);

  // Carrega última sincronização
  useEffect(() => {
    async function loadLastSync() {
      const syncTimes = await Promise.all([
        getLastSync('students'),
        getLastSync('classes'),
        getLastSync('courses'),
        getLastSync('schools')
      ]);
      
      // Pega a mais recente
      const validTimes = syncTimes.filter(Boolean);
      if (validTimes.length > 0) {
        setLastSyncTime(new Date(Math.max(...validTimes.map(t => new Date(t)))));
      }
    }
    loadLastSync();
  }, []);

  // Sincroniza uma coleção específica
  const syncCollection = useCallback(async (collection, fetchFn, params = {}) => {
    try {
      setProgress(prev => ({ ...prev, collection }));
      
      const data = await fetchFn(params);
      const records = Array.isArray(data) ? data : (data.data || data.students || data.classes || data.courses || data.schools || []);
      
      await db.transaction('rw', db[collection], async () => {
        // Limpa dados antigos
        await db[collection].clear();
        
        // Adiciona novos dados
        if (records.length > 0) {
          await db[collection].bulkAdd(records);
        }
      });
      
      await updateSyncMeta(collection, records.length);
      
      return records.length;
    } catch (err) {
      console.error(`[Offline Sync] Erro ao sincronizar ${collection}:`, err);
      throw err;
    }
  }, []);

  // Sincroniza todos os dados de referência
  const syncAll = useCallback(async (filters = {}) => {
    if (!isOnline) {
      setError('Sem conexão com a internet');
      return false;
    }

    setSyncing(true);
    setError(null);
    setProgress({ current: 0, total: 4, collection: '' });

    try {
      // 1. Sincroniza escolas
      setProgress({ current: 1, total: 4, collection: 'escolas' });
      await syncCollection('schools', schoolsAPI.getAll);

      // 2. Sincroniza turmas
      setProgress({ current: 2, total: 4, collection: 'turmas' });
      await syncCollection('classes', classesAPI.getAll, { academic_year: filters.academicYear || new Date().getFullYear() });

      // 3. Sincroniza componentes curriculares
      setProgress({ current: 3, total: 4, collection: 'componentes' });
      await syncCollection('courses', coursesAPI.getAll);

      // 4. Sincroniza alunos (se tiver turma específica)
      setProgress({ current: 4, total: 4, collection: 'alunos' });
      if (filters.classId) {
        await syncCollection('students', studentsAPI.getByClass, filters.classId);
      } else {
        // Sincroniza todos os alunos
        await syncCollection('students', studentsAPI.getAll);
      }

      setLastSyncTime(new Date());
      setProgress({ current: 4, total: 4, collection: 'concluído' });
      
      // Atualiza contador de pendências
      updatePendingCount();
      
      return true;
    } catch (err) {
      console.error('[Offline Sync] Erro na sincronização:', err);
      setError(err.message);
      return false;
    } finally {
      setSyncing(false);
    }
  }, [isOnline, syncCollection, updatePendingCount]);

  // Sincroniza apenas uma turma específica (para uso otimizado)
  const syncClass = useCallback(async (classId, academicYear) => {
    if (!isOnline || !classId) return false;

    setSyncing(true);
    setError(null);

    try {
      // Sincroniza alunos da turma
      const students = await studentsAPI.getByClass(classId);
      
      await db.transaction('rw', db.students, async () => {
        // Remove alunos antigos dessa turma
        await db.students.where('class_id').equals(classId).delete();
        
        // Adiciona novos
        if (students.length > 0) {
          await db.students.bulkAdd(students.map(s => ({ ...s, class_id: classId })));
        }
      });

      // Sincroniza componentes da turma (se disponível)
      try {
        const courses = await coursesAPI.getByClass(classId);
        if (courses.length > 0) {
          await db.courses.bulkPut(courses);
        }
      } catch {
        // Ignora se endpoint não existir
      }

      return true;
    } catch (err) {
      console.error('[Offline Sync] Erro ao sincronizar turma:', err);
      setError(err.message);
      return false;
    } finally {
      setSyncing(false);
    }
  }, [isOnline]);

  return {
    syncing,
    progress,
    error,
    lastSyncTime,
    syncAll,
    syncClass
  };
}

/**
 * Hook para acessar alunos do cache local
 */
export function useOfflineStudents(classId) {
  const students = useLiveQuery(
    async () => {
      if (!classId) return [];
      return await db.students.where('class_id').equals(classId).toArray();
    },
    [classId],
    []
  );

  return students || [];
}

/**
 * Hook para acessar turmas do cache local
 */
export function useOfflineClasses(schoolId, academicYear) {
  const classes = useLiveQuery(
    async () => {
      let query = db.classes;
      
      if (schoolId) {
        query = query.where('school_id').equals(schoolId);
      }
      
      const results = await query.toArray();
      
      if (academicYear) {
        return results.filter(c => c.academic_year === academicYear);
      }
      
      return results;
    },
    [schoolId, academicYear],
    []
  );

  return classes || [];
}

/**
 * Hook para acessar componentes curriculares do cache local
 */
export function useOfflineCourses(schoolId) {
  const courses = useLiveQuery(
    async () => {
      if (schoolId) {
        return await db.courses.where('school_id').equals(schoolId).toArray();
      }
      return await db.courses.toArray();
    },
    [schoolId],
    []
  );

  return courses || [];
}

/**
 * Hook para acessar escolas do cache local
 */
export function useOfflineSchools() {
  const schools = useLiveQuery(
    async () => await db.schools.toArray(),
    [],
    []
  );

  return schools || [];
}

export default useOfflineSync;
