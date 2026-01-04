import { useState, useEffect, useCallback } from 'react';
import { calendarAPI } from '@/services/api';

/**
 * Hook para verificar o status de edição dos bimestres
 * Retorna informações sobre quais bimestres estão abertos ou bloqueados para edição
 */
export const useBimestreEditStatus = (academicYear) => {
  const [editStatus, setEditStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchEditStatus = useCallback(async () => {
    if (!academicYear) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const status = await calendarAPI.getEditStatus(academicYear);
      setEditStatus(status);
      setError(null);
    } catch (err) {
      console.error('Erro ao verificar status de edição:', err);
      setError(err.message);
      // Em caso de erro, assume que pode editar (fail-open)
      setEditStatus({
        ano_letivo: academicYear,
        pode_editar_todos: true,
        bimestres: [1, 2, 3, 4].map(i => ({
          bimestre: i,
          pode_editar: true,
          data_limite: null,
          motivo: 'Erro ao verificar status'
        }))
      });
    } finally {
      setLoading(false);
    }
  }, [academicYear]);

  useEffect(() => {
    fetchEditStatus();
  }, [fetchEditStatus]);

  /**
   * Verifica se um bimestre específico pode ser editado
   */
  const canEditBimestre = useCallback((bimestre) => {
    if (!editStatus || !editStatus.bimestres) return true;
    const bimestreStatus = editStatus.bimestres.find(b => b.bimestre === bimestre);
    return bimestreStatus?.pode_editar ?? true;
  }, [editStatus]);

  /**
   * Retorna informações de um bimestre específico
   */
  const getBimestreInfo = useCallback((bimestre) => {
    if (!editStatus || !editStatus.bimestres) return null;
    return editStatus.bimestres.find(b => b.bimestre === bimestre);
  }, [editStatus]);

  /**
   * Verifica se todos os bimestres podem ser editados
   */
  const canEditAll = editStatus?.pode_editar_todos ?? true;

  /**
   * Retorna lista de bimestres bloqueados
   */
  const blockedBimestres = editStatus?.bimestres?.filter(b => !b.pode_editar) || [];

  return {
    editStatus,
    loading,
    error,
    canEditBimestre,
    getBimestreInfo,
    canEditAll,
    blockedBimestres,
    refresh: fetchEditStatus
  };
};

export default useBimestreEditStatus;
