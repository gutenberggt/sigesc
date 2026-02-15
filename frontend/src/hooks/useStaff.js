import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { staffAPI, schoolAssignmentAPI, teacherAssignmentAPI, schoolsAPI, classesAPI, coursesAPI } from '@/services/api';
import { INITIAL_STAFF_FORM, INITIAL_LOTACAO_FORM, INITIAL_ALOCACAO_FORM } from '@/components/staff/constants';

export const useStaff = () => {
  const { user } = useAuth();
  const academicYear = new Date().getFullYear();
  
  // Estados principais
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  
  // Dados
  const [staffList, setStaffList] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [lotacoes, setLotacoes] = useState([]);
  const [alocacoes, setAlocacoes] = useState([]);
  
  // Filtros
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCargo, setFilterCargo] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSchool, setFilterSchool] = useState('');
  const [filterYear, setFilterYear] = useState(academicYear.toString());
  const [activeTab, setActiveTab] = useState('servidores');
  
  // Modais
  const [showStaffModal, setShowStaffModal] = useState(false);
  const [showLotacaoModal, setShowLotacaoModal] = useState(false);
  const [showAlocacaoModal, setShowAlocacaoModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  
  // Edição
  const [editingStaff, setEditingStaff] = useState(null);
  const [selectedStaff, setSelectedStaff] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteType, setDeleteType] = useState('');
  
  // Formulários
  const [staffForm, setStaffForm] = useState(INITIAL_STAFF_FORM);
  const [lotacaoForm, setLotacaoForm] = useState(INITIAL_LOTACAO_FORM);
  const [alocacaoForm, setAlocacaoForm] = useState(INITIAL_ALOCACAO_FORM);
  
  // Foto
  const [fotoPreview, setFotoPreview] = useState(null);
  const [fotoFile, setFotoFile] = useState(null);
  
  // Formações
  const [novaFormacao, setNovaFormacao] = useState('');
  const [novaEspecializacao, setNovaEspecializacao] = useState('');
  
  // Lotação multi-escola
  const [lotacaoEscolas, setLotacaoEscolas] = useState([]);
  const [selectedLotacaoSchool, setSelectedLotacaoSchool] = useState('');
  
  // Alocação multi-turma/componente
  const [alocacaoTurmas, setAlocacaoTurmas] = useState([]);
  const [alocacaoComponentes, setAlocacaoComponentes] = useState([]);
  const [selectedAlocacaoClass, setSelectedAlocacaoClass] = useState('');
  const [selectedAlocacaoComponent, setSelectedAlocacaoComponent] = useState('');
  const [cargaHorariaTotal, setCargaHorariaTotal] = useState(0);
  
  // Escolas do professor
  const [professorSchools, setProfessorSchools] = useState([]);
  const [loadingProfessorSchools, setLoadingProfessorSchools] = useState(false);
  
  // Existentes
  const [existingLotacoes, setExistingLotacoes] = useState([]);
  const [existingAlocacoes, setExistingAlocacoes] = useState([]);
  const [loadingExisting, setLoadingExisting] = useState(false);
  
  // Edição de lotação
  const [editingLotacao, setEditingLotacao] = useState(null);
  
  // Carga horária do professor
  const [professorCargaHoraria, setProfessorCargaHoraria] = useState(0);
  const [cargaHorariaExistente, setCargaHorariaExistente] = useState(0);
  
  // Alert
  const [alert, setAlert] = useState({ show: false, type: '', message: '' });
  
  // Permissões
  const canEdit = user?.role === 'admin' || user?.role === 'secretario';
  const canDelete = user?.role === 'admin';
  
  // Helper para extrair mensagem de erro do Pydantic ou string
  const extractErrorMessage = (error) => {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      // Erro de validação Pydantic - extrai a mensagem do primeiro erro
      return detail[0]?.msg || detail[0]?.message || 'Erro de validação';
    }
    if (detail && typeof detail === 'object') {
      return detail.msg || detail.message || 'Erro desconhecido';
    }
    return 'Erro ao processar requisição';
  };
  
  // Alert helper
  const showAlertMessage = useCallback((type, message) => {
    // Garante que message seja sempre uma string
    const safeMessage = typeof message === 'string' ? message : String(message);
    setAlert({ show: true, type, message: safeMessage });
    setTimeout(() => setAlert({ show: false, type: '', message: '' }), 3000);
  }, []);
  
  // ========== CARREGAMENTO DE DADOS ==========
  
  const loadInitialData = useCallback(async () => {
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
  }, []);
  
  const loadStaff = useCallback(async () => {
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
  }, [filterCargo, filterStatus, filterSchool]);
  
  const loadLotacoes = useCallback(async () => {
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
  }, [academicYear, filterSchool]);
  
  const loadAlocacoes = useCallback(async () => {
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
  }, [academicYear, filterSchool]);
  
  const loadProfessorSchools = useCallback(async (staffId) => {
    if (!staffId) {
      setProfessorSchools([]);
      return;
    }
    
    setLoadingProfessorSchools(true);
    try {
      // Buscar escolas de TODAS as lotações ativas (sem filtro de ano)
      const schoolsData = await schoolAssignmentAPI.getStaffSchools(staffId);
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
  }, [showAlertMessage]);
  
  const loadExistingLotacoes = useCallback(async (staffId, yearFilter = null) => {
    if (!staffId) {
      setExistingLotacoes([]);
      return;
    }
    
    setLoadingExisting(true);
    try {
      // Se não tiver filtro de ano, buscar todas as lotações ativas
      const params = { 
        staff_id: staffId, 
        status: 'ativo'
      };
      
      // Aplicar filtro de ano apenas se especificado
      if (yearFilter) {
        params.academic_year = parseInt(yearFilter);
      }
      
      const data = await schoolAssignmentAPI.list(params);
      setExistingLotacoes(data);
    } catch (error) {
      console.error('Erro ao carregar lotações existentes:', error);
      setExistingLotacoes([]);
    } finally {
      setLoadingExisting(false);
    }
  }, []);
  
  const loadExistingAlocacoes = useCallback(async (staffId, yearFilter = null) => {
    if (!staffId) {
      setExistingAlocacoes([]);
      return;
    }
    
    setLoadingExisting(true);
    try {
      // Usar o ano passado como parâmetro ou buscar todas se não especificado
      const params = { 
        staff_id: staffId, 
        status: 'ativo'
      };
      
      if (yearFilter) {
        params.academic_year = yearFilter;
      }
      
      const data = await teacherAssignmentAPI.list(params);
      setExistingAlocacoes(data);
      
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
  }, [courses]);
  
  // Effects
  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);
  
  useEffect(() => {
    if (activeTab === 'servidores') {
      loadStaff();
    } else if (activeTab === 'lotacoes') {
      loadLotacoes();
    } else if (activeTab === 'alocacoes') {
      loadAlocacoes();
    }
  }, [activeTab, filterSchool, loadStaff, loadLotacoes, loadAlocacoes]);
  
  // ========== MEMOS ==========
  
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
  
  const professors = useMemo(() => {
    return staffList.filter(s => s.cargo === 'professor' && s.status === 'ativo');
  }, [staffList]);
  
  const filteredClasses = useMemo(() => {
    if (!alocacaoForm.school_id) return [];
    return classes.filter(c => {
      // Filtrar por escola
      if (c.school_id !== alocacaoForm.school_id) return false;
      
      // Filtrar por ano letivo selecionado
      if (alocacaoForm.academic_year && c.academic_year) {
        if (c.academic_year !== alocacaoForm.academic_year) return false;
      }
      
      return true;
    });
  }, [classes, alocacaoForm.school_id, alocacaoForm.academic_year]);
  
  // Filtrar componentes curriculares com base nas turmas selecionadas e escola
  const filteredCourses = useMemo(() => {
    // Se não há turmas selecionadas, não mostrar componentes
    if (alocacaoTurmas.length === 0) return [];
    
    // Obter a escola selecionada para verificar se tem "Escola Integral"
    const selectedSchool = schools.find(s => s.id === alocacaoForm.school_id);
    const escolaTemIntegral = selectedSchool?.atendimento_integral === true;
    
    // Obter níveis de ensino e séries das turmas selecionadas
    const niveisEnsino = new Set();
    const seriesTurmas = new Set();
    
    alocacaoTurmas.forEach(turma => {
      if (turma.education_level) niveisEnsino.add(turma.education_level);
      if (turma.grade_level) seriesTurmas.add(turma.grade_level);
    });
    
    return courses.filter(curso => {
      // Se for componente de "Escola Integral", só mostrar se a escola tiver essa opção
      if (curso.atendimento_programa === 'atendimento_integral') {
        if (!escolaTemIntegral) return false;
      }
      
      // Verificar se o nível de ensino do componente corresponde às turmas
      if (curso.nivel_ensino && !niveisEnsino.has(curso.nivel_ensino)) {
        return false;
      }
      
      // Se o componente tiver séries específicas, verificar se corresponde às turmas
      if (curso.grade_levels && curso.grade_levels.length > 0) {
        const temSerieCorrespondente = curso.grade_levels.some(serie => seriesTurmas.has(serie));
        if (!temSerieCorrespondente) return false;
      }
      
      return true;
    });
  }, [courses, alocacaoTurmas, alocacaoForm.school_id, schools]);

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
  
  // ========== HANDLERS ==========
  
  const handleDeleteExistingLotacao = useCallback(async (lotacaoId) => {
    try {
      await schoolAssignmentAPI.delete(lotacaoId);
      showAlertMessage('success', 'Lotação excluída!');
      await loadExistingLotacoes(lotacaoForm.staff_id);
      if (activeTab === 'lotacoes') {
        loadLotacoes();
      }
    } catch (error) {
      console.error('Erro ao excluir lotação:', error);
      showAlertMessage('error', extractErrorMessage(error) || 'Erro ao excluir lotação');
    }
  }, [lotacaoForm.staff_id, activeTab, loadExistingLotacoes, loadLotacoes, showAlertMessage]);
  
  const handleDeleteExistingAlocacao = useCallback(async (alocacaoId) => {
    try {
      await teacherAssignmentAPI.delete(alocacaoId);
      showAlertMessage('success', 'Alocação excluída!');
      await loadExistingAlocacoes(alocacaoForm.staff_id);
      if (activeTab === 'alocacoes') {
        loadAlocacoes();
      }
    } catch (error) {
      console.error('Erro ao excluir alocação:', error);
      showAlertMessage('error', extractErrorMessage(error) || 'Erro ao excluir alocação');
    }
  }, [alocacaoForm.staff_id, activeTab, loadExistingAlocacoes, loadAlocacoes, showAlertMessage]);
  
  const handleDeleteTurmaAlocacoes = useCallback(async (classId) => {
    const alocacoesDaTurma = existingAlocacoes.filter(a => a.class_id === classId);
    
    try {
      for (const aloc of alocacoesDaTurma) {
        await teacherAssignmentAPI.delete(aloc.id);
      }
      showAlertMessage('success', `${alocacoesDaTurma.length} alocação(ões) da turma excluída(s)!`);
      await loadExistingAlocacoes(alocacaoForm.staff_id);
      if (activeTab === 'alocacoes') {
        loadAlocacoes();
      }
    } catch (error) {
      console.error('Erro ao excluir alocações da turma:', error);
      showAlertMessage('error', 'Erro ao excluir alocações da turma');
    }
  }, [existingAlocacoes, alocacaoForm.staff_id, activeTab, loadExistingAlocacoes, loadAlocacoes, showAlertMessage]);
  
  // Formação handlers
  const addFormacao = useCallback(() => {
    if (novaFormacao.trim()) {
      setStaffForm(prev => ({
        ...prev,
        formacoes: [...(prev.formacoes || []), novaFormacao.trim()]
      }));
      setNovaFormacao('');
    }
  }, [novaFormacao]);
  
  const removeFormacao = useCallback((index) => {
    setStaffForm(prev => {
      const newFormacoes = [...prev.formacoes];
      newFormacoes.splice(index, 1);
      return { ...prev, formacoes: newFormacoes };
    });
  }, []);
  
  const addEspecializacao = useCallback(() => {
    if (novaEspecializacao.trim()) {
      setStaffForm(prev => ({
        ...prev,
        especializacoes: [...(prev.especializacoes || []), novaEspecializacao.trim()]
      }));
      setNovaEspecializacao('');
    }
  }, [novaEspecializacao]);
  
  const removeEspecializacao = useCallback((index) => {
    setStaffForm(prev => {
      const newEspecializacoes = [...prev.especializacoes];
      newEspecializacoes.splice(index, 1);
      return { ...prev, especializacoes: newEspecializacoes };
    });
  }, []);
  
  // Staff handlers
  const handleNewStaff = useCallback(() => {
    setEditingStaff(null);
    setStaffForm(INITIAL_STAFF_FORM);
    setFotoPreview(null);
    setFotoFile(null);
    setNovaFormacao('');
    setNovaEspecializacao('');
    setShowStaffModal(true);
  }, []);
  
  const handleEditStaff = useCallback((staff) => {
    setEditingStaff(staff);
    setStaffForm({
      nome: staff.nome || '',
      cpf: staff.cpf || '',
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
    const API_URL = process.env.REACT_APP_BACKEND_URL;
    setFotoPreview(staff.foto_url ? `${API_URL}${staff.foto_url}` : null);
    setFotoFile(null);
    setNovaFormacao('');
    setNovaEspecializacao('');
    setShowStaffModal(true);
  }, []);
  
  const handleViewStaff = useCallback(async (staff) => {
    try {
      const fullStaff = await staffAPI.get(staff.id);
      setSelectedStaff(fullStaff);
      setShowDetailModal(true);
    } catch (error) {
      console.error('Erro ao carregar detalhes:', error);
      showAlertMessage('error', 'Erro ao carregar detalhes do servidor');
    }
  }, [showAlertMessage]);
  
  const handleSaveStaff = useCallback(async () => {
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
      showAlertMessage('error', extractErrorMessage(error) || 'Erro ao salvar servidor');
    } finally {
      setSaving(false);
    }
  }, [staffForm, editingStaff, fotoFile, loadStaff, showAlertMessage]);
  
  // Lotação handlers
  const handleNewLotacao = useCallback(async (staff = null) => {
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
    
    if (staffId) {
      await loadExistingLotacoes(staffId);
    }
    
    setShowLotacaoModal(true);
  }, [academicYear, loadExistingLotacoes]);
  
  const handleLotacaoStaffChange = useCallback(async (staffId) => {
    const staff = staffList.find(s => s.id === staffId);
    setLotacaoForm(prev => ({ 
      ...prev, 
      staff_id: staffId,
      funcao: staff?.cargo === 'professor' ? 'professor' : 'apoio'
    }));
    setExistingLotacoes([]);
    
    if (staffId) {
      // Carregar lotações do ano selecionado
      await loadExistingLotacoes(staffId, lotacaoForm.academic_year);
    }
  }, [staffList, loadExistingLotacoes, lotacaoForm.academic_year]);
  
  // Função para mudar o ano letivo e recarregar as lotações
  const handleLotacaoYearChange = useCallback(async (year) => {
    setLotacaoForm(prev => ({ ...prev, academic_year: year }));
    
    // Recarregar lotações do servidor para o ano selecionado
    if (lotacaoForm.staff_id) {
      await loadExistingLotacoes(lotacaoForm.staff_id, year);
    }
  }, [lotacaoForm.staff_id, loadExistingLotacoes]);
  
  const addEscolaLotacao = useCallback(() => {
    if (!selectedLotacaoSchool) return;
    
    const escola = schools.find(s => s.id === selectedLotacaoSchool);
    if (!escola) return;
    
    // Verificar se já existe uma entrada com a mesma escola E mesma função
    if (lotacaoEscolas.find(e => e.id === escola.id && e.funcao === lotacaoForm.funcao)) {
      showAlertMessage('error', 'Esta escola já foi adicionada com esta função');
      return;
    }
    
    // Adicionar escola com a função selecionada
    setLotacaoEscolas(prev => [...prev, { ...escola, funcao: lotacaoForm.funcao }]);
    setSelectedLotacaoSchool('');
  }, [selectedLotacaoSchool, schools, lotacaoEscolas, lotacaoForm.funcao, showAlertMessage]);
  
  const removeEscolaLotacao = useCallback((schoolId, funcao) => {
    setLotacaoEscolas(prev => prev.filter(e => !(e.id === schoolId && e.funcao === funcao)));
  }, []);
  
  const handleSaveLotacao = useCallback(async () => {
    if (!lotacaoForm.staff_id || lotacaoEscolas.length === 0 || !lotacaoForm.data_inicio) {
      showAlertMessage('error', 'Selecione o servidor e adicione pelo menos uma escola');
      return;
    }
    
    setSaving(true);
    try {
      for (const escola of lotacaoEscolas) {
        const data = {
          ...lotacaoForm,
          school_id: escola.id,
          funcao: escola.funcao || lotacaoForm.funcao  // Usar a função salva na escola
        };
        
        try {
          await schoolAssignmentAPI.create(data);
        } catch (err) {
          console.log(`Lotação para ${escola.name}: ${err.response?.data?.detail || 'erro'}`);
        }
      }
      
      showAlertMessage('success', `${lotacaoEscolas.length} lotação(ões) criada(s)!`);
      
      // CORREÇÃO: Atualizar a lista de escolas do professor após criar lotação
      // Isso garante que o modal de alocação reconheça as novas lotações
      const staffIdSaved = lotacaoForm.staff_id;
      await loadProfessorSchools(staffIdSaved);
      
      // Também recarregar as lotações existentes para manter o estado sincronizado
      await loadExistingLotacoes(staffIdSaved);
      
      setShowLotacaoModal(false);
      loadLotacoes();
    } catch (error) {
      console.error('Erro ao salvar lotações:', error);
      showAlertMessage('error', extractErrorMessage(error) || 'Erro ao salvar lotações');
    } finally {
      setSaving(false);
    }
  }, [lotacaoForm, lotacaoEscolas, loadLotacoes, loadProfessorSchools, loadExistingLotacoes, showAlertMessage]);
  
  // Alocação handlers
  const calcularCargaHoraria = useCallback((componentes) => {
    const total = componentes.reduce((sum, comp) => {
      const carga = comp.workload || 0;
      return sum + (carga / 40);
    }, 0);
    setCargaHorariaTotal(total);
  }, []);
  
  const handleNewAlocacao = useCallback(async (staff = null) => {
    const staffId = staff?.id || '';
    
    // Limpar estados primeiro
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
    
    // Mostrar o modal imediatamente, indicando loading
    setShowAlocacaoModal(true);
    
    // Depois carregar os dados do professor selecionado
    if (staffId) {
      const professor = staffList.find(s => s.id === staffId);
      setProfessorCargaHoraria(professor?.carga_horaria_semanal || 0);
      
      // Carregar dados em paralelo
      await Promise.all([
        loadProfessorSchools(staffId),
        loadExistingAlocacoes(staffId)
      ]);
    } else {
      setProfessorCargaHoraria(0);
    }
  }, [academicYear, staffList, loadProfessorSchools, loadExistingAlocacoes]);
  
  const handleProfessorChange = useCallback(async (staffId) => {
    setAlocacaoForm(prev => ({ 
      ...prev, 
      staff_id: staffId,
      school_id: ''
    }));
    setAlocacaoTurmas([]);
    setAlocacaoComponentes([]);
    setCargaHorariaTotal(0);
    setExistingAlocacoes([]);
    setCargaHorariaExistente(0);
    
    if (staffId) {
      const professor = staffList.find(s => s.id === staffId);
      setProfessorCargaHoraria(professor?.carga_horaria_semanal || 0);
      
      await Promise.all([
        loadProfessorSchools(staffId),
        loadExistingAlocacoes(staffId, alocacaoForm.academic_year)
      ]);
    } else {
      setProfessorCargaHoraria(0);
    }
  }, [staffList, loadProfessorSchools, loadExistingAlocacoes, alocacaoForm.academic_year]);
  
  const handleAlocacaoSchoolChange = useCallback((schoolId) => {
    setAlocacaoForm(prev => ({ ...prev, school_id: schoolId }));
    setAlocacaoTurmas([]);
    setAlocacaoComponentes([]);
    setSelectedAlocacaoClass('');
    setSelectedAlocacaoComponent('');
    setCargaHorariaTotal(0);
  }, []);
  
  const handleAlocacaoAcademicYearChange = useCallback(async (year) => {
    setAlocacaoForm(prev => ({ ...prev, academic_year: year }));
    // Limpar turmas e componentes pois podem mudar com o ano
    setAlocacaoTurmas([]);
    setAlocacaoComponentes([]);
    setSelectedAlocacaoClass('');
    setSelectedAlocacaoComponent('');
    setCargaHorariaTotal(0);
    
    // Recarregar alocações existentes do professor para o novo ano
    if (alocacaoForm.staff_id) {
      await loadExistingAlocacoes(alocacaoForm.staff_id, year);
    }
  }, [alocacaoForm.staff_id, loadExistingAlocacoes]);
  
  const addTurmaAlocacao = useCallback(() => {
    if (!selectedAlocacaoClass) return;
    
    const turma = filteredClasses.find(c => c.id === selectedAlocacaoClass);
    if (!turma) return;
    
    if (alocacaoTurmas.find(t => t.id === turma.id)) {
      showAlertMessage('error', 'Turma já adicionada');
      return;
    }
    
    setAlocacaoTurmas(prev => [...prev, turma]);
    setSelectedAlocacaoClass('');
  }, [selectedAlocacaoClass, filteredClasses, alocacaoTurmas, showAlertMessage]);
  
  const removeTurmaAlocacao = useCallback((classId) => {
    setAlocacaoTurmas(prev => prev.filter(t => t.id !== classId));
  }, []);
  
  const addComponenteAlocacao = useCallback(() => {
    if (!selectedAlocacaoComponent) return;
    
    if (selectedAlocacaoComponent === 'TODOS') {
      const novosComponentes = filteredCourses.filter(c => !alocacaoComponentes.find(ac => ac.id === c.id));
      if (novosComponentes.length > 0) {
        const todosComponentes = [...alocacaoComponentes, ...novosComponentes];
        setAlocacaoComponentes(todosComponentes);
        calcularCargaHoraria(todosComponentes);
      }
      setSelectedAlocacaoComponent('');
      return;
    }
    
    const componente = filteredCourses.find(c => c.id === selectedAlocacaoComponent);
    if (!componente) return;
    
    if (alocacaoComponentes.find(c => c.id === componente.id)) {
      showAlertMessage('error', 'Componente já adicionado');
      return;
    }
    
    const novosComponentes = [...alocacaoComponentes, componente];
    setAlocacaoComponentes(novosComponentes);
    calcularCargaHoraria(novosComponentes);
    setSelectedAlocacaoComponent('');
  }, [selectedAlocacaoComponent, filteredCourses, alocacaoComponentes, calcularCargaHoraria, showAlertMessage]);
  
  const removeComponenteAlocacao = useCallback((courseId) => {
    const novosComponentes = alocacaoComponentes.filter(c => c.id !== courseId);
    setAlocacaoComponentes(novosComponentes);
    calcularCargaHoraria(novosComponentes);
  }, [alocacaoComponentes, calcularCargaHoraria]);
  
  const handleSaveAlocacao = useCallback(async () => {
    if (!alocacaoForm.staff_id || !alocacaoForm.school_id || alocacaoTurmas.length === 0 || alocacaoComponentes.length === 0) {
      showAlertMessage('error', 'Selecione o professor, escola, adicione turma(s) e componente(s)');
      return;
    }
    
    setSaving(true);
    let created = 0;
    try {
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
      showAlertMessage('error', extractErrorMessage(error) || 'Erro ao salvar alocações');
    } finally {
      setSaving(false);
    }
  }, [alocacaoForm, alocacaoTurmas, alocacaoComponentes, loadAlocacoes, showAlertMessage]);
  
  // Delete handlers
  const handleDelete = useCallback((item, type) => {
    setDeleteTarget(item);
    setDeleteType(type);
    setShowDeleteModal(true);
  }, []);
  
  const confirmDelete = useCallback(async () => {
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
      showAlertMessage('error', extractErrorMessage(error) || 'Erro ao excluir');
    } finally {
      setDeleting(false);
    }
  }, [deleteType, deleteTarget, loadStaff, loadLotacoes, loadAlocacoes, showAlertMessage]);
  
  const handleEncerrarLotacao = useCallback(async (lotacao) => {
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
  }, [loadLotacoes, showAlertMessage]);
  
  return {
    // Estados
    loading,
    saving,
    deleting,
    staffList,
    schools,
    classes,
    courses,
    lotacoes,
    alocacoes,
    
    // Filtros
    searchTerm,
    setSearchTerm,
    filterCargo,
    setFilterCargo,
    filterStatus,
    setFilterStatus,
    filterSchool,
    setFilterSchool,
    filterYear,
    setFilterYear,
    activeTab,
    setActiveTab,
    
    // Memos
    filteredStaff,
    professors,
    filteredClasses,
    filteredCourses,
    groupedAlocacoes,
    
    // Modais
    showStaffModal,
    setShowStaffModal,
    showLotacaoModal,
    setShowLotacaoModal,
    showAlocacaoModal,
    setShowAlocacaoModal,
    showDetailModal,
    setShowDetailModal,
    showDeleteModal,
    setShowDeleteModal,
    
    // Edição
    editingStaff,
    selectedStaff,
    deleteTarget,
    deleteType,
    
    // Formulários
    staffForm,
    setStaffForm,
    lotacaoForm,
    setLotacaoForm,
    alocacaoForm,
    setAlocacaoForm,
    
    // Foto
    fotoPreview,
    setFotoPreview,
    fotoFile,
    setFotoFile,
    
    // Formações
    novaFormacao,
    setNovaFormacao,
    novaEspecializacao,
    setNovaEspecializacao,
    addFormacao,
    removeFormacao,
    addEspecializacao,
    removeEspecializacao,
    
    // Lotação
    lotacaoEscolas,
    selectedLotacaoSchool,
    setSelectedLotacaoSchool,
    existingLotacoes,
    loadingExisting,
    addEscolaLotacao,
    removeEscolaLotacao,
    
    // Alocação
    alocacaoTurmas,
    alocacaoComponentes,
    selectedAlocacaoClass,
    setSelectedAlocacaoClass,
    selectedAlocacaoComponent,
    setSelectedAlocacaoComponent,
    cargaHorariaTotal,
    professorSchools,
    loadingProfessorSchools,
    existingAlocacoes,
    professorCargaHoraria,
    cargaHorariaExistente,
    addTurmaAlocacao,
    removeTurmaAlocacao,
    addComponenteAlocacao,
    removeComponenteAlocacao,
    
    // Alert
    alert,
    showAlertMessage,
    
    // Permissões
    canEdit,
    canDelete,
    academicYear,
    
    // Handlers
    handleNewStaff,
    handleEditStaff,
    handleViewStaff,
    handleSaveStaff,
    handleNewLotacao,
    handleLotacaoStaffChange,
    handleLotacaoYearChange,
    handleSaveLotacao,
    handleNewAlocacao,
    handleProfessorChange,
    handleAlocacaoSchoolChange,
    handleAlocacaoAcademicYearChange,
    handleSaveAlocacao,
    handleDelete,
    confirmDelete,
    handleEncerrarLotacao,
    handleDeleteExistingLotacao,
    handleDeleteExistingAlocacao,
    handleDeleteTurmaAlocacoes
  };
};
