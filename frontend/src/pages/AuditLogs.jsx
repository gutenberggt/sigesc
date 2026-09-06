import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Download,
  Edit,
  FileText,
  FileText as FilePdf,
  Home,
  LogIn,
  Plus,
  RefreshCw,
  Shield,
  Trash2,
  User,
  X
} from 'lucide-react';

import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { useAuth } from '@/contexts/AuthContext';
import { apiFetch, buildFetchAuthHeaders } from '@/services/api';
import { hasRole } from '@/utils/permissions';
import { browserLocalTodayISO } from '@/utils/browserLocalDate';
import { downloadBlob } from '@/utils/downloadBlob';

const API = process.env.REACT_APP_BACKEND_URL;

const ACTION_ICONS = {
  login: LogIn,
  logout: LogIn,
  create: Plus,
  update: Edit,
  delete: Trash2,
  export: Download,
  import: Download
};

const ACTION_LABELS = {
  login: 'Login',
  logout: 'Logout',
  create: 'Criação',
  update: 'Alteração',
  delete: 'Exclusão',
  export: 'Exportação',
  import: 'Importação',
  approve: 'Aprovação',
  reject: 'Rejeição'
};

const COLLECTION_LABELS = {
  users: 'Usuários',
  students: 'Estudantes',
  grades: 'Notas',
  attendance: 'Frequência',
  content_entries: 'Conteúdos',
  staff: 'Servidores(as)',
  schools: 'Escolas',
  classes: 'Turmas',
  courses: 'Componentes',
  enrollments: 'Matrículas',
  school_assignments: 'Lotações',
  teacher_assignments: 'Alocações'
};

async function apiErrorMessage(response, fallback) {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (detail?.message) return detail.message;
    if (body?.message) return body.message;
  } catch (_error) {
    // O status HTTP continua sendo exibido abaixo.
  }
  return `${fallback} (HTTP ${response.status})`;
}

export const AuditLogs = () => {
  const navigate = useNavigate();
  const { accessToken: token, user } = useAuth();

  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [statsError, setStatsError] = useState('');
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [users, setUsers] = useState([]);
  const [userQuery, setUserQuery] = useState('');
  const [showUserSuggestions, setShowUserSuggestions] = useState(false);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  const [filters, setFilters] = useState({
    collection: '',
    search: '',
    user_id: ''
  });

  const fetchLogs = async () => {
    setLoading(true);
    setLoadError('');
    try {
      const params = new URLSearchParams({
        skip: String(page * limit),
        limit: String(limit)
      });
      if (filters.collection) params.append('collection', filters.collection);
      if (filters.search) params.append('search', filters.search);
      if (filters.user_id) params.append('user_id', filters.user_id);

      // MT-1: apiFetch injeta Authorization, cookie e X-Mantenedora-Id no
      // momento da chamada. Não montar headers manualmente nesta tela.
      const response = await apiFetch(`${API}/api/audit-logs?${params}`);
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response, 'Não foi possível carregar a auditoria'));
      }

      const data = await response.json();
      setLogs(Array.isArray(data.items) ? data.items : []);
      setTotal(Number(data.total || 0));
    } catch (error) {
      console.error('Erro ao buscar logs:', error);
      setLogs([]);
      setTotal(0);
      setLoadError(error?.message || 'Não foi possível carregar os logs de auditoria.');
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await apiFetch(`${API}/api/users`);
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response, 'Não foi possível carregar usuários'));
      }
      const data = await response.json();
      const sortedUsers = (data.users || data || [])
        .slice()
        .sort((a, b) =>
          (a.full_name || a.email || '').localeCompare(b.full_name || b.email || '')
        );
      setUsers(sortedUsers);
    } catch (error) {
      console.error('Erro ao buscar usuários da auditoria:', error);
      setUsers([]);
    }
  };

  const fetchStats = async () => {
    setStatsError('');
    try {
      const response = await apiFetch(`${API}/api/audit-logs/stats?days=7`);
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response, 'Não foi possível carregar as estatísticas'));
      }
      setStats(await response.json());
    } catch (error) {
      console.error('Erro ao buscar estatísticas:', error);
      setStats(null);
      setStatsError(error?.message || 'Estatísticas de auditoria indisponíveis.');
    }
  };

  useEffect(() => {
    if (token) {
      fetchLogs();
      fetchStats();
      fetchUsers();
    }
    // Mantém a semântica anterior: filtros e paginação recarregam a visão.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, page, filters]);

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const totalPages = Math.ceil(total / limit);
  const userSuggestions = userQuery.trim().length >= 3
    ? users.filter((candidate) => {
        const query = userQuery.trim().toLowerCase();
        return (
          (candidate.full_name || '').toLowerCase().includes(query)
          || (candidate.email || '').toLowerCase().includes(query)
        );
      }).slice(0, 8)
    : [];

  const selectUser = (candidate) => {
    setFilters((current) => ({ ...current, user_id: candidate.id }));
    setUserQuery(candidate.full_name || candidate.email || '');
    setShowUserSuggestions(false);
    setPage(0);
  };

  const clearUser = () => {
    setFilters((current) => ({ ...current, user_id: '' }));
    setUserQuery('');
    setShowUserSuggestions(false);
    setPage(0);
  };

  const handleGeneratePdf = async () => {
    try {
      setGeneratingPdf(true);
      const params = new URLSearchParams();
      if (filters.collection) params.append('collection', filters.collection);
      if (filters.search) params.append('search', filters.search);
      if (filters.user_id) params.append('user_id', filters.user_id);
      const filename = `logs_auditoria_${browserLocalTodayISO()}.pdf`;

      // downloadBlob é fetch nativo; portanto recebe explicitamente o helper
      // canônico de auth/tenant em vez de somente Authorization.
      await downloadBlob(
        `${API}/api/audit-logs/pdf?${params}`,
        filename,
        buildFetchAuthHeaders('GET')
      );
    } catch (error) {
      console.error('Erro ao gerar PDF:', error);
      alert(error?.message || 'Não foi possível gerar o PDF. Tente novamente.');
    } finally {
      setGeneratingPdf(false);
    }
  };

  const refreshAll = () => {
    fetchLogs();
    fetchStats();
    fetchUsers();
  };

  if (!hasRole(user, ['admin', 'admin_teste', 'secretario', 'semed'])) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <Shield className="w-16 h-16 mx-auto text-gray-400 mb-4" />
            <h2 className="text-xl font-semibold text-gray-700">Acesso Restrito</h2>
            <p className="text-gray-500 mt-2">
              Você não tem permissão para visualizar os logs de auditoria.
            </p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
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
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <Shield className="w-7 h-7 text-blue-600" />
                Logs de Auditoria
              </h1>
              <p className="text-gray-500 mt-1">
                Rastreamento de todas as alterações críticas no sistema
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={handleGeneratePdf}
              disabled={generatingPdf || Boolean(loadError)}
              data-testid="audit-generate-pdf-button"
            >
              <FilePdf className="w-4 h-4 mr-2" />
              {generatingPdf ? 'Gerando...' : 'Gerar PDF'}
            </Button>
            <Button onClick={refreshAll} variant="outline">
              <RefreshCw className="w-4 h-4 mr-2" />
              Atualizar
            </Button>
          </div>
        </div>

        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Total (7 dias)</div>
              <div className="text-2xl font-bold text-gray-900">{stats.total_events}</div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Ação mais comum</div>
              <div className="text-2xl font-bold text-gray-900">
                {stats.by_action?.[0]?._id
                  ? ACTION_LABELS[stats.by_action[0]._id] || stats.by_action[0]._id
                  : '-'}
              </div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Coleção mais afetada</div>
              <div className="text-2xl font-bold text-gray-900">
                {stats.by_collection?.[0]?._id
                  ? COLLECTION_LABELS[stats.by_collection[0]._id] || stats.by_collection[0]._id
                  : '-'}
              </div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Eventos críticos</div>
              <div className="text-2xl font-bold text-red-600">
                {stats.by_severity?.find((item) => item._id === 'critical')?.count || 0}
              </div>
            </div>
          </div>
        )}

        {statsError && !loadError && (
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <AlertTriangle className="h-5 w-5 flex-shrink-0" />
            <span>{statsError}</span>
          </div>
        )}

        <div className="bg-white rounded-lg shadow-sm border p-4">
          <div className="flex flex-wrap gap-4">
            <div className="flex-1 min-w-[200px]">
              <Input
                placeholder="Buscar na descrição..."
                value={filters.search}
                onChange={(event) => {
                  setFilters((current) => ({ ...current, search: event.target.value }));
                  setPage(0);
                }}
                className="w-full"
                data-testid="audit-search-input"
              />
            </div>

            <div className="relative w-[260px]">
              <div className="relative">
                <User className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  placeholder="Buscar por usuário..."
                  value={userQuery}
                  onChange={(event) => {
                    setUserQuery(event.target.value);
                    setShowUserSuggestions(true);
                    if (filters.user_id) {
                      setFilters((current) => ({ ...current, user_id: '' }));
                    }
                  }}
                  onFocus={() => setShowUserSuggestions(true)}
                  onBlur={() => setTimeout(() => setShowUserSuggestions(false), 150)}
                  className="w-full pl-8 pr-8"
                  data-testid="audit-user-search-input"
                />
                {userQuery && (
                  <button
                    type="button"
                    onClick={clearUser}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    data-testid="audit-user-clear-button"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>

              {showUserSuggestions && userQuery.trim().length >= 3 && (
                <div
                  className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-64 overflow-auto"
                  data-testid="audit-user-suggestions"
                >
                  {userSuggestions.length > 0 ? (
                    userSuggestions.map((candidate) => (
                      <button
                        key={candidate.id}
                        type="button"
                        onMouseDown={() => selectUser(candidate)}
                        className="w-full text-left px-3 py-2 hover:bg-blue-50 text-sm"
                        data-testid={`audit-user-suggestion-${candidate.id}`}
                      >
                        <div className="font-medium text-gray-900">
                          {candidate.full_name || candidate.email}
                        </div>
                        {candidate.full_name && (
                          <div className="text-xs text-gray-500">{candidate.email}</div>
                        )}
                      </button>
                    ))
                  ) : (
                    <div className="px-3 py-2 text-sm text-gray-500">
                      Nenhum usuário encontrado
                    </div>
                  )}
                </div>
              )}

              {userQuery.trim().length > 0 && userQuery.trim().length < 3 && (
                <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-sm px-3 py-2 text-xs text-gray-400">
                  Digite pelo menos 3 caracteres…
                </div>
              )}
            </div>

            <Select
              value={filters.collection || 'all'}
              onValueChange={(value) => {
                setFilters((current) => ({
                  ...current,
                  collection: value === 'all' ? '' : value
                }));
                setPage(0);
              }}
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Coleção" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="users">Usuários</SelectItem>
                <SelectItem value="students">Estudantes</SelectItem>
                <SelectItem value="grades">Notas</SelectItem>
                <SelectItem value="attendance">Frequência</SelectItem>
                <SelectItem value="content_entries">Conteúdos</SelectItem>
                <SelectItem value="staff">Servidores(as)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          {loading ? (
            <div className="p-8 text-center">
              <RefreshCw className="w-8 h-8 mx-auto text-gray-400 animate-spin" />
              <p className="text-gray-500 mt-2">Carregando...</p>
            </div>
          ) : loadError ? (
            <div className="p-8 text-center" data-testid="audit-load-error">
              <AlertTriangle className="w-9 h-9 mx-auto text-red-500" />
              <p className="font-medium text-red-700 mt-3">Falha ao carregar a auditoria</p>
              <p className="text-sm text-gray-600 mt-1 max-w-xl mx-auto">{loadError}</p>
              <Button variant="outline" className="mt-4" onClick={refreshAll}>
                <RefreshCw className="w-4 h-4 mr-2" />
                Tentar novamente
              </Button>
            </div>
          ) : logs.length === 0 ? (
            <div className="p-8 text-center">
              <FileText className="w-8 h-8 mx-auto text-gray-400" />
              <p className="text-gray-500 mt-2">Nenhum log encontrado</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data/Hora</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Usuário</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Ação</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Descrição</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tempo</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {logs.map((log, index) => {
                    const ActionIcon = ACTION_ICONS[log.action] || FileText;
                    return (
                      <tr key={`${log.timestamp || 'log'}-${index}`} className="hover:bg-gray-50">
                        <td className="px-4 py-3 whitespace-nowrap align-top">
                          <div className="text-sm text-gray-900">
                            {formatDate(log.timestamp_local || log.timestamp)}
                          </div>
                          <div className="text-xs text-gray-500">{log.ip_address}</div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex items-start">
                            <div className="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                              <User className="h-4 w-4 text-gray-500" />
                            </div>
                            <div className="ml-3 min-w-0 max-w-[220px]">
                              <div
                                className="text-sm font-medium text-gray-900 whitespace-normal break-words"
                                data-testid="audit-user-cell"
                              >
                                {log.user_name || log.user_email || '-'}
                              </div>
                              <div className="text-xs text-gray-500 whitespace-normal break-words">
                                {log.user_role}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap align-top">
                          <div className="flex items-center gap-2">
                            <ActionIcon className="h-4 w-4 text-gray-400" />
                            <span className="text-sm">{ACTION_LABELS[log.action] || log.action}</span>
                          </div>
                          <div className="text-xs text-gray-500">
                            {COLLECTION_LABELS[log.collection] || log.collection}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div
                            className="text-sm text-gray-900 max-w-md whitespace-normal break-words"
                            title={log.description}
                            data-testid="audit-description-cell"
                          >
                            {log.description}
                          </div>
                          {log.school_name && (
                            <div className="text-xs text-gray-500">Escola: {log.school_name}</div>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap" data-testid="audit-tempo-cell">
                          {Number.isInteger(log.tempo_dias) ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700">
                              {log.tempo_dias} {log.tempo_dias === 1 ? 'dia' : 'dias'}
                            </span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {!loadError && totalPages > 1 && (
            <div className="px-4 py-3 border-t flex items-center justify-between">
              <div className="text-sm text-gray-500">
                Mostrando {page * limit + 1} a {Math.min((page + 1) * limit, total)} de {total}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((current) => Math.max(0, current - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((current) => current + 1)}
                  disabled={page >= totalPages - 1}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
};

export default AuditLogs;
