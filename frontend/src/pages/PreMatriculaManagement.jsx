import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Users, Search, Eye, CheckCircle, XCircle, Clock, 
  UserPlus, Filter, ChevronDown, ChevronUp, Phone, 
  Mail, MapPin, Calendar, FileText, AlertCircle,
  Loader2, RefreshCw, UserCheck
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Status possíveis e suas cores
const STATUS_CONFIG = {
  pendente: { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  analisando: { label: 'Em Análise', color: 'bg-blue-100 text-blue-800', icon: Eye },
  aprovada: { label: 'Aprovada', color: 'bg-green-100 text-green-800', icon: CheckCircle },
  rejeitada: { label: 'Rejeitada', color: 'bg-red-100 text-red-800', icon: XCircle },
  convertida: { label: 'Convertida', color: 'bg-purple-100 text-purple-800', icon: UserCheck }
};

// Labels de parentesco
const PARENTESCO_LABELS = {
  mae: 'Mãe',
  pai: 'Pai',
  avo: 'Avô/Avó',
  tio: 'Tio/Tia',
  responsavel: 'Responsável Legal',
  outro: 'Outro'
};

// Labels de nível de ensino
const NIVEL_LABELS = {
  educacao_infantil: 'Educação Infantil',
  fundamental_anos_iniciais: 'Fundamental - Anos Iniciais',
  fundamental_anos_finais: 'Fundamental - Anos Finais',
  ensino_medio: 'Ensino Médio',
  eja: 'EJA'
};

export default function PreMatriculaManagement() {
  const { user, accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [preMatriculas, setPreMatriculas] = useState([]);
  const [schools, setSchools] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [processing, setProcessing] = useState(null);

  // Contadores por status
  const statusCounts = preMatriculas.reduce((acc, pm) => {
    acc[pm.status] = (acc[pm.status] || 0) + 1;
    return acc;
  }, {});

  // Carrega dados iniciais
  useEffect(() => {
    loadSchools();
    loadPreMatriculas();
  }, []);

  // Recarrega quando filtros mudam
  useEffect(() => {
    loadPreMatriculas();
  }, [selectedSchool, selectedStatus]);

  const loadSchools = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/schools`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      setSchools(response.data || []);
    } catch (error) {
      console.error('Erro ao carregar escolas:', error);
    }
  };

  const loadPreMatriculas = async () => {
    setLoading(true);
    try {
      let url = `${API_URL}/api/pre-matriculas`;
      const params = new URLSearchParams();
      
      if (selectedSchool) params.append('school_id', selectedSchool);
      if (selectedStatus) params.append('status_filter', selectedStatus);
      
      if (params.toString()) url += `?${params.toString()}`;
      
      const response = await axios.get(url, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      setPreMatriculas(response.data || []);
    } catch (error) {
      console.error('Erro ao carregar pré-matrículas:', error);
      toast.error('Erro ao carregar pré-matrículas');
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (id, newStatus, rejectionReason = null) => {
    setProcessing(id);
    try {
      let url = `${API_URL}/api/pre-matriculas/${id}/status?new_status=${newStatus}`;
      if (rejectionReason) {
        url += `&rejection_reason=${encodeURIComponent(rejectionReason)}`;
      }
      
      await axios.put(url, {}, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      
      toast.success(`Status atualizado para: ${STATUS_CONFIG[newStatus].label}`);
      loadPreMatriculas();
    } catch (error) {
      console.error('Erro ao atualizar status:', error);
      toast.error('Erro ao atualizar status');
    } finally {
      setProcessing(null);
    }
  };

  const handleApprove = (pm) => {
    if (window.confirm(`Deseja aprovar a pré-matrícula de ${pm.aluno_nome}?`)) {
      updateStatus(pm.id, 'aprovada');
    }
  };

  const handleReject = (pm) => {
    const reason = window.prompt(`Motivo da rejeição da pré-matrícula de ${pm.aluno_nome}:`);
    if (reason !== null) {
      updateStatus(pm.id, 'rejeitada', reason);
    }
  };

  const handleAnalyze = (pm) => {
    updateStatus(pm.id, 'analisando');
  };

  // Filtra por termo de busca
  const filteredPreMatriculas = preMatriculas.filter(pm => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      pm.aluno_nome?.toLowerCase().includes(term) ||
      pm.responsavel_nome?.toLowerCase().includes(term) ||
      pm.responsavel_telefone?.includes(term)
    );
  });

  // Busca nome da escola
  const getSchoolName = (schoolId) => {
    const school = schools.find(s => s.id === schoolId);
    return school?.name || 'Escola não encontrada';
  };

  // Formata data
  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR');
  };

  // Formata data/hora
  const formatDateTime = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('pt-BR');
  };

  return (
    <Layout>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Users className="w-7 h-7 text-blue-600" />
              Gestão de Pré-Matrículas
            </h1>
            <p className="text-gray-600 mt-1">
              Gerencie as solicitações de pré-matrícula recebidas
            </p>
          </div>
          
          <Button onClick={loadPreMatriculas} variant="outline" disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        </div>

        {/* Contadores de Status */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {Object.entries(STATUS_CONFIG).map(([key, config]) => {
            const Icon = config.icon;
            const count = statusCounts[key] || 0;
            return (
              <button
                key={key}
                onClick={() => setSelectedStatus(selectedStatus === key ? '' : key)}
                className={`p-4 rounded-lg border transition-all ${
                  selectedStatus === key 
                    ? 'ring-2 ring-blue-500 border-blue-500' 
                    : 'hover:border-gray-300'
                } ${config.color.replace('text-', 'border-').split(' ')[0]} bg-white`}
              >
                <div className="flex items-center justify-between">
                  <Icon className={`w-5 h-5 ${config.color.split(' ')[1]}`} />
                  <span className="text-2xl font-bold text-gray-900">{count}</span>
                </div>
                <p className="text-sm text-gray-600 mt-1 text-left">{config.label}</p>
              </button>
            );
          })}
        </div>

        {/* Filtros */}
        <div className="bg-white rounded-lg border p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                <Input
                  placeholder="Buscar por nome do aluno, responsável ou telefone..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            
            <select
              value={selectedSchool}
              onChange={(e) => setSelectedSchool(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm min-w-[200px]"
            >
              <option value="">Todas as escolas</option>
              {schools.map(school => (
                <option key={school.id} value={school.id}>{school.name}</option>
              ))}
            </select>
            
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm min-w-[150px]"
            >
              <option value="">Todos os status</option>
              {Object.entries(STATUS_CONFIG).map(([key, config]) => (
                <option key={key} value={key}>{config.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Lista de Pré-Matrículas */}
        <div className="space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
              <span className="ml-2 text-gray-600">Carregando...</span>
            </div>
          ) : filteredPreMatriculas.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-lg border">
              <Users className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-gray-900">Nenhuma pré-matrícula encontrada</h3>
              <p className="text-gray-500 mt-1">
                {searchTerm || selectedSchool || selectedStatus 
                  ? 'Tente ajustar os filtros de busca'
                  : 'As pré-matrículas aparecerão aqui quando forem recebidas'}
              </p>
            </div>
          ) : (
            filteredPreMatriculas.map((pm) => {
              const StatusIcon = STATUS_CONFIG[pm.status]?.icon || Clock;
              const isExpanded = expandedId === pm.id;
              
              return (
                <div 
                  key={pm.id} 
                  className="bg-white rounded-lg border shadow-sm overflow-hidden"
                >
                  {/* Cabeçalho do Card */}
                  <div 
                    className="p-4 cursor-pointer hover:bg-gray-50"
                    onClick={() => setExpandedId(isExpanded ? null : pm.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="font-semibold text-gray-900 truncate">
                            {pm.aluno_nome}
                          </h3>
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_CONFIG[pm.status]?.color}`}>
                            {STATUS_CONFIG[pm.status]?.label}
                          </span>
                        </div>
                        
                        <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
                          <span className="flex items-center gap-1">
                            <Calendar className="w-4 h-4" />
                            {formatDate(pm.aluno_data_nascimento)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Phone className="w-4 h-4" />
                            {pm.responsavel_telefone}
                          </span>
                          <span className="truncate">
                            {getSchoolName(pm.school_id)}
                          </span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2 ml-4">
                        {pm.status === 'pendente' && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={(e) => { e.stopPropagation(); handleAnalyze(pm); }}
                              disabled={processing === pm.id}
                            >
                              <Eye className="w-4 h-4 mr-1" />
                              Analisar
                            </Button>
                          </>
                        )}
                        {(pm.status === 'pendente' || pm.status === 'analisando') && (
                          <>
                            <Button
                              size="sm"
                              className="bg-green-600 hover:bg-green-700"
                              onClick={(e) => { e.stopPropagation(); handleApprove(pm); }}
                              disabled={processing === pm.id}
                            >
                              <CheckCircle className="w-4 h-4 mr-1" />
                              Aprovar
                            </Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={(e) => { e.stopPropagation(); handleReject(pm); }}
                              disabled={processing === pm.id}
                            >
                              <XCircle className="w-4 h-4 mr-1" />
                              Rejeitar
                            </Button>
                          </>
                        )}
                        {isExpanded ? (
                          <ChevronUp className="w-5 h-5 text-gray-400" />
                        ) : (
                          <ChevronDown className="w-5 h-5 text-gray-400" />
                        )}
                      </div>
                    </div>
                  </div>
                  
                  {/* Detalhes Expandidos */}
                  {isExpanded && (
                    <div className="border-t bg-gray-50 p-4">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* Dados do Aluno */}
                        <div>
                          <h4 className="font-medium text-gray-900 mb-3 flex items-center gap-2">
                            <UserPlus className="w-4 h-4 text-blue-600" />
                            Dados do Aluno
                          </h4>
                          <dl className="space-y-2 text-sm">
                            <div>
                              <dt className="text-gray-500">Nome</dt>
                              <dd className="font-medium">{pm.aluno_nome}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Data de Nascimento</dt>
                              <dd>{formatDate(pm.aluno_data_nascimento)}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Sexo</dt>
                              <dd>{pm.aluno_sexo === 'masculino' ? 'Masculino' : pm.aluno_sexo === 'feminino' ? 'Feminino' : '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">CPF</dt>
                              <dd>{pm.aluno_cpf || '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Nível de Ensino</dt>
                              <dd>{NIVEL_LABELS[pm.nivel_ensino] || pm.nivel_ensino || '-'}</dd>
                            </div>
                          </dl>
                        </div>
                        
                        {/* Dados do Responsável */}
                        <div>
                          <h4 className="font-medium text-gray-900 mb-3 flex items-center gap-2">
                            <Users className="w-4 h-4 text-green-600" />
                            Dados do Responsável
                          </h4>
                          <dl className="space-y-2 text-sm">
                            <div>
                              <dt className="text-gray-500">Nome</dt>
                              <dd className="font-medium">{pm.responsavel_nome}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Parentesco</dt>
                              <dd>{PARENTESCO_LABELS[pm.responsavel_parentesco] || pm.responsavel_parentesco || '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">CPF</dt>
                              <dd>{pm.responsavel_cpf || '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Telefone</dt>
                              <dd className="flex items-center gap-1">
                                <Phone className="w-3 h-3" />
                                {pm.responsavel_telefone}
                              </dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">E-mail</dt>
                              <dd className="flex items-center gap-1">
                                <Mail className="w-3 h-3" />
                                {pm.responsavel_email || '-'}
                              </dd>
                            </div>
                          </dl>
                        </div>
                        
                        {/* Endereço e Info */}
                        <div>
                          <h4 className="font-medium text-gray-900 mb-3 flex items-center gap-2">
                            <MapPin className="w-4 h-4 text-purple-600" />
                            Endereço
                          </h4>
                          <dl className="space-y-2 text-sm">
                            <div>
                              <dt className="text-gray-500">Logradouro</dt>
                              <dd>{pm.endereco_logradouro ? `${pm.endereco_logradouro}, ${pm.endereco_numero || 'S/N'}` : '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Bairro</dt>
                              <dd>{pm.endereco_bairro || '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">Cidade</dt>
                              <dd>{pm.endereco_cidade || '-'}</dd>
                            </div>
                            <div>
                              <dt className="text-gray-500">CEP</dt>
                              <dd>{pm.endereco_cep || '-'}</dd>
                            </div>
                          </dl>
                          
                          {/* Metadados */}
                          <div className="mt-4 pt-4 border-t">
                            <h4 className="font-medium text-gray-900 mb-2 flex items-center gap-2">
                              <FileText className="w-4 h-4 text-gray-600" />
                              Informações
                            </h4>
                            <dl className="space-y-1 text-xs text-gray-500">
                              <div>
                                <dt className="inline">Recebido em:</dt>
                                <dd className="inline ml-1">{formatDateTime(pm.created_at)}</dd>
                              </div>
                              {pm.analyzed_at && (
                                <div>
                                  <dt className="inline">Analisado em:</dt>
                                  <dd className="inline ml-1">{formatDateTime(pm.analyzed_at)}</dd>
                                </div>
                              )}
                            </dl>
                          </div>
                        </div>
                      </div>
                      
                      {/* Observações */}
                      {pm.observacoes && (
                        <div className="mt-4 pt-4 border-t">
                          <h4 className="font-medium text-gray-900 mb-2">Observações</h4>
                          <p className="text-sm text-gray-600 bg-white p-3 rounded border">
                            {pm.observacoes}
                          </p>
                        </div>
                      )}
                      
                      {/* Motivo da Rejeição */}
                      {pm.status === 'rejeitada' && pm.rejection_reason && (
                        <div className="mt-4 pt-4 border-t">
                          <h4 className="font-medium text-red-700 mb-2 flex items-center gap-2">
                            <AlertCircle className="w-4 h-4" />
                            Motivo da Rejeição
                          </h4>
                          <p className="text-sm text-red-600 bg-red-50 p-3 rounded border border-red-200">
                            {pm.rejection_reason}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </Layout>
  );
}
