/**
 * Hook para gestão do calendário letivo
 * Gerencia anos letivos e suas configurações
 */
import { useState, useCallback } from 'react';
import { calendarAPI } from '@/services/api';

export function useCalendarioLetivo(initialYear = new Date().getFullYear()) {
  const [calendarioLetivo, setCalendarioLetivo] = useState(null);
  const [selectedYear, setSelectedYear] = useState(initialYear);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Anos disponíveis para seleção
  const anosDisponiveis = [2025, 2026, 2027, 2028, 2029, 2030];

  // Fetch calendar for a specific year
  const fetchCalendario = useCallback(async (year) => {
    setLoading(true);
    setError(null);
    
    try {
      const data = await calendarAPI.get(year);
      setCalendarioLetivo(data);
      return data;
    } catch (err) {
      console.error('Erro ao carregar calendário:', err);
      setError(err.message || 'Erro ao carregar calendário');
      setCalendarioLetivo(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Add a new academic year
  const adicionarAnoLetivo = useCallback((ano) => {
    const anoNum = parseInt(ano);
    if (isNaN(anoNum) || anoNum < 2020 || anoNum > 2050) {
      throw new Error('Ano inválido');
    }

    setCalendarioLetivo(prev => {
      const novosAnos = {
        ...prev?.anos_letivos,
        [anoNum]: { status: 'configurando' }
      };
      return { ...prev, anos_letivos: novosAnos };
    });
  }, []);

  // Change academic year status
  const alterarStatusAnoLetivo = useCallback((ano, novoStatus) => {
    setCalendarioLetivo(prev => {
      if (!prev?.anos_letivos?.[ano]) return prev;
      
      const novosAnos = {
        ...prev.anos_letivos,
        [ano]: { ...prev.anos_letivos[ano], status: novoStatus }
      };
      return { ...prev, anos_letivos: novosAnos };
    });
  }, []);

  // Save calendar changes
  const saveCalendario = useCallback(async (calendarioData) => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await calendarAPI.update(calendarioData);
      setCalendarioLetivo(result);
      return result;
    } catch (err) {
      console.error('Erro ao salvar calendário:', err);
      setError(err.message || 'Erro ao salvar calendário');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    calendarioLetivo,
    selectedYear,
    loading,
    error,
    anosDisponiveis,
    
    setSelectedYear,
    fetchCalendario,
    adicionarAnoLetivo,
    alterarStatusAnoLetivo,
    saveCalendario
  };
}

export default useCalendarioLetivo;
