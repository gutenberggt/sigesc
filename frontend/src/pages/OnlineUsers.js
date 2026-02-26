import { useState, useEffect, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Users, Wifi, Monitor, Clock, RefreshCw, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ROLE_LABELS = {
  'admin': 'Administrador',
  'admin_teste': 'Admin Teste',
  'semed': 'SEMED',
  'semed3': 'SEMED 3',
  'secretario': 'Secretário(a)',
  'diretor': 'Diretor(a)',
  'coordenador': 'Coordenador(a)',
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
  'professor': 'bg-yellow-100 text-yellow-800',
  'ass_social': 'bg-pink-100 text-pink-800',
};

export default function OnlineUsers() {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const tokenRef = useRef(accessToken);
  tokenRef.current = accessToken;
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);

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

  useEffect(() => {
    fetchOnlineUsers();
    const interval = setInterval(fetchOnlineUsers, 10000);
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
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg">
              <Wifi size={24} className="text-green-600" />
            </div>
            Usuários Online
          </h1>
          <p className="text-gray-500 mt-1">Monitoramento em tempo real de usuários conectados</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Clock size={14} />
            {lastUpdate && `Atualizado: ${lastUpdate.toLocaleTimeString('pt-BR')}`}
          </div>
          <button
            onClick={fetchOnlineUsers}
            data-testid="refresh-online-users"
            className="flex items-center gap-2 px-3 py-2 text-sm bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <RefreshCw size={14} />
            Atualizar
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
