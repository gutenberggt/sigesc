import { useState, useEffect, useRef } from 'react';
import { MessageCircle, X, ChevronRight, Minus, Maximize2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { notificationsAPI, connectionsAPI, getWebSocketUrl } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { useMessaging } from '@/contexts/MessagingContext';

export const MessagesBadge = () => {
  const { user } = useAuth();
  const { openChat } = useMessaging();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);
  const wsRef = useRef(null);

  // Buscar contagem de mensagens não lidas
  const fetchUnreadCount = async () => {
    try {
      const data = await notificationsAPI.getUnreadCount();
      setUnreadCount(data.unread_messages);
    } catch (error) {
      console.error('Erro ao buscar contagem:', error);
    }
  };

  // Buscar conexões com mensagens
  const fetchConversations = async () => {
    setLoading(true);
    try {
      const connections = await connectionsAPI.list();
      // Filtrar apenas conexões aceitas
      const accepted = connections.filter(c => c.status === 'accepted');
      setConversations(accepted.slice(0, 5));
    } catch (error) {
      console.error('Erro ao buscar conversas:', error);
    } finally {
      setLoading(false);
    }
  };

  // WebSocket para atualizações em tempo real
  useEffect(() => {
    const wsUrl = getWebSocketUrl();
    if (!wsUrl) return;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (event.data === 'pong') return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'new_message') {
          fetchUnreadCount();
        }
      } catch (error) {
        // Ignorar erros de parsing
      }
    };

    ws.onopen = () => {
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 25000);
      ws.pingInterval = pingInterval;
    };

    ws.onclose = () => {
      if (ws.pingInterval) clearInterval(ws.pingInterval);
    };

    return () => {
      if (ws.pingInterval) clearInterval(ws.pingInterval);
      ws.close();
    };
  }, []);

  // Buscar contagem ao montar
  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 60000);
    return () => clearInterval(interval);
  }, []);

  // Buscar conversas quando o dropdown abre
  useEffect(() => {
    if (isOpen) {
      fetchConversations();
    }
  }, [isOpen]);

  // Fechar ao clicar fora
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Botão do Envelope */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors"
        title="Mensagens"
      >
        <MessageCircle size={20} />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-blue-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && minimized && (
        <div
          className="absolute right-0 mt-2 bg-white rounded-lg shadow-lg border border-gray-200 z-50 cursor-pointer hover:bg-gray-50 transition-colors"
          onClick={() => setMinimized(false)}
          title="Expandir mensagens"
          data-testid="messages-minimized"
        >
          <div className="p-3 flex items-center justify-center">
            <Maximize2 size={18} className="text-blue-600" />
          </div>
        </div>
      )}

      {isOpen && !minimized && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50 overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Mensagens</h3>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setMinimized(true)}
                className="p-1 rounded hover:bg-gray-200 transition-colors"
                title="Minimizar"
                data-testid="messages-minimize-btn"
              >
                <Minus size={16} className="text-gray-500" />
              </button>
              <button
                onClick={() => { setIsOpen(false); setMinimized(false); }}
                className="p-1 rounded hover:bg-gray-200 transition-colors"
                title="Fechar"
              >
                <X size={16} className="text-gray-500" />
              </button>
            </div>
          </div>

          {/* Lista de conversas */}
          <div className="max-h-80 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-center text-gray-500">Carregando...</div>
            ) : conversations.length === 0 ? (
              <div className="p-4 text-center text-gray-500">
                Nenhuma conversa encontrada
              </div>
            ) : (
              conversations.map((conv) => (
                <div
                  key={conv.id}
                  className="p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors"
                  data-testid={`conversation-item-${conv.user_id}`}
                  onClick={() => {
                    // Open ChatBox directly using global context (no navigation)
                    openChat({
                      id: conv.id,
                      user_id: conv.user_id,
                      full_name: conv.full_name,
                      foto_url: conv.foto_url,
                      headline: conv.headline
                    });
                    setIsOpen(false);
                  }}
                >
                  <div className="flex items-center gap-3">
                    {/* Avatar */}
                    <div className="flex-shrink-0">
                      {conv.foto_url ? (
                        <img
                          src={conv.foto_url}
                          alt={conv.full_name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
                          <span className="text-gray-600 font-medium">
                            {conv.full_name?.charAt(0)?.toUpperCase()}
                          </span>
                        </div>
                      )}
                    </div>
                    
                    {/* Conteúdo */}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-900 text-sm truncate">
                        {conv.full_name}
                      </p>
                      <p className="text-gray-500 text-xs truncate">
                        {conv.headline || conv.role}
                      </p>
                    </div>

                    {/* Indicador */}
                    {conv.unread_count > 0 && (
                      <div className="flex-shrink-0">
                        <span className="bg-blue-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center">
                          {conv.unread_count > 9 ? '9+' : conv.unread_count}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 bg-gray-50 border-t border-gray-200">
            <button
              onClick={() => {
                navigate('/profile');
                setIsOpen(false);
              }}
              className="w-full text-center text-blue-600 hover:text-blue-700 text-sm font-medium flex items-center justify-center gap-1"
            >
              Ver todas as mensagens
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default MessagesBadge;
