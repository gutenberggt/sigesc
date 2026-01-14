import { createContext, useContext, useState, useEffect } from 'react';
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
  LAST_LOGIN: 'lastLoginTime'
};

// Tempo máximo para sessão offline (7 dias em ms)
const MAX_OFFLINE_SESSION = 7 * 24 * 60 * 60 * 1000;

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [accessToken, setAccessToken] = useState(localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem(STORAGE_KEYS.REFRESH_TOKEN));
  const [isOfflineSession, setIsOfflineSession] = useState(false);

  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
  const API = `${BACKEND_URL}/api`;

  // Verifica se está online
  const isOnline = () => navigator.onLine;

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

  // Configura interceptor do axios para incluir token
  useEffect(() => {
    const interceptor = axios.interceptors.request.use(
      (config) => {
        if (accessToken) {
          config.headers.Authorization = `Bearer ${accessToken}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    return () => {
      axios.interceptors.request.eject(interceptor);
    };
  }, [accessToken]);

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

        setAccessToken(access_token);
        setRefreshToken(refresh_token);
        setUser(userData);
        setIsOfflineSession(false);

        localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, access_token);
        localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refresh_token);
        saveUserDataLocally(userData);

        return { success: true, user: userData };
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
      
      if (cachedUser && savedToken) {
        // Verifica se o email corresponde ao usuário em cache
        if (cachedUser.email === email) {
          setUser(cachedUser);
          setAccessToken(savedToken);
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
            error: 'Modo offline: apenas o último usuário logado pode acessar',
            offline: true
          };
        }
      } else {
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
