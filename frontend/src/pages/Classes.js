import { useState, useEffect, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { classesAPI, schoolsAPI, documentsAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, Home, Eye, Phone, FileText, User, Users, School, Calendar, ExternalLink } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { extractErrorMessage } from '@/utils/errorHandler';

// Mapeamento de níveis de ensino para séries/etapas
const GRADE_LEVELS_BY_EDUCATION = {
  educacao_infantil: [
    { value: 'bercario_i', label: 'Berçário I', field: 'educacao_infantil_bercario_i', ageRange: '3 a 11 meses' },
    { value: 'bercario_ii', label: 'Berçário II', field: 'educacao_infantil_bercario_ii', ageRange: '1 ano a 1 ano e 11 meses' },
    { value: 'maternal_i', label: 'Maternal I', field: 'educacao_infantil_maternal_i', ageRange: '2 anos a 2 anos e 11 meses' },
    { value: 'maternal_ii', label: 'Maternal II', field: 'educacao_infantil_maternal_ii', ageRange: '3 anos a 3 anos e 11 meses' },
    { value: 'pre_i', label: 'Pré I', field: 'educacao_infantil_pre_i', ageRange: '4 anos' },
    { value: 'pre_ii', label: 'Pré II', field: 'educacao_infantil_pre_ii', ageRange: '5 anos' }
  ],
  fundamental_anos_iniciais: [
    { value: '1ano', label: '1º Ano', field: 'fundamental_inicial_1ano' },
    { value: '2ano', label: '2º Ano', field: 'fundamental_inicial_2ano' },
    { value: '3ano', label: '3º Ano', field: 'fundamental_inicial_3ano' },
    { value: '4ano', label: '4º Ano', field: 'fundamental_inicial_4ano' },
    { value: '5ano', label: '5º Ano', field: 'fundamental_inicial_5ano' }
  ],
  fundamental_anos_finais: [
    { value: '6ano', label: '6º Ano', field: 'fundamental_final_6ano' },
    { value: '7ano', label: '7º Ano', field: 'fundamental_final_7ano' },
    { value: '8ano', label: '8º Ano', field: 'fundamental_final_8ano' },
    { value: '9ano', label: '9º Ano', field: 'fundamental_final_9ano' }
  ],
  ensino_medio: [
    { value: '1serie_em', label: '1ª Série EM', field: null },
    { value: '2serie_em', label: '2ª Série EM', field: null },
    { value: '3serie_em', label: '3ª Série EM', field: null }
  ],
  eja: [
    { value: 'eja_1etapa', label: 'EJA 1ª Etapa', field: 'eja_inicial_1etapa' },
    { value: 'eja_2etapa', label: 'EJA 2ª Etapa', field: 'eja_inicial_2etapa' }
  ],
  eja_final: [
    { value: 'eja_3etapa', label: 'EJA 3ª Etapa', field: 'eja_final_3etapa' },
    { value: 'eja_4etapa', label: 'EJA 4ª Etapa', field: 'eja_final_4etapa' }
  ]
};

const EDUCATION_LEVELS = [
  { value: 'educacao_infantil', label: 'Educação Infantil' },
  { value: 'fundamental_anos_iniciais', label: 'Ensino Fundamental - Anos Iniciais' },
  { value: 'fundamental_anos_finais', label: 'Ensino Fundamental - Anos Finais' },
  { value: 'ensino_medio', label: 'Ensino Médio' },
  { value: 'eja', label: 'EJA - Anos Iniciais' },
  { value: 'eja_final', label: 'EJA - Anos Finais' }
];

export const Classes = () => {
  const { user } = useAuth();
  
  // IDs das escolas que o usuário (secretário) tem vínculo - estabilizado com JSON
  const userSchoolIdsJson = JSON.stringify(user?.school_ids || user?.school_links?.map(link => link.school_id) || []);
  const userSchoolIds = useMemo(() => {
    return JSON.parse(userSchoolIdsJson);
  }, [userSchoolIdsJson]);
  
  const isAdmin = user?.role === 'admin' || user?.role === 'admin_teste';
  const isSecretario = user?.role === 'secretario';
  const isSemed = user?.role === 'semed';
  const navigate = useNavigate();
  const [classes, setClasses] = useState([]);
  const [schools, setSchools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingClass, setEditingClass] = useState(null);
  const [formData, setFormData] = useState({
    school_id: '',
    academic_year: new Date().getFullYear(),
    name: '',
    shift: 'morning',
    education_level: '',
    grade_level: '',
    teacher_ids: [],
    atendimento_programa: '',
    is_multi_grade: false,
    series: []
  });
  
  // Permissões de edição:
  // - SEMED: apenas visualização (não pode editar/excluir)
  // - Coordenador: apenas visualização de turmas (não pode editar/excluir)
  // - Outros roles com acesso: podem editar/excluir
  const canEditClasses = user?.role !== 'semed' && user?.role !== 'coordenador';
  const canDeleteClasses = user?.role !== 'semed' && user?.role !== 'coordenador';
  
  // Mantém variáveis originais para compatibilidade
  const canEdit = canEditClasses;
  const canDelete = canDeleteClasses;
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);
  const [filterSchoolId, setFilterSchoolId] = useState('');
  const [atendimentoChangeWarning, setAtendimentoChangeWarning] = useState(null);
  
  // Estados para modal de visualização
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [viewingClass, setViewingClass] = useState(null);
  const [classDetails, setClassDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const isModalOpenRef = useRef(false);
  isModalOpenRef.current = isModalOpen;
  const initialLoadDone = useRef(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Não mostra loading se é apenas um re-fetch (modal aberto)
        if (!initialLoadDone.current) setLoading(true);
        const [classesData, schoolsData] = await Promise.all([
          classesAPI.getAll(),
          schoolsAPI.getAll()
        ]);
        
        // Secretário vê apenas turmas das escolas vinculadas
        let filteredClasses = classesData;
        let filteredSchools = schoolsData;
        
        if (isSecretario && userSchoolIds.length > 0) {
          filteredClasses = classesData.filter(c => userSchoolIds.includes(c.school_id));
          filteredSchools = schoolsData.filter(s => userSchoolIds.includes(s.id));
        }
        
        setClasses(filteredClasses);
        setSchools(filteredSchools);
        
        // Só define escola padrão no carregamento inicial, NÃO quando modal está aberto
        if (!initialLoadDone.current && !['admin', 'semed'].includes(user?.role) && filteredSchools.length > 0) {
          setFormData(prev => ({ ...prev, school_id: filteredSchools[0].id }));
        }
        initialLoadDone.current = true;
      } catch (error) {
        setAlert({ type: 'error', message: 'Erro ao carregar dados' });
        setTimeout(() => setAlert(null), 5000);
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadTrigger]);
  
  const reloadData = () => setReloadTrigger(prev => prev + 1);

  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  };

  // Obtém a escola selecionada
  const selectedSchool = schools.find(s => s.id === formData.school_id);

  // Filtra os níveis de ensino disponíveis para a escola selecionada
  const getAvailableEducationLevels = () => {
    if (!selectedSchool) return [];
    
    return EDUCATION_LEVELS.filter(level => {
      return selectedSchool[level.value] === true;
    });
  };

  // Filtra as séries/etapas disponíveis para o nível selecionado e escola
  const getAvailableGradeLevels = () => {
    if (!selectedSchool || !formData.education_level) return [];
    
    const gradeLevels = GRADE_LEVELS_BY_EDUCATION[formData.education_level] || [];
    
    return gradeLevels.filter(grade => {
      // Se não tem campo específico (ex: ensino médio), mostra todas
      if (!grade.field) return true;
      // Se tem campo, verifica se está habilitado na escola
      return selectedSchool[grade.field] === true;
    });
  };

  // Retorna os programas/atendimentos disponíveis baseados nas configurações da escola
  const getAvailableProgramas = () => {
    if (!selectedSchool) return [];
    
    const programas = [];
    
    if (selectedSchool.atendimento_integral) {
      programas.push({ value: 'atendimento_integral', label: 'Escola Integral' });
    }
    if (selectedSchool.reforco_escolar) {
      programas.push({ value: 'reforco_escolar', label: 'Reforço Escolar' });
    }
    if (selectedSchool.aulas_complementares) {
      programas.push({ value: 'aulas_complementares', label: 'Aulas Complementares' });
    }
    if (selectedSchool.aee) {
      programas.push({ value: 'aee', label: 'AEE - Atendimento Educacional Especializado' });
    }
    
    return programas;
  };

  const handleCreate = () => {
    setEditingClass(null);
    const defaultSchoolId = schools.length > 0 ? schools[0].id : '';
    const defaultSchool = schools.find(s => s.id === defaultSchoolId);
    
    // Pré-seleciona "Escola Integral" se a escola tem essa opção marcada
    let defaultAtendimento = '';
    if (defaultSchool?.atendimento_integral) {
      defaultAtendimento = 'atendimento_integral';
    }
    
    setFormData({
      school_id: defaultSchoolId,
      academic_year: new Date().getFullYear(),
      name: '',
      shift: 'morning',
      education_level: '',
      grade_level: '',
      teacher_ids: [],
      atendimento_programa: defaultAtendimento,
      is_multi_grade: false,
      series: []
    });
    setIsModalOpen(true);
  };

  const handleEdit = (classItem) => {
    setEditingClass(classItem);
    
    // Tenta identificar o nível de ensino baseado na série/etapa existente
    let educationLevel = classItem.education_level || '';
    if (!educationLevel && classItem.grade_level) {
      // Tenta encontrar o nível de ensino baseado na série
      for (const [level, grades] of Object.entries(GRADE_LEVELS_BY_EDUCATION)) {
        const found = grades.find(g => g.label === classItem.grade_level || g.value === classItem.grade_level);
        if (found) {
          educationLevel = level;
          break;
        }
      }
    }
    
    setFormData({
      school_id: classItem.school_id,
      academic_year: classItem.academic_year,
      name: classItem.name,
      shift: classItem.shift,
      education_level: educationLevel,
      grade_level: classItem.grade_level,
      teacher_ids: classItem.teacher_ids || [],
      atendimento_programa: classItem.atendimento_programa || '',
      is_multi_grade: classItem.is_multi_grade || false,
      series: classItem.series || []
    });
    setIsModalOpen(true);
  };

  const handleView = async (classItem) => {
    setViewingClass(classItem);
    setIsViewModalOpen(true);
    setLoadingDetails(true);
    
    try {
      const details = await classesAPI.getDetails(classItem.id);
      setClassDetails(details);
    } catch (error) {
      console.error('Erro ao carregar detalhes:', error);
      showAlert('error', 'Erro ao carregar detalhes da turma');
    } finally {
      setLoadingDetails(false);
    }
  };

  const formatPhone = (phone) => {
    if (!phone) return '';
    return phone.replace(/\D/g, '');
  };

  const formatPhoneDisplay = (phone) => {
    if (!phone) return '-';
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 11) {
      return `(${cleaned.slice(0,2)}) ${cleaned.slice(2,7)}-${cleaned.slice(7)}`;
    }
    return phone;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('pt-BR');
  };

  const handleOpenPDF = async (studentId) => {
    try {
      const academicYear = viewingClass?.academic_year || new Date().getFullYear();
      // Baixa o PDF com autenticação
      const blob = await documentsAPI.getBoletim(studentId, academicYear);
      // Cria URL do blob e abre em nova aba
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      // Limpa URL após um tempo
      setTimeout(() => window.URL.revokeObjectURL(url), 10000);
    } catch (error) {
      console.error('Erro ao abrir PDF:', error);
      showAlert('error', 'Erro ao gerar PDF do aluno');
    }
  };

  const handleOpenBatchPDF = async (documentType) => {
    try {
      const academicYear = viewingClass?.academic_year || new Date().getFullYear();
      // Baixa o PDF em lote com autenticação
      const blob = await documentsAPI.getBatchDocuments(viewingClass.id, documentType, academicYear);
      // Cria URL do blob e abre em nova aba
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      // Limpa URL após um tempo
      setTimeout(() => window.URL.revokeObjectURL(url), 10000);
    } catch (error) {
      console.error('Erro ao abrir PDF em lote:', error);
      showAlert('error', 'Erro ao gerar PDF da turma');
    }
  };

  const handleOpenDetailsPDF = async () => {
    try {
      // Baixa o PDF de detalhes da turma com autenticação
      const blob = await classesAPI.getDetailsPdf(viewingClass.id);
      // Cria URL do blob e abre em nova aba
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      // Limpa URL após um tempo
      setTimeout(() => window.URL.revokeObjectURL(url), 10000);
    } catch (error) {
      console.error('Erro ao abrir PDF de detalhes:', error);
      showAlert('error', 'Erro ao gerar PDF dos detalhes da turma');
    }
  };

  const handleDelete = async (classItem) => {
    if (window.confirm(`Tem certeza que deseja excluir a turma "${classItem.name}"?`)) {
      try {
        await classesAPI.delete(classItem.id);
        showAlert('success', 'Turma excluída com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir turma');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      // Validação para turma multisseriada
      if (formData.is_multi_grade && formData.series.length < 2) {
        showAlert('error', 'Selecione pelo menos 2 séries para uma turma multisseriada');
        setSubmitting(false);
        return;
      }
      
      const dataToSend = {
        ...formData,
        // Salva o label da série/etapa em vez do value
        grade_level: formData.grade_level
      };
      
      if (editingClass) {
        await classesAPI.update(editingClass.id, dataToSend);
        showAlert('success', 'Turma atualizada com sucesso');
      } else {
        await classesAPI.create(dataToSend);
        showAlert('success', 'Turma criada com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      // Trata erros de validação do Pydantic (array de objetos)
      let errorMessage = 'Erro ao salvar turma';
      const detail = error.response?.data?.detail;
      
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        // Erro de validação Pydantic - extrai a mensagem do primeiro erro
        errorMessage = detail[0]?.msg || detail[0]?.message || 'Erro de validação';
      } else if (detail && typeof detail === 'object') {
        errorMessage = detail.msg || detail.message || 'Erro ao salvar turma';
      }
      
      showAlert('error', errorMessage);
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  // Handlers para mudança de campos
  const handleSchoolChange = (schoolId) => {
    const newSchool = schools.find(s => s.id === schoolId);
    
    // Pré-seleciona "Escola Integral" se a escola tem essa opção marcada
    let defaultAtendimento = '';
    if (newSchool?.atendimento_integral) {
      defaultAtendimento = 'atendimento_integral';
    }
    
    setFormData({
      ...formData,
      school_id: schoolId,
      education_level: '',
      grade_level: '',
      atendimento_programa: defaultAtendimento,
      is_multi_grade: false,
      series: []
    });
  };

  const handleEducationLevelChange = (level) => {
    setFormData({
      ...formData,
      education_level: level,
      grade_level: '',
      is_multi_grade: false,
      series: []
    });
  };

  // Handler para toggle de turma multisseriada
  const handleMultiGradeToggle = (checked) => {
    if (checked) {
      // Ao ativar multisseriada, limpa grade_level e prepara para seleção múltipla
      setFormData({
        ...formData,
        is_multi_grade: true,
        grade_level: '',
        series: []
      });
    } else {
      // Ao desativar, limpa series e volta ao modo single
      setFormData({
        ...formData,
        is_multi_grade: false,
        grade_level: '',
        series: []
      });
    }
  };

  // Handler para seleção de séries (modo multisseriada)
  const handleSeriesChange = (gradeLabel, checked) => {
    let newSeries = [...formData.series];
    if (checked) {
      if (!newSeries.includes(gradeLabel)) {
        newSeries.push(gradeLabel);
      }
    } else {
      newSeries = newSeries.filter(s => s !== gradeLabel);
    }
    
    // Define grade_level como a primeira série selecionada (para compatibilidade)
    const firstSeries = newSeries.length > 0 ? newSeries[0] : '';
    
    setFormData({
      ...formData,
      series: newSeries,
      grade_level: firstSeries
    });
  };

  // Função para lidar com mudança de atendimento/programa
  const handleAtendimentoChange = (newValue) => {
    const oldValue = formData.atendimento_programa;
    
    // Obtém labels para exibição
    const getAtendimentoLabel = (value) => {
      if (!value) return 'Turma Regular';
      const labels = {
        'atendimento_integral': 'Escola Integral',
        'reforco_escolar': 'Reforço Escolar',
        'aulas_complementares': 'Aulas Complementares',
        'aee': 'AEE - Atendimento Educacional Especializado'
      };
      return labels[value] || value;
    };

    // Mostra aviso se está mudando de um tipo para outro
    if (oldValue !== newValue) {
      const oldLabel = getAtendimentoLabel(oldValue);
      const newLabel = getAtendimentoLabel(newValue);
      
      setAtendimentoChangeWarning({
        from: oldLabel,
        to: newLabel,
        message: `Esta turma será alterada de "${oldLabel}" para "${newLabel}". A turma se adequará às configurações do novo tipo de atendimento.`
      });
      
      // Limpa o aviso após 8 segundos
      setTimeout(() => setAtendimentoChangeWarning(null), 8000);
    }
    
    setFormData({ ...formData, atendimento_programa: newValue });
  };

  const shiftLabels = {
    morning: 'Manhã',
    afternoon: 'Tarde',
    evening: 'Noite',
    full_time: 'Integral'
  };

  const getSchoolName = (schoolId) => {
    const school = schools.find(s => s.id === schoolId);
    return school?.name || schoolId;
  };

  const getEducationLevelLabel = (value) => {
    const level = EDUCATION_LEVELS.find(l => l.value === value);
    return level?.label || value;
  };

  const columns = [
    { header: 'Turma', accessor: 'name' },
    {
      header: 'Escola',
      accessor: 'school_id',
      render: (row) => getSchoolName(row.school_id)
    },
    { header: 'Ano Letivo', accessor: 'academic_year' },
    {
      header: 'Série/Etapa',
      accessor: 'grade_level',
      render: (row) => {
        if (row.is_multi_grade && row.series?.length > 0) {
          return (
            <div className="flex items-center gap-1">
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
                Multi
              </span>
              <span className="text-xs text-gray-600" title={row.series.join(', ')}>
                {row.series.length} séries
              </span>
            </div>
          );
        }
        return row.grade_level || '-';
      }
    },
    {
      header: 'Tipo',
      accessor: 'atendimento_programa',
      render: (row) => {
        if (!row.atendimento_programa) return <span className="text-gray-400 text-xs">Regular</span>;
        
        const programaLabels = {
          'atendimento_integral': { label: 'Integral', color: 'bg-purple-100 text-purple-800' },
          'reforco_escolar': { label: 'Reforço', color: 'bg-orange-100 text-orange-800' },
          'aulas_complementares': { label: 'Complementar', color: 'bg-teal-100 text-teal-800' },
          'aee': { label: 'AEE', color: 'bg-blue-100 text-blue-800' }
        };
        
        const programa = programaLabels[row.atendimento_programa];
        if (!programa) return row.atendimento_programa;
        
        return (
          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${programa.color}`}>
            {programa.label}
          </span>
        );
      }
    }
  ];

  const availableEducationLevels = getAvailableEducationLevels();
  const availableGradeLevels = getAvailableGradeLevels();

  // Filtra as turmas por escola selecionada
  const filteredClasses = filterSchoolId 
    ? classes.filter(c => c.school_id === filterSchoolId)
    : classes;

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
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
              <h1 className="text-2xl font-bold text-gray-900" data-testid="classes-title">Turmas</h1>
              <p className="text-gray-600 text-sm">Gerencie as turmas das escolas</p>
            </div>
          </div>
          {canEdit && (
            <button
              onClick={handleCreate}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
              data-testid="create-class-button"
            >
              <Plus size={20} />
              <span>Nova Turma</span>
            </button>
          )}
        </div>

        {alert && (
          <div
            className={`p-4 rounded-lg flex items-start ${
              alert.type === 'success'
                ? 'bg-green-50 border border-green-200'
                : 'bg-red-50 border border-red-200'
            }`}
            data-testid="alert-message"
          >
            {alert.type === 'success' ? (
              <CheckCircle className="text-green-600 mr-2 flex-shrink-0" size={20} />
            ) : (
              <AlertCircle className="text-red-600 mr-2 flex-shrink-0" size={20} />
            )}
            <p className={`text-sm ${alert.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
              {alert.message}
            </p>
          </div>
        )}

        {/* Filtro por Escola */}
        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-700">Filtrar por Escola:</label>
            <select
              value={filterSchoolId}
              onChange={(e) => setFilterSchoolId(e.target.value)}
              className="flex-1 max-w-md border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              data-testid="filter-school-select"
            >
              <option value="">Todas as escolas</option>
              {schools.map(school => (
                <option key={school.id} value={school.id}>{school.name}</option>
              ))}
            </select>
            <span className="text-sm text-gray-500">
              {filteredClasses.length} turma(s) encontrada(s)
            </span>
          </div>
        </div>

        <DataTable
          columns={columns}
          data={filteredClasses}
          loading={loading}
          onView={handleView}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          canDelete={canDelete}
        />

        {/* Modal de Visualização de Detalhes */}
        <Modal
          isOpen={isViewModalOpen}
          onClose={() => {
            setIsViewModalOpen(false);
            setClassDetails(null);
          }}
          title={
            <div className="flex items-center justify-between w-full pr-8">
              <span>Detalhes da Turma: {viewingClass?.name || ''}</span>
              {classDetails && !loadingDetails && (
                <button
                  onClick={handleOpenDetailsPDF}
                  className="flex items-center gap-2 px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition-colors"
                  title="Gerar PDF dos detalhes"
                >
                  <FileText size={16} />
                  Gerar PDF
                </button>
              )}
            </div>
          }
          size="xl"
        >
          {loadingDetails ? (
            <div className="flex justify-center items-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="ml-3 text-gray-600">Carregando...</span>
            </div>
          ) : classDetails ? (
            <div className="space-y-6">
              {/* Dados da Turma */}
              <div className="bg-blue-50 rounded-lg p-4">
                <h3 className="font-semibold text-blue-900 mb-3 flex items-center gap-2">
                  <School size={18} />
                  Dados da Turma
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Nome:</span>
                    <p className="font-medium">{classDetails.class?.name}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Escola:</span>
                    <p className="font-medium">{classDetails.school?.name}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Ano Letivo:</span>
                    <p className="font-medium">{classDetails.class?.academic_year}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Nível de Ensino:</span>
                    <p className="font-medium">{getEducationLevelLabel(classDetails.class?.education_level)}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Série/Etapa:</span>
                    {classDetails.class?.is_multi_grade && classDetails.class?.series?.length > 0 ? (
                      <div className="mt-1">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800 mr-2">
                          Multisseriada
                        </span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {classDetails.class.series.map((serie) => (
                            <span key={serie} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700">
                              {serie}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="font-medium">{classDetails.class?.grade_level || '-'}</p>
                    )}
                  </div>
                  <div>
                    <span className="text-gray-500">Turno:</span>
                    <p className="font-medium">{shiftLabels[classDetails.class?.shift] || '-'}</p>
                  </div>
                  {classDetails.class?.atendimento_programa && (
                    <div className="col-span-2 md:col-span-3">
                      <span className="text-gray-500">Tipo de Atendimento:</span>
                      <p className="font-medium">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          classDetails.class.atendimento_programa === 'atendimento_integral' ? 'bg-purple-100 text-purple-800' :
                          classDetails.class.atendimento_programa === 'reforco_escolar' ? 'bg-orange-100 text-orange-800' :
                          classDetails.class.atendimento_programa === 'aulas_complementares' ? 'bg-teal-100 text-teal-800' :
                          classDetails.class.atendimento_programa === 'aee' ? 'bg-blue-100 text-blue-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {classDetails.class.atendimento_programa === 'atendimento_integral' ? 'Escola Integral' :
                           classDetails.class.atendimento_programa === 'reforco_escolar' ? 'Reforço Escolar' :
                           classDetails.class.atendimento_programa === 'aulas_complementares' ? 'Aulas Complementares' :
                           classDetails.class.atendimento_programa === 'aee' ? 'AEE' :
                           classDetails.class.atendimento_programa}
                        </span>
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Professores Alocados */}
              <div className="bg-green-50 rounded-lg p-4">
                <h3 className="font-semibold text-green-900 mb-3 flex items-center gap-2">
                  <User size={18} />
                  Professor(es) Alocado(s)
                </h3>
                {classDetails.teachers?.length > 0 ? (
                  <div className="space-y-2">
                    {classDetails.teachers.map((teacher, idx) => (
                      <div key={idx} className="flex items-center justify-between bg-white rounded p-2 text-sm">
                        <div>
                          <span className="font-medium">{teacher.nome}</span>
                          {teacher.componente && (
                            <span className="ml-2 text-gray-500">({teacher.componente})</span>
                          )}
                        </div>
                        {teacher.celular && (
                          <a
                            href={`https://wa.me/55${formatPhone(teacher.celular)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-green-600 hover:text-green-800 flex items-center gap-1"
                          >
                            <Phone size={14} />
                            {formatPhoneDisplay(teacher.celular)}
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">Nenhum professor alocado</p>
                )}
              </div>

              {/* Resumo por Série - apenas para turmas multisseriadas */}
              {classDetails.class?.is_multi_grade && classDetails.series_count && (
                <div className="bg-indigo-50 rounded-lg p-4">
                  <h3 className="font-semibold text-indigo-900 mb-3 flex items-center gap-2">
                    <Calendar size={18} />
                    Distribuição por Série
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {Object.entries(classDetails.series_count).map(([serie, count]) => (
                      <div 
                        key={serie}
                        className="bg-white rounded-lg p-3 border border-indigo-100 text-center"
                      >
                        <p className="text-2xl font-bold text-indigo-600">{count}</p>
                        <p className="text-sm text-gray-600">{serie}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-3 pt-3 border-t border-indigo-200 flex justify-between items-center">
                    <span className="text-sm text-indigo-700 font-medium">Total de Alunos(as):</span>
                    <span className="text-lg font-bold text-indigo-900">{classDetails.total_students || 0}</span>
                  </div>
                </div>
              )}

              {/* Lista de Alunos */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <Users size={18} />
                  Alunos Matriculados ({classDetails.total_students || 0})
                </h3>
                {classDetails.students?.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead>
                        <tr className="bg-gray-200">
                          <th className="px-3 py-2 text-left font-medium">#</th>
                          <th className="px-3 py-2 text-left font-medium">Aluno</th>
                          {classDetails.class?.is_multi_grade && (
                            <th className="px-3 py-2 text-left font-medium">Série</th>
                          )}
                          <th className="px-3 py-2 text-left font-medium">Data Nasc.</th>
                          <th className="px-3 py-2 text-left font-medium">Responsável</th>
                          <th className="px-3 py-2 text-left font-medium">Celular</th>
                          <th className="px-3 py-2 text-center font-medium">Ações</th>
                        </tr>
                      </thead>
                      <tbody>
                        {classDetails.students.map((student, idx) => (
                          <tr key={student.id} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                            <td className="px-3 py-2">{idx + 1}</td>
                            <td className="px-3 py-2 font-medium">{student.full_name}</td>
                            {classDetails.class?.is_multi_grade && (
                              <td className="px-3 py-2">
                                {student.student_series ? (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
                                    {student.student_series}
                                  </span>
                                ) : (
                                  <span className="text-gray-400 text-xs">N/D</span>
                                )}
                              </td>
                            )}
                            <td className="px-3 py-2">{formatDate(student.birth_date)}</td>
                            <td className="px-3 py-2">{student.guardian_name}</td>
                            <td className="px-3 py-2">
                              {student.guardian_phone ? (
                                <a
                                  href={`https://wa.me/55${formatPhone(student.guardian_phone)}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-green-600 hover:text-green-800 flex items-center gap-1"
                                >
                                  <Phone size={14} />
                                  {formatPhoneDisplay(student.guardian_phone)}
                                </a>
                              ) : '-'}
                            </td>
                            <td className="px-3 py-2 text-center">
                              <button
                                onClick={() => handleOpenPDF(student.id)}
                                className="text-blue-600 hover:text-blue-800 p-1 rounded hover:bg-blue-50"
                                title="Abrir Boletim"
                              >
                                <FileText size={16} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">Nenhum aluno matriculado</p>
                )}
              </div>

              {/* Botão para PDF da Turma */}
              {classDetails.students?.length > 0 && (
                <div className="flex justify-end gap-3 pt-4 border-t">
                  <button
                    onClick={() => handleOpenBatchPDF('boletim')}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    <FileText size={18} />
                    Boletins da Turma (PDF)
                  </button>
                  <button
                    onClick={() => handleOpenBatchPDF('ficha_individual')}
                    className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
                  >
                    <FileText size={18} />
                    Fichas Individuais (PDF)
                  </button>
                </div>
              )}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-8">Erro ao carregar detalhes</p>
          )}
        </Modal>

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={editingClass ? 'Editar Turma' : 'Nova Turma'}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Ano Letivo *</label>
              <input
                type="number"
                value={formData.academic_year}
                onChange={(e) => setFormData({ ...formData, academic_year: parseInt(e.target.value) })}
                required
                min="2020"
                max="2030"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="class-year-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Escola *</label>
              <select
                value={formData.school_id}
                onChange={(e) => handleSchoolChange(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="class-school-select"
              >
                <option value="">Selecione uma escola</option>
                {schools.map((school) => (
                  <option key={school.id} value={school.id}>
                    {school.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nome da Turma *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                placeholder="Ex: Turma A"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="class-name-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nível de Ensino *</label>
              <select
                value={formData.education_level}
                onChange={(e) => handleEducationLevelChange(e.target.value)}
                required
                disabled={!formData.school_id}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
                data-testid="class-education-level-select"
              >
                <option value="">Selecione o nível de ensino</option>
                {availableEducationLevels.map((level) => (
                  <option key={level.value} value={level.value}>
                    {level.label}
                  </option>
                ))}
              </select>
              {formData.school_id && availableEducationLevels.length === 0 && (
                <p className="text-sm text-orange-600 mt-1">
                  ⚠️ Esta escola não possui níveis de ensino cadastrados
                </p>
              )}
            </div>

            {/* Checkbox para Turma Multisseriada */}
            {formData.education_level && availableGradeLevels.length > 1 && (
              <div className="flex items-center gap-3 p-3 bg-indigo-50 rounded-lg border border-indigo-100">
                <input
                  type="checkbox"
                  id="is_multi_grade"
                  checked={formData.is_multi_grade}
                  onChange={(e) => handleMultiGradeToggle(e.target.checked)}
                  className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                  data-testid="class-multi-grade-checkbox"
                />
                <label htmlFor="is_multi_grade" className="text-sm font-medium text-indigo-900 cursor-pointer">
                  Turma Multisseriada
                </label>
                <span className="text-xs text-indigo-600">
                  (atende múltiplas séries/etapas simultaneamente)
                </span>
              </div>
            )}

            {/* Seleção de Série - modo único */}
            {!formData.is_multi_grade && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Série/Etapa *</label>
                <select
                  value={formData.grade_level}
                  onChange={(e) => setFormData({ ...formData, grade_level: e.target.value })}
                  required
                  disabled={!formData.education_level}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
                  data-testid="class-grade-select"
                >
                  <option value="">Selecione a série/etapa</option>
                  {availableGradeLevels.map((grade) => (
                    <option key={grade.value} value={grade.label}>
                      {grade.label}
                    </option>
                  ))}
                </select>
                {formData.education_level && availableGradeLevels.length === 0 && (
                  <p className="text-sm text-orange-600 mt-1">
                    ⚠️ Esta escola não possui séries/etapas cadastradas para este nível
                  </p>
                )}
              </div>
            )}

            {/* Seleção de Séries - modo multisseriada */}
            {formData.is_multi_grade && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Séries/Etapas da Turma *
                  <span className="text-xs text-gray-500 font-normal ml-2">
                    (selecione ao menos 2 séries)
                  </span>
                </label>
                <div className="border border-gray-300 rounded-lg p-3 max-h-48 overflow-y-auto bg-white">
                  {availableGradeLevels.map((grade) => (
                    <label 
                      key={grade.value} 
                      className="flex items-center gap-2 py-1.5 px-2 hover:bg-gray-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={formData.series.includes(grade.label)}
                        onChange={(e) => handleSeriesChange(grade.label, e.target.checked)}
                        className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">{grade.label}</span>
                    </label>
                  ))}
                </div>
                {formData.series.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {formData.series.map((serie) => (
                      <span 
                        key={serie}
                        className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800"
                      >
                        {serie}
                        <button
                          type="button"
                          onClick={() => handleSeriesChange(serie, false)}
                          className="ml-1 text-indigo-600 hover:text-indigo-900"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                {formData.series.length < 2 && formData.is_multi_grade && (
                  <p className="text-sm text-orange-600 mt-1">
                    ⚠️ Selecione pelo menos 2 séries para uma turma multisseriada
                  </p>
                )}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Turno *</label>
              <select
                value={formData.shift}
                onChange={(e) => setFormData({ ...formData, shift: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="class-shift-select"
              >
                <option value="morning">Manhã</option>
                <option value="afternoon">Tarde</option>
                <option value="evening">Noite</option>
                <option value="full_time">Integral</option>
              </select>
            </div>

            {/* Campo de Atendimento/Programa - mostrado apenas se escola tem opções habilitadas */}
            {getAvailableProgramas().length > 0 && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Tipo de Atendimento/Programa
                </label>
                <select
                  value={formData.atendimento_programa}
                  onChange={(e) => handleAtendimentoChange(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  data-testid="class-programa-select"
                >
                  <option value="">Turma Regular (sem programa específico)</option>
                  {getAvailableProgramas().map((programa) => (
                    <option key={programa.value} value={programa.value}>
                      {programa.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  Selecione se esta turma faz parte de algum programa especial
                </p>
                
                {/* Aviso de mudança de tipo de atendimento */}
                {atendimentoChangeWarning && (
                  <div className="mt-2 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
                    <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">Atenção: Mudança de Tipo de Atendimento</p>
                      <p className="text-xs text-amber-700 mt-1">{atendimentoChangeWarning.message}</p>
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end space-x-2 mt-6 pt-4 border-t">
              <button
                type="button"
                onClick={() => {
                  setIsModalOpen(false);
                  setAtendimentoChangeWarning(null);
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                data-testid="class-submit-button"
              >
                {submitting ? 'Salvando...' : (editingClass ? 'Atualizar' : 'Criar')}
              </button>
            </div>
          </form>
        </Modal>
      </div>
    </Layout>
  );
};
