import { useState, useCallback, useEffect } from 'react';
import { useLiveQuery } from 'dexie-react-hooks';
import { db, SYNC_STATUS, addToSyncQueue, SYNC_OPERATIONS } from '@/db/database';
import { useOffline } from '@/contexts/OfflineContext';
import { attendanceAPI } from '@/services/api';

/**
 * Hook para gerenciar frequência com suporte offline
 * 
 * Funcionalidades:
 * - Lê dados do IndexedDB quando offline
 * - Salva localmente e sincroniza quando online
 * - Mantém fila de operações pendentes
 */
export function useOfflineAttendance(classId, date) {
  const { isOnline } = useOffline();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Query reativa do IndexedDB
  const localAttendance = useLiveQuery(
    async () => {
      if (!classId || !date) return null;
      
      return await db.attendance
        .where('[class_id+date]')
        .equals([classId, date])
        .first();
    },
    [classId, date],
    null
  );

  // Busca frequência do servidor e atualiza cache local
  const fetchAttendance = useCallback(async () => {
    if (!classId || !date) return;
    
    setLoading(true);
    setError(null);
    
    try {
      if (isOnline) {
        // Buscar do servidor
        const serverAttendance = await attendanceAPI.getByClassAndDate(classId, date);
        
        if (serverAttendance) {
          // Atualizar cache local
          await db.transaction('rw', db.attendance, async () => {
            // Remove registro antigo
            await db.attendance
              .where('[class_id+date]')
              .equals([classId, date])
              .delete();
            
            // Adiciona registro do servidor
            await db.attendance.add({
              ...serverAttendance,
              syncStatus: SYNC_STATUS.SYNCED
            });
          });
        }
      }
      // Se offline, usa dados do cache (já carregados via useLiveQuery)
    } catch (err) {
      console.error('[Offline Attendance] Erro ao buscar frequência:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [classId, date, isOnline]);

  // Salva frequência (local + servidor se online)
  const saveAttendance = useCallback(async (attendanceData) => {
    setError(null);
    
    try {
      const now = new Date().toISOString();
      const dataWithMeta = {
        ...attendanceData,
        class_id: classId,
        date: date,
        updated_at: now,
        syncStatus: isOnline ? SYNC_STATUS.SYNCED : SYNC_STATUS.PENDING
      };

      if (isOnline) {
        // Salva no servidor primeiro
        const savedAttendance = attendanceData.id 
          ? await attendanceAPI.update(attendanceData.id, attendanceData)
          : await attendanceAPI.create(attendanceData);
        
        // Atualiza cache local
        await db.transaction('rw', db.attendance, async () => {
          await db.attendance
            .where('[class_id+date]')
            .equals([classId, date])
            .delete();
          
          await db.attendance.add({
            ...savedAttendance,
            syncStatus: SYNC_STATUS.SYNCED
          });
        });
        
        return savedAttendance;
      } else {
        // Offline: salva apenas localmente
        await db.transaction('rw', [db.attendance, db.syncQueue], async () => {
          const existing = await db.attendance
            .where('[class_id+date]')
            .equals([classId, date])
            .first();
          
          if (existing) {
            // Atualiza registro existente
            await db.attendance.update(existing.localId, dataWithMeta);
            await addToSyncQueue('attendance', SYNC_OPERATIONS.UPDATE, existing.id, dataWithMeta);
          } else {
            // Cria novo registro com ID temporário
            const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            const newRecord = { ...dataWithMeta, id: tempId };
            
            await db.attendance.add(newRecord);
            await addToSyncQueue('attendance', SYNC_OPERATIONS.CREATE, tempId, newRecord);
          }
        });
        
        return dataWithMeta;
      }
    } catch (err) {
      console.error('[Offline Attendance] Erro ao salvar frequência:', err);
      setError(err.message);
      throw err;
    }
  }, [classId, date, isOnline]);

  // Efeito para buscar dados iniciais
  useEffect(() => {
    if (classId && date) {
      fetchAttendance();
    }
  }, [classId, date, fetchAttendance]);

  return {
    attendance: localAttendance,
    loading,
    error,
    isOfflineData: !isOnline && localAttendance !== null,
    saveAttendance,
    refresh: fetchAttendance
  };
}

/**
 * Hook para gerenciar frequência de um período (mês)
 */
export function useOfflineAttendanceMonth(classId, year, month) {
  const { isOnline } = useOffline();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Query reativa do IndexedDB para o mês
  const localAttendance = useLiveQuery(
    async () => {
      if (!classId || !year || !month) return [];
      
      const startDate = `${year}-${String(month).padStart(2, '0')}-01`;
      const endDate = `${year}-${String(month).padStart(2, '0')}-31`;
      
      return await db.attendance
        .where('class_id').equals(classId)
        .and(a => a.date >= startDate && a.date <= endDate)
        .toArray();
    },
    [classId, year, month],
    []
  );

  // Busca frequência do mês do servidor
  const fetchMonthAttendance = useCallback(async () => {
    if (!classId || !year || !month) return;
    
    setLoading(true);
    setError(null);
    
    try {
      if (isOnline) {
        const startDate = `${year}-${String(month).padStart(2, '0')}-01`;
        const endDate = `${year}-${String(month).padStart(2, '0')}-31`;
        
        const serverRecords = await attendanceAPI.getByClassAndDateRange(classId, startDate, endDate);
        
        // Atualizar cache local
        await db.transaction('rw', db.attendance, async () => {
          // Remove registros sincronizados do período
          await db.attendance
            .where('class_id').equals(classId)
            .and(a => a.date >= startDate && a.date <= endDate && a.syncStatus === SYNC_STATUS.SYNCED)
            .delete();
          
          // Adiciona registros do servidor
          for (const record of serverRecords) {
            await db.attendance.add({
              ...record,
              syncStatus: SYNC_STATUS.SYNCED
            });
          }
        });
      }
    } catch (err) {
      console.error('[Offline Attendance] Erro ao buscar frequência do mês:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [classId, year, month, isOnline]);

  useEffect(() => {
    if (classId && year && month) {
      fetchMonthAttendance();
    }
  }, [classId, year, month, fetchMonthAttendance]);

  // Conta registros pendentes de sincronização
  const pendingCount = useLiveQuery(
    async () => {
      if (!classId) return 0;
      return await db.attendance
        .where('class_id').equals(classId)
        .and(a => a.syncStatus === SYNC_STATUS.PENDING)
        .count();
    },
    [classId],
    0
  );

  return {
    attendanceRecords: localAttendance || [],
    loading,
    error,
    isOfflineData: !isOnline,
    pendingCount,
    refresh: fetchMonthAttendance
  };
}

export default useOfflineAttendance;
