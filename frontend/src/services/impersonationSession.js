import axios from 'axios';
import { clearApplicationState, setCsrfToken } from '@/services/api';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const installSessionPayload = (payload) => {
  const { access_token, refresh_token, csrf_token } = payload || {};
  if (!access_token || !refresh_token) {
    throw new Error('Resposta de sessão incompleta');
  }

  clearApplicationState();
  localStorage.removeItem('userData');
  localStorage.removeItem('lastLoginTime');
  localStorage.setItem('accessToken', access_token);
  localStorage.setItem('refreshToken', refresh_token);
  if (csrf_token) setCsrfToken(csrf_token);
};

export const searchImpersonationUsers = async (query, limit = 20) => {
  const response = await axios.get(`${API}/auth/impersonation/users/search`, {
    params: { q: query, limit },
  });
  return response.data?.items || [];
};

export const startImpersonationSession = async ({ targetUserId, password, activeRole }) => {
  const response = await axios.post(`${API}/auth/impersonation/start`, {
    target_user_id: targetUserId,
    password,
    ...(activeRole ? { active_role: activeRole } : {}),
  });

  installSessionPayload(response.data);
  window.location.assign('/dashboard');
};

export const stopImpersonationSession = async () => {
  const response = await axios.post(`${API}/auth/impersonation/stop`, {});
  installSessionPayload(response.data);
  window.location.assign('/dashboard');
};
