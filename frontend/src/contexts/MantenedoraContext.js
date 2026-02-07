import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { mantenedoraAPI } from '@/services/api';

const MantenedoraContext = createContext(null);

export const MantenedoraProvider = ({ children }) => {
  const [mantenedora, setMantenedora] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMantenedora = useCallback(async () => {
    try {
      const data = await mantenedoraAPI.get();
      setMantenedora(data);
    } catch (error) {
      console.error('Erro ao carregar mantenedora:', error);
      // Valores padrão caso não consiga carregar
      setMantenedora({
        nome: 'Prefeitura Municipal',
        municipio: 'Floresta do Araguaia',
        estado: 'PA',
        brasao_url: ''
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMantenedora();
  }, [loadMantenedora]);

  // Função para recarregar os dados (útil após atualização)
  const refreshMantenedora = () => {
    loadMantenedora();
  };

  // Dados padrão para formulários
  const getDefaultLocation = () => ({
    municipio: mantenedora?.municipio || 'Floresta do Araguaia',
    estado: mantenedora?.estado || 'PA',
    city: mantenedora?.municipio || 'Floresta do Araguaia',
    state: mantenedora?.estado || 'PA'
  });

  // Retorna o brasão (ou fallback para logotipo antigo)
  const getBrasaoUrl = () => mantenedora?.brasao_url || mantenedora?.logotipo_url || '';

  const value = {
    mantenedora,
    loading,
    refreshMantenedora,
    getDefaultLocation,
    getBrasaoUrl
  };

  return (
    <MantenedoraContext.Provider value={value}>
      {children}
    </MantenedoraContext.Provider>
  );
};

export const useMantenedora = () => {
  const context = useContext(MantenedoraContext);
  if (!context) {
    throw new Error('useMantenedora deve ser usado dentro de MantenedoraProvider');
  }
  return context;
};

export default MantenedoraContext;
