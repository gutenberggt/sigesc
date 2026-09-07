import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { mantenedoraAPI, getActiveTenantId } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

const MantenedoraContext = createContext(null);
const ACCESS_STATUS_URL = `${process.env.REACT_APP_BACKEND_URL}/api/mantenedora/access-status`;
const ACCESS_BLOCK_CODES = new Set(['TENANT_INACTIVE', 'TENANT_MAINTENANCE']);

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
        maintenance_mode: false,
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
      console.error('Erro ao verificar disponibilidade/manutenção da mantenedora:', error);
      return null;
    } finally {
      setAccessLoading(false);
    }
  }, [user]);

  const loadMantenedora = useCallback(async () => {
    if (!user) {
      setMantenedora(null);
      setLoading(false);
      return null;
    }

    // MT-1: super_admin sem tenant selecionado permanece apenas no control plane.
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
      // Se disponibilidade/manutenção bloquear a rota, ProtectedRoute renderiza
      // a página institucional correspondente. O fallback não projeta outro tenant.
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

  // Usuários que já estavam conectados quando a manutenção foi ativada precisam
  // sair do plano operacional sem depender de novo login. Há três gatilhos:
  // 1) qualquer resposta axios com código TENANT_MAINTENANCE/TENANT_INACTIVE;
  // 2) retorno da aba/janela ao foco;
  // 3) revalidação leve de segurança a cada 60s como fallback para telas ociosas.
  useEffect(() => {
    if (!user) return undefined;

    const responseInterceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        const code = error?.response?.data?.detail?.code;
        if (ACCESS_BLOCK_CODES.has(code)) {
          loadAccessStatus();
        }
        return Promise.reject(error);
      }
    );

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        loadAccessStatus();
      }
    };
    const refreshOnFocus = () => loadAccessStatus();
    const intervalId = window.setInterval(() => loadAccessStatus(), 60000);

    document.addEventListener('visibilitychange', refreshWhenVisible);
    window.addEventListener('focus', refreshOnFocus);

    return () => {
      axios.interceptors.response.eject(responseInterceptor);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      window.removeEventListener('focus', refreshOnFocus);
      window.clearInterval(intervalId);
    };
  }, [user, loadAccessStatus]);

  const refreshMantenedora = () => loadMantenedora();
  const refreshAccessStatus = async () => loadAccessStatus();

  const getDefaultLocation = () => ({
    municipio: mantenedora?.municipio || '',
    estado: mantenedora?.estado || '',
    city: mantenedora?.municipio || '',
    state: mantenedora?.estado || ''
  });

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
