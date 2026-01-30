import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { 
  Users, Search, Eye, CheckCircle, XCircle, Clock, 
  UserPlus, ChevronDown, ChevronUp, Phone, 
  Mail, MapPin, Calendar, FileText, AlertCircle,
  Loader2, RefreshCw, UserCheck, GraduationCap, ExternalLink, Home
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

// Labels de série/ano
const SERIE_ANO_LABELS = {
  // Educação Infantil
  educacao_infantil_bercario: 'Berçário',
  educacao_infantil_maternal_i: 'Maternal I',
  educacao_infantil_maternal_ii: 'Maternal II',
  educacao_infantil_pre_i: 'Pré I',
  educacao_infantil_pre_ii: 'Pré II',
  
  // Fundamental Anos Iniciais
  fundamental_inicial_1ano: '1º Ano',
  fundamental_inicial_2ano: '2º Ano',
  fundamental_inicial_3ano: '3º Ano',
  fundamental_inicial_4ano: '4º Ano',
  fundamental_inicial_5ano: '5º Ano',
  
  // Fundamental Anos Finais
  fundamental_final_6ano: '6º Ano',
  fundamental_final_7ano: '7º Ano',
  fundamental_final_8ano: '8º Ano',
  fundamental_final_9ano: '9º Ano',
  
  // EJA Anos Iniciais
  eja_inicial_1etapa: 'EJA 1ª Etapa',
  eja_inicial_2etapa: 'EJA 2ª Etapa',
  
  // EJA Anos Finais
  eja_final_3etapa: 'EJA 3ª Etapa',
  eja_final_4etapa: 'EJA 4ª Etapa',
};

export default function PreMatriculaManagement() {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [preMatriculas, setPreMatriculas] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [processing, setProcessing] = useState(null);
  
  // Estado do modal de conversão
  const [convertModalOpen, setConvertModalOpen] = useState(false);
  const [selectedPreMatricula, setSelectedPreMatricula] = useState(null);
  const [selectedClassId, setSelectedClassId] = useState('');
  const [converting, setConverting] = useState(false);

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

  const loadClasses = async (schoolId) => {
    try {
      const response = await axios.get(`${API_URL}/api/classes?school_id=${schoolId}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      setClasses(response.data || []);
    } catch (error) {
      console.error('Erro ao carregar turmas:', error);
      setClasses([]);
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

  // Abre modal de conversão
  const handleOpenConvertModal = async (pm) => {
    setSelectedPreMatricula(pm);
    setSelectedClassId('');
    await loadClasses(pm.school_id);
    setConvertModalOpen(true);
  };

  // Converte pré-matrícula em aluno
  const handleConvert = async () => {
    if (!selectedPreMatricula) return;
    
    setConverting(true);
    try {
      let url = `${API_URL}/api/pre-matriculas/${selectedPreMatricula.id}/convert`;
      if (selectedClassId) {
        url += `?class_id=${selectedClassId}`;
      }
      
      const response = await axios.post(url, {}, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      
      const studentId = response.data.student_id;
      
      toast.success(
        <div className="space-y-2">
          <p className="font-medium">Aluno criado com sucesso!</p>
          <p className="text-sm">Matrícula: {response.data.enrollment_number}</p>
          <button
            onClick={() => navigate(`/admin/students?highlight=${studentId}`)}
            className="flex items-center gap-1 text-sm text-purple-600 hover:text-purple-800 font-medium"
          >
            <ExternalLink className="w-3 h-3" />
            Ver cadastro do aluno
          </button>
        </div>,
        { duration: 8000 }
      );
      
      setConvertModalOpen(false);
      setSelectedPreMatricula(null);
      loadPreMatriculas();
    } catch (error) {
      console.error('Erro ao converter pré-matrícula:', error);
      const errorMsg = error.response?.data?.detail || 'Erro ao converter pré-matrícula';
      toast.error(errorMsg);
    } finally {
      setConverting(false);
    }
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
          
          <div className="flex gap-2">
            <Button onClick={() => navigate('/admin')} variant="outline" data-testid="home-btn">
              <Home className="w-4 h-4 mr-2" />
              Início
            </Button>
            <Button onClick={loadPreMatriculas} variant="outline" disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
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
                data-testid={`status-filter-${key}`}
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
                  data-testid="search-input"
                />
              </div>
            </div>
            
            <select
              value={selectedSchool}
              onChange={(e) => setSelectedSchool(e.target.value)}
              className="px-3 py-2 border rounded-lg text-sm min-w-[200px]"
              data-testid="school-filter"
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
              data-testid="status-select-filter"
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
              const isExpanded = expandedId === pm.id;
              
              return (
                <div 
                  key={pm.id} 
                  className="bg-white rounded-lg border shadow-sm overflow-hidden"
                  data-testid={`pre-matricula-card-${pm.id}`}
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
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => { e.stopPropagation(); handleAnalyze(pm); }}
                            disabled={processing === pm.id}
                            data-testid={`analyze-btn-${pm.id}`}
                          >
                            <Eye className="w-4 h-4 mr-1" />
                            Analisar
                          </Button>
                        )}
                        {(pm.status === 'pendente' || pm.status === 'analisando') && (
                          <>
                            <Button
                              size="sm"
                              className="bg-green-600 hover:bg-green-700"
                              onClick={(e) => { e.stopPropagation(); handleApprove(pm); }}
                              disabled={processing === pm.id}
                              data-testid={`approve-btn-${pm.id}`}
                            >
                              <CheckCircle className="w-4 h-4 mr-1" />
                              Aprovar
                            </Button>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={(e) => { e.stopPropagation(); handleReject(pm); }}
                              disabled={processing === pm.id}
                              data-testid={`reject-btn-${pm.id}`}
                            >
                              <XCircle className="w-4 h-4 mr-1" />
                              Rejeitar
                            </Button>
                          </>
                        )}
                        {pm.status === 'aprovada' && (
                          <Button
                            size="sm"
                            className="bg-purple-600 hover:bg-purple-700"
                            onClick={(e) => { e.stopPropagation(); handleOpenConvertModal(pm); }}
                            disabled={processing === pm.id}
                            data-testid={`convert-btn-${pm.id}`}
                          >
                            <GraduationCap className="w-4 h-4 mr-1" />
                            Converter em Aluno
                          </Button>
                        )}
                        {pm.status === 'convertida' && pm.converted_student_id && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-purple-600 border-purple-300 hover:bg-purple-50"
                            onClick={(e) => { 
                              e.stopPropagation(); 
                              navigate(`/admin/students?highlight=${pm.converted_student_id}`);
                            }}
                            data-testid={`view-student-btn-${pm.id}`}
                          >
                            <UserCheck className="w-4 h-4 mr-1" />
                            Ver Aluno
                          </Button>
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
                              <dt className="text-gray-500">Série/Ano Desejado</dt>
                              <dd>{SERIE_ANO_LABELS[pm.serie_ano_desejado] || pm.serie_ano_desejado || NIVEL_LABELS[pm.nivel_ensino] || pm.nivel_ensino || '-'}</dd>
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

                      {/* Info de Conversão */}
                      {pm.status === 'convertida' && pm.converted_student_id && (
                        <div className="mt-4 pt-4 border-t">
                          <h4 className="font-medium text-purple-700 mb-2 flex items-center gap-2">
                            <UserCheck className="w-4 h-4" />
                            Conversão Realizada
                          </h4>
                          <div className="flex items-center justify-between bg-purple-50 p-3 rounded border border-purple-200">
                            <p className="text-sm text-purple-600">
                              Esta pré-matrícula foi convertida em aluno com sucesso.
                            </p>
                            <Button
                              size="sm"
                              className="bg-purple-600 hover:bg-purple-700"
                              onClick={() => navigate(`/admin/students?highlight=${pm.converted_student_id}`)}
                            >
                              <ExternalLink className="w-4 h-4 mr-1" />
                              Abrir Cadastro do Aluno
                            </Button>
                          </div>
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

      {/* Modal de Conversão */}
      <Dialog open={convertModalOpen} onOpenChange={setConvertModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <GraduationCap className="w-5 h-5 text-purple-600" />
              Converter em Aluno
            </DialogTitle>
            <DialogDescription>
              Crie um novo aluno a partir dos dados da pré-matrícula de <strong>{selectedPreMatricula?.aluno_nome}</strong>.
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4 py-4">
            <div className="bg-gray-50 rounded-lg p-3 text-sm">
              <p className="text-gray-600 mb-2">Dados que serão transferidos:</p>
              <ul className="space-y-1 text-gray-700">
                <li>• Nome: <strong>{selectedPreMatricula?.aluno_nome}</strong></li>
                <li>• Data de Nasc.: <strong>{formatDate(selectedPreMatricula?.aluno_data_nascimento)}</strong></li>
                <li>• Responsável: <strong>{selectedPreMatricula?.responsavel_nome}</strong></li>
                <li>• Telefone: <strong>{selectedPreMatricula?.responsavel_telefone}</strong></li>
              </ul>
            </div>
            
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-2">
                Turma (opcional)
              </label>
              <select
                value={selectedClassId}
                onChange={(e) => setSelectedClassId(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg text-sm"
                data-testid="class-select-modal"
              >
                <option value="">Selecionar turma depois</option>
                {classes.map(cls => (
                  <option key={cls.id} value={cls.id}>
                    {cls.name} - {cls.grade_level} ({cls.shift === 'morning' ? 'Manhã' : cls.shift === 'afternoon' ? 'Tarde' : cls.shift === 'evening' ? 'Noite' : 'Integral'})
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Você pode vincular o aluno a uma turma agora ou fazer isso posteriormente.
              </p>
            </div>
          </div>
          
          <DialogFooter>
            <Button 
              variant="outline" 
              onClick={() => setConvertModalOpen(false)}
              disabled={converting}
            >
              Cancelar
            </Button>
            <Button 
              onClick={handleConvert}
              disabled={converting}
              className="bg-purple-600 hover:bg-purple-700"
              data-testid="confirm-convert-btn"
            >
              {converting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Convertendo...
                </>
              ) : (
                <>
                  <UserCheck className="w-4 h-4 mr-2" />
                  Confirmar Conversão
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
