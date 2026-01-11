import { useState, useCallback, useEffect } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import Dexie from 'dexie';
import { db, SYNC_STATUS, addToSyncQueue, SYNC_OPERATIONS } from '@/db/database';
import { useOffline } from '@/contexts/OfflineContext';
import { gradesAPI } from '@/services/api';

/**
 * Hook para gerenciar notas com suporte offline
 * 
 * Funcionalidades:
 * - Lê dados do IndexedDB quando offline
 * - Salva localmente e sincroniza quando online
 * - Mantém fila de operações pendentes
 */
export function useOfflineGrades(studentId, academicYear) {
  const { isOnline } = useOffline();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Query reativa do IndexedDB
  const localGrades = useLiveQuery(
    async () => {
      if (!studentId || !academicYear) return [];
      
      return await db.grades
        .where('[student_id+course_id+academic_year]')
        .between(
          [studentId, Dexie.minKey, academicYear],
          [studentId, Dexie.maxKey, academicYear]
        )
        .toArray();
    },
    [studentId, academicYear],
    []
  );

  // Busca notas do servidor e atualiza cache local
  const fetchGrades = useCallback(async () => {
    if (!studentId || !academicYear) return;
    
    setLoading(true);
    setError(null);
    
    try {
      if (isOnline) {
        // Buscar do servidor
        const serverGrades = await gradesAPI.getAll({ student_id: studentId, academic_year: academicYear });
        
        // Atualizar cache local
        await db.transaction('rw', db.grades, async () => {
          // Remove notas antigas desse aluno/ano
          await db.grades
            .where('student_id').equals(studentId)
            .and(g => g.academic_year === academicYear)
            .delete();
          
          // Adiciona notas do servidor
          for (const grade of serverGrades) {
            await db.grades.add({
              ...grade,
              syncStatus: SYNC_STATUS.SYNCED
            });
          }
        });
      }
      // Se offline, usa dados do cache (já carregados via useLiveQuery)
    } catch (err) {
      console.error('[Offline Grades] Erro ao buscar notas:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [studentId, academicYear, isOnline]);

  // Salva nota (local + servidor se online)
  const saveGrade = useCallback(async (gradeData) => {
    setError(null);
    
    try {
      const now = new Date().toISOString();
      const gradeWithMeta = {
        ...gradeData,
        student_id: studentId,
        academic_year: academicYear,
        updated_at: now,
        syncStatus: isOnline ? SYNC_STATUS.SYNCED : SYNC_STATUS.PENDING
      };

      if (isOnline) {
        // Salva no servidor primeiro
        const savedGrade = gradeData.id 
          ? await gradesAPI.update(gradeData.id, gradeData)
          : await gradesAPI.create(gradeData);
        
        // Atualiza cache local
        const existingLocal = await db.grades
          .where('id').equals(savedGrade.id)
          .first();
        
        if (existingLocal) {
          await db.grades.update(existingLocal.localId, {
            ...savedGrade,
            syncStatus: SYNC_STATUS.SYNCED
          });
        } else {
          await db.grades.add({
            ...savedGrade,
            syncStatus: SYNC_STATUS.SYNCED
          });
        }
        
        return savedGrade;
      } else {
        // Offline: salva apenas localmente
        const localId = gradeData.id 
          ? (await db.grades.where('id').equals(gradeData.id).first())?.localId
          : null;
        
        if (localId) {
          // Atualiza registro existente
          await db.grades.update(localId, gradeWithMeta);
          
          // Adiciona à fila de sincronização
          await addToSyncQueue('grades', SYNC_OPERATIONS.UPDATE, gradeData.id, gradeWithMeta);
        } else {
          // Cria novo registro com ID temporário
          const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          const newGrade = { ...gradeWithMeta, id: tempId };
          
          await db.grades.add(newGrade);
          await addToSyncQueue('grades', SYNC_OPERATIONS.CREATE, tempId, newGrade);
        }
        
        return gradeWithMeta;
      }
    } catch (err) {
      console.error('[Offline Grades] Erro ao salvar nota:', err);
      setError(err.message);
      throw err;
    }
  }, [studentId, academicYear, isOnline]);

  // Salva múltiplas notas de uma vez (batch)
  const saveGradesBatch = useCallback(async (gradesArray) => {
    setError(null);
    
    try {
      if (isOnline) {
        // Salva no servidor
        const savedGrades = await gradesAPI.saveBatch(gradesArray);
        
        // Atualiza cache local
        await db.transaction('rw', db.grades, async () => {
          for (const grade of savedGrades) {
            const existing = await db.grades.where('id').equals(grade.id).first();
            if (existing) {
              await db.grades.update(existing.localId, { ...grade, syncStatus: SYNC_STATUS.SYNCED });
            } else {
              await db.grades.add({ ...grade, syncStatus: SYNC_STATUS.SYNCED });
            }
          }
        });
        
        return savedGrades;
      } else {
        // Offline: salva localmente e adiciona à fila
        const savedGrades = [];
        
        await db.transaction('rw', [db.grades, db.syncQueue], async () => {
          for (const gradeData of gradesArray) {
            const now = new Date().toISOString();
            const gradeWithMeta = {
              ...gradeData,
              updated_at: now,
              syncStatus: SYNC_STATUS.PENDING
            };
            
            const existing = gradeData.id 
              ? await db.grades.where('id').equals(gradeData.id).first()
              : null;
            
            if (existing) {
              await db.grades.update(existing.localId, gradeWithMeta);
              await addToSyncQueue('grades', SYNC_OPERATIONS.UPDATE, gradeData.id, gradeWithMeta);
            } else {
              const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
              const newGrade = { ...gradeWithMeta, id: tempId };
              await db.grades.add(newGrade);
              await addToSyncQueue('grades', SYNC_OPERATIONS.CREATE, tempId, newGrade);
            }
            
            savedGrades.push(gradeWithMeta);
          }
        });
        
        return savedGrades;
      }
    } catch (err) {
      console.error('[Offline Grades] Erro ao salvar notas em batch:', err);
      setError(err.message);
      throw err;
    }
  }, [isOnline]);

  // Efeito para buscar dados iniciais
  useEffect(() => {
    if (studentId && academicYear) {
      fetchGrades();
    }
  }, [studentId, academicYear, fetchGrades]);

  return {
    grades: localGrades || [],
    loading,
    error,
    isOfflineData: !isOnline && localGrades?.length > 0,
    saveGrade,
    saveGradesBatch,
    refresh: fetchGrades
  };
}

/**
 * Hook para gerenciar notas de uma turma inteira
 */
export function useOfflineClassGrades(classId, academicYear) {
  const { isOnline } = useOffline();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Query reativa do IndexedDB
  const localGrades = useLiveQuery(
    async () => {
      if (!classId || !academicYear) return [];
      
      return await db.grades
        .where('class_id').equals(classId)
        .and(g => g.academic_year === academicYear)
        .toArray();
    },
    [classId, academicYear],
    []
  );

  // Busca notas da turma do servidor
  const fetchClassGrades = useCallback(async () => {
    if (!classId || !academicYear) return;
    
    setLoading(true);
    setError(null);
    
    try {
      if (isOnline) {
        const response = await gradesAPI.getByClass(classId, academicYear);
        const serverGrades = response.grades || [];
        
        // Atualizar cache local
        await db.transaction('rw', db.grades, async () => {
          // Remove notas antigas dessa turma/ano que estão sincronizadas
          await db.grades
            .where('class_id').equals(classId)
            .and(g => g.academic_year === academicYear && g.syncStatus === SYNC_STATUS.SYNCED)
            .delete();
          
          // Adiciona notas do servidor
          for (const grade of serverGrades) {
            await db.grades.add({
              ...grade,
              class_id: classId,
              syncStatus: SYNC_STATUS.SYNCED
            });
          }
        });
      }
    } catch (err) {
      console.error('[Offline Grades] Erro ao buscar notas da turma:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [classId, academicYear, isOnline]);

  useEffect(() => {
    if (classId && academicYear) {
      fetchClassGrades();
    }
  }, [classId, academicYear, fetchClassGrades]);

  // Conta notas pendentes de sincronização
  const pendingCount = useLiveQuery(
    async () => {
      if (!classId) return 0;
      return await db.grades
        .where('class_id').equals(classId)
        .and(g => g.syncStatus === SYNC_STATUS.PENDING)
        .count();
    },
    [classId],
    0
  );

  return {
    grades: localGrades || [],
    loading,
    error,
    isOfflineData: !isOnline,
    pendingCount,
    refresh: fetchClassGrades
  };
}

export default useOfflineGrades;
