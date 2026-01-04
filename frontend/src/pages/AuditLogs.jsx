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
  students: 'Alunos',
  grades: 'Notas',
  attendance: 'Frequência',
  staff: 'Servidores',
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
  
  // Filtros
  const [filters, setFilters] = useState({
    action: '',
    collection: '',
    severity: '',
    search: ''
  });

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        skip: page * limit,
        limit: limit
      });
      
      if (filters.action) params.append('action', filters.action);
      if (filters.collection) params.append('collection', filters.collection);
      if (filters.severity) params.append('severity', filters.severity);
      if (filters.search) params.append('search', filters.search);
      
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

  // Verifica permissão
  if (!['admin', 'secretario', 'semed'].includes(user?.role)) {
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
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Shield className="w-7 h-7 text-blue-600" />
              Logs de Auditoria
            </h1>
            <p className="text-gray-500 mt-1">
              Rastreamento de todas as alterações críticas no sistema
            </p>
          </div>
          <Button onClick={() => { fetchLogs(); fetchStats(); }} variant="outline">
            <RefreshCw className="w-4 h-4 mr-2" />
            Atualizar
          </Button>
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
              />
            </div>
            <Select
              value={filters.action || 'all'}
              onValueChange={(value) => setFilters({...filters, action: value === 'all' ? '' : value})}
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Ação" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="login">Login</SelectItem>
                <SelectItem value="create">Criação</SelectItem>
                <SelectItem value="update">Alteração</SelectItem>
                <SelectItem value="delete">Exclusão</SelectItem>
              </SelectContent>
            </Select>
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
                <SelectItem value="students">Alunos</SelectItem>
                <SelectItem value="grades">Notas</SelectItem>
                <SelectItem value="attendance">Frequência</SelectItem>
                <SelectItem value="staff">Servidores</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={filters.severity || 'all'}
              onValueChange={(value) => setFilters({...filters, severity: value === 'all' ? '' : value})}
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Severidade" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="info">Informação</SelectItem>
                <SelectItem value="warning">Aviso</SelectItem>
                <SelectItem value="critical">Crítico</SelectItem>
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
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Severidade</th>
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
                        <td className="px-4 py-3">
                          <div className="flex items-center">
                            <div className="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center">
                              <User className="h-4 w-4 text-gray-500" />
                            </div>
                            <div className="ml-3">
                              <div className="text-sm font-medium text-gray-900">{log.user_name || log.user_email}</div>
                              <div className="text-xs text-gray-500">{log.user_role}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
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
                        <td className="px-4 py-3">
                          <div className="text-sm text-gray-900 max-w-md truncate" title={log.description}>
                            {log.description}
                          </div>
                          {log.school_name && (
                            <div className="text-xs text-gray-500">
                              Escola: {log.school_name}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <Badge className={SEVERITY_COLORS[log.severity]}>
                            {log.severity === 'critical' && <AlertTriangle className="h-3 w-3 mr-1" />}
                            {SEVERITY_LABELS[log.severity] || log.severity}
                          </Badge>
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
