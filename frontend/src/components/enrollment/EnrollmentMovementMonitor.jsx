import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  ArrowRightLeft,
  RefreshCw,
  Shuffle,
  Trash2,
  UserPlus,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

const API = process.env.REACT_APP_BACKEND_URL;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100, 'all'];

const ACTION_META = {
  matricula: {
    label: 'Matrícula',
    plural: 'Matrículas',
    icon: UserPlus,
    card: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-100',
  },
  transferencia: {
    label: 'Transferência',
    plural: 'Transferências',
    icon: ArrowRightLeft,
    card: 'border-blue-200 bg-blue-50 text-blue-700',
    badge: 'bg-blue-100 text-blue-700 hover:bg-blue-100',
  },
  remanejamento: {
    label: 'Remanejamento',
    plural: 'Remanejamentos',
    icon: Shuffle,
    card: 'border-violet-200 bg-violet-50 text-violet-700',
    badge: 'bg-violet-100 text-violet-700 hover:bg-violet-100',
  },
  exclusao: {
    label: 'Exclusão',
    plural: 'Exclusões',
    icon: Trash2,
    card: 'border-red-200 bg-red-50 text-red-700',
    badge: 'bg-red-100 text-red-700 hover:bg-red-100',
  },
};

const getArray = (value) => {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.data)) return value.data;
  return [];
};

const compact = (value) => String(value || '').trim();

const authHeaders = (token) => {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const tenant = localStorage.getItem('activeMantenedoraId');
  if (tenant) headers['X-Mantenedora-Id'] = tenant;
  return headers;
};

const fetchJson = async (url, token) => {
  const response = await fetch(url, {
    headers: authHeaders(token),
    credentials: 'include',
  });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
};

const fetchAllAuditLogs = async (params, token) => {
  const qs = new URLSearchParams({ ...params, skip: '0', limit: '1' });
  const first = await fetchJson(`${API}/api/audit-logs?${qs.toString()}`, token);
  const total = Number(first?.total || 0);
  if (!total) return [];
  qs.set('limit', String(total));
  const full = await fetchJson(`${API}/api/audit-logs?${qs.toString()}`, token);
  return getArray(full);
};

const parseStudentName = (log) => {
  const direct = compact(log?.new_value?.full_name || log?.old_value?.full_name);
  if (direct) return direct;
  const description = compact(log?.description);
  const patterns = [
    /(?:cadastrou|atualizou|excluiu)\s+aluno:\s*(.+?)(?:\s+-\s+|\s+\(CPF:|$)/i, // nomenclature-allow: leitura de logs históricos legados
    /(?:aluno|estudante)\s+(.+?)(?:\s+-\s+|$)/i, // nomenclature-allow: leitura de logs históricos legados
  ];
  for (const pattern of patterns) {
    const match = description.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return log?.document_id ? `Estudante ${String(log.document_id).slice(0, 8)}…` : '—';
};

const actionType = (log) => compact(log?.extra_data?.action_type).toLowerCase();

const classifyLog = (log) => {
  const type = actionType(log);
  if (compact(log?.action).toLowerCase() === 'delete') return 'exclusao';
  if (type === 'remanejamento') return 'remanejamento';
  if (type.startsWith('transferencia')) return 'transferencia';
  if (type === 'matricula') return 'matricula';
  if (compact(log?.action).toLowerCase() === 'create' && compact(log?.new_value?.class_id)) return 'matricula';
  return null;
};

const dedupeLogs = (logs) => {
  const seen = new Set();
  return logs.filter((log) => {
    const key = [
      log?.document_id,
      log?.timestamp_local || log?.timestamp,
      log?.action,
      actionType(log),
      log?.description,
    ].join('|');
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

const normalizeDate = (value) => {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const formatDate = (value) => {
  const parsed = normalizeDate(value);
  if (!parsed) return '—';
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(parsed);
};

const nameById = (map, id, fallback = '—') => {
  const key = compact(id);
  if (!key) return fallback;
  return map[key] || fallback;
};

const MonitorStatCard = ({ action, value }) => {
  const meta = ACTION_META[action];
  const Icon = meta.icon;
  return (
    <Card className={`border ${meta.card}`} data-testid={`movement-stat-${action}`}>
      <CardContent className="p-4 flex items-center gap-3">
        <div className="p-2.5 rounded-xl bg-white/70 border border-current/10">
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-2xl font-bold leading-none">{value}</p>
          <p className="text-sm font-medium mt-1 opacity-80">{meta.plural}</p>
        </div>
      </CardContent>
    </Card>
  );
};

export const EnrollmentMovementMonitor = ({ token }) => {
  const [rawLogs, setRawLogs] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [schoolFilter, setSchoolFilter] = useState('all');
  const [actionFilter, setActionFilter] = useState('all');
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  const loadMonitor = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [created, enrolled, transfers, relocations, deleted, schoolsData, classesData] = await Promise.all([
        fetchAllAuditLogs({ collection: 'students', action: 'create' }, token),
        fetchAllAuditLogs({ collection: 'students', search: 'matricula' }, token),
        fetchAllAuditLogs({ collection: 'students', search: 'transferencia' }, token),
        fetchAllAuditLogs({ collection: 'students', search: 'remanejamento' }, token),
        fetchAllAuditLogs({ collection: 'students', action: 'delete' }, token),
        fetchJson(`${API}/api/schools`, token).catch(() => []),
        fetchJson(`${API}/api/classes`, token).catch(() => []),
      ]);

      setRawLogs(dedupeLogs([...created, ...enrolled, ...transfers, ...relocations, ...deleted]));
      setSchools(getArray(schoolsData));
      setClasses(getArray(classesData));
    } catch (e) {
      setError(
        e?.status === 403
          ? 'Seu perfil não possui permissão para consultar os logs de auditoria.'
          : 'Não foi possível carregar o monitor de movimentações.'
      );
      setRawLogs([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadMonitor();
  }, [loadMonitor]);

  const schoolMap = useMemo(() => {
    const map = {};
    schools.forEach((school) => {
      if (school?.id) map[school.id] = school.name || school.nome || school.id;
    });
    rawLogs.forEach((log) => {
      if (log?.school_id && log?.school_name && !map[log.school_id]) map[log.school_id] = log.school_name;
    });
    return map;
  }, [schools, rawLogs]);

  const classMap = useMemo(() => {
    const map = {};
    classes.forEach((item) => {
      if (item?.id) map[item.id] = item.name || item.nome || item.id;
    });
    return map;
  }, [classes]);

  const events = useMemo(() => rawLogs
    .map((log) => {
      const action = classifyLog(log);
      if (!action) return null;

      const oldSchoolId = compact(log?.old_value?.school_id);
      const newSchoolId = compact(log?.new_value?.school_id || log?.school_id);
      const oldClassId = compact(log?.old_value?.class_id);
      const newClassId = compact(log?.new_value?.class_id);
      const isInternalTransfer = action === 'transferencia' && oldSchoolId && newSchoolId && oldSchoolId !== newSchoolId;

      let schoolText = nameById(schoolMap, newSchoolId, compact(log?.school_name) || '—');
      if (isInternalTransfer) {
        schoolText = `${nameById(schoolMap, oldSchoolId, oldSchoolId)}\npara\n${nameById(schoolMap, newSchoolId, compact(log?.school_name) || newSchoolId)}`;
      }

      let classText = nameById(classMap, newClassId, newClassId || '—');
      if (action === 'remanejamento' && oldClassId && newClassId && oldClassId !== newClassId) {
        classText = `${nameById(classMap, oldClassId, oldClassId)}\npara\n${nameById(classMap, newClassId, newClassId)}`;
      } else if (action === 'exclusao') {
        classText = nameById(classMap, oldClassId, oldClassId || '—');
      }

      const schoolIds = [oldSchoolId, newSchoolId, compact(log?.school_id)].filter(Boolean);
      return {
        key: [log?.document_id, log?.timestamp_local || log?.timestamp, action, actionType(log)].join('|'),
        action,
        student: parseStudentName(log),
        date: log?.timestamp_local || log?.timestamp,
        schoolText,
        classText,
        executor: compact(log?.user_name || log?.user_email) || '—',
        schoolIds: [...new Set(schoolIds)],
      };
    })
    .filter(Boolean)
    .sort((a, b) => (normalizeDate(b.date)?.getTime() || 0) - (normalizeDate(a.date)?.getTime() || 0)),
  [rawLogs, schoolMap, classMap]);

  const counts = useMemo(() => ({
    matricula: events.filter((e) => e.action === 'matricula').length,
    transferencia: events.filter((e) => e.action === 'transferencia').length,
    remanejamento: events.filter((e) => e.action === 'remanejamento').length,
    exclusao: events.filter((e) => e.action === 'exclusao').length,
  }), [events]);

  const schoolOptions = useMemo(() => {
    const ids = new Set();
    events.forEach((event) => event.schoolIds.forEach((id) => ids.add(id)));
    return [...ids]
      .map((id) => ({ id, name: nameById(schoolMap, id, id) }))
      .sort((a, b) => a.name.localeCompare(b.name, 'pt-BR'));
  }, [events, schoolMap]);

  const filteredEvents = useMemo(() => events.filter((event) => {
    if (actionFilter !== 'all' && event.action !== actionFilter) return false;
    if (schoolFilter !== 'all' && !event.schoolIds.includes(schoolFilter)) return false;
    return true;
  }), [events, actionFilter, schoolFilter]);

  useEffect(() => {
    setPage(1);
  }, [schoolFilter, actionFilter, pageSize]);

  const isAll = pageSize === 'all';
  const numericPageSize = isAll ? Math.max(filteredEvents.length, 1) : Number(pageSize);
  const totalPages = isAll ? 1 : Math.max(1, Math.ceil(filteredEvents.length / numericPageSize));
  const safePage = Math.min(page, totalPages);
  const start = isAll ? 0 : (safePage - 1) * numericPageSize;
  const visibleEvents = isAll ? filteredEvents : filteredEvents.slice(start, start + numericPageSize);

  return (
    <section className="space-y-4" data-testid="enrollment-movement-monitor">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-600" />
            Monitor de Movimentações de Matrícula
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Matrículas, transferências, remanejamentos e exclusões registradas pela auditoria do SIGESC.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadMonitor} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Atualizar monitor
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <MonitorStatCard action="matricula" value={counts.matricula} />
        <MonitorStatCard action="transferencia" value={counts.transferencia} />
        <MonitorStatCard action="remanejamento" value={counts.remanejamento} />
        <MonitorStatCard action="exclusao" value={counts.exclusao} />
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-4 py-4 border-b border-slate-100 flex flex-wrap items-end gap-3">
          <label className="text-xs font-medium text-slate-600 min-w-[170px]">
            Escola
            <select
              value={schoolFilter}
              onChange={(e) => setSchoolFilter(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="movement-school-filter"
            >
              <option value="all">Todas as escolas</option>
              {schoolOptions.map((school) => (
                <option key={school.id} value={school.id}>{school.name}</option>
              ))}
            </select>
          </label>

          <label className="text-xs font-medium text-slate-600 min-w-[170px]">
            Ação
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="movement-action-filter"
            >
              <option value="all">Todas as ações</option>
              {Object.entries(ACTION_META).map(([key, meta]) => (
                <option key={key} value={key}>{meta.label}</option>
              ))}
            </select>
          </label>

          <label className="text-xs font-medium text-slate-600 min-w-[120px]">
            Visualização
            <select
              value={pageSize}
              onChange={(e) => setPageSize(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              data-testid="movement-page-size"
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>{size === 'all' ? 'Todos' : size}</option>
              ))}
            </select>
          </label>

          <div className="ml-auto text-sm text-slate-500 pb-2">
            {filteredEvents.length} registro(s)
          </div>
        </div>

        {error ? (
          <div className="px-5 py-6 text-sm text-amber-700 bg-amber-50">{error}</div>
        ) : loading && events.length === 0 ? (
          <div className="px-5 py-10 flex items-center justify-center text-slate-400">
            <RefreshCw className="w-5 h-5 animate-spin mr-2" /> Carregando movimentações...
          </div>
        ) : visibleEvents.length === 0 ? (
          <div className="px-5 py-8 text-sm text-slate-500">Nenhuma movimentação encontrada para os filtros selecionados.</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-sm" data-testid="movement-table">
                <thead className="bg-slate-50 text-slate-500 text-xs uppercase">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium w-[23%]">Estudante</th>
                    <th className="text-left px-4 py-3 font-medium w-[13%]">Ação</th>
                    <th className="text-left px-4 py-3 font-medium w-[14%]">Data</th>
                    <th className="text-left px-4 py-3 font-medium w-[19%]">Escola</th>
                    <th className="text-left px-4 py-3 font-medium w-[17%]">Turma</th>
                    <th className="text-left px-4 py-3 font-medium w-[14%]">Executor</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleEvents.map((event) => {
                    const meta = ACTION_META[event.action];
                    return (
                      <tr key={event.key} className="border-t border-slate-100 hover:bg-slate-50/60">
                        <td className="px-4 py-3 align-top whitespace-pre-line break-words text-slate-800 font-medium">{event.student}</td>
                        <td className="px-4 py-3 align-top whitespace-normal break-words">
                          <Badge className={meta.badge}>{meta.label}</Badge>
                        </td>
                        <td className="px-4 py-3 align-top whitespace-normal break-words text-slate-600">{formatDate(event.date)}</td>
                        <td className="px-4 py-3 align-top whitespace-pre-line break-words text-slate-600">{event.schoolText}</td>
                        <td className="px-4 py-3 align-top whitespace-pre-line break-words text-slate-600">{event.classText}</td>
                        <td className="px-4 py-3 align-top whitespace-normal break-words text-slate-600">{event.executor}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {!isAll && totalPages > 1 && (
              <div className="px-4 py-3 border-t border-slate-100 flex items-center justify-between gap-3 flex-wrap">
                <span className="text-xs text-slate-500">
                  Página {safePage} de {totalPages} · exibindo {start + 1}–{Math.min(start + numericPageSize, filteredEvents.length)} de {filteredEvents.length}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={safePage <= 1}
                  >
                    <ArrowLeft className="w-4 h-4 mr-1" /> Anterior
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={safePage >= totalPages}
                  >
                    Próxima <ArrowRight className="w-4 h-4 ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
};

export default EnrollmentMovementMonitor;