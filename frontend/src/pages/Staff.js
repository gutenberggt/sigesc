import { useState, useEffect, useMemo, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
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
  AlertTriangle,
  XCircle,
  Home,
  GraduationCap,
  Briefcase,
  Plus,
  Minus,
  Phone,
  Camera,
  User,
  BookOpen
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { staffAPI, schoolAssignmentAPI, teacherAssignmentAPI, schoolsAPI, classesAPI, coursesAPI } from '@/services/api';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const CARGOS = {
  professor: 'Professor',
  diretor: 'Diretor',
  coordenador: 'Coordenador',
  secretario: 'Secretário',
  auxiliar_secretaria: 'Auxiliar de Secretaria',
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

const SEXOS = {
  masculino: 'Masculino',
  feminino: 'Feminino',
  outro: 'Outro'
};

const COR_RACA = {
  branca: 'Branca',
  preta: 'Preta',
  parda: 'Parda',
  amarela: 'Amarela',
  indigena: 'Indígena',
  nao_declarado: 'Não Declarado'
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
  const fileInputRef = useRef(null);
  
  // Estados principais
  const [loading, setLoading] = useState(true);
  const [staffList, setStaffList] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  
  // Filtros
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCargo, setFilterCargo] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSchool, setFilterSchool] = useState('');
  
  // Abas
  const [activeTab, setActiveTab] = useState('servidores');
  
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
  const [deleteType, setDeleteType] = useState('');
  
  // Lotações e Alocações
  const [lotacoes, setLotacoes] = useState([]);
  const [alocacoes, setAlocacoes] = useState([]);
  
  // Form states - Servidor
  const [staffForm, setStaffForm] = useState({
    nome: '',
    foto_url: '',
    data_nascimento: '',
    sexo: '',
    cor_raca: '',
    celular: '',
    email: '',
    cargo: 'professor',
    cargo_especifico: '',
    tipo_vinculo: 'efetivo',
    data_admissao: '',
    carga_horaria_semanal: '',
    formacoes: [],
    especializacoes: [],
    status: 'ativo',
    motivo_afastamento: '',
    data_afastamento: '',
    previsao_retorno: '',
    observacoes: ''
  });
  
  // Campos temporários para formação/especialização
  const [novaFormacao, setNovaFormacao] = useState('');
  const [novaEspecializacao, setNovaEspecializacao] = useState('');
  
  // Preview da foto
  const [fotoPreview, setFotoPreview] = useState(null);
  const [fotoFile, setFotoFile] = useState(null);
  
  const [lotacaoForm, setLotacaoForm] = useState({
    staff_id: '',
    funcao: 'professor',
    data_inicio: new Date().toISOString().split('T')[0],
    turno: '',
    status: 'ativo',
    academic_year: academicYear,
    observacoes: ''
  });
  
  // Lista de escolas selecionadas para lotação
  const [lotacaoEscolas, setLotacaoEscolas] = useState([]);
  const [selectedLotacaoSchool, setSelectedLotacaoSchool] = useState('');
  
  const [alocacaoForm, setAlocacaoForm] = useState({
    staff_id: '',
    school_id: '',
    academic_year: academicYear,
    status: 'ativo',
    observacoes: ''
  });
  
  // Listas de turmas e componentes selecionados para alocação
  const [alocacaoTurmas, setAlocacaoTurmas] = useState([]);
  const [alocacaoComponentes, setAlocacaoComponentes] = useState([]);
  const [selectedAlocacaoClass, setSelectedAlocacaoClass] = useState('');
  const [selectedAlocacaoComponent, setSelectedAlocacaoComponent] = useState('');
  const [cargaHorariaTotal, setCargaHorariaTotal] = useState(0);
  
  // Escolas do professor selecionado para alocação
  const [professorSchools, setProfessorSchools] = useState([]);
  const [loadingProfessorSchools, setLoadingProfessorSchools] = useState(false);
  
  // Lotações e Alocações existentes do servidor selecionado
  const [existingLotacoes, setExistingLotacoes] = useState([]);
  const [existingAlocacoes, setExistingAlocacoes] = useState([]);
  const [loadingExisting, setLoadingExisting] = useState(false);
  
  // Carga horária do professor e validação
  const [professorCargaHoraria, setProfessorCargaHoraria] = useState(0);
  const [cargaHorariaExistente, setCargaHorariaExistente] = useState(0);
  
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
      const [schoolsData, classesData, coursesData] = await Promise.all([
        schoolsAPI.list(),
        classesAPI.list(),
        coursesAPI.list()
      ]);
      setSchools(schoolsData);
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
        s.nome?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.matricula?.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCargo = !filterCargo || s.cargo === filterCargo;
      const matchesStatus = !filterStatus || s.status === filterStatus;
      return matchesSearch && matchesCargo && matchesStatus;
    });
  }, [staffList, searchTerm, filterCargo, filterStatus]);
  
  // Professores para alocação
  const professors = useMemo(() => {
    return staffList.filter(s => s.cargo === 'professor' && s.status === 'ativo');
  }, [staffList]);
  
  // Turmas filtradas por escola
  const filteredClasses = useMemo(() => {
    if (!alocacaoForm.school_id) return [];
    return classes.filter(c => c.school_id === alocacaoForm.school_id);
  }, [classes, alocacaoForm.school_id]);
  
  // Carregar escolas do professor quando selecionado
  const loadProfessorSchools = async (staffId) => {
    if (!staffId) {
      setProfessorSchools([]);
      return;
    }
    
    setLoadingProfessorSchools(true);
    try {
      const schoolsData = await schoolAssignmentAPI.getStaffSchools(staffId, academicYear);
      setProfessorSchools(schoolsData);
      
      if (schoolsData.length === 0) {
        showAlertMessage('error', 'Este professor não possui lotação ativa. Faça a lotação primeiro.');
      }
    } catch (error) {
      console.error('Erro ao carregar escolas do professor:', error);
      setProfessorSchools([]);
    } finally {
      setLoadingProfessorSchools(false);
    }
  };
  
  // Carregar lotações existentes do servidor
  const loadExistingLotacoes = async (staffId) => {
    if (!staffId) {
      setExistingLotacoes([]);
      return;
    }
    
    setLoadingExisting(true);
    try {
      const data = await schoolAssignmentAPI.list({ 
        staff_id: staffId, 
        academic_year: academicYear,
        status: 'ativo'
      });
      setExistingLotacoes(data);
    } catch (error) {
      console.error('Erro ao carregar lotações existentes:', error);
      setExistingLotacoes([]);
    } finally {
      setLoadingExisting(false);
    }
  };
  
  // Carregar alocações existentes do professor
  const loadExistingAlocacoes = async (staffId) => {
    if (!staffId) {
      setExistingAlocacoes([]);
      return;
    }
    
    setLoadingExisting(true);
    try {
      const data = await teacherAssignmentAPI.list({ 
        staff_id: staffId, 
        academic_year: academicYear,
        status: 'ativo'
      });
      setExistingAlocacoes(data);
      
      // Calcular carga horária existente baseada nos componentes
      // Precisamos buscar o workload de cada componente
      const cargaExistente = data.reduce((sum, aloc) => {
        const courseData = courses.find(c => c.id === aloc.course_id);
        const workload = courseData?.workload || 0;
        return sum + (workload / 40);
      }, 0);
      setCargaHorariaExistente(cargaExistente);
    } catch (error) {
      console.error('Erro ao carregar alocações existentes:', error);
      setExistingAlocacoes([]);
      setCargaHorariaExistente(0);
    } finally {
      setLoadingExisting(false);
    }
  };
  
  // Excluir lotação existente
  const handleDeleteExistingLotacao = async (lotacaoId) => {
    try {
      await schoolAssignmentAPI.delete(lotacaoId);
      showAlertMessage('success', 'Lotação excluída!');
      // Recarregar as lotações existentes
      await loadExistingLotacoes(lotacaoForm.staff_id);
      // Recarregar a lista geral se estiver na aba de lotações
      if (activeTab === 'lotacoes') {
        loadLotacoes();
      }
    } catch (error) {
      console.error('Erro ao excluir lotação:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao excluir lotação');
    }
  };
  
  // Excluir alocação existente (por componente)
  const handleDeleteExistingAlocacao = async (alocacaoId) => {
    try {
      await teacherAssignmentAPI.delete(alocacaoId);
      showAlertMessage('success', 'Alocação excluída!');
      // Recarregar as alocações existentes
      await loadExistingAlocacoes(alocacaoForm.staff_id);
      // Recarregar a lista geral se estiver na aba de alocações
      if (activeTab === 'alocacoes') {
        loadAlocacoes();
      }
    } catch (error) {
      console.error('Erro ao excluir alocação:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao excluir alocação');
    }
  };
  
  // Excluir todas alocações de uma turma
  const handleDeleteTurmaAlocacoes = async (classId) => {
    const alocacoesDaTurma = existingAlocacoes.filter(a => a.class_id === classId);
    
    try {
      for (const aloc of alocacoesDaTurma) {
        await teacherAssignmentAPI.delete(aloc.id);
      }
      showAlertMessage('success', `${alocacoesDaTurma.length} alocação(ões) da turma excluída(s)!`);
      // Recarregar as alocações existentes
      await loadExistingAlocacoes(alocacaoForm.staff_id);
      // Recarregar a lista geral se estiver na aba de alocações
      if (activeTab === 'alocacoes') {
        loadAlocacoes();
      }
    } catch (error) {
      console.error('Erro ao excluir alocações da turma:', error);
      showAlertMessage('error', 'Erro ao excluir alocações da turma');
    }
  };
  
  // Agrupar alocações por turma
  const groupedAlocacoes = useMemo(() => {
    const grouped = {};
    existingAlocacoes.forEach(aloc => {
      if (!grouped[aloc.class_id]) {
        grouped[aloc.class_id] = {
          class_id: aloc.class_id,
          class_name: aloc.class_name,
          school_name: aloc.school_name,
          componentes: []
        };
      }
      grouped[aloc.class_id].componentes.push(aloc);
    });
    return Object.values(grouped);
  }, [existingAlocacoes]);
  
  // Formatar celular para WhatsApp
  const formatWhatsAppLink = (celular) => {
    if (!celular) return null;
    const numero = celular.replace(/\D/g, '');
    const numeroCompleto = numero.startsWith('55') ? numero : `55${numero}`;
    return `https://wa.me/${numeroCompleto}`;
  };
  
  // Handlers de foto
  const handleFotoClick = () => {
    fileInputRef.current?.click();
  };
  
  const handleFotoChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setFotoFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setFotoPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };
  
  // Handlers de formação
  const addFormacao = () => {
    if (novaFormacao.trim()) {
      setStaffForm({
        ...staffForm,
        formacoes: [...(staffForm.formacoes || []), novaFormacao.trim()]
      });
      setNovaFormacao('');
    }
  };
  
  const removeFormacao = (index) => {
    const newFormacoes = [...staffForm.formacoes];
    newFormacoes.splice(index, 1);
    setStaffForm({ ...staffForm, formacoes: newFormacoes });
  };
  
  const addEspecializacao = () => {
    if (novaEspecializacao.trim()) {
      setStaffForm({
        ...staffForm,
        especializacoes: [...(staffForm.especializacoes || []), novaEspecializacao.trim()]
      });
      setNovaEspecializacao('');
    }
  };
  
  const removeEspecializacao = (index) => {
    const newEspecializacoes = [...staffForm.especializacoes];
    newEspecializacoes.splice(index, 1);
    setStaffForm({ ...staffForm, especializacoes: newEspecializacoes });
  };
  
  // ===== HANDLERS =====
  
  const handleNewStaff = () => {
    setEditingStaff(null);
    setStaffForm({
      nome: '',
      foto_url: '',
      data_nascimento: '',
      sexo: '',
      cor_raca: '',
      celular: '',
      email: '',
      cargo: 'professor',
      cargo_especifico: '',
      tipo_vinculo: 'efetivo',
      data_admissao: '',
      carga_horaria_semanal: '',
      formacoes: [],
      especializacoes: [],
      status: 'ativo',
      motivo_afastamento: '',
      data_afastamento: '',
      previsao_retorno: '',
      observacoes: ''
    });
    setFotoPreview(null);
    setFotoFile(null);
    setNovaFormacao('');
    setNovaEspecializacao('');
    setShowStaffModal(true);
  };
  
  const handleEditStaff = (staff) => {
    setEditingStaff(staff);
    setStaffForm({
      nome: staff.nome || '',
      foto_url: staff.foto_url || '',
      data_nascimento: staff.data_nascimento || '',
      sexo: staff.sexo || '',
      cor_raca: staff.cor_raca || '',
      celular: staff.celular || '',
      email: staff.email || '',
      cargo: staff.cargo || 'professor',
      cargo_especifico: staff.cargo_especifico || '',
      tipo_vinculo: staff.tipo_vinculo || 'efetivo',
      data_admissao: staff.data_admissao || '',
      carga_horaria_semanal: staff.carga_horaria_semanal || '',
      formacoes: staff.formacoes || [],
      especializacoes: staff.especializacoes || [],
      status: staff.status || 'ativo',
      motivo_afastamento: staff.motivo_afastamento || '',
      data_afastamento: staff.data_afastamento || '',
      previsao_retorno: staff.previsao_retorno || '',
      observacoes: staff.observacoes || ''
    });
    setFotoPreview(staff.foto_url ? `${API_URL}${staff.foto_url}` : null);
    setFotoFile(null);
    setNovaFormacao('');
    setNovaEspecializacao('');
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
    if (!staffForm.nome || !staffForm.cargo) {
      showAlertMessage('error', 'Preencha os campos obrigatórios (Nome e Cargo)');
      return;
    }
    
    setSaving(true);
    try {
      const data = {
        ...staffForm,
        carga_horaria_semanal: staffForm.carga_horaria_semanal ? parseInt(staffForm.carga_horaria_semanal) : null
      };
      
      let savedStaff;
      if (editingStaff) {
        savedStaff = await staffAPI.update(editingStaff.id, data);
        showAlertMessage('success', 'Servidor atualizado!');
      } else {
        savedStaff = await staffAPI.create(data);
        showAlertMessage('success', `Servidor cadastrado! Matrícula: ${savedStaff.matricula}`);
      }
      
      // Upload da foto se houver
      if (fotoFile && savedStaff?.id) {
        try {
          await staffAPI.uploadPhoto(savedStaff.id, fotoFile);
        } catch (photoError) {
          console.error('Erro ao fazer upload da foto:', photoError);
        }
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
  const handleNewLotacao = async (staff = null) => {
    const staffId = staff?.id || '';
    setLotacaoForm({
      staff_id: staffId,
      funcao: staff?.cargo === 'professor' ? 'professor' : 'apoio',
      data_inicio: new Date().toISOString().split('T')[0],
      turno: '',
      status: 'ativo',
      academic_year: academicYear,
      observacoes: ''
    });
    setLotacaoEscolas([]);
    setSelectedLotacaoSchool('');
    setExistingLotacoes([]);
    
    // Carregar lotações existentes se tiver um servidor
    if (staffId) {
      await loadExistingLotacoes(staffId);
    }
    
    setShowLotacaoModal(true);
  };
  
  // Handler para quando o servidor é alterado no modal de lotação
  const handleLotacaoStaffChange = async (staffId) => {
    const staff = staffList.find(s => s.id === staffId);
    setLotacaoForm({ 
      ...lotacaoForm, 
      staff_id: staffId,
      funcao: staff?.cargo === 'professor' ? 'professor' : 'apoio'
    });
    setExistingLotacoes([]);
    
    if (staffId) {
      await loadExistingLotacoes(staffId);
    }
  };
  
  // Adicionar escola à lista de lotação
  const addEscolaLotacao = () => {
    if (!selectedLotacaoSchool) return;
    
    const escola = schools.find(s => s.id === selectedLotacaoSchool);
    if (!escola) return;
    
    // Verificar se já está na lista
    if (lotacaoEscolas.find(e => e.id === escola.id)) {
      showAlertMessage('error', 'Escola já adicionada');
      return;
    }
    
    setLotacaoEscolas([...lotacaoEscolas, escola]);
    setSelectedLotacaoSchool('');
  };
  
  // Remover escola da lista de lotação
  const removeEscolaLotacao = (schoolId) => {
    setLotacaoEscolas(lotacaoEscolas.filter(e => e.id !== schoolId));
  };
  
  const handleSaveLotacao = async () => {
    if (!lotacaoForm.staff_id || lotacaoEscolas.length === 0 || !lotacaoForm.data_inicio) {
      showAlertMessage('error', 'Selecione o servidor e adicione pelo menos uma escola');
      return;
    }
    
    setSaving(true);
    try {
      // Criar uma lotação para cada escola selecionada
      for (const escola of lotacaoEscolas) {
        const data = {
          ...lotacaoForm,
          school_id: escola.id
        };
        
        try {
          await schoolAssignmentAPI.create(data);
        } catch (err) {
          // Ignora erro de duplicação, continua com as outras
          console.log(`Lotação para ${escola.name}: ${err.response?.data?.detail || 'erro'}`);
        }
      }
      
      showAlertMessage('success', `${lotacaoEscolas.length} lotação(ões) criada(s)!`);
      setShowLotacaoModal(false);
      loadLotacoes();
    } catch (error) {
      console.error('Erro ao salvar lotações:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao salvar lotações');
    } finally {
      setSaving(false);
    }
  };
  
  // Alocação handlers
  const handleNewAlocacao = async (staff = null) => {
    const staffId = staff?.id || '';
    setAlocacaoForm({
      staff_id: staffId,
      school_id: '',
      academic_year: academicYear,
      status: 'ativo',
      observacoes: ''
    });
    setAlocacaoTurmas([]);
    setAlocacaoComponentes([]);
    setSelectedAlocacaoClass('');
    setSelectedAlocacaoComponent('');
    setCargaHorariaTotal(0);
    setProfessorSchools([]);
    setExistingAlocacoes([]);
    setCargaHorariaExistente(0);
    
    // Se já tem um professor, carregar os dados dele
    if (staffId) {
      // Buscar a carga horária semanal do professor
      const professor = staffList.find(s => s.id === staffId);
      setProfessorCargaHoraria(professor?.carga_horaria_semanal || 0);
      
      await Promise.all([
        loadProfessorSchools(staffId),
        loadExistingAlocacoes(staffId)
      ]);
    } else {
      setProfessorCargaHoraria(0);
    }
    
    setShowAlocacaoModal(true);
  };
  
  // Handler para quando o professor é alterado no dropdown
  const handleProfessorChange = async (staffId) => {
    setAlocacaoForm({ 
      ...alocacaoForm, 
      staff_id: staffId,
      school_id: ''
    });
    setAlocacaoTurmas([]);
    setAlocacaoComponentes([]);
    setCargaHorariaTotal(0);
    setExistingAlocacoes([]);
    setCargaHorariaExistente(0);
    
    if (staffId) {
      // Buscar a carga horária semanal do professor
      const professor = staffList.find(s => s.id === staffId);
      setProfessorCargaHoraria(professor?.carga_horaria_semanal || 0);
      
      await Promise.all([
        loadProfessorSchools(staffId),
        loadExistingAlocacoes(staffId)
      ]);
    } else {
      setProfessorCargaHoraria(0);
    }
  };
  
  // Handler para quando a escola é alterada
  const handleAlocacaoSchoolChange = (schoolId) => {
    setAlocacaoForm({ ...alocacaoForm, school_id: schoolId });
    setAlocacaoTurmas([]);
    setAlocacaoComponentes([]);
    setSelectedAlocacaoClass('');
    setSelectedAlocacaoComponent('');
    setCargaHorariaTotal(0);
  };
  
  // Adicionar turma à lista de alocação
  const addTurmaAlocacao = () => {
    if (!selectedAlocacaoClass) return;
    
    const turma = filteredClasses.find(c => c.id === selectedAlocacaoClass);
    if (!turma) return;
    
    // Verificar se já está na lista
    if (alocacaoTurmas.find(t => t.id === turma.id)) {
      showAlertMessage('error', 'Turma já adicionada');
      return;
    }
    
    setAlocacaoTurmas([...alocacaoTurmas, turma]);
    setSelectedAlocacaoClass('');
  };
  
  // Remover turma da lista de alocação
  const removeTurmaAlocacao = (classId) => {
    setAlocacaoTurmas(alocacaoTurmas.filter(t => t.id !== classId));
  };
  
  // Adicionar componente à lista de alocação
  const addComponenteAlocacao = () => {
    if (!selectedAlocacaoComponent) return;
    
    // Se selecionou "Todos"
    if (selectedAlocacaoComponent === 'TODOS') {
      const novosComponentes = courses.filter(c => !alocacaoComponentes.find(ac => ac.id === c.id));
      if (novosComponentes.length > 0) {
        const todosComponentes = [...alocacaoComponentes, ...novosComponentes];
        setAlocacaoComponentes(todosComponentes);
        // Calcular carga horária
        calcularCargaHoraria(todosComponentes);
      }
      setSelectedAlocacaoComponent('');
      return;
    }
    
    const componente = courses.find(c => c.id === selectedAlocacaoComponent);
    if (!componente) return;
    
    // Verificar se já está na lista
    if (alocacaoComponentes.find(c => c.id === componente.id)) {
      showAlertMessage('error', 'Componente já adicionado');
      return;
    }
    
    const novosComponentes = [...alocacaoComponentes, componente];
    setAlocacaoComponentes(novosComponentes);
    calcularCargaHoraria(novosComponentes);
    setSelectedAlocacaoComponent('');
  };
  
  // Remover componente da lista de alocação
  const removeComponenteAlocacao = (courseId) => {
    const novosComponentes = alocacaoComponentes.filter(c => c.id !== courseId);
    setAlocacaoComponentes(novosComponentes);
    calcularCargaHoraria(novosComponentes);
  };
  
  // Calcular carga horária total (workload / 40)
  const calcularCargaHoraria = (componentes) => {
    const total = componentes.reduce((sum, comp) => {
      const carga = comp.workload || 0;
      return sum + (carga / 40);
    }, 0);
    setCargaHorariaTotal(total);
  };
  
  const handleSaveAlocacao = async () => {
    if (!alocacaoForm.staff_id || !alocacaoForm.school_id || alocacaoTurmas.length === 0 || alocacaoComponentes.length === 0) {
      showAlertMessage('error', 'Selecione o professor, escola, adicione turma(s) e componente(s)');
      return;
    }
    
    setSaving(true);
    let created = 0;
    try {
      // Criar uma alocação para cada combinação turma + componente
      for (const turma of alocacaoTurmas) {
        for (const componente of alocacaoComponentes) {
          const cargaHoraria = componente.workload ? (componente.workload / 40) : null;
          
          const data = {
            staff_id: alocacaoForm.staff_id,
            school_id: alocacaoForm.school_id,
            class_id: turma.id,
            course_id: componente.id,
            academic_year: alocacaoForm.academic_year,
            carga_horaria_semanal: cargaHoraria,
            status: 'ativo'
          };
          
          try {
            await teacherAssignmentAPI.create(data);
            created++;
          } catch (err) {
            console.log(`Alocação ${turma.name} + ${componente.name}: ${err.response?.data?.detail || 'erro'}`);
          }
        }
      }
      
      showAlertMessage('success', `${created} alocação(ões) criada(s)!`);
      setShowAlocacaoModal(false);
      loadAlocacoes();
    } catch (error) {
      console.error('Erro ao salvar alocações:', error);
      showAlertMessage('error', error.response?.data?.detail || 'Erro ao salvar alocações');
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
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Foto</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nome</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Cargo</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Vínculo</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Celular</th>
                      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {filteredStaff.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                          Nenhum servidor encontrado
                        </td>
                      </tr>
                    ) : filteredStaff.map(staff => (
                      <tr key={staff.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center overflow-hidden">
                            {staff.foto_url ? (
                              <img 
                                src={`${API_URL}${staff.foto_url}`} 
                                alt={staff.nome}
                                className="w-full h-full object-cover"
                              />
                            ) : (
                              <User size={20} className="text-gray-400" />
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-gray-900">{staff.nome}</div>
                          <div className="text-xs text-gray-500">Mat: {staff.matricula}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-700">{CARGOS[staff.cargo] || staff.cargo}</td>
                        <td className="px-4 py-3 text-gray-700">{TIPOS_VINCULO[staff.tipo_vinculo] || staff.tipo_vinculo}</td>
                        <td className="px-4 py-3">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_SERVIDOR[staff.status]?.color || 'bg-gray-100'}`}>
                            {STATUS_SERVIDOR[staff.status]?.label || staff.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {staff.celular ? (
                            <a
                              href={formatWhatsAppLink(staff.celular)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 text-green-600 hover:text-green-700"
                            >
                              <Phone size={14} />
                              <span className="text-sm">{staff.celular}</span>
                            </a>
                          ) : (
                            <span className="text-gray-400 text-sm">-</span>
                          )}
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
                          <div className="font-medium text-gray-900">{lot.staff?.nome || lot.staff?.user_name || '-'}</div>
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
            {/* Foto */}
            <div className="flex justify-center">
              <div 
                onClick={handleFotoClick}
                className="w-24 h-24 rounded-full bg-gray-100 border-2 border-dashed border-gray-300 flex items-center justify-center cursor-pointer hover:bg-gray-50 overflow-hidden"
              >
                {fotoPreview ? (
                  <img src={fotoPreview} alt="Preview" className="w-full h-full object-cover" />
                ) : (
                  <div className="text-center">
                    <Camera size={24} className="mx-auto text-gray-400" />
                    <span className="text-xs text-gray-500">Adicionar foto</span>
                  </div>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFotoChange}
                className="hidden"
              />
            </div>
            
            {/* Nome */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo *</label>
              <input
                type="text"
                value={staffForm.nome}
                onChange={(e) => setStaffForm({ ...staffForm, nome: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                placeholder="Nome completo do servidor"
              />
            </div>
            
            {/* Matrícula (apenas visualização se editando) */}
            {editingStaff && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Matrícula</label>
                <input
                  type="text"
                  value={editingStaff.matricula}
                  disabled
                  className="w-full px-3 py-2 border rounded-lg bg-gray-100 text-gray-600"
                />
                <p className="text-xs text-gray-500 mt-1">Matrícula gerada automaticamente</p>
              </div>
            )}
            
            {/* Dados pessoais */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Nascimento</label>
                <input
                  type="date"
                  value={staffForm.data_nascimento}
                  onChange={(e) => setStaffForm({ ...staffForm, data_nascimento: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Sexo</label>
                <select
                  value={staffForm.sexo}
                  onChange={(e) => setStaffForm({ ...staffForm, sexo: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selecione</option>
                  {Object.entries(SEXOS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Cor/Raça</label>
                <select
                  value={staffForm.cor_raca}
                  onChange={(e) => setStaffForm({ ...staffForm, cor_raca: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Selecione</option>
                  {Object.entries(COR_RACA).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
            </div>
            
            {/* Contato */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Celular</label>
                <input
                  type="text"
                  value={staffForm.celular}
                  onChange={(e) => setStaffForm({ ...staffForm, celular: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="(99) 99999-9999"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
                <input
                  type="email"
                  value={staffForm.email}
                  onChange={(e) => setStaffForm({ ...staffForm, email: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="email@exemplo.com"
                />
              </div>
            </div>
            
            {/* Dados funcionais */}
            <div className="grid grid-cols-2 gap-4">
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
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data de Admissão</label>
                <input
                  type="date"
                  value={staffForm.data_admissao}
                  onChange={(e) => setStaffForm({ ...staffForm, data_admissao: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>
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
            </div>
            
            <div className="grid grid-cols-2 gap-4">
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
            
            {/* Formações - com botão de adicionar/remover */}
            <div className="p-4 bg-blue-50 rounded-lg space-y-3">
              <h4 className="font-medium text-blue-900">Formação Acadêmica</h4>
              
              {/* Adicionar formação */}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={novaFormacao}
                  onChange={(e) => setNovaFormacao(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addFormacao())}
                  className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Ex: Licenciatura em Matemática"
                />
                <Button type="button" onClick={addFormacao} size="sm">
                  <Plus size={16} />
                </Button>
              </div>
              
              {/* Lista de formações */}
              {staffForm.formacoes?.length > 0 && (
                <div className="space-y-1">
                  {staffForm.formacoes.map((f, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-white px-3 py-1.5 rounded border">
                      <span className="flex-1 text-sm">{f}</span>
                      <button 
                        type="button"
                        onClick={() => removeFormacao(idx)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Minus size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
              
              {/* Adicionar especialização */}
              <h4 className="font-medium text-blue-900 pt-2">Especializações</h4>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={novaEspecializacao}
                  onChange={(e) => setNovaEspecializacao(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addEspecializacao())}
                  className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
                  placeholder="Ex: Pós-graduação em Educação Especial"
                />
                <Button type="button" onClick={addEspecializacao} size="sm">
                  <Plus size={16} />
                </Button>
              </div>
              
              {/* Lista de especializações */}
              {staffForm.especializacoes?.length > 0 && (
                <div className="space-y-1">
                  {staffForm.especializacoes.map((e, idx) => (
                    <div key={idx} className="flex items-center gap-2 bg-white px-3 py-1.5 rounded border">
                      <span className="flex-1 text-sm">{e}</span>
                      <button 
                        type="button"
                        onClick={() => removeEspecializacao(idx)}
                        className="text-red-500 hover:text-red-700"
                      >
                        <Minus size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
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
            
            {/* Nota sobre matrícula */}
            {!editingStaff && (
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-sm text-green-800">
                  <strong>Nota:</strong> A matrícula será gerada automaticamente após salvar.
                </p>
              </div>
            )}
            
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
          title="Gerenciar Lotações"
        >
          <div className="space-y-4 max-h-[70vh] overflow-y-auto">
            {/* Servidor */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Servidor *</label>
              <select
                value={lotacaoForm.staff_id}
                onChange={(e) => handleLotacaoStaffChange(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione o servidor</option>
                {staffList.filter(s => s.status === 'ativo').map(s => (
                  <option key={s.id} value={s.id}>
                    {s.nome} - {s.matricula} ({CARGOS[s.cargo]})
                  </option>
                ))}
              </select>
            </div>
            
            {/* Lotações existentes */}
            {lotacaoForm.staff_id && (
              <div className="p-4 bg-gray-50 rounded-lg border">
                <h4 className="font-medium text-gray-800 mb-2 flex items-center gap-2">
                  <Building2 size={16} />
                  Lotações Atuais
                  {loadingExisting && <span className="text-gray-400 text-sm">(carregando...)</span>}
                </h4>
                
                {!loadingExisting && existingLotacoes.length === 0 ? (
                  <p className="text-sm text-gray-500 italic">
                    O servidor não está lotado em nenhuma escola.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {existingLotacoes.map(lot => (
                      <div key={lot.id} className="flex items-center gap-2 bg-white px-3 py-2 rounded border">
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-900">{lot.school_name}</p>
                          <p className="text-xs text-gray-500">
                            {FUNCOES[lot.funcao]} • {TURNOS[lot.turno] || 'Sem turno'} • Desde {lot.data_inicio}
                          </p>
                        </div>
                        {canDelete && (
                          <button 
                            type="button"
                            onClick={() => handleDeleteExistingLotacao(lot.id)}
                            className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
                            title="Excluir lotação"
                          >
                            <Minus size={16} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            
            {/* Adicionar nova lotação */}
            {lotacaoForm.staff_id && (
              <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h4 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
                  <Plus size={16} />
                  Adicionar Nova Lotação
                </h4>
                
                {/* Escola com botão + */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Escola(s)</label>
                  <div className="flex gap-2">
                    <select
                      value={selectedLotacaoSchool}
                      onChange={(e) => setSelectedLotacaoSchool(e.target.value)}
                      className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      <option value="">Selecione a escola</option>
                      {schools
                        .filter(s => 
                          !lotacaoEscolas.find(e => e.id === s.id) && 
                          !existingLotacoes.find(l => l.school_id === s.id)
                        )
                        .map(s => (
                          <option key={s.id} value={s.id}>{s.name}</option>
                        ))
                      }
                    </select>
                    <Button type="button" onClick={addEscolaLotacao} disabled={!selectedLotacaoSchool}>
                      <Plus size={16} />
                    </Button>
                  </div>
                  
                  {/* Lista de escolas a serem adicionadas */}
                  {lotacaoEscolas.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {lotacaoEscolas.map(escola => (
                        <div key={escola.id} className="flex items-center gap-2 bg-green-50 px-3 py-2 rounded border border-green-200">
                          <Building2 size={16} className="text-green-600" />
                          <span className="flex-1 text-sm font-medium">{escola.name}</span>
                          <button 
                            type="button"
                            onClick={() => removeEscolaLotacao(escola.id)}
                            className="text-red-500 hover:text-red-700"
                          >
                            <Minus size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                
                <div className="grid grid-cols-2 gap-4 mb-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Função</label>
                    <select
                      value={lotacaoForm.funcao}
                      onChange={(e) => setLotacaoForm({ ...lotacaoForm, funcao: e.target.value })}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      {Object.entries(FUNCOES).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Turno</label>
                    <select
                      value={lotacaoForm.turno}
                      onChange={(e) => setLotacaoForm({ ...lotacaoForm, turno: e.target.value })}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      <option value="">Selecione</option>
                      {Object.entries(TURNOS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Data Início</label>
                  <input
                    type="date"
                    value={lotacaoForm.data_inicio}
                    onChange={(e) => setLotacaoForm({ ...lotacaoForm, data_inicio: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                  />
                </div>
              </div>
            )}
            
            <div className="flex gap-2 pt-4 border-t">
              <Button 
                onClick={handleSaveLotacao} 
                disabled={saving || lotacaoEscolas.length === 0} 
                className="flex-1"
              >
                {saving ? 'Salvando...' : lotacaoEscolas.length > 0 ? `Adicionar ${lotacaoEscolas.length} lotação(ões)` : 'Adicionar Lotação'}
              </Button>
              <Button variant="outline" onClick={() => setShowLotacaoModal(false)}>
                Fechar
              </Button>
            </div>
          </div>
        </Modal>
        
        {/* Modal Alocação */}
        <Modal
          isOpen={showAlocacaoModal}
          onClose={() => setShowAlocacaoModal(false)}
          title="Gerenciar Alocações de Professor"
          size="lg"
        >
          <div className="space-y-4 max-h-[70vh] overflow-y-auto">
            {/* Professor */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Professor *</label>
              <select
                value={alocacaoForm.staff_id}
                onChange={(e) => handleProfessorChange(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecione o professor</option>
                {professors.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.nome} - {s.matricula}
                  </option>
                ))}
              </select>
            </div>
            
            {/* Alocações existentes */}
            {alocacaoForm.staff_id && (
              <div className="p-4 bg-gray-50 rounded-lg border">
                <h4 className="font-medium text-gray-800 mb-2 flex items-center gap-2">
                  <GraduationCap size={16} />
                  Alocações Atuais
                  {loadingExisting && <span className="text-gray-400 text-sm">(carregando...)</span>}
                </h4>
                
                {!loadingExisting && groupedAlocacoes.length === 0 ? (
                  <p className="text-sm text-gray-500 italic">
                    O professor não está alocado em nenhuma turma.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {groupedAlocacoes.map(turma => {
                      // Calcular as somas de carga horária da turma
                      const totalSemanal = turma.componentes.reduce((sum, comp) => {
                        const courseData = courses.find(c => c.id === comp.course_id);
                        const workload = courseData?.workload || 0;
                        return sum + (workload / 40);
                      }, 0);
                      
                      const totalMensal = turma.componentes.reduce((sum, comp) => {
                        const courseData = courses.find(c => c.id === comp.course_id);
                        const workload = courseData?.workload || 0;
                        return sum + (workload / 8);
                      }, 0);
                      
                      return (
                        <div key={turma.class_id} className="bg-white rounded border overflow-hidden">
                          {/* Header da turma */}
                          <div className="flex items-center gap-2 bg-blue-50 px-3 py-2 border-b">
                            <GraduationCap size={16} className="text-blue-600" />
                            <div className="flex-1">
                              <p className="text-sm font-medium text-blue-900">{turma.class_name}</p>
                              <p className="text-xs text-blue-600">
                                {turma.school_name}
                                {totalSemanal > 0 && (
                                  <span className="ml-2 font-medium text-green-700">
                                    ({totalSemanal}h/sem • {totalMensal}h/mês)
                                  </span>
                                )}
                              </p>
                            </div>
                            {canDelete && (
                              <button 
                                type="button"
                                onClick={() => handleDeleteTurmaAlocacoes(turma.class_id)}
                                className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
                                title="Excluir todas alocações desta turma"
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                          
                          {/* Componentes da turma */}
                        <div className="p-2 space-y-1">
                          {turma.componentes.map(comp => {
                            // Buscar o workload do componente na lista de courses
                            const courseData = courses.find(c => c.id === comp.course_id);
                            const workloadTotal = courseData?.workload || 0;
                            const cargaSemanalCalculada = workloadTotal > 0 ? workloadTotal / 40 : null;
                            
                            return (
                              <div key={comp.id} className="flex items-center gap-2 bg-purple-50 px-3 py-1.5 rounded">
                                <BookOpen size={14} className="text-purple-600" />
                                <span className="flex-1 text-sm">
                                  {comp.course_name}
                                  {cargaSemanalCalculada && (
                                    <span className="text-gray-500 ml-1">({cargaSemanalCalculada}h/sem)</span>
                                  )}
                                </span>
                                {canDelete && (
                                  <button 
                                    type="button"
                                    onClick={() => handleDeleteExistingAlocacao(comp.id)}
                                    className="p-0.5 text-red-500 hover:text-red-700"
                                    title="Excluir alocação"
                                  >
                                    <Minus size={14} />
                                  </button>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
            
            {/* Adicionar nova alocação */}
            {alocacaoForm.staff_id && professorSchools.length > 0 && (
              <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h4 className="font-medium text-blue-800 mb-3 flex items-center gap-2">
                  <Plus size={16} />
                  Adicionar Nova Alocação
                </h4>
                
                {/* Escola */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Escola
                    {loadingProfessorSchools && <span className="text-gray-400 ml-2">(carregando...)</span>}
                  </label>
                  <select
                    value={alocacaoForm.school_id}
                    onChange={(e) => handleAlocacaoSchoolChange(e.target.value)}
                    disabled={loadingProfessorSchools}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-gray-100"
                  >
                    <option value="">Selecione a escola</option>
                    {professorSchools.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                
                {/* Série/Ano (Turmas) com botão + */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Série/Ano (Turma)</label>
                  <div className="flex gap-2">
                    <select
                      value={selectedAlocacaoClass}
                      onChange={(e) => setSelectedAlocacaoClass(e.target.value)}
                      disabled={!alocacaoForm.school_id}
                      className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white disabled:bg-gray-100"
                    >
                      <option value="">Selecione a turma</option>
                      {filteredClasses.filter(c => !alocacaoTurmas.find(t => t.id === c.id)).map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                    <Button type="button" onClick={addTurmaAlocacao} disabled={!selectedAlocacaoClass}>
                      <Plus size={16} />
                    </Button>
                  </div>
                  
                  {/* Lista de turmas a serem adicionadas */}
                  {alocacaoTurmas.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {alocacaoTurmas.map(turma => (
                        <div key={turma.id} className="flex items-center gap-2 bg-blue-100 px-3 py-2 rounded border border-blue-300">
                          <GraduationCap size={16} className="text-blue-600" />
                          <span className="flex-1 text-sm font-medium">{turma.name}</span>
                          <button 
                            type="button"
                            onClick={() => removeTurmaAlocacao(turma.id)}
                            className="text-red-500 hover:text-red-700"
                          >
                            <Minus size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                
                {/* Componentes Curriculares com botão + */}
                <div className="mb-3">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Componentes Curriculares</label>
                  <div className="flex gap-2">
                    <select
                      value={selectedAlocacaoComponent}
                      onChange={(e) => setSelectedAlocacaoComponent(e.target.value)}
                      className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                    >
                      <option value="">Selecione o componente</option>
                      <option value="TODOS" className="font-bold">TODOS</option>
                      {courses.filter(c => !alocacaoComponentes.find(ac => ac.id === c.id)).map(c => (
                        <option key={c.id} value={c.id}>
                          {c.name} {c.workload ? `(${c.workload}h)` : ''}
                        </option>
                      ))}
                    </select>
                    <Button type="button" onClick={addComponenteAlocacao} disabled={!selectedAlocacaoComponent}>
                      <Plus size={16} />
                    </Button>
                  </div>
                  
                  {/* Lista de componentes a serem adicionados */}
                  {alocacaoComponentes.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {alocacaoComponentes.map(comp => (
                        <div key={comp.id} className="flex items-center gap-2 bg-purple-100 px-3 py-2 rounded border border-purple-300">
                          <BookOpen size={16} className="text-purple-600" />
                          <span className="flex-1 text-sm font-medium">
                            {comp.name}
                            {comp.workload && (
                              <span className="text-gray-500 ml-1">
                                ({comp.workload}h → {comp.workload / 40}h/sem)
                              </span>
                            )}
                          </span>
                          <button 
                            type="button"
                            onClick={() => removeComponenteAlocacao(comp.id)}
                            className="text-red-500 hover:text-red-700"
                          >
                            <Minus size={16} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                
                {/* Carga Horária Total (calculada automaticamente) */}
                {(alocacaoTurmas.length > 0 && alocacaoComponentes.length > 0) && (
                  <div className="p-3 bg-green-100 border border-green-300 rounded-lg">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="text-sm font-medium text-green-800">Carga Horária Semanal Total:</span>
                        <p className="text-xs text-green-600 mt-0.5">
                          {alocacaoTurmas.length} turma(s) × {alocacaoComponentes.length} componente(s) = {alocacaoTurmas.length * alocacaoComponentes.length} alocações
                        </p>
                      </div>
                      <span className="text-xl font-bold text-green-700">{cargaHorariaTotal}h</span>
                    </div>
                  </div>
                )}
                
                {/* Aviso de carga horária excedida */}
                {alocacaoForm.staff_id && professorCargaHoraria > 0 && (
                  <div className={`p-3 rounded-lg border ${
                    (cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria 
                      ? 'bg-red-50 border-red-300' 
                      : 'bg-blue-50 border-blue-200'
                  }`}>
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-sm font-medium text-gray-700">Resumo da Carga Horária do Professor:</span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center text-sm">
                      <div className="bg-white rounded p-2">
                        <p className="text-gray-500 text-xs">Cadastrada</p>
                        <p className="font-bold text-gray-800">{professorCargaHoraria}h/sem</p>
                      </div>
                      <div className="bg-white rounded p-2">
                        <p className="text-gray-500 text-xs">Já Alocada</p>
                        <p className="font-bold text-blue-600">{cargaHorariaExistente}h/sem</p>
                      </div>
                      <div className="bg-white rounded p-2">
                        <p className="text-gray-500 text-xs">Nova Alocação</p>
                        <p className="font-bold text-green-600">+{cargaHorariaTotal}h/sem</p>
                      </div>
                    </div>
                    <div className="mt-2 pt-2 border-t border-gray-200 flex justify-between items-center">
                      <span className="text-sm text-gray-600">Total após salvar:</span>
                      <span className={`font-bold ${
                        (cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria 
                          ? 'text-red-600' 
                          : 'text-green-600'
                      }`}>
                        {cargaHorariaExistente + cargaHorariaTotal}h / {professorCargaHoraria}h
                      </span>
                    </div>
                    
                    {/* Aviso de excesso */}
                    {(cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria && (
                      <div className="mt-2 p-2 bg-red-100 rounded border border-red-200">
                        <p className="text-sm text-red-800 font-bold flex items-center gap-1">
                          <AlertTriangle size={16} />
                          Não é possível salvar:
                        </p>
                        <ul className="text-xs text-red-700 mt-2 ml-4 list-disc">
                          <li>Aumentar a carga horária semanal no cadastro do professor (aba Servidores)</li>
                          <li>Reduzir o número de turmas ou componentes nesta alocação</li>
                          <li>Remover alocações existentes antes de adicionar novas</li>
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            
            {/* Mensagem se professor não tem lotação */}
            {alocacaoForm.staff_id && professorSchools.length === 0 && !loadingProfessorSchools && (
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-sm text-yellow-800">
                  <strong>Atenção:</strong> Este professor não possui lotação em nenhuma escola. 
                  Vá na aba Lotações para adicionar antes de fazer alocações.
                </p>
              </div>
            )}
            
            <div className="flex gap-2 pt-4 border-t">
              <Button 
                onClick={handleSaveAlocacao} 
                disabled={
                  saving || 
                  alocacaoTurmas.length === 0 || 
                  alocacaoComponentes.length === 0 ||
                  (professorCargaHoraria > 0 && (cargaHorariaExistente + cargaHorariaTotal) > professorCargaHoraria)
                } 
                className="flex-1"
              >
                {saving ? 'Salvando...' : 
                  (alocacaoTurmas.length > 0 && alocacaoComponentes.length > 0) 
                    ? `Adicionar ${alocacaoTurmas.length * alocacaoComponentes.length} alocação(ões)` 
                    : 'Adicionar Alocação'}
              </Button>
              <Button 
                variant="outline" 
                onClick={() => setShowAlocacaoModal(false)}
              >
                Fechar
              </Button>
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
              {/* Info básica com foto */}
              <div className="p-4 bg-gray-50 rounded-lg flex gap-4">
                <div className="w-20 h-20 rounded-full bg-gray-200 flex items-center justify-center overflow-hidden flex-shrink-0">
                  {selectedStaff.foto_url ? (
                    <img 
                      src={`${API_URL}${selectedStaff.foto_url}`} 
                      alt={selectedStaff.nome}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <User size={32} className="text-gray-400" />
                  )}
                </div>
                <div>
                  <h3 className="font-bold text-lg text-gray-900">{selectedStaff.nome}</h3>
                  <p className="text-gray-600">Matrícula: {selectedStaff.matricula}</p>
                  <div className="mt-2 flex gap-2 flex-wrap">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_SERVIDOR[selectedStaff.status]?.color}`}>
                      {STATUS_SERVIDOR[selectedStaff.status]?.label}
                    </span>
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {CARGOS[selectedStaff.cargo]}
                    </span>
                  </div>
                </div>
              </div>
              
              {/* Dados pessoais */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-sm text-gray-500">Celular</span>
                  {selectedStaff.celular ? (
                    <a
                      href={formatWhatsAppLink(selectedStaff.celular)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-green-600 hover:text-green-700 font-medium"
                    >
                      <Phone size={14} />
                      {selectedStaff.celular}
                    </a>
                  ) : (
                    <p className="font-medium">-</p>
                  )}
                </div>
                <div>
                  <span className="text-sm text-gray-500">E-mail</span>
                  <p className="font-medium">{selectedStaff.email || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Data de Nascimento</span>
                  <p className="font-medium">{selectedStaff.data_nascimento || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Sexo</span>
                  <p className="font-medium">{SEXOS[selectedStaff.sexo] || '-'}</p>
                </div>
              </div>
              
              {/* Dados funcionais */}
              <div className="grid grid-cols-2 gap-4">
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
              
              {/* Formações */}
              {(selectedStaff.formacoes?.length > 0 || selectedStaff.especializacoes?.length > 0) && (
                <div className="p-4 bg-blue-50 rounded-lg">
                  <h4 className="font-medium text-blue-900 mb-2 flex items-center gap-2">
                    <GraduationCap size={18} />
                    Formação Acadêmica
                  </h4>
                  {selectedStaff.formacoes?.length > 0 && (
                    <div className="mb-2">
                      <span className="text-sm text-gray-600 font-medium">Formações:</span>
                      <ul className="list-disc list-inside text-sm">
                        {selectedStaff.formacoes.map((f, i) => (
                          <li key={i}>{f}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {selectedStaff.especializacoes?.length > 0 && (
                    <div>
                      <span className="text-sm text-gray-600 font-medium">Especializações:</span>
                      <ul className="list-disc list-inside text-sm">
                        {selectedStaff.especializacoes.map((e, i) => (
                          <li key={i}>{e}</li>
                        ))}
                      </ul>
                    </div>
                  )}
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
              
              {/* Alocações */}
              {selectedStaff.alocacoes?.length > 0 && (
                <div className="p-4 bg-purple-50 rounded-lg">
                  <h4 className="font-medium text-purple-900 mb-2 flex items-center gap-2">
                    <Briefcase size={18} />
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
