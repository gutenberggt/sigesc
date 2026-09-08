import { useState, useEffect, useRef } from 'react';
import { Bell, X, ChevronRight, ShieldAlert, AlertTriangle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { notificationsAPI, announcementsAPI, getWebSocketUrl } from '@/services/api';
import { curriculumAlertsAPI } from '@/services/curriculumAlerts';
import { useAuth } from '@/contexts/AuthContext';

export const NotificationBell = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(false);
  const [counts, setCounts] = useState({
    unread_messages: 0,
    unread_announcements: 0,
    unread_curriculum_alerts: 0,
    total: 0,
  });
  const [announcements, setAnnouncements] = useState([]);
  const [curriculumAlerts, setCurriculumAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [forceLogout, setForceLogout] = useState(null); // { message }
  const dropdownRef = useRef(null);
  const wsRef = useRef(null);

  const fetchCounts = async () => {
    try {
      const [baseResult, curriculumResult] = await Promise.allSettled([
        notificationsAPI.getUnreadCount(),
        curriculumAlertsAPI.list(5),
      ]);
      const base = baseResult.status === 'fulfilled' ? baseResult.value : {};
      const curriculumUnread = curriculumResult.status === 'fulfilled'
        ? (curriculumResult.value?.unread || 0)
        : 0;
      setCounts({
        unread_messages: base.unread_messages || 0,
        unread_announcements: base.unread_announcements || 0,
        unread_curriculum_alerts: curriculumUnread,
        total: (base.total || 0) + curriculumUnread,
      });
    } catch (error) {
      console.error('Erro ao buscar contagem:', error);
    }
  };

  const fetchAnnouncements = async () => {
    try {
      const data = await announcementsAPI.list(0, 5);
      setAnnouncements(data);
    } catch (error) {
      console.error('Erro ao buscar avisos:', error);
    }
  };

  const fetchCurriculumAlerts = async () => {
    try {
      const data = await curriculumAlertsAPI.list(8);
      setCurriculumAlerts(data?.items || []);
    } catch (error) {
      console.error('Erro ao buscar alertas curriculares:', error);
      setCurriculumAlerts([]);
    }
  };

  const fetchDropdown = async () => {
    setLoading(true);
    try {
      await Promise.all([fetchAnnouncements(), fetchCurriculumAlerts()]);
    } finally {
      setLoading(false);
    }
  };

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
        } else if (data.type === 'force_logout') {
          setForceLogout({
            message: data.message || 'Sua sessão foi encerrada pelo administrador.'
          });
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

  useEffect(() => {
    fetchCounts();
    const interval = setInterval(fetchCounts, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchDropdown();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleMarkAnnouncementAsRead = async (announcementId) => {
    try {
      await announcementsAPI.markAsRead(announcementId);
      setAnnouncements(prev =>
        prev.map(a => a.id === announcementId ? { ...a, is_read: true } : a)
      );
      fetchCounts();
    } catch (error) {
      console.error('Erro ao marcar aviso como lido:', error);
    }
  };

  const curriculumTarget = (alert) => {
    const role = user?.role || '';
    if (role === 'professor') return '/professor#meus-diarios';
    if (role === 'gerente' || role.startsWith('semed')) return '/semed/panel';
    return alert?.link || '/admin/curriculo/cobertura';
  };

  const handleCurriculumAlert = async (alert) => {
    try {
      if (!alert.read) {
        await curriculumAlertsAPI.markAsRead(alert.id);
        setCurriculumAlerts(prev => prev.map(item =>
          item.id === alert.id ? { ...item, read: true } : item
        ));
      }
    } catch (error) {
      console.error('Erro ao marcar alerta curricular como lido:', error);
    }
    navigate(curriculumTarget(alert));
    setIsOpen(false);
    fetchCounts();
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
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    apoio_pedagogico: 'Apoio Pedagógico',
    auxiliar_secretaria: 'Auxiliar de Secretaria',
    professor: 'Professor(a)'
  };

  const bellUnread = (counts.unread_announcements || 0) + (counts.unread_curriculum_alerts || 0);
  const nothingToShow = announcements.length === 0 && curriculumAlerts.length === 0;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors"
        title="Alertas e avisos"
      >
        <Bell size={20} />
        {bellUnread > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center">
            {bellUnread > 9 ? '9+' : bellUnread}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-50 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Alertas e avisos</h3>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 rounded hover:bg-gray-200 transition-colors"
            >
              <X size={16} className="text-gray-500" />
            </button>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-center text-gray-500">Carregando...</div>
            ) : nothingToShow ? (
              <div className="p-4 text-center text-gray-500">Nenhum alerta ou aviso encontrado</div>
            ) : (
              <>
                {curriculumAlerts.length > 0 && (
                  <div data-testid="curriculum-alerts-inbox">
                    <div className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 bg-gray-50 border-b border-gray-100">
                      Cobertura curricular
                    </div>
                    {curriculumAlerts.map((alert) => (
                      <button
                        type="button"
                        key={alert.id}
                        onClick={() => handleCurriculumAlert(alert)}
                        className={`w-full text-left p-3 border-b border-gray-100 hover:bg-gray-50 transition-colors ${!alert.read ? 'bg-amber-50' : ''}`}
                        data-testid={`curriculum-alert-${alert.id}`}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${alert.severity === 'grave' ? 'bg-red-100' : 'bg-amber-100'}`}>
                            <AlertTriangle size={17} className={alert.severity === 'grave' ? 'text-red-600' : 'text-amber-600'} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="font-semibold text-gray-900 text-sm truncate">{alert.title}</p>
                              {!alert.read && <span className="w-2 h-2 bg-amber-500 rounded-full flex-shrink-0" />}
                            </div>
                            <p className="text-gray-600 text-xs line-clamp-2 mt-0.5">{alert.message}</p>
                            <span className="text-xs text-gray-400">{formatDate(alert.created_at)}</span>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}

                {announcements.length > 0 && (
                  <div>
                    <div className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 bg-gray-50 border-b border-gray-100">
                      Avisos
                    </div>
                    {announcements.map((announcement) => (
                      <div
                        key={announcement.id}
                        className={`p-3 border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors ${!announcement.is_read ? 'bg-blue-50' : ''}`}
                        onClick={() => {
                          if (!announcement.is_read) {
                            handleMarkAnnouncementAsRead(announcement.id);
                          }
                          navigate(`/avisos?id=${announcement.id}`);
                          setIsOpen(false);
                        }}
                      >
                        <div className="flex items-start gap-3">
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
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-900 text-sm truncate">{announcement.sender_name}</span>
                              <span className="text-xs text-gray-500">{roleLabels[announcement.sender_role] || announcement.sender_role}</span>
                            </div>
                            <p className="font-medium text-gray-800 text-sm truncate">{announcement.title}</p>
                            <p className="text-gray-600 text-xs truncate">{announcement.content.substring(0, 60)}...</p>
                            <span className="text-xs text-gray-400">{formatDate(announcement.created_at)}</span>
                          </div>
                          {!announcement.is_read && <div className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0" />}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

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

      {forceLogout && (
        <div
          className="fixed inset-0 bg-black/60 flex items-center justify-center z-[100] p-4"
          data-testid="force-logout-notice-modal"
        >
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-red-100 rounded-lg flex-shrink-0">
                <ShieldAlert size={28} className="text-red-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900">Sessão encerrada</h3>
                <p className="text-sm text-gray-600 mt-1">{forceLogout.message}</p>
              </div>
            </div>
            <p className="text-xs text-gray-500 mb-4 bg-gray-50 rounded-lg p-3">
              Por motivos de segurança, você precisará fazer login novamente para continuar.
            </p>
            <div className="flex justify-end">
              <button
                onClick={() => {
                  setForceLogout(null);
                  try {
                    localStorage.removeItem('accessToken');
                    localStorage.removeItem('refreshToken');
                    localStorage.removeItem('userData');
                    localStorage.removeItem('lastActivityTime');
                  } catch (e) {
                    // ignora
                  }
                  window.location.replace('/login');
                }}
                data-testid="force-logout-notice-confirm"
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700"
              >
                Ir para o login
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
