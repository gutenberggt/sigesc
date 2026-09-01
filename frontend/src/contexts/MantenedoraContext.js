import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { mantenedoraAPI, getActiveTenantId } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

const MantenedoraContext = createContext(null);

export const MantenedoraProvider = ({ children }) => {
  const { user } = useAuth();
  const [mantenedora, setMantenedora] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMantenedora = useCallback(async () => {
    // Sem usuário autenticado, não tenta carregar (o axios falharia com 401).
    if (!user) {
      setMantenedora(null);
      setLoading(false);
      return;
    }

    // MT-1: super_admin sem tenant selecionado permanece apenas no control plane.
    // Não dispara /api/mantenedora nem cria fallback visual de outra prefeitura.
    if (user.role === 'super_admin' && !getActiveTenantId()) {
      setMantenedora(null);
      setLoading(false);
      return;
    }

    try {
      const data = await mantenedoraAPI.get();
      setMantenedora(data);
    } catch (error) {
      console.error('Erro ao carregar mantenedora:', error);
      // Fallback genérico, sem inferir dados de outra mantenedora.
      setMantenedora({
        nome: 'Mantenedora não disponível',
        municipio: '',
        estado: '',
        brasao_url: ''
      });
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    loadMantenedora();
  }, [loadMantenedora]);

  // Recarrega quando o tenant ativo muda (TenantSwitcher dispara esse evento).
  useEffect(() => {
    const handler = () => loadMantenedora();
    window.addEventListener('tenant-changed', handler);
    return () => window.removeEventListener('tenant-changed', handler);
  }, [loadMantenedora]);

  // Função para recarregar os dados (útil após atualização).
  const refreshMantenedora = () => {
    loadMantenedora();
  };

  // Dados padrão para formulários. Sem contexto válido, usa campos vazios para
  // não projetar silenciosamente município/UF de outro tenant.
  const getDefaultLocation = () => ({
    municipio: mantenedora?.municipio || '',
    estado: mantenedora?.estado || '',
    city: mantenedora?.municipio || '',
    state: mantenedora?.estado || ''
  });

  // Retorna o brasão (ou fallback para logotipo antigo).
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
