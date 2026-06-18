import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import { setCsrfToken, clearApplicationState } from '@/services/api';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

// Chaves para armazenamento local
const STORAGE_KEYS = {
  ACCESS_TOKEN: 'accessToken',
  REFRESH_TOKEN: 'refreshToken',
  USER_DATA: 'userData',
  LAST_LOGIN: 'lastLoginTime',
  LAST_ACTIVITY: 'lastActivityTime'  // PATCH 3.1: Para idle timeout
};

// Tempo máximo para sessão offline (30 dias em ms) — uso em campo/escolas sem internet
const MAX_OFFLINE_SESSION = 30 * 24 * 60 * 60 * 1000;

// PATCH 3.1: Configurações de idle timeout
const IDLE_TIMEOUT_MS = 15 * 60 * 1000;  // 15 minutos de inatividade para expirar
const TOKEN_REFRESH_INTERVAL_MS = 10 * 60 * 1000;  // Renova token a cada 10 minutos se ativo
const ACTIVITY_THROTTLE_MS = 30 * 1000;  // Atualiza timestamp de atividade a cada 30s

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accessToken, setAccessToken] = useState(localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN));
  const [isOfflineSession, setIsOfflineSession] = useState(false);
  const isRefreshing = useRef(false);
  const refreshSubscribers = useRef([]);
  
  // PATCH 3.1: Refs para controle de atividade e refresh proativo
  const lastActivityRef = useRef(Date.now());
  const refreshTimerRef = useRef(null);
  const activityThrottleRef = useRef(null);

  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
  const API = `${BACKEND_URL}/api`;

  // Verifica se está online
  const isOnline = () => navigator.onLine;

  // PATCH 3.1: Atualiza timestamp de última atividade (throttled)
  const updateActivity = useCallback(() => {
    const now = Date.now();
    lastActivityRef.current = now;
    
    // Throttle para não atualizar localStorage muito frequentemente
    if (!activityThrottleRef.current) {
      activityThrottleRef.current = setTimeout(() => {
        localStorage.setItem(STORAGE_KEYS.LAST_ACTIVITY, now.toString());
        activityThrottleRef.current = null;
      }, ACTIVITY_THROTTLE_MS);
    }
  }, []);

  // PATCH 3.1: Verifica se o usuário está inativo
  const isUserIdle = useCallback(() => {
    const lastActivity = lastActivityRef.current;
    const now = Date.now();
    return (now - lastActivity) > IDLE_TIMEOUT_MS;
  }, []);

  // Salva dados do usuário localmente para acesso offline
  const saveUserDataLocally = (userData) => {
    try {
      localStorage.setItem(STORAGE_KEYS.USER_DATA, JSON.stringify(userData));
      localStorage.setItem(STORAGE_KEYS.LAST_LOGIN, Date.now().toString());
    } catch (e) {
      console.error('Erro ao salvar dados do usuário localmente:', e);
    }
  };

  // Recupera dados do usuário salvos localmente
  const getLocalUserData = () => {
    try {
      const userData = localStorage.getItem(STORAGE_KEYS.USER_DATA);
      const lastLogin = localStorage.getItem(STORAGE_KEYS.LAST_LOGIN);
      
      if (!userData || !lastLogin) return null;
      
      // Verifica se a sessão offline ainda é válida
      const sessionAge = Date.now() - parseInt(lastLogin);
      if (sessionAge > MAX_OFFLINE_SESSION) {
        console.log('Sessão offline expirada');
        return null;
      }
      
      return JSON.parse(userData);
    } catch (e) {
      console.error('Erro ao recuperar dados do usuário:', e);
      return null;
    }
  };

  // Função para renovar o token
  const refreshAccessToken = useCallback(async (force = false) => {
    const currentRefreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
    if (!currentRefreshToken) {
      return null;
    }

    // PATCH 3.1: Não renova se usuário está inativo (a menos que seja forçado)
    if (!force && isUserIdle()) {
      console.log('[Auth] Usuário inativo, não renovando token automaticamente');
      return null;
    }

    try {
      const response = await axios.post(`${API}/auth/refresh`, {
        refresh_token: currentRefreshToken
      });
      
      const { access_token, refresh_token: newRefreshToken, csrf_token, user: userData } = response.data;
      
      // Atualiza tokens
      setAccessToken(access_token);
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      
      if (newRefreshToken) {
        setRefreshToken(newRefreshToken);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, newRefreshToken);
      }

      // G2 Mai/2026: atualiza CSRF em sessionStorage após rotação
      if (csrf_token) {
        setCsrfToken(csrf_token);
      }
      
      if (userData) {
        setUser(userData);
        saveUserDataLocally(userData);
      }

      // P0 (Jun/2026): refresh OK = conectividade real + token válido →
      // promove a sessão de volta para ONLINE (caso estivesse em modo offline
      // por falha transitória anterior).
      setIsOfflineSession(false);

      // PATCH 3.1: Atualiza timestamp de atividade ao renovar
      updateActivity();
      
      console.log('[Auth] Token renovado com sucesso');
      return access_token;
    } catch (error) {
      console.error('[Auth] Erro ao renovar token:', error);

      // P0 (Jun/2026) — NUNCA fazer logout/wipe automático aqui. Mesmo que o backend
      // responda "Refresh token revogado" (cenário comum: CORRIDA DE ROTAÇÃO entre
      // múltiplas abas, onde uma aba rotaciona o token e revoga o jti antigo, e a
      // outra aba usa o antigo), a sessão OFFLINE local (userData/lastLoginTime) DEVE
      // ser preservada. Conforme diretriz do produto: SOMENTE logout MANUAL invalida
      // a sessão local. Aqui apenas não renovamos; requests podem falhar até novo
      // login online, mas o acesso offline continua disponível.
      return null;
    }
  }, [API, isUserIdle, updateActivity]);

  // Notifica subscribers após refresh
  const onRefreshed = useCallback((token) => {
    refreshSubscribers.current.forEach(callback => callback(token));
    refreshSubscribers.current = [];
  }, []);

  // Adiciona subscriber para esperar refresh
  const addRefreshSubscriber = useCallback((callback) => {
    refreshSubscribers.current.push(callback);
  }, []);

  // Configura interceptor do axios para incluir token e renovar automaticamente
  useEffect(() => {
    const requestInterceptor = axios.interceptors.request.use(
      (config) => {
        // P1: endpoints de auth são pristinos (não herdam token anterior).
        const url = config.url || '';
        const isAuth = ['/auth/login', '/auth/register', '/auth/refresh'].some((p) => url.includes(p));
        if (isAuth) return config;
        const token = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    const responseInterceptor = axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        const reqUrl = originalRequest?.url || '';
        // P0 (Jun/2026): NUNCA tentar refresh-on-401 para os PRÓPRIOS endpoints de
        // auth. Caso contrário, um 401 do /auth/refresh entra aqui com isRefreshing=true
        // e fica aguardando o refresh que falhou → DEADLOCK (app trava em "Carregando").
        const isAuthEndpoint = ['/auth/login', '/auth/register', '/auth/refresh'].some((p) => reqUrl.includes(p));

        // Se o erro for 401, não for retry e não for endpoint de auth
        if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
          // Se já está renovando, aguarda
          if (isRefreshing.current) {
            return new Promise((resolve, reject) => {
              addRefreshSubscriber((token) => {
                if (!token) {
                  // Refresh falhou: rejeita a request em espera (evita travamento).
                  reject(error);
                  return;
                }
                originalRequest.headers.Authorization = `Bearer ${token}`;
                resolve(axios(originalRequest));
              });
            });
          }

          originalRequest._retry = true;
          isRefreshing.current = true;

          const newToken = await refreshAccessToken();
          
          isRefreshing.current = false;

          if (newToken) {
            onRefreshed(newToken);
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return axios(originalRequest);
          }

          // Refresh falhou (rede/expirado/revogado): libera TODOS os subscribers em
          // espera para que rejeitem em vez de travar indefinidamente.
          refreshSubscribers.current.forEach((cb) => cb(null));
          refreshSubscribers.current = [];
        }
        
        return Promise.reject(error);
      }
    );

    return () => {
      axios.interceptors.request.eject(requestInterceptor);
      axios.interceptors.response.eject(responseInterceptor);
    };
  }, [refreshAccessToken, onRefreshed, addRefreshSubscriber]);

  // PATCH 3.1: Monitora atividade do usuário para idle timeout
  useEffect(() => {
    if (!user) return;  // Só monitora se estiver logado

    // Eventos que indicam atividade do usuário
    const activityEvents = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click'];
    
    // Handler para eventos de atividade
    const handleActivity = () => {
      updateActivity();
    };

    // Adiciona listeners para todos os eventos de atividade
    activityEvents.forEach(event => {
      window.addEventListener(event, handleActivity, { passive: true });
    });

    // Inicializa timestamp de atividade
    updateActivity();

    return () => {
      activityEvents.forEach(event => {
        window.removeEventListener(event, handleActivity);
      });
    };
  }, [user, updateActivity]);

  // PATCH 3.1: Refresh proativo do token enquanto usuário está ativo.
  // P0 (Jun/2026): também roda quando a sessão está em modo offline POR FALHA
  // TRANSITÓRIA — assim, ao voltar a conectividade real, o refresh promove a
  // sessão de volta para online automaticamente (checkAndRefresh só age online).
  useEffect(() => {
    if (!user || !accessToken) return;

    // Função para verificar e renovar token
    const checkAndRefresh = async () => {
      if (!isUserIdle() && isOnline()) {
        console.log('[Auth] Renovação proativa do token (usuário ativo)');
        await refreshAccessToken(false);  // false = não força se inativo
      } else if (isUserIdle()) {
        console.log('[Auth] Usuário inativo, pulando renovação proativa');
      }
    };

    // Configura intervalo para renovação proativa
    refreshTimerRef.current = setInterval(checkAndRefresh, TOKEN_REFRESH_INTERVAL_MS);

    // Faz uma renovação inicial após 1 minuto
    const initialRefresh = setTimeout(checkAndRefresh, 60 * 1000);

    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
      }
      clearTimeout(initialRefresh);
    };
  }, [user, accessToken, isUserIdle, refreshAccessToken]);

  // Carrega usuário ao iniciar.
  // P0 (Jun/2026) — PRESERVAÇÃO DA SESSÃO OFFLINE: falhas de REDE/timeout/
  // Wi-Fi-sem-internet/backend-fora ou um 401 SEM revogação explícita NUNCA
  // destroem a sessão local. Nesses casos caímos para a sessão offline
  // cacheada. Somente logout MANUAL (botão "Sair") ou revogação EXPLÍCITA do
  // servidor invalidam o estado local. NUNCA chamamos logout()/localStorage.clear()
  // aqui por falha temporária — isso apagava a sessão e gerava o erro
  // "Faça login online primeiro".
  useEffect(() => {
    const loadUser = async () => {
      if (accessToken) {
        const cachedUser = getLocalUserData();
        if (isOnline()) {
          // Online (segundo navigator.onLine, que é otimista): tenta validar.
          try {
            const response = await axios.get(`${API}/auth/me`);
            setUser(response.data);
            saveUserDataLocally(response.data);
            setIsOfflineSession(false);
          } catch (error) {
            const status = error.response?.status;
            // P0 (Jun/2026) — NUNCA faz logout/wipe automático no bootstrap. QUALQUER
            // falha (rede, timeout, backend fora, 401 expirado OU "revogado") preserva
            // a sessão offline cacheada. Conforme diretriz: SOMENTE logout MANUAL
            // invalida o estado local. Isso elimina o apagamento indevido de
            // userData/lastLoginTime que gerava "Faça login online primeiro".
            if (cachedUser) {
              console.warn('[Auth] /auth/me indisponível — mantendo sessão offline cacheada.', { status });
              setUser(cachedUser);
              setIsOfflineSession(true);
            } else {
              console.warn('[Auth] Sem sessão cacheada para restaurar — exibindo login.', { status });
              setUser(null);
            }
          }
        } else {
          // Offline real: usa dados em cache. Sem cache → mostra login (sem wipe).
          if (cachedUser) {
            setUser(cachedUser);
            setIsOfflineSession(true);
            console.log('[Auth] Sessão offline restaurada');
          } else {
            console.warn('[Auth] Offline e sem sessão cacheada — exibindo login.');
            setUser(null);
          }
        }
      }
      setLoading(false);
    };

    loadUser();
  }, []);

  const login = async (email, password) => {
    // Se estiver online, faz login normal
    if (isOnline()) {
      try {
        const response = await axios.post(`${API}/auth/login`, { email, password });
        const { access_token, refresh_token, csrf_token, user: userData } = response.data;

        // P1: LOGIN UNIVERSAL — descarta QUALQUER estado anterior (tenant/escola/
        // perfil/usuário) antes de reconstruir a sessão a partir do backend.
        clearApplicationState();

        // Garante que userData tenha o email para validação offline
        const userDataWithEmail = userData ? { ...userData, email } : { email };
        
        setAccessToken(access_token);
        setRefreshToken(refresh_token);
        setUser(userDataWithEmail);
        setIsOfflineSession(false);

        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);
        // G2 Mai/2026: armazena CSRF em sessionStorage para deploys cross-domain
        // (frontend ≠ backend) onde JS não consegue ler o cookie via document.cookie
        if (csrf_token) {
          setCsrfToken(csrf_token);
        }
        saveUserDataLocally(userDataWithEmail);
        
        console.log('[Auth] Dados salvos para offline:', userDataWithEmail);

        return { success: true, user: userDataWithEmail };
      } catch (error) {
        console.error('Erro no login:', error);
        return {
          success: false,
          error: error.response?.data?.detail || 'Erro ao fazer login'
        };
      }
    } else {
      // Offline: tenta usar sessão salva
      const cachedUser = getLocalUserData();
      const savedToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
      
      console.log('[Auth Offline] cachedUser:', cachedUser);
      console.log('[Auth Offline] savedToken exists:', !!savedToken);
      console.log('[Auth Offline] email tentado:', email);
      
      // Permite login offline se tiver dados do usuário (mesmo sem token)
      if (cachedUser) {
        // Verifica se o email corresponde ao usuário em cache
        if (cachedUser.email === email) {
          setUser(cachedUser);
          // Usa token salvo se existir, ou cria um token temporário para sessão offline
          setAccessToken(savedToken || 'offline-session-token');
          setIsOfflineSession(true);
          
          return { 
            success: true, 
            user: cachedUser,
            offline: true,
            message: 'Login offline - usando sessão salva'
          };
        } else {
          return {
            success: false,
            error: `Modo offline: apenas o último usuário logado (${cachedUser.email}) pode acessar`,
            offline: true
          };
        }
      } else {
        console.warn('[Auth Offline] Sessão offline ausente/expirada:', {
          temUserData: !!localStorage.getItem(STORAGE_KEYS.USER_DATA),
          temLastLogin: !!localStorage.getItem(STORAGE_KEYS.LAST_LOGIN),
          lastLogin: localStorage.getItem(STORAGE_KEYS.LAST_LOGIN),
          diasDesdeLogin: localStorage.getItem(STORAGE_KEYS.LAST_LOGIN)
            ? ((Date.now() - Number(localStorage.getItem(STORAGE_KEYS.LAST_LOGIN))) / 86400000).toFixed(2)
            : null,
        });
        return {
          success: false,
          error: 'Sem conexão com a internet. Faça login online primeiro para habilitar o acesso offline.',
          offline: true
        };
      }
    }
  };

  const register = async (userData) => {
    if (!isOnline()) {
      return {
        success: false,
        error: 'Sem conexão com a internet. O registro requer conexão online.'
      };
    }
    
    try {
      const response = await axios.post(`${API}/auth/register`, userData);
      return { success: true, user: response.data };
    } catch (error) {
      console.error('Erro no registro:', error);
      return {
        success: false,
        error: error.response?.data?.detail || 'Erro ao registrar usuário'
      };
    }
  };

  const logout = async () => {
    // PATCH 3.3: Tenta revogar o token no backend antes de limpar localmente
    const currentRefreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
    const currentAccessToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    
    if (isOnline() && currentAccessToken && currentRefreshToken) {
      try {
        await axios.post(`${API}/auth/logout`, {
          refresh_token: currentRefreshToken
        }, {
          headers: { Authorization: `Bearer ${currentAccessToken}` }
        });
        console.log('[Auth] Logout no servidor realizado');
      } catch (error) {
        // Ignora erros de logout no servidor (pode já estar expirado)
        console.log('[Auth] Erro ao fazer logout no servidor (ignorado):', error.message);
      }
    }

    // PATCH 3.1: Limpa timers de refresh proativo
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    if (activityThrottleRef.current) {
      clearTimeout(activityThrottleRef.current);
      activityThrottleRef.current = null;
    }

    setUser(null);
    setAccessToken(null);
    setRefreshToken(null);
    setIsOfflineSession(false);
    // P1: reset TOTAL do estado local — volta ao estado de "primeira visita".
    // Remove tokens, tenant ativo, contexto selecionado, CSRF e caches locais.
    clearApplicationState();
  };

  // Logout completo (remove também dados offline)
  const logoutComplete = async () => {
    // PATCH 3.3: Tenta revogar TODAS as sessões no backend
    const currentAccessToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    
    if (isOnline() && currentAccessToken) {
      try {
        await axios.post(`${API}/auth/logout-all`, {}, {
          headers: { Authorization: `Bearer ${currentAccessToken}` }
        });
        console.log('[Auth] Logout de todas as sessões realizado');
      } catch (error) {
        console.log('[Auth] Erro ao fazer logout-all (ignorado):', error.message);
      }
    }

    await logout();
    localStorage.removeItem(STORAGE_KEYS.USER_DATA);
    localStorage.removeItem(STORAGE_KEYS.LAST_LOGIN);
  };

  // Função para trocar o papel ativo (quando usuário tem múltiplos papéis)
  const switchRole = async (newRole) => {
    if (!isOnline()) {
      return {
        success: false,
        error: 'Sem conexão com a internet. A troca de papel requer conexão online.'
      };
    }
    
    const currentToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
    if (!currentToken) {
      return {
        success: false,
        error: 'Usuário não autenticado'
      };
    }
    
    try {
      const response = await axios.post(`${API}/users/switch-role`, 
        { role: newRole },
        { headers: { Authorization: `Bearer ${currentToken}` } }
      );
      
      // Atualiza o usuário com o novo papel
      const updatedUser = { ...user, role: newRole };
      setUser(updatedUser);
      saveUserDataLocally(updatedUser);
      
      return { 
        success: true, 
        message: response.data.message,
        newRole: newRole 
      };
    } catch (error) {
      console.error('Erro ao trocar papel:', error);
      return {
        success: false,
        error: error.response?.data?.detail || 'Erro ao trocar papel'
      };
    }
  };

  // Retorna a lista de papéis disponíveis para o usuário
  const getAvailableRoles = () => {
    if (!user) return [];
    // Se tem lista de roles, usa ela; senão usa apenas o role principal
    return user.roles && user.roles.length > 0 ? user.roles : [user.role];
  };

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    logoutComplete,
    switchRole,
    getAvailableRoles,
    isAuthenticated: !!user,
    accessToken,
    isOfflineSession,
    isOnline: isOnline()
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
