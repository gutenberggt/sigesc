import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { 
  Shield, 
  Search, 
  Filter, 
  RefreshCw, 
  AlertTriangle,
  User,
  Calendar,
  FileText,
  LogIn,
  Edit,
  Trash2,
  Plus,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText as FilePdf,
  X,
  Home
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/contexts/AuthContext';
import { hasRole } from '@/utils/permissions';
import { downloadBlob } from '@/utils/downloadBlob';

const API = process.env.REACT_APP_BACKEND_URL;

// Ícones por ação
const ACTION_ICONS = {
  login: LogIn,
  logout: LogIn,
  create: Plus,
  update: Edit,
  delete: Trash2,
  export: Download,
  import: Download
};

// Cores por severidade
const SEVERITY_COLORS = {
  info: 'bg-blue-100 text-blue-800',
  warning: 'bg-yellow-100 text-yellow-800',
  critical: 'bg-red-100 text-red-800'
};

// Labels de severidade em português
const SEVERITY_LABELS = {
  info: 'Informação',
  warning: 'Aviso',
  critical: 'Crítico'
};

// Labels legíveis
const ACTION_LABELS = {
  login: 'Login',
  logout: 'Logout',
  create: 'Criação',
  update: 'Alteração',
  delete: 'Exclusão',
  export: 'Exportação',
  import: 'Importação'
};

const COLLECTION_LABELS = {
  users: 'Usuários',
  students: 'Estudantes',
  grades: 'Notas',
  attendance: 'Frequência',
  staff: 'Servidores(as)',
  schools: 'Escolas',
  classes: 'Turmas',
  courses: 'Componentes',
  enrollments: 'Matrículas',
  school_assignments: 'Lotações',
  teacher_assignments: 'Alocações'
};

export const AuditLogs = () => {
  const navigate = useNavigate();
  const { accessToken: token, user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [limit] = useState(20);
  const [users, setUsers] = useState([]);
  const [userQuery, setUserQuery] = useState(''); // texto digitado no "Buscar por Usuário"
  const [showUserSuggestions, setShowUserSuggestions] = useState(false);
  const [generatingPdf, setGeneratingPdf] = useState(false);
  
  // Filtros
  const [filters, setFilters] = useState({
    collection: '',
    search: '',
    user_id: ''
  });

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        skip: page * limit,
        limit: limit
      });
      
      if (filters.collection) params.append('collection', filters.collection);
      if (filters.search) params.append('search', filters.search);
      if (filters.user_id) params.append('user_id', filters.user_id);
      
      const response = await fetch(`${API}/api/audit-logs?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setLogs(data.items);
        setTotal(data.total);
      }
    } catch (error) {
      console.error('Erro ao buscar logs:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await fetch(`${API}/api/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Ordenar por nome
        const sortedUsers = (data.users || data || []).sort((a, b) => 
          (a.full_name || a.email || '').localeCompare(b.full_name || b.email || '')
        );
        setUsers(sortedUsers);
      }
    } catch (error) {
      console.error('Erro ao buscar usuários:', error);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API}/api/audit-logs/stats?days=7`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Erro ao buscar estatísticas:', error);
    }
  };

  useEffect(() => {
    if (token) {
      fetchLogs();
      fetchStats();
      fetchUsers();
    }
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

  // Sugestões de usuário (a partir do 3º caractere), filtrando pela lista já carregada
  const userSuggestions = userQuery.trim().length >= 3
    ? users.filter(u => {
        const q = userQuery.trim().toLowerCase();
        return (u.full_name || '').toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q);
      }).slice(0, 8)
    : [];

  const selectUser = (u) => {
    setFilters({ ...filters, user_id: u.id });
    setUserQuery(u.full_name || u.email || '');
    setShowUserSuggestions(false);
    setPage(0);
  };

  const clearUser = () => {
    setFilters({ ...filters, user_id: '' });
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
      const filename = `logs_auditoria_${new Date().toISOString().slice(0, 10)}.pdf`;
      await downloadBlob(`${API}/api/audit-logs/pdf?${params}`, filename, {
        Authorization: token ? `Bearer ${token}` : ''
      });
    } catch (e) {
      console.error('Erro ao gerar PDF:', e);
      alert('Não foi possível gerar o PDF. Tente novamente.');
    } finally {
      setGeneratingPdf(false);
    }
  };

  // Verifica permissão
  if (!hasRole(user, ['admin', 'admin_teste', 'secretario', 'semed'])) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <Shield className="w-16 h-16 mx-auto text-gray-400 mb-4" />
            <h2 className="text-xl font-semibold text-gray-700">Acesso Restrito</h2>
            <p className="text-gray-500 mt-2">Você não tem permissão para visualizar os logs de auditoria.</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
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
            <Button onClick={handleGeneratePdf} disabled={generatingPdf} data-testid="audit-generate-pdf-button">
              <FilePdf className="w-4 h-4 mr-2" />
              {generatingPdf ? 'Gerando...' : 'Gerar PDF'}
            </Button>
            <Button onClick={() => { fetchLogs(); fetchStats(); }} variant="outline">
              <RefreshCw className="w-4 h-4 mr-2" />
              Atualizar
            </Button>
          </div>
        </div>

        {/* Estatísticas */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Total (7 dias)</div>
              <div className="text-2xl font-bold text-gray-900">{stats.total_events}</div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Ação mais comum</div>
              <div className="text-2xl font-bold text-gray-900">
                {stats.by_action?.[0]?._id ? ACTION_LABELS[stats.by_action[0]._id] || stats.by_action[0]._id : '-'}
              </div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Coleção mais afetada</div>
              <div className="text-2xl font-bold text-gray-900">
                {stats.by_collection?.[0]?._id ? COLLECTION_LABELS[stats.by_collection[0]._id] || stats.by_collection[0]._id : '-'}
              </div>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-4">
              <div className="text-sm text-gray-500">Eventos críticos</div>
              <div className="text-2xl font-bold text-red-600">
                {stats.by_severity?.find(s => s._id === 'critical')?.count || 0}
              </div>
            </div>
          </div>
        )}

        {/* Filtros */}
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <div className="flex flex-wrap gap-4">
            <div className="flex-1 min-w-[200px]">
              <Input
                placeholder="Buscar na descrição..."
                value={filters.search}
                onChange={(e) => setFilters({...filters, search: e.target.value})}
                className="w-full"
                data-testid="audit-search-input"
              />
            </div>
            {/* Buscar por Usuário — autocomplete a partir do 3º caractere */}
            <div className="relative w-[260px]">
              <div className="relative">
                <User className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  placeholder="Buscar por usuário..."
                  value={userQuery}
                  onChange={(e) => {
                    setUserQuery(e.target.value);
                    setShowUserSuggestions(true);
                    if (filters.user_id) setFilters({ ...filters, user_id: '' });
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
                <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-64 overflow-auto" data-testid="audit-user-suggestions">
                  {userSuggestions.length > 0 ? (
                    userSuggestions.map(u => (
                      <button
                        key={u.id}
                        type="button"
                        onMouseDown={() => selectUser(u)}
                        className="w-full text-left px-3 py-2 hover:bg-blue-50 text-sm"
                        data-testid={`audit-user-suggestion-${u.id}`}
                      >
                        <div className="font-medium text-gray-900">{u.full_name || u.email}</div>
                        {u.full_name && <div className="text-xs text-gray-500">{u.email}</div>}
                      </button>
                    ))
                  ) : (
                    <div className="px-3 py-2 text-sm text-gray-500">Nenhum usuário encontrado</div>
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
              onValueChange={(value) => setFilters({...filters, collection: value === 'all' ? '' : value})}
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

        {/* Tabela de Logs */}
        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          {loading ? (
            <div className="p-8 text-center">
              <RefreshCw className="w-8 h-8 mx-auto text-gray-400 animate-spin" />
              <p className="text-gray-500 mt-2">Carregando...</p>
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
                  {logs.map((log, idx) => {
                    const ActionIcon = ACTION_ICONS[log.action] || FileText;
                    return (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="text-sm text-gray-900">{formatDate(log.timestamp)}</div>
                          <div className="text-xs text-gray-500">{log.ip_address}</div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="flex items-start">
                            <div className="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
                              <User className="h-4 w-4 text-gray-500" />
                            </div>
                            <div className="ml-3 min-w-0 max-w-[220px]">
                              <div className="text-sm font-medium text-gray-900 whitespace-normal break-words" data-testid="audit-user-cell">{log.user_name || log.user_email}</div>
                              <div className="text-xs text-gray-500 whitespace-normal break-words">{log.user_role}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap align-top">
                          <div className="flex items-center gap-2">
                            <ActionIcon className="h-4 w-4 text-gray-400" />
                            <span className="text-sm">
                              {ACTION_LABELS[log.action] || log.action}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500">
                            {COLLECTION_LABELS[log.collection] || log.collection}
                          </div>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="text-sm text-gray-900 max-w-md whitespace-normal break-words" title={log.description} data-testid="audit-description-cell">
                            {log.description}
                          </div>
                          {log.school_name && (
                            <div className="text-xs text-gray-500">
                              Escola: {log.school_name}
                            </div>
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

          {/* Paginação */}
          {totalPages > 1 && (
            <div className="px-4 py-3 border-t flex items-center justify-between">
              <div className="text-sm text-gray-500">
                Mostrando {page * limit + 1} a {Math.min((page + 1) * limit, total)} de {total}
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage(p => p + 1)}
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
