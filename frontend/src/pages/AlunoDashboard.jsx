import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import axios from 'axios';
import {
  GraduationCap, FileText, ArrowRight, Calendar, Megaphone,
  Clock, Sparkles, ChevronRight, UserCircle
} from 'lucide-react';
import { Layout } from '@/components/Layout';
import { Card, CardContent } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EVENT_TYPE_LABEL = {
  feriado_nacional: { label: 'Feriado Nacional', color: 'bg-red-100 text-red-700' },
  feriado_estadual: { label: 'Feriado Estadual', color: 'bg-orange-100 text-orange-700' },
  feriado_municipal: { label: 'Feriado Municipal', color: 'bg-amber-100 text-amber-700' },
  sabado_letivo: { label: 'Sábado Letivo', color: 'bg-blue-100 text-blue-700' },
  recesso_escolar: { label: 'Recesso', color: 'bg-purple-100 text-purple-700' },
  evento_escolar: { label: 'Evento Escolar', color: 'bg-green-100 text-green-700' },
  outros: { label: 'Evento', color: 'bg-gray-100 text-gray-700' },
};

const formatDatePt = (iso) => {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
};

const formatDateTimePt = (iso) => {
  if (!iso) return '';
  try {
    const dt = new Date(iso);
    return dt.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
};

const dayDelta = (iso) => {
  if (!iso) return 0;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const [y, m, d] = iso.split('-').map(Number);
  const target = new Date(y, m - 1, d);
  return Math.round((target - today) / 86400000);
};

const relativeDay = (iso) => {
  const d = dayDelta(iso);
  if (d === 0) return 'Hoje';
  if (d === 1) return 'Amanhã';
  if (d > 1 && d < 7) return `em ${d} dias`;
  return formatDatePt(iso);
};

export default function AlunoDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [announcements, setAnnouncements] = useState([]);
  const [loadingE, setLoadingE] = useState(true);
  const [loadingA, setLoadingA] = useState(true);
  const [me, setMe] = useState(null);

  useEffect(() => {
    axios.get(`${API}/student/me`).then((r) => setMe(r.data)).catch(() => setMe(null));
    axios.get(`${API}/student/me/upcoming-events?limit=5`)
      .then((r) => setEvents(r.data?.events || []))
      .catch(() => setEvents([]))
      .finally(() => setLoadingE(false));
    axios.get(`${API}/student/me/announcements?limit=5`)
      .then((r) => setAnnouncements(r.data?.announcements || []))
      .catch(() => setAnnouncements([]))
      .finally(() => setLoadingA(false));
  }, []);

  const unreadCount = announcements.filter((a) => !a.is_read).length;

  // Iniciais para avatar fallback (sem foto)
  const fullName = me?.full_name || user?.full_name || 'Aluno(a)';
  const initials = fullName
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() || '')
    .join('') || 'A';
  const firstName = fullName.split(' ')[0] || 'Aluno(a)';

  return (
    <Layout>
      <div className="max-w-5xl mx-auto space-y-6" data-testid="aluno-dashboard">
        {/* Saudação + identidade do aluno */}
        <Card className="border-2 border-blue-100 bg-gradient-to-br from-blue-50 to-indigo-50">
          <CardContent className="p-6 flex items-center gap-4">
            {me?.photo_url ? (
              <img
                src={me.photo_url}
                alt={fullName}
                className="w-14 h-14 rounded-full object-cover shadow-md ring-2 ring-white shrink-0"
                data-testid="aluno-avatar-photo"
              />
            ) : (
              <div
                className="w-14 h-14 rounded-full bg-blue-600 flex items-center justify-center shrink-0 shadow-md text-white font-bold text-lg"
                data-testid="aluno-avatar-initials"
                aria-label={`Avatar de ${fullName}`}
              >
                {initials}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-bold text-gray-900 truncate" data-testid="aluno-greeting-name">
                Olá, {firstName}!
              </h1>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600 mt-0.5">
                {me?.registration_number && (
                  <span data-testid="aluno-matricula">
                    <span className="text-gray-500">Matrícula:</span>{' '}
                    <span className="font-semibold text-gray-800">{me.registration_number}</span>
                  </span>
                )}
                {me?.class_name && (
                  <span className="flex items-center gap-1" data-testid="aluno-turma">
                    <GraduationCap className="w-3 h-3 text-blue-600" />
                    <span className="font-medium text-gray-800">{me.class_name}</span>
                  </span>
                )}
                {me?.school_name && (
                  <span className="text-gray-500 truncate max-w-[18rem]" data-testid="aluno-escola">
                    {me.school_name}
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <p className="text-xs text-blue-700 font-medium mt-1.5">
                  Você tem {unreadCount} aviso{unreadCount > 1 ? 's' : ''} não lido{unreadCount > 1 ? 's' : ''}.
                </p>
              )}
            </div>
            <Sparkles className="w-5 h-5 text-blue-400 hidden md:block" />
          </CardContent>
        </Card>

        {/* Ações principais: Boletim + Meu Perfil */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button
            onClick={() => navigate('/aluno/boletim')}
            className="w-full text-left group"
            data-testid="btn-boletim"
          >
            <Card className="h-full hover:border-blue-500 hover:shadow-lg transition-all cursor-pointer">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-lg bg-blue-600 flex items-center justify-center shrink-0">
                      <FileText className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-gray-900">Boletim</h2>
                      <p className="text-xs text-gray-500">Notas, faltas e situação</p>
                    </div>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-blue-600 group-hover:translate-x-1 transition-all" />
                </div>
              </CardContent>
            </Card>
          </button>

          <button
            onClick={() => navigate('/profile')}
            className="w-full text-left group"
            data-testid="btn-meu-perfil"
          >
            <Card className="h-full hover:border-emerald-500 hover:shadow-lg transition-all cursor-pointer">
              <CardContent className="p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-lg bg-emerald-600 flex items-center justify-center shrink-0">
                      <UserCircle className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <h2 className="text-lg font-bold text-gray-900">Meu Perfil</h2>
                      <p className="text-xs text-gray-500">Dados, e-mail e senha</p>
                    </div>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400 group-hover:text-emerald-600 group-hover:translate-x-1 transition-all" />
                </div>
              </CardContent>
            </Card>
          </button>
        </div>

        {/* Grid de cards secundários */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Próximos eventos */}
          <Card data-testid="card-eventos">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Calendar className="w-5 h-5 text-indigo-600" />
                  <h3 className="font-semibold text-gray-900">Próximos Eventos</h3>
                </div>
                <span className="text-xs text-gray-400">{events.length}</span>
              </div>
              {loadingE ? (
                <div className="text-center text-xs text-gray-400 py-6">Carregando…</div>
              ) : events.length === 0 ? (
                <div className="text-center py-6">
                  <Clock className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                  <p className="text-xs text-gray-500">Nenhum evento futuro no calendário.</p>
                </div>
              ) : (
                <ul className="space-y-2">
                  {events.map((ev) => {
                    const meta = EVENT_TYPE_LABEL[ev.event_type] || EVENT_TYPE_LABEL.outros;
                    return (
                      <li key={ev.id} className="flex items-start gap-3 py-1.5 border-b last:border-0 border-gray-100">
                        <div className="shrink-0 w-12 text-center">
                          <div className="text-[10px] uppercase text-gray-500 leading-none">
                            {relativeDay(ev.start_date)}
                          </div>
                          <div className="text-lg font-bold text-gray-800 leading-tight mt-0.5">
                            {ev.start_date?.split('-')[2]}
                          </div>
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-800 truncate">{ev.name}</p>
                          <span className={`inline-block text-[10px] px-2 py-0.5 rounded-full ${meta.color} mt-0.5`}>
                            {meta.label}
                          </span>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          {/* Avisos da escola */}
          <Card data-testid="card-avisos">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Megaphone className="w-5 h-5 text-emerald-600" />
                  <h3 className="font-semibold text-gray-900">Avisos</h3>
                </div>
                {unreadCount > 0 && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-500 text-white">
                    {unreadCount} novo{unreadCount > 1 ? 's' : ''}
                  </span>
                )}
              </div>
              {loadingA ? (
                <div className="text-center text-xs text-gray-400 py-6">Carregando…</div>
              ) : announcements.length === 0 ? (
                <div className="text-center py-6">
                  <Megaphone className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                  <p className="text-xs text-gray-500">Nenhum aviso no momento.</p>
                </div>
              ) : (
                <ul className="space-y-2">
                  {announcements.map((a) => (
                    <li
                      key={a.id}
                      className={`flex items-start gap-2 py-2 border-b last:border-0 border-gray-100 ${
                        !a.is_read ? 'bg-blue-50/40 -mx-2 px-2 rounded' : ''
                      }`}
                    >
                      <div className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${!a.is_read ? 'bg-blue-500' : 'bg-gray-200'}`} />
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm truncate ${!a.is_read ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
                          {a.title}
                        </p>
                        <p className="text-[11px] text-gray-500 truncate">
                          {a.sender_name} · {formatDateTimePt(a.created_at)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <Link
                to="/comunicacao"
                className="text-xs text-emerald-700 hover:underline flex items-center gap-1 mt-3 justify-end"
                data-testid="link-ver-todos-avisos"
              >
                Ver todos <ChevronRight className="w-3 h-3" />
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
