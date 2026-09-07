import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { mantenedoraAPI, getActiveTenantId } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

const MantenedoraContext = createContext(null);
const ACCESS_STATUS_URL = `${process.env.REACT_APP_BACKEND_URL}/api/mantenedora/access-status`;

export const MantenedoraProvider = ({ children }) => {
  const { user } = useAuth();
  const [mantenedora, setMantenedora] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accessStatus, setAccessStatus] = useState(null);
  const [accessLoading, setAccessLoading] = useState(false);

  const loadAccessStatus = useCallback(async () => {
    if (!user) {
      setAccessStatus(null);
      setAccessLoading(false);
      return null;
    }

    // Super Admin sem tenant selecionado está legitimamente no control plane.
    if (user.role === 'super_admin' && !getActiveTenantId()) {
      const status = {
        tenant_selected: false,
        active: true,
        access_allowed: true,
        reason: 'SUPER_ADMIN_CONTROL_PLANE',
        mantenedora: null,
        allowed_roles: []
      };
      setAccessStatus(status);
      setAccessLoading(false);
      return status;
    }

    try {
      setAccessLoading(true);
      const response = await axios.get(ACCESS_STATUS_URL);
      setAccessStatus(response.data);
      return response.data;
    } catch (error) {
      // Não converte falha de rede em "mantenedora ativa". Preserva o último
      // estado conhecido e deixa a política offline existente decidir a sessão.
      console.error('Erro ao verificar disponibilidade da mantenedora:', error);
      return null;
    } finally {
      setAccessLoading(false);
    }
  }, [user]);

  const loadMantenedora = useCallback(async () => {
    // Sem usuário autenticado, não tenta carregar (o axios falharia com 401).
    if (!user) {
      setMantenedora(null);
      setLoading(false);
      return null;
    }

    // MT-1: super_admin sem tenant selecionado permanece apenas no control plane.
    // Não dispara /api/mantenedora nem cria fallback visual de outra prefeitura.
    if (user.role === 'super_admin' && !getActiveTenantId()) {
      setMantenedora(null);
      setLoading(false);
      return null;
    }

    try {
      setLoading(true);
      const data = await mantenedoraAPI.get();
      setMantenedora(data);
      return data;
    } catch (error) {
      console.error('Erro ao carregar mantenedora:', error);
      // Se a trava de disponibilidade foi a causa, a tela global específica será
      // renderizada pelo ProtectedRoute. Este fallback continua servindo aos
      // demais erros sem inferir dados de outra mantenedora.
      setMantenedora({
        nome: 'Mantenedora não disponível',
        municipio: '',
        estado: '',
        brasao_url: ''
      });
      return null;
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (!user) {
      setAccessStatus(null);
      return;
    }
    loadAccessStatus();
  }, [user, loadAccessStatus]);

  useEffect(() => {
    loadMantenedora();
  }, [loadMantenedora]);

  // Recarrega status + dados quando o tenant ativo muda (TenantSwitcher).
  useEffect(() => {
    const handler = () => {
      setAccessStatus(null);
      loadAccessStatus();
      loadMantenedora();
    };
    window.addEventListener('tenant-changed', handler);
    return () => window.removeEventListener('tenant-changed', handler);
  }, [loadAccessStatus, loadMantenedora]);

  // Função para recarregar os dados (útil após atualização). Retorna a Promise
  // para que fluxos de ativação possam aguardar a projeção institucional nova.
  const refreshMantenedora = () => loadMantenedora();

  // Revalida a trava. Retorna o novo status para telas que desejam reagir
  // imediatamente ao botão "Verificar novamente".
  const refreshAccessStatus = async () => loadAccessStatus();

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
    accessStatus,
    accessLoading,
    refreshAccessStatus,
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
