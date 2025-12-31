import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { classesAPI, schoolsAPI, documentsAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, Home, Eye, Phone, FileText, User, Users, School, Calendar, ExternalLink } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

// Mapeamento de níveis de ensino para séries/etapas
const GRADE_LEVELS_BY_EDUCATION = {
  educacao_infantil: [
    { value: 'bercario', label: 'Berçário', field: 'educacao_infantil_bercario' },
    { value: 'maternal_i', label: 'Maternal I', field: 'educacao_infantil_maternal_i' },
    { value: 'maternal_ii', label: 'Maternal II', field: 'educacao_infantil_maternal_ii' },
    { value: 'pre_i', label: 'Pré I', field: 'educacao_infantil_pre_i' },
    { value: 'pre_ii', label: 'Pré II', field: 'educacao_infantil_pre_ii' }
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
    teacher_ids: []
  });
  
  // SEMED pode visualizar tudo, mas não pode editar/excluir
  const canEdit = user?.role !== 'semed';
  const canDelete = user?.role !== 'semed';
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);
  const [filterSchoolId, setFilterSchoolId] = useState('');
  
  // Estados para modal de visualização
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [viewingClass, setViewingClass] = useState(null);
  const [classDetails, setClassDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [classesData, schoolsData] = await Promise.all([
          classesAPI.getAll(),
          schoolsAPI.getAll()
        ]);
        setClasses(classesData);
        setSchools(schoolsData);
        
        // Se não for admin/semed e tiver schools, seleciona a primeira
        if (!['admin', 'semed'].includes(user?.role) && schoolsData.length > 0) {
          setFormData(prev => ({ ...prev, school_id: schoolsData[0].id }));
        }
      } catch (error) {
        setAlert({ type: 'error', message: 'Erro ao carregar dados' });
        setTimeout(() => setAlert(null), 5000);
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [reloadTrigger, user?.role]);
  
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

  const handleCreate = () => {
    setEditingClass(null);
    const defaultSchoolId = schools.length > 0 ? schools[0].id : '';
    setFormData({
      school_id: defaultSchoolId,
      academic_year: new Date().getFullYear(),
      name: '',
      shift: 'morning',
      education_level: '',
      grade_level: '',
      teacher_ids: []
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
      teacher_ids: classItem.teacher_ids || []
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
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar turma');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  // Handlers para mudança de campos
  const handleSchoolChange = (schoolId) => {
    setFormData({
      ...formData,
      school_id: schoolId,
      education_level: '',
      grade_level: ''
    });
  };

  const handleEducationLevelChange = (level) => {
    setFormData({
      ...formData,
      education_level: level,
      grade_level: ''
    });
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
    { header: 'Nome', accessor: 'name' },
    {
      header: 'Escola',
      accessor: 'school_id',
      render: (row) => getSchoolName(row.school_id)
    },
    { header: 'Ano Letivo', accessor: 'academic_year' },
    {
      header: 'Nível de Ensino',
      accessor: 'education_level',
      render: (row) => getEducationLevelLabel(row.education_level) || '-'
    },
    { header: 'Série/Etapa', accessor: 'grade_level' },
    {
      header: 'Turno',
      accessor: 'shift',
      render: (row) => shiftLabels[row.shift]
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
          title={`Detalhes da Turma: ${viewingClass?.name || ''}`}
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
                    <p className="font-medium">{classDetails.class?.grade_level || '-'}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Turno:</span>
                    <p className="font-medium">{shiftLabels[classDetails.class?.shift] || '-'}</p>
                  </div>
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

            <div className="flex justify-end space-x-2 mt-6 pt-4 border-t">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
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
