import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

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

// Tempo máximo para sessão offline (7 dias em ms)
const MAX_OFFLINE_SESSION = 7 * 24 * 60 * 60 * 1000;

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
  const refreshAccessToken = useCallback(async () => {
    const currentRefreshToken = localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN);
    if (!currentRefreshToken) {
      return null;
    }

    try {
      const response = await axios.post(`${API}/auth/refresh`, {
        refresh_token: currentRefreshToken
      });
      
      const { access_token, refresh_token: newRefreshToken, user: userData } = response.data;
      
      // Atualiza tokens
      setAccessToken(access_token);
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
      
      if (newRefreshToken) {
        setRefreshToken(newRefreshToken);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, newRefreshToken);
      }
      
      if (userData) {
        setUser(userData);
        saveUserDataLocally(userData);
      }
      
      console.log('[Auth] Token renovado com sucesso');
      return access_token;
    } catch (error) {
      console.error('[Auth] Erro ao renovar token:', error);
      return null;
    }
  }, [API]);

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
        
        // Se o erro for 401 e não for uma tentativa de retry
        if (error.response?.status === 401 && !originalRequest._retry) {
          // Se já está renovando, aguarda
          if (isRefreshing.current) {
            return new Promise((resolve) => {
              addRefreshSubscriber((token) => {
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
        }
        
        return Promise.reject(error);
      }
    );

    return () => {
      axios.interceptors.request.eject(requestInterceptor);
      axios.interceptors.response.eject(responseInterceptor);
    };
  }, [refreshAccessToken, onRefreshed, addRefreshSubscriber]);

  // Carrega usuário ao iniciar
  useEffect(() => {
    const loadUser = async () => {
      if (accessToken) {
        if (isOnline()) {
          // Online: tenta validar token com servidor
          try {
            const response = await axios.get(`${API}/auth/me`);
            setUser(response.data);
            saveUserDataLocally(response.data);
            setIsOfflineSession(false);
          } catch (error) {
            console.error('Erro ao carregar usuário:', error);
            // Token inválido, limpa storage
            logout();
          }
        } else {
          // Offline: usa dados em cache
          const cachedUser = getLocalUserData();
          if (cachedUser) {
            setUser(cachedUser);
            setIsOfflineSession(true);
            console.log('[Auth] Sessão offline restaurada');
          } else {
            logout();
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
        const { access_token, refresh_token, user: userData } = response.data;

        // Garante que userData tenha o email para validação offline
        const userDataWithEmail = userData ? { ...userData, email } : { email };
        
        setAccessToken(access_token);
        setRefreshToken(refresh_token);
        setUser(userDataWithEmail);
        setIsOfflineSession(false);

        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);
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
        console.log('[Auth Offline] Dados não encontrados no localStorage');
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

  const logout = () => {
    setUser(null);
    setAccessToken(null);
    setRefreshToken(null);
    setIsOfflineSession(false);
    localStorage.removeItem(STORAGE_KEYS.ACCESS_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
    // Mantém USER_DATA e LAST_LOGIN para permitir login offline futuro
  };

  // Logout completo (remove também dados offline)
  const logoutComplete = () => {
    logout();
    localStorage.removeItem(STORAGE_KEYS.USER_DATA);
    localStorage.removeItem(STORAGE_KEYS.LAST_LOGIN);
  };

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    logoutComplete,
    isAuthenticated: !!user,
    accessToken,
    isOfflineSession,
    isOnline: isOnline()
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
