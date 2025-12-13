import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import Layout from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/Modal';
import { 
  Users, 
  UserPlus,
  Building2,
  Search,
  Edit,
  Trash2,
  Eye,
  ChevronDown,
  ChevronUp,
  BookOpen,
  MapPin,
  Clock,
  AlertTriangle,
  CheckCircle,
  XCircle,
  ArrowLeft,
  GraduationCap,
  Briefcase,
  Calendar
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { staffAPI, schoolAssignmentAPI, teacherAssignmentAPI, schoolsAPI, usersAPI, classesAPI, coursesAPI } from '@/services/api';

const CARGOS = {
  professor: 'Professor',
  diretor: 'Diretor',
  coordenador: 'Coordenador',
  secretario: 'Secretário',
  auxiliar: 'Auxiliar Administrativo',
  merendeira: 'Merendeira',
  zelador: 'Zelador',
  vigia: 'Vigia',
  outro: 'Outro'
};

const STATUS_SERVIDOR = {
  ativo: { label: 'Ativo', color: 'bg-green-100 text-green-800' },
  afastado: { label: 'Afastado', color: 'bg-yellow-100 text-yellow-800' },
  licenca: { label: 'Licença', color: 'bg-blue-100 text-blue-800' },
  ferias: { label: 'Férias', color: 'bg-purple-100 text-purple-800' },
  aposentado: { label: 'Aposentado', color: 'bg-gray-100 text-gray-800' },
  exonerado: { label: 'Exonerado', color: 'bg-red-100 text-red-800' }
};

const TIPOS_VINCULO = {
  efetivo: 'Efetivo',
  contratado: 'Contratado',
  temporario: 'Temporário',
  comissionado: 'Comissionado'
};

const FUNCOES = {
  professor: 'Professor',
  diretor: 'Diretor',
  vice_diretor: 'Vice-Diretor',
  coordenador: 'Coordenador',
  secretario: 'Secretário',
  apoio: 'Apoio'
};

const TURNOS = {
  matutino: 'Matutino',
  vespertino: 'Vespertino',
  noturno: 'Noturno',
  integral: 'Integral'
};

export const Staff = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const academicYear = new Date().getFullYear();
  
  // Estados principais
  const [loading, setLoading] = useState(true);
  const [staffList, setStaffList] = useState([]);
  const [schools, setSchools] = useState([]);
  const [users, setUsers] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  
  // Filtros
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCargo, setFilterCargo] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSchool, setFilterSchool] = useState('');
  
  // Abas
  const [activeTab, setActiveTab] = useState('servidores'); // servidores, lotacoes, alocacoes
  
  // Modais
  const [showStaffModal, setShowStaffModal] = useState(false);
  const [showLotacaoModal, setShowLotacaoModal] = useState(false);
  const [showAlocacaoModal, setShowAlocacaoModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  
  // Dados do formulário
  const [editingStaff, setEditingStaff] = useState(null);
  const [selectedStaff, setSelectedStaff] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteType, setDeleteType] = useState(''); // staff, lotacao, alocacao
  
  // Lotações e Alocações
  const [lotacoes, setLotacoes] = useState([]);
  const [alocacoes, setAlocacoes] = useState([]);
  
  // Form states
  const [staffForm, setStaffForm] = useState({
    user_id: '',
    matricula: '',
    cargo: 'professor',
    cargo_especifico: '',
    tipo_vinculo: 'efetivo',
    data_admissao: '',
    carga_horaria_semanal: '',
    formacao: '',
    especializacao: '',
    status: 'ativo',
    motivo_afastamento: '',
    data_afastamento: '',
    previsao_retorno: '',
    observacoes: ''
  });
  
  const [lotacaoForm, setLotacaoForm] = useState({
    staff_id: '',
    school_id: '',
    funcao: 'professor',
    data_inicio: new Date().toISOString().split('T')[0],
    data_fim: '',
    carga_horaria: '',
    turno: '',
    status: 'ativo',
    academic_year: academicYear,
    observacoes: ''
  });
  
  const [alocacaoForm, setAlocacaoForm] = useState({
    staff_id: '',
    school_id: '',
    class_id: '',
    course_id: '',
    academic_year: academicYear,
    carga_horaria_semanal: '',
    status: 'ativo',
    observacoes: ''
  });
  
  // Alert
  const [alert, setAlert] = useState({ show: false, type: '', message: '' });
  
  // Saving states
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  
  // Permissões
  const canEdit = user?.role === 'admin' || user?.role === 'secretario';
  const canDelete = user?.role === 'admin';
  
  // Carrega dados iniciais
  useEffect(() => {
    loadInitialData();
  }, []);
  
  // Carrega dados baseado na aba ativa
  useEffect(() => {
    if (activeTab === 'servidores') {
      loadStaff();
    } else if (activeTab === 'lotacoes') {
      loadLotacoes();
    } else if (activeTab === 'alocacoes') {
      loadAlocacoes();
    }
  }, [activeTab, filterSchool]);
  
  const loadInitialData = async () => {
    try {
      const [schoolsData, usersData, classesData, coursesData] = await Promise.all([
        schoolsAPI.list(),
        usersAPI.list(),
        classesAPI.list(),
        coursesAPI.list()
      ]);
      setSchools(schoolsData);
      setUsers(usersData.filter(u => !['aluno', 'responsavel'].includes(u.role)));
      setClasses(classesData);
      setCourses(coursesData);
    } catch (error) {
      console.error('Erro ao carregar dados:', error);
    }
  };
  
  const loadStaff = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterCargo) params.cargo = filterCargo;
      if (filterStatus) params.status = filterStatus;
      if (filterSchool) params.school_id = filterSchool;
      
      const data = await staffAPI.list(params);
      setStaffList(data);
    } catch (error) {
      console.error('Erro ao carregar servidores:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const loadLotacoes = async () => {
    setLoading(true);
    try {
      const params = { academic_year: academicYear };
      if (filterSchool) params.school_id = filterSchool;
      
      const data = await schoolAssignmentAPI.list(params);
      setLotacoes(data);
    } catch (error) {
      console.error('Erro ao carregar lotações:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const loadAlocacoes = async () => {
    setLoading(true);
    try {
      const params = { academic_year: academicYear };
      if (filterSchool) params.school_id = filterSchool;
      
      const data = await teacherAssignmentAPI.list(params);
      setAlocacoes(data);
    } catch (error) {
      console.error('Erro ao carregar alocações:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const showAlertMessage = (type, message) => {
    setAlert({ show: true, type, message });
    setTimeout(() => setAlert({ show: false, type: '', message: '' }), 3000);
  };
  
  // Filtro de servidores
  const filteredStaff = useMemo(() => {
    return staffList.filter(s => {
      const matchesSearch = !searchTerm || 
        s.user?.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.matricula?.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCargo = !filterCargo || s.cargo === filterCargo;
      const matchesStatus = !filterStatus || s.status === filterStatus;
      return matchesSearch && matchesCargo && matchesStatus;
    });
  }, [staffList, searchTerm, filterCargo, filterStatus]);
  
  // Usuários disponíveis (sem cadastro de servidor)
  const availableUsers = useMemo(() => {
    const staffUserIds = staffList.map(s => s.user_id);
    return users.filter(u => !staffUserIds.includes(u.id));
  }, [users, staffList]);
  
  // Professores para alocação
  const professors = useMemo(() => {
    return staffList.filter(s => s.cargo === 'professor' && s.status === 'ativo');
  }, [staffList]);
  
  // Turmas filtradas por escola
  const filteredClasses = useMemo(() => {
    if (!alocacaoForm.school_id) return [];
    return classes.filter(c => c.school_id === alocacaoForm.school_id);
  }, [classes, alocacaoForm.school_id]);
  
  // ===== HANDLERS =====
  
  const handleNewStaff = () => {
    setEditingStaff(null);
    setStaffForm({
      user_id: '',
      matricula: '',
      cargo: 'professor',
      cargo_especifico: '',
      tipo_vinculo: 'efetivo',
      data_admissao: '',
      carga_horaria_semanal: '',
      formacao: '',
      especializacao: '',
      status: 'ativo',
      motivo_afastamento: '',
      data_afastamento: '',
      previsao_retorno: '',
      observacoes: ''
    });
    setShowStaffModal(true);
  };
  
  const handleEditStaff = (staff) => {
    setEditingStaff(staff);
    setStaffForm({
      user_id: staff.user_id,
      matricula: staff.matricula || '',
      cargo: staff.cargo || 'professor',
      cargo_especifico: staff.cargo_especifico || '',
      tipo_vinculo: staff.tipo_vinculo || 'efetivo',
      data_admissao: staff.data_admissao || '',
      carga_horaria_semanal: staff.carga_horaria_semanal || '',
      formacao: staff.formacao || '',
      especializacao: staff.especializacao || '',
      status: staff.status || 'ativo',
      motivo_afastamento: staff.motivo_afastamento || '',
      data_afastamento: staff.data_afastamento || '',
      previsao_retorno: staff.previsao_retorno || '',
      observacoes: staff.observacoes || ''
    });
    setShowStaffModal(true);
  };
  
  const handleViewStaff = async (staff) => {
    try {
      const fullStaff = await staffAPI.get(staff.id);
      setSelectedStaff(fullStaff);
      setShowDetailModal(true);
    } catch (error) {
      console.error('Erro ao carregar detalhes:', error);
      showAlertMessage('error', 'Erro ao carregar detalhes do servidor');
    }
  };
  
  const handleSaveStaff = async () => {
    if (!staffForm.user_id || !staffForm.matricula || !staffForm.cargo) {
      showAlertMessage('error', 'Preencha os campos obrigatórios');
      return;
    }
    
    setSaving(true);
    try {
      const data = {
        ...staffForm,
        carga_horaria_semanal: staffForm.carga_horaria_semanal ? parseInt(staffForm.carga_horaria_semanal) : null
      };
      
      if (editingStaff) {
        await staffAPI.update(editingStaff.id, data);
        showAlertMessage('success', 'Servidor atualizado!');
      } else {
        await staffAPI.create(data);
        showAlertMessage('success', 'Servidor cadastrado!');
      }
      
      setShowStaffModal(false);
      loadStaff();
    } catch (error) {
      console.error('Erro ao salvar servidor:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao salvar servidor');
    } finally {
      setSaving(false);
    }
  };
  
  // Lotação handlers
  const handleNewLotacao = (staff = null) => {
    setLotacaoForm({
      staff_id: staff?.id || '',
      school_id: '',
      funcao: staff?.cargo === 'professor' ? 'professor' : 'apoio',
      data_inicio: new Date().toISOString().split('T')[0],
      data_fim: '',
      carga_horaria: '',
      turno: '',
      status: 'ativo',
      academic_year: academicYear,
      observacoes: ''
    });
    setShowLotacaoModal(true);
  };
  
  const handleSaveLotacao = async () => {
    if (!lotacaoForm.staff_id || !lotacaoForm.school_id || !lotacaoForm.data_inicio) {
      showAlertMessage('error', 'Preencha os campos obrigatórios');
      return;
    }
    
    setSaving(true);
    try {
      const data = {
        ...lotacaoForm,
        carga_horaria: lotacaoForm.carga_horaria ? parseInt(lotacaoForm.carga_horaria) : null
      };
      
      await schoolAssignmentAPI.create(data);
      showAlertMessage('success', 'Lotação criada!');
      setShowLotacaoModal(false);
      loadLotacoes();
    } catch (error) {
      console.error('Erro ao salvar lotação:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao salvar lotação');
    } finally {
      setSaving(false);
    }
  };
  
  // Alocação handlers
  const handleNewAlocacao = (staff = null) => {
    setAlocacaoForm({
      staff_id: staff?.id || '',
      school_id: '',
      class_id: '',
      course_id: '',
      academic_year: academicYear,
      carga_horaria_semanal: '',
      status: 'ativo',
      observacoes: ''
    });
    setShowAlocacaoModal(true);
  };
  
  const handleSaveAlocacao = async () => {
    if (!alocacaoForm.staff_id || !alocacaoForm.school_id || !alocacaoForm.class_id || !alocacaoForm.course_id) {
      showAlertMessage('error', 'Preencha os campos obrigatórios');
      return;
    }
    
    setSaving(true);
    try {
      const data = {
        ...alocacaoForm,
        carga_horaria_semanal: alocacaoForm.carga_horaria_semanal ? parseInt(alocacaoForm.carga_horaria_semanal) : null
      };
      
      await teacherAssignmentAPI.create(data);
      showAlertMessage('success', 'Alocação criada!');
      setShowAlocacaoModal(false);
      loadAlocacoes();
    } catch (error) {
      console.error('Erro ao salvar alocação:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao salvar alocação');
    } finally {
      setSaving(false);
    }
  };
  
  // Delete handlers
  const handleDelete = (item, type) => {
    setDeleteTarget(item);
    setDeleteType(type);
    setShowDeleteModal(true);
  };
  
  const confirmDelete = async () => {
    setDeleting(true);
    try {
      if (deleteType === 'staff') {
        await staffAPI.delete(deleteTarget.id);
        showAlertMessage('success', 'Servidor removido!');
        loadStaff();
      } else if (deleteType === 'lotacao') {
        await schoolAssignmentAPI.delete(deleteTarget.id);
        showAlertMessage('success', 'Lotação removida!');
        loadLotacoes();
      } else if (deleteType === 'alocacao') {
        await teacherAssignmentAPI.delete(deleteTarget.id);
        showAlertMessage('success', 'Alocação removida!');
        loadAlocacoes();
      }
      setShowDeleteModal(false);
    } catch (error) {
      console.error('Erro ao excluir:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao excluir');
    } finally {
      setDeleting(false);
    }
  };
  
  const handleEncerrarLotacao = async (lotacao) => {
    try {
      await schoolAssignmentAPI.update(lotacao.id, {
        status: 'encerrado',
        data_fim: new Date().toISOString().split('T')[0]
      });
      showAlertMessage('success', 'Lotação encerrada!');
      loadLotacoes();
    } catch (error) {
      showAlertMessage('error', 'Erro ao encerrar lotação');
    }
  };
  
  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Alert */}
        {alert.show && (
          <div className={`fixed top-4 right-4 z-50 p-4 rounded-lg shadow-lg ${
            alert.type === 'success' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
          }`}>
            {alert.message}
          </div>
        )}
        
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              onClick={() => navigate('/dashboard')}
              className="flex items-center gap-2"
            >
              <ArrowLeft size={16} />
              Voltar ao Dashboard
            </Button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <Users className="text-blue-600" />
                Gestão de Servidores
              </h1>
              <p className="text-sm text-gray-600">Cadastro, Lotação e Alocação de Servidores</p>
            </div>
          </div>
          
          {canEdit && (
            <div className="flex gap-2">
              {activeTab === 'servidores' && (
                <Button onClick={handleNewStaff}>
                  <UserPlus size={16} className="mr-2" />
                  Novo Servidor
                </Button>
              )}
              {activeTab === 'lotacoes' && (
                <Button onClick={() => handleNewLotacao()}>
                  <Building2 size={16} className="mr-2" />
                  Nova Lotação
                </Button>
              )}
              {activeTab === 'alocacoes' && (
                <Button onClick={() => handleNewAlocacao()}>
                  <GraduationCap size={16} className="mr-2" />
                  Nova Alocação
                </Button>
              )}
            </div>
          )}
        </div>
        
        {/* Abas */}
        <div className="bg-white rounded-lg shadow-sm border mb-6">
          <div className="flex border-b">
            {[
              { id: 'servidores', label: 'Servidores', icon: Users },
              { id: 'lotacoes', label: 'Lotações', icon: Building2 },
              { id: 'alocacoes', label: 'Alocações de Professores', icon: GraduationCap }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-6 py-3 font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'border-b-2 border-blue-600 text-blue-600 bg-blue-50'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                <tab.icon size={18} />
                {tab.label}
              </button>
            ))}
          </div>
          
          {/* Filtros */}
          <div className="p-4 border-b bg-gray-50">
            <div className="flex flex-wrap gap-4 items-center">
              <div className="flex-1 min-w-[200px]">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={18} />
                  <input
                    type="text"
                    placeholder="Buscar por nome ou matrícula..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>
              
              <select
                value={filterSchool}
                onChange={(e) => setFilterSchool(e.target.value)}
                className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Todas as Escolas</option>
                {schools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              
              {activeTab === 'servidores' && (
                <>
                  <select
                    value={filterCargo}
                    onChange={(e) => setFilterCargo(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Todos os Cargos</option>
                    {Object.entries(CARGOS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">Todos os Status</option>
                    {Object.entries(STATUS_SERVIDOR).map(([value, { label }]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </>
              )}
            </div>
          </div>
          
          {/* Conteúdo */}
          <div className="p-4">
            {loading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                <p className="mt-2 text-gray-500">Carregando...</p>
              </div>
            ) : activeTab === 'servidores' ? (
              /* Lista de Servidores */
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Servidor</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Matrícula</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cargo</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Vínculo</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {filteredStaff.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                          Nenhum servidor encontrado
                        </td>
                      </tr>
                    ) : filteredStaff.map(staff => (
                      <tr key={staff.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{staff.user?.full_name || '-'}</div>
                          <div className="text-sm text-gray-500">{staff.user?.email}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-700">{staff.matricula}</td>
                        <td className="px-4 py-3 text-gray-700">{CARGOS[staff.cargo] || staff.cargo}</td>
                        <td className="px-4 py-3 text-gray-700">{TIPOS_VINCULO[staff.tipo_vinculo] || staff.tipo_vinculo}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_SERVIDOR[staff.status]?.color || 'bg-gray-100'}`}>
                            {STATUS_SERVIDOR[staff.status]?.label || staff.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-center gap-2">
                            <button
                              onClick={() => handleViewStaff(staff)}
                              className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"
                              title="Ver detalhes"
                            >
                              <Eye size={16} />
                            </button>
                            {canEdit && (
                              <>
                                <button
                                  onClick={() => handleEditStaff(staff)}
                                  className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded"
                                  title="Editar"
                                >
                                  <Edit size={16} />
                                </button>
                                <button
                                  onClick={() => handleNewLotacao(staff)}
                                  className="p-1.5 text-green-600 hover:bg-green-50 rounded"
                                  title="Nova Lotação"
                                >
                                  <Building2 size={16} />
                                </button>
                                {staff.cargo === 'professor' && (
                                  <button
                                    onClick={() => handleNewAlocacao(staff)}
                                    className="p-1.5 text-purple-600 hover:bg-purple-50 rounded"
                                    title="Alocar Turma"
                                  >
                                    <GraduationCap size={16} />
                                  </button>
                                )}
                              </>
                            )}
                            {canDelete && (
                              <button
                                onClick={() => handleDelete(staff, 'staff')}
                                className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                                title="Excluir"
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : activeTab === 'lotacoes' ? (
              /* Lista de Lotações */
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Servidor</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Escola</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Função</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turno</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Período</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {lotacoes.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                          Nenhuma lotação encontrada
                        </td>
                      </tr>
                    ) : lotacoes.map(lot => (
                      <tr key={lot.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{lot.staff?.user_name || '-'}</div>
                          <div className="text-sm text-gray-500">{lot.staff?.matricula}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-700">{lot.school_name}</td>
                        <td className="px-4 py-3 text-gray-700">{FUNCOES[lot.funcao] || lot.funcao}</td>
                        <td className="px-4 py-3 text-gray-700">{TURNOS[lot.turno] || lot.turno || '-'}</td>
                        <td className="px-4 py-3 text-sm text-gray-700">
                          {lot.data_inicio} {lot.data_fim ? `- ${lot.data_fim}` : '- atual'}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            lot.status === 'ativo' ? 'bg-green-100 text-green-800' :
                            lot.status === 'encerrado' ? 'bg-gray-100 text-gray-800' :
                            'bg-yellow-100 text-yellow-800'
                          }`}>
                            {lot.status === 'ativo' ? 'Ativo' : lot.status === 'encerrado' ? 'Encerrado' : 'Transferido'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-center gap-2">
                            {canEdit && lot.status === 'ativo' && (
                              <button
                                onClick={() => handleEncerrarLotacao(lot)}
                                className="p-1.5 text-yellow-600 hover:bg-yellow-50 rounded"
                                title="Encerrar Lotação"
                              >
                                <XCircle size={16} />
                              </button>
                            )}
                            {canDelete && (
                              <button
                                onClick={() => handleDelete(lot, 'lotacao')}
                                className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                                title="Excluir"
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Lista de Alocações */
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Professor</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Escola</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turma</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Componente</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">CH/Sem</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {alocacoes.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                          Nenhuma alocação encontrada
                        </td>
                      </tr>
                    ) : alocacoes.map(aloc => (
                      <tr key={aloc.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{aloc.staff_name || '-'}</td>
                        <td className="px-4 py-3 text-gray-700">{aloc.school_name}</td>
                        <td className="px-4 py-3 text-gray-700">{aloc.class_name}</td>
                        <td className="px-4 py-3 text-gray-700">{aloc.course_name}</td>
                        <td className="px-4 py-3 text-gray-700">{aloc.carga_horaria_semanal || '-'}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            aloc.status === 'ativo' ? 'bg-green-100 text-green-800' :
                            aloc.status === 'substituido' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {aloc.status === 'ativo' ? 'Ativo' : aloc.status === 'substituido' ? 'Substituído' : 'Encerrado'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-center gap-2">
                            {canDelete && (
                              <button
                                onClick={() => handleDelete(aloc, 'alocacao')}
                                className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                                title="Excluir"
                              >
                                <Trash2 size={16} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
        
        {/* Modal Servidor */}
        <Modal
          isOpen={showStaffModal}
          onClose={() => setShowStaffModal(false)}
          title={editingStaff ? 'Editar Servidor' : 'Novo Servidor'}
          size="lg"
        >
          <div className="space-y-4 max-h-[70vh] overflow-y-auto">
            {/* Usuário */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Usuário *</label>
              <select
                value={staffForm.user_id}
                onChange={(e) => setStaffForm({ ...staffForm, user_id: e.target.value })}
                disabled={!!editingStaff}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Selecione o usuário</option>
                {(editingStaff ? users : availableUsers).map(u => (
                  <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
                ))}
              </select>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              {/* Matrícula */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Matrícula *</label>
                <input
                  type="text"
                  value={staffForm.matricula}
                  onChange={(e) => setStaffForm({ ...staffForm, matricula: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Ex: 12345"
                />
              </div>
              
              {/* Cargo */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Cargo *</label>
                <select
                  value={staffForm.cargo}
                  onChange={(e) => setStaffForm({ ...staffForm, cargo: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  {Object.entries(CARGOS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              {/* Tipo Vínculo */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Vínculo</label>
                <select
                  value={staffForm.tipo_vinculo}
                  onChange={(e) => setStaffForm({ ...staffForm, tipo_vinculo: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  {Object.entries(TIPOS_VINCULO).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              
              {/* Data Admissão */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Admissão</label>
                <input
                  type="date"
                  value={staffForm.data_admissao}
                  onChange={(e) => setStaffForm({ ...staffForm, data_admissao: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              {/* Carga Horária */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Carga Horária Semanal</label>
                <input
                  type="number"
                  value={staffForm.carga_horaria_semanal}
                  onChange={(e) => setStaffForm({ ...staffForm, carga_horaria_semanal: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Ex: 40"
                />
              </div>
              
              {/* Status */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <select
                  value={staffForm.status}
                  onChange={(e) => setStaffForm({ ...staffForm, status: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  {Object.entries(STATUS_SERVIDOR).map(([value, { label }]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>
            
            {/* Campos de Professor */}
            {staffForm.cargo === 'professor' && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-blue-50 rounded-lg">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Formação</label>
                  <input
                    type="text"
                    value={staffForm.formacao}
                    onChange={(e) => setStaffForm({ ...staffForm, formacao: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="Ex: Licenciatura em Matemática"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Especialização</label>
                  <input
                    type="text"
                    value={staffForm.especializacao}
                    onChange={(e) => setStaffForm({ ...staffForm, especializacao: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    placeholder="Ex: Pós em Educação"
                  />
                </div>
              </div>
            )}
            
            {/* Campos de Afastamento */}
            {['afastado', 'licenca'].includes(staffForm.status) && (
              <div className="p-4 bg-yellow-50 rounded-lg space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Motivo do Afastamento</label>
                  <input
                    type="text"
                    value={staffForm.motivo_afastamento}
                    onChange={(e) => setStaffForm({ ...staffForm, motivo_afastamento: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Data do Afastamento</label>
                    <input
                      type="date"
                      value={staffForm.data_afastamento}
                      onChange={(e) => setStaffForm({ ...staffForm, data_afastamento: e.target.value })}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Previsão de Retorno</label>
                    <input
                      type="date"
                      value={staffForm.previsao_retorno}
                      onChange={(e) => setStaffForm({ ...staffForm, previsao_retorno: e.target.value })}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>
            )}
            
            {/* Observações */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Observações</label>
              <textarea
                value={staffForm.observacoes}
                onChange={(e) => setStaffForm({ ...staffForm, observacoes: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            
            {/* Botões */}
            <div className="flex gap-2 pt-4 border-t">
              <Button onClick={handleSaveStaff} disabled={saving} className="flex-1">
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
              <Button variant="outline" onClick={() => setShowStaffModal(false)}>Cancelar</Button>
            </div>
          </div>
        </Modal>
        
        {/* Modal Lotação */}
        <Modal
          isOpen={showLotacaoModal}
          onClose={() => setShowLotacaoModal(false)}
          title="Nova Lotação"
        >
          <div className="space-y-4">
            {/* Servidor */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Servidor *</label>
              <select
                value={lotacaoForm.staff_id}
                onChange={(e) => setLotacaoForm({ ...lotacaoForm, staff_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione o servidor</option>
                {staffList.filter(s => s.status === 'ativo').map(s => (
                  <option key={s.id} value={s.id}>
                    {s.user?.full_name} - {s.matricula} ({CARGOS[s.cargo]})
                  </option>
                ))}
              </select>
            </div>
            
            {/* Escola */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola *</label>
              <select
                value={lotacaoForm.school_id}
                onChange={(e) => setLotacaoForm({ ...lotacaoForm, school_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione a escola</option>
                {schools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              {/* Função */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Função</label>
                <select
                  value={lotacaoForm.funcao}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, funcao: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  {Object.entries(FUNCOES).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              
              {/* Turno */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turno</label>
                <select
                  value={lotacaoForm.turno}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, turno: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selecione</option>
                  {Object.entries(TURNOS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              {/* Data Início */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data Início *</label>
                <input
                  type="date"
                  value={lotacaoForm.data_inicio}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, data_inicio: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              
              {/* Carga Horária */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Carga Horária</label>
                <input
                  type="number"
                  value={lotacaoForm.carga_horaria}
                  onChange={(e) => setLotacaoForm({ ...lotacaoForm, carga_horaria: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Horas semanais"
                />
              </div>
            </div>
            
            {/* Botões */}
            <div className="flex gap-2 pt-4 border-t">
              <Button onClick={handleSaveLotacao} disabled={saving} className="flex-1">
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
              <Button variant="outline" onClick={() => setShowLotacaoModal(false)}>Cancelar</Button>
            </div>
          </div>
        </Modal>
        
        {/* Modal Alocação */}
        <Modal
          isOpen={showAlocacaoModal}
          onClose={() => setShowAlocacaoModal(false)}
          title="Nova Alocação de Professor"
        >
          <div className="space-y-4">
            {/* Professor */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Professor *</label>
              <select
                value={alocacaoForm.staff_id}
                onChange={(e) => setAlocacaoForm({ ...alocacaoForm, staff_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione o professor</option>
                {professors.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.user?.full_name} - {s.matricula}
                  </option>
                ))}
              </select>
            </div>
            
            {/* Escola */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Escola *</label>
              <select
                value={alocacaoForm.school_id}
                onChange={(e) => setAlocacaoForm({ ...alocacaoForm, school_id: e.target.value, class_id: '' })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione a escola</option>
                {schools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            
            {/* Turma */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Turma *</label>
              <select
                value={alocacaoForm.class_id}
                onChange={(e) => setAlocacaoForm({ ...alocacaoForm, class_id: e.target.value })}
                disabled={!alocacaoForm.school_id}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Selecione a turma</option>
                {filteredClasses.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            
            {/* Componente */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular *</label>
              <select
                value={alocacaoForm.course_id}
                onChange={(e) => setAlocacaoForm({ ...alocacaoForm, course_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione o componente</option>
                {courses.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            
            {/* Carga Horária */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Carga Horária Semanal</label>
              <input
                type="number"
                value={alocacaoForm.carga_horaria_semanal}
                onChange={(e) => setAlocacaoForm({ ...alocacaoForm, carga_horaria_semanal: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Aulas por semana"
              />
            </div>
            
            {/* Botões */}
            <div className="flex gap-2 pt-4 border-t">
              <Button onClick={handleSaveAlocacao} disabled={saving} className="flex-1">
                {saving ? 'Salvando...' : 'Salvar'}
              </Button>
              <Button variant="outline" onClick={() => setShowAlocacaoModal(false)}>Cancelar</Button>
            </div>
          </div>
        </Modal>
        
        {/* Modal Detalhes */}
        <Modal
          isOpen={showDetailModal}
          onClose={() => setShowDetailModal(false)}
          title="Detalhes do Servidor"
          size="lg"
        >
          {selectedStaff && (
            <div className="space-y-4 max-h-[70vh] overflow-y-auto">
              {/* Info básica */}
              <div className="p-4 bg-gray-50 rounded-lg">
                <h3 className="font-bold text-lg text-gray-900">{selectedStaff.user?.full_name}</h3>
                <p className="text-gray-600">{selectedStaff.user?.email}</p>
                <div className="mt-2 flex gap-2">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_SERVIDOR[selectedStaff.status]?.color}`}>
                    {STATUS_SERVIDOR[selectedStaff.status]?.label}
                  </span>
                  <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    {CARGOS[selectedStaff.cargo]}
                  </span>
                </div>
              </div>
              
              {/* Dados funcionais */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-sm text-gray-500">Matrícula</span>
                  <p className="font-medium">{selectedStaff.matricula}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Tipo de Vínculo</span>
                  <p className="font-medium">{TIPOS_VINCULO[selectedStaff.tipo_vinculo]}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Data de Admissão</span>
                  <p className="font-medium">{selectedStaff.data_admissao || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Carga Horária</span>
                  <p className="font-medium">{selectedStaff.carga_horaria_semanal ? `${selectedStaff.carga_horaria_semanal}h/semana` : '-'}</p>
                </div>
              </div>
              
              {/* Formação (para professores) */}
              {selectedStaff.cargo === 'professor' && (
                <div className="p-4 bg-blue-50 rounded-lg">
                  <h4 className="font-medium text-blue-900 mb-2 flex items-center gap-2">
                    <GraduationCap size={18} />
                    Formação
                  </h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-sm text-gray-500">Formação</span>
                      <p className="font-medium">{selectedStaff.formacao || '-'}</p>
                    </div>
                    <div>
                      <span className="text-sm text-gray-500">Especialização</span>
                      <p className="font-medium">{selectedStaff.especializacao || '-'}</p>
                    </div>
                  </div>
                </div>
              )}
              
              {/* Lotações */}
              {selectedStaff.lotacoes?.length > 0 && (
                <div className="p-4 bg-green-50 rounded-lg">
                  <h4 className="font-medium text-green-900 mb-2 flex items-center gap-2">
                    <Building2 size={18} />
                    Lotações
                  </h4>
                  <div className="space-y-2">
                    {selectedStaff.lotacoes.map(lot => (
                      <div key={lot.id} className="p-2 bg-white rounded border">
                        <div className="flex justify-between items-start">
                          <div>
                            <p className="font-medium">{lot.school_name}</p>
                            <p className="text-sm text-gray-600">{FUNCOES[lot.funcao]} • {TURNOS[lot.turno] || '-'}</p>
                          </div>
                          <span className={`px-2 py-1 rounded-full text-xs ${
                            lot.status === 'ativo' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                          }`}>
                            {lot.status === 'ativo' ? 'Ativo' : 'Encerrado'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Alocações (para professores) */}
              {selectedStaff.alocacoes?.length > 0 && (
                <div className="p-4 bg-purple-50 rounded-lg">
                  <h4 className="font-medium text-purple-900 mb-2 flex items-center gap-2">
                    <BookOpen size={18} />
                    Turmas/Componentes
                  </h4>
                  <div className="space-y-2">
                    {selectedStaff.alocacoes.map(aloc => (
                      <div key={aloc.id} className="p-2 bg-white rounded border">
                        <p className="font-medium">{aloc.class_name}</p>
                        <p className="text-sm text-gray-600">{aloc.course_name}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              <Button variant="outline" onClick={() => setShowDetailModal(false)} className="w-full">
                Fechar
              </Button>
            </div>
          )}
        </Modal>
        
        {/* Modal Excluir */}
        <Modal
          isOpen={showDeleteModal}
          onClose={() => setShowDeleteModal(false)}
          title="Confirmar Exclusão"
        >
          <div className="space-y-4">
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <div className="flex items-start gap-3">
                <AlertTriangle className="text-red-500 mt-0.5" size={20} />
                <div>
                  <div className="font-medium text-red-800">Tem certeza que deseja excluir?</div>
                  <div className="text-sm text-red-600 mt-1">Esta ação não pode ser desfeita.</div>
                </div>
              </div>
            </div>
            
            <div className="flex gap-2">
              <Button 
                onClick={confirmDelete} 
                disabled={deleting}
                className="flex-1 bg-red-600 hover:bg-red-700"
              >
                {deleting ? 'Excluindo...' : 'Sim, Excluir'}
              </Button>
              <Button variant="outline" onClick={() => setShowDeleteModal(false)}>Cancelar</Button>
            </div>
          </div>
        </Modal>
      </div>
    </Layout>
  );
};

export default Staff;
