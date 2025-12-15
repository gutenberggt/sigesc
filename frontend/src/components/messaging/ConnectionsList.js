import { useState, useEffect } from 'react';
import { User, UserPlus, Check, X, MessageCircle, Clock, Users } from 'lucide-react';
import { connectionsAPI, uploadAPI } from '@/services/api';
import { Button } from '@/components/ui/button';

export const ConnectionsList = ({ onSelectConnection, onOpenChat, selectedConnectionId }) => {
  const [connections, setConnections] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('connections'); // 'connections' | 'pending'

  const loadData = async () => {
    try {
      const [conns, pending] = await Promise.all([
        connectionsAPI.list(),
        connectionsAPI.listPending()
      ]);
      setConnections(conns);
      setPendingInvites(pending);
    } catch (error) {
      console.error('Erro ao carregar conexões:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleAccept = async (connectionId) => {
    try {
      await connectionsAPI.accept(connectionId);
      loadData();
    } catch (error) {
      console.error('Erro ao aceitar convite:', error);
    }
  };

  const handleReject = async (connectionId) => {
    try {
      await connectionsAPI.reject(connectionId);
      loadData();
    } catch (error) {
      console.error('Erro ao rejeitar convite:', error);
    }
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>
        <p className="mt-2 text-sm">Carregando...</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-3 border-b bg-gray-50">
        <h3 className="font-semibold text-gray-800 flex items-center gap-2">
          <Users size={18} />
          Conexões
        </h3>
      </div>

      {/* Tabs */}
      <div className="flex border-b">
        <button
          onClick={() => setActiveTab('connections')}
          className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'connections'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Minhas ({connections.length})
        </button>
        <button
          onClick={() => setActiveTab('pending')}
          className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
            activeTab === 'pending'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Pendentes {pendingInvites.length > 0 && (
            <span className="ml-1 bg-red-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {pendingInvites.length}
            </span>
          )}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'connections' ? (
          connections.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              <UserPlus size={32} className="mx-auto mb-2 text-gray-300" />
              <p className="text-sm">Nenhuma conexão ainda</p>
              <p className="text-xs mt-1">Busque perfis e envie convites</p>
            </div>
          ) : (
            <div className="divide-y">
              {connections.map(conn => (
                <div
                  key={conn.id}
                  className={`p-3 hover:bg-gray-50 cursor-pointer transition-colors ${
                    selectedConnectionId === conn.id ? 'bg-blue-50' : ''
                  }`}
                  onClick={() => onSelectConnection?.(conn)}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center overflow-hidden flex-shrink-0">
                      {conn.foto_url ? (
                        <img
                          src={uploadAPI.getUrl(conn.foto_url)}
                          alt={conn.full_name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <User size={20} className="text-gray-400" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-gray-900 truncate">
                        {conn.full_name}
                      </p>
                      <p className="text-xs text-gray-500 truncate">
                        {conn.headline || conn.role}
                      </p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenChat?.(conn);
                      }}
                      className="p-2 text-blue-600 hover:bg-blue-100 rounded-full transition-colors"
                      title="Enviar mensagem"
                    >
                      <MessageCircle size={18} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )
        ) : (
          pendingInvites.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              <Clock size={32} className="mx-auto mb-2 text-gray-300" />
              <p className="text-sm">Nenhum convite pendente</p>
            </div>
          ) : (
            <div className="divide-y">
              {pendingInvites.map(invite => (
                <div key={invite.id} className="p-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center overflow-hidden flex-shrink-0">
                      {invite.foto_url ? (
                        <img
                          src={uploadAPI.getUrl(invite.foto_url)}
                          alt={invite.full_name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <User size={20} className="text-gray-400" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-gray-900 truncate">
                        {invite.full_name}
                      </p>
                      <p className="text-xs text-gray-500 truncate">
                        {invite.headline || invite.role}
                      </p>
                      {invite.message && (
                        <p className="text-xs text-gray-600 mt-1 italic">
                          "{invite.message}"
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-2 mt-2 ml-13">
                    <Button
                      size="sm"
                      onClick={() => handleAccept(invite.id)}
                      className="flex-1 bg-blue-600 hover:bg-blue-700"
                    >
                      <Check size={14} className="mr-1" />
                      Aceitar
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleReject(invite.id)}
                      className="flex-1"
                    >
                      <X size={14} className="mr-1" />
                      Recusar
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )
        )}
      </div>
    </div>
  );
};

export default ConnectionsList;
