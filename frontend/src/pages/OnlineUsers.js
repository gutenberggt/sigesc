import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Users, Wifi, Monitor, Clock, RefreshCw, Home, LogOut, AlertTriangle, History } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { hasRole } from '@/utils/permissions';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ROLE_LABELS = {
  'admin': 'Administrador',
  'admin_teste': 'Admin Teste',
  'semed': 'SEMED',
  'semed3': 'Administração',
  'secretario': 'Secretário(a)',
  'diretor': 'Diretor(a)',
  'coordenador': 'Coordenador(a)',
  'apoio_pedagogico': 'Apoio Pedagógico',
  'auxiliar_secretaria': 'Auxiliar de Secretaria',
  'professor': 'Professor(a)',
  'ass_social': 'Ass. Social',
};

const ROLE_COLORS = {
  'admin': 'bg-red-100 text-red-800',
  'admin_teste': 'bg-orange-100 text-orange-800',
  'semed': 'bg-purple-100 text-purple-800',
  'semed3': 'bg-purple-100 text-purple-800',
  'secretario': 'bg-blue-100 text-blue-800',
  'diretor': 'bg-green-100 text-green-800',
  'coordenador': 'bg-teal-100 text-teal-800',
  'apoio_pedagogico': 'bg-teal-100 text-teal-800',
  'auxiliar_secretaria': 'bg-teal-100 text-teal-800',
  'professor': 'bg-yellow-100 text-yellow-800',
  'ass_social': 'bg-pink-100 text-pink-800',
};

export default function OnlineUsers() {
  const { user: currentUser, accessToken } = useAuth();
  const navigate = useNavigate();
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [confirmTarget, setConfirmTarget] = useState(null); // user a desconectar
  const [revoking, setRevoking] = useState(false);
  const [feedback, setFeedback] = useState(null); // { type, message }
  const [loginCount, setLoginCount] = useState(null); // { total, successful }
  
  const isSuperAdmin = hasRole(currentUser, ['super_admin']);

  const fetchOnlineUsers = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/online-users`, {
        headers: { 'Authorization': `Bearer ${tokenRef.current}` }
      });
      if (response.ok) {
        const data = await response.json();
        setUsers(data);
        setLastUpdate(new Date());
      }
    } catch (error) {
      console.error('Erro ao buscar usuários online:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchLoginCount = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/online-users/login-count`, {
        headers: { 'Authorization': `Bearer ${tokenRef.current}` }
      });
      if (response.ok) {
        const data = await response.json();
        setLoginCount(data);
      }
    } catch (error) {
      console.error('Erro ao buscar contagem de conexões:', error);
    }
  };

  const handleForceLogout = async () => {
    if (!confirmTarget) return;
    setRevoking(true);
    try {
      const response = await fetch(
        `${API_URL}/api/admin/sessions/revoke/${confirmTarget.id}`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${tokenRef.current}` }
        }
      );
      if (response.ok) {
        setFeedback({ type: 'success', message: `Sessões de ${confirmTarget.full_name} encerradas com sucesso.` });
        setConfirmTarget(null);
        // Atualiza lista após pequeno delay (deixa backend processar)
        setTimeout(fetchOnlineUsers, 800);
      } else {
        const body = await response.json().catch(() => ({}));
        setFeedback({ type: 'error', message: body.detail || 'Erro ao encerrar sessões.' });
      }
    } catch (error) {
      setFeedback({ type: 'error', message: 'Falha de rede ao encerrar sessões.' });
    } finally {
      setRevoking(false);
    }
    setTimeout(() => setFeedback(null), 5000);
  };

  useEffect(() => {
    fetchOnlineUsers();
    fetchLoginCount();
    const interval = setInterval(() => {
      fetchOnlineUsers();
      fetchLoginCount();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const getInitials = (name) => {
    if (!name) return '?';
    return name.split(' ').filter(Boolean).slice(0, 2).map(n => n[0]).join('').toUpperCase();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="online-users-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            data-testid="back-to-dashboard-button"
          >
            <Home size={18} />
            <span>Início</span>
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <Wifi size={24} className="text-green-600" />
              </div>
              Usuários Online
            </h1>
            <p className="text-gray-500 mt-1">Monitoramento em tempo real de usuários conectados</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Clock size={14} />
            {lastUpdate && `Atualizado: ${lastUpdate.toLocaleTimeString('pt-BR')}`}
          </div>
          <button
            onClick={() => { fetchOnlineUsers(); fetchLoginCount(); }}
            data-testid="refresh-online-users"
            className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <RefreshCw size={14} />
            Atualizar
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
          <div className="p-3 bg-green-50 rounded-lg">
            <Users size={20} className="text-green-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900" data-testid="total-online">{users.length}</p>
            <p className="text-sm text-gray-500">Total Online</p>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
          <div className="p-3 bg-blue-50 rounded-lg">
            <Monitor size={20} className="text-blue-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900">
              {users.reduce((acc, u) => acc + (u.connections || 1), 0)}
            </p>
            <p className="text-sm text-gray-500">Conexões Ativas</p>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
          <div className="p-3 bg-purple-50 rounded-lg">
            <Users size={20} className="text-purple-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900">
              {[...new Set(users.map(u => u.role))].length}
            </p>
            <p className="text-sm text-gray-500">Perfis Diferentes</p>
          </div>
        </div>
        <div
          className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4"
          data-testid="total-connections-card"
          title="Total acumulado de eventos de login registrados na auditoria (inclui tentativas)."
        >
          <div className="p-3 bg-amber-50 rounded-lg">
            <History size={20} className="text-amber-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900" data-testid="total-connections-value">
              {loginCount === null
                ? '—'
                : (loginCount.total ?? 0).toLocaleString('pt-BR')}
            </p>
            <p className="text-sm text-gray-500">Conexões Registradas</p>
            {loginCount !== null && (
              <p
                className="text-[11px] text-gray-400 mt-0.5"
                data-testid="total-connections-successful"
              >
                {(loginCount.successful ?? 0).toLocaleString('pt-BR')} bem-sucedidas
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Users List */}
      {users.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Users size={48} className="mx-auto text-gray-300 mb-4" />
          <p className="text-gray-500 text-lg">Nenhum usuário online no momento</p>
          <p className="text-gray-400 text-sm mt-1">A lista atualiza automaticamente a cada 10 segundos</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full" data-testid="online-users-table">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Usuário</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Perfil</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Escola(s)</th>
                <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Conexões</th>
                <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Última Atividade</th>
                {isSuperAdmin && (
                  <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Ações</th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-gray-50 transition-colors" data-testid={`online-user-${user.id}`}>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      {user.avatar_url ? (
                        <img src={user.avatar_url} alt="" className="w-10 h-10 rounded-full object-cover" />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm">
                          {getInitials(user.full_name)}
                        </div>
                      )}
                      <div>
                        <p className="font-medium text-gray-900">{user.full_name}</p>
                        <p className="text-sm text-gray-500">{user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium ${ROLE_COLORS[user.role] || 'bg-gray-100 text-gray-800'}`}>
                      {ROLE_LABELS[user.role] || user.role}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    {user.schools && user.schools.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {user.schools.map((school, idx) => (
                          <span key={idx} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                            {school}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-sm text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-blue-50 text-blue-700 text-sm font-medium">
                      {user.connections || 1}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse"></span>
                      <span className="text-sm text-green-700 font-medium">Online</span>
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right text-sm text-gray-500">
                    {user.last_activity ? new Date(user.last_activity).toLocaleTimeString('pt-BR') : '-'}
                  </td>
                  {isSuperAdmin && (
                    <td className="px-6 py-4 text-center">
                      {user.id === currentUser?.id ? (
                        <span className="text-xs text-gray-400 italic">Você</span>
                      ) : (
                        <button
                          onClick={() => setConfirmTarget(user)}
                          data-testid={`force-logout-btn-${user.id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-red-50 text-red-700 rounded-lg hover:bg-red-100 transition-colors border border-red-200"
                          title="Forçar logout deste usuário"
                        >
                          <LogOut size={13} />
                          Forçar Logout
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Feedback toast */}
      {feedback && (
        <div
          data-testid="force-logout-feedback"
          className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg z-50 ${
            feedback.type === 'success'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {feedback.message}
        </div>
      )}

      {/* Modal de confirmação */}
      {confirmTarget && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => !revoking && setConfirmTarget(null)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
            data-testid="force-logout-modal"
          >
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-red-100 rounded-lg">
                <AlertTriangle size={24} className="text-red-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">Forçar Logout</h3>
                <p className="text-sm text-gray-500 mt-1">Esta ação encerra todas as sessões ativas do usuário.</p>
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 mb-4">
              <p className="text-sm text-gray-600">Usuário:</p>
              <p className="font-medium text-gray-900">{confirmTarget.full_name}</p>
              <p className="text-sm text-gray-500">{confirmTarget.email}</p>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Todos os tokens (web e mobile) serão invalidados imediatamente.
              O usuário precisará fazer login novamente.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmTarget(null)}
                disabled={revoking}
                data-testid="cancel-force-logout"
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleForceLogout}
                disabled={revoking}
                data-testid="confirm-force-logout"
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 inline-flex items-center gap-2"
              >
                {revoking ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    Encerrando...
                  </>
                ) : (
                  <>
                    <LogOut size={14} />
                    Confirmar Logout
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
