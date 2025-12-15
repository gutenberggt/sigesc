import { useState, useEffect, useRef } from 'react';
import { Bell, MessageCircle, X, Check, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { notificationsAPI, announcementsAPI, getWebSocketUrl } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

export const NotificationBell = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [counts, setCounts] = useState({ unread_messages: 0, unread_announcements: 0, total: 0 });
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);
  const wsRef = useRef(null);

  // Buscar contagem de notificações
  const fetchCounts = async () => {
    try {
      const data = await notificationsAPI.getUnreadCount();
      setCounts(data);
    } catch (error) {
      console.error('Erro ao buscar contagem:', error);
    }
  };

  // Buscar avisos recentes
  const fetchAnnouncements = async () => {
    setLoading(true);
    try {
      const data = await announcementsAPI.list(0, 5);
      setAnnouncements(data);
    } catch (error) {
      console.error('Erro ao buscar avisos:', error);
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
        if (data.type === 'new_announcement' || data.type === 'new_message') {
          fetchCounts();
        }
      } catch (error) {
        // Ignorar erros de parsing
      }
    };

    ws.onopen = () => {
      // Ping periódico
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

  // Buscar contagens ao montar
  useEffect(() => {
    fetchCounts();
    const interval = setInterval(fetchCounts, 60000); // Atualizar a cada minuto
    return () => clearInterval(interval);
  }, []);

  // Buscar avisos quando o dropdown abre
  useEffect(() => {
    if (isOpen) {
      fetchAnnouncements();
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

  const handleMarkAsRead = async (announcementId) => {
    try {
      await announcementsAPI.markAsRead(announcementId);
      setAnnouncements(prev => 
        prev.map(a => a.id === announcementId ? { ...a, is_read: true } : a)
      );
      fetchCounts();
    } catch (error) {
      console.error('Erro ao marcar como lido:', error);
    }
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return 'Agora';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}min`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`;
    return date.toLocaleDateString('pt-BR');
  };

  const roleLabels = {
    admin: 'Administrador',
    secretario: 'Secretário',
    diretor: 'Diretor',
    coordenador: 'Coordenador',
    professor: 'Professor'
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Botão do Sininho */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors"
        title="Avisos"
      >
        <Bell size={20} />
        {counts.unread_announcements > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center">
            {counts.unread_announcements > 9 ? '9+' : counts.unread_announcements}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50 overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Avisos</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded hover:bg-gray-200 transition-colors"
            >
              <X size={16} className="text-gray-500" />
            </button>
          </div>

          {/* Lista de avisos */}
          <div className="max-h-80 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-center text-gray-500">Carregando...</div>
            ) : announcements.length === 0 ? (
              <div className="p-4 text-center text-gray-500">
                Nenhum aviso encontrado
              </div>
            ) : (
              announcements.map((announcement) => (
                <div
                  key={announcement.id}
                  className={`p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors ${
                    !announcement.is_read ? 'bg-blue-50' : ''
                  }`}
                  onClick={() => {
                    if (!announcement.is_read) {
                      handleMarkAsRead(announcement.id);
                    }
                    navigate(`/avisos?id=${announcement.id}`);
                    setIsOpen(false);
                  }}
                >
                  <div className="flex items-start gap-3">
                    {/* Avatar */}
                    <div className="flex-shrink-0">
                      {announcement.sender_foto_url ? (
                        <img
                          src={announcement.sender_foto_url}
                          alt={announcement.sender_name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                          <Bell size={18} className="text-blue-600" />
                        </div>
                      )}
                    </div>
                    
                    {/* Conteúdo */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900 text-sm truncate">
                          {announcement.sender_name}
                        </span>
                        <span className="text-xs text-gray-500">
                          {roleLabels[announcement.sender_role] || announcement.sender_role}
                        </span>
                      </div>
                      <p className="font-medium text-gray-800 text-sm truncate">
                        {announcement.title}
                      </p>
                      <p className="text-gray-600 text-xs truncate">
                        {announcement.content.substring(0, 60)}...
                      </p>
                      <span className="text-xs text-gray-400">
                        {formatDate(announcement.created_at)}
                      </span>
                    </div>

                    {/* Indicador de não lido */}
                    {!announcement.is_read && (
                      <div className="flex-shrink-0">
                        <div className="w-2 h-2 bg-blue-500 rounded-full" />
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
                navigate('/avisos');
                setIsOpen(false);
              }}
              className="w-full text-center text-blue-600 hover:text-blue-700 text-sm font-medium flex items-center justify-center gap-1"
            >
              Ver todos os avisos
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
