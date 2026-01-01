import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { coursesAPI, schoolsAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { Plus, AlertCircle, CheckCircle, Home, Info } from 'lucide-react';

// Mapeamento de níveis de ensino para séries/etapas
const GRADE_LEVELS_BY_EDUCATION = {
  educacao_infantil: [
    { value: 'Berçário', label: 'Berçário' },
    { value: 'Maternal I', label: 'Maternal I' },
    { value: 'Maternal II', label: 'Maternal II' },
    { value: 'Pré I', label: 'Pré I' },
    { value: 'Pré II', label: 'Pré II' }
  ],
  fundamental_anos_iniciais: [
    { value: '1º Ano', label: '1º Ano' },
    { value: '2º Ano', label: '2º Ano' },
    { value: '3º Ano', label: '3º Ano' },
    { value: '4º Ano', label: '4º Ano' },
    { value: '5º Ano', label: '5º Ano' }
  ],
  fundamental_anos_finais: [
    { value: '6º Ano', label: '6º Ano' },
    { value: '7º Ano', label: '7º Ano' },
    { value: '8º Ano', label: '8º Ano' },
    { value: '9º Ano', label: '9º Ano' }
  ],
  ensino_medio: [
    { value: '1ª Série EM', label: '1ª Série EM' },
    { value: '2ª Série EM', label: '2ª Série EM' },
    { value: '3ª Série EM', label: '3ª Série EM' }
  ],
  eja: [
    { value: 'EJA 1ª Etapa', label: 'EJA 1ª Etapa' },
    { value: 'EJA 2ª Etapa', label: 'EJA 2ª Etapa' }
  ],
  eja_final: [
    { value: 'EJA 3ª Etapa', label: 'EJA 3ª Etapa' },
    { value: 'EJA 4ª Etapa', label: 'EJA 4ª Etapa' }
  ]
};

export const Courses = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [courses, setCourses] = useState([]);
  const [schools, setSchools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [formData, setFormData] = useState({
    school_id: '',
    nivel_ensino: '',
    grade_levels: [],
    atendimento_programa: '',
    name: '',
    optativo: false,
    code: '',
    workload: ''
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  
  // SEMED pode visualizar tudo, mas não pode editar/excluir
  const canEdit = user?.role !== 'semed';
  const canDelete = user?.role !== 'semed';

  const niveisEnsino = {
    'educacao_infantil': 'Educação Infantil',
    'fundamental_anos_iniciais': 'Fundamental - Anos Iniciais',
    'fundamental_anos_finais': 'Fundamental - Anos Finais',
    'ensino_medio': 'Ensino Médio',
    'eja': 'EJA - Anos Iniciais',
    'eja_final': 'EJA - Anos Finais'
  };

  const atendimentosProgramas = {
    'aee': 'Atendimento Educacional Especializado - AEE',
    'atendimento_integral': 'Escola Integral',
    'reforco_escolar': 'Reforço Escolar',
    'aulas_complementares': 'Aulas Complementares',
    'recomposicao_aprendizagem': 'Recomposição de Aprendizagem'
  };

  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [coursesData, schoolsData] = await Promise.all([
          coursesAPI.getAll(),
          schoolsAPI.getAll()
        ]);
        setCourses(coursesData);
        setSchools(schoolsData);
      } catch (error) {
        setAlert({ type: 'error', message: 'Erro ao carregar dados' });
        setTimeout(() => setAlert(null), 5000);
        console.error(error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [reloadTrigger]);

  const reloadData = () => setReloadTrigger(prev => prev + 1);

  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  };

  const getSchoolName = (schoolId) => {
    if (!schoolId) {
      return <span className="text-blue-600 font-medium">Todas as escolas</span>;
    }
    const school = schools.find(s => s.id === schoolId);
    return school?.name || '-';
  };

  // Séries/anos disponíveis baseado no nível de ensino
  const availableGradeLevels = formData.nivel_ensino 
    ? GRADE_LEVELS_BY_EDUCATION[formData.nivel_ensino] || []
    : [];

  // Verifica se o nível requer especificação de séries (Anos Finais pode variar)
  const requiresGradeSpecification = formData.nivel_ensino === 'fundamental_anos_finais';

  const handleCreate = () => {
    setEditingCourse(null);
    setViewMode(false);
    setFormData({
      school_id: '', // Vazio = componente para todas as escolas
      nivel_ensino: '',
      grade_levels: [],
      atendimento_programa: '',
      name: '',
      code: '',
      workload: ''
    });
    setIsModalOpen(true);
  };

  const handleEdit = (course) => {
    setEditingCourse(course);
    setViewMode(false);
    setFormData({
      school_id: course.school_id || '',
      nivel_ensino: course.nivel_ensino || '',
      grade_levels: course.grade_levels || [],
      atendimento_programa: course.atendimento_programa || '',
      name: course.name || '',
      code: course.code || '',
      workload: course.workload || ''
    });
    setIsModalOpen(true);
  };

  const handleView = (course) => {
    setEditingCourse(course);
    setViewMode(true);
    setFormData({
      school_id: course.school_id || '',
      nivel_ensino: course.nivel_ensino || '',
      grade_levels: course.grade_levels || [],
      atendimento_programa: course.atendimento_programa || '',
      name: course.name || '',
      code: course.code || '',
      workload: course.workload || ''
    });
    setIsModalOpen(true);
  };

  const handleDelete = async (course) => {
    if (window.confirm(`Tem certeza que deseja excluir "${course.name}"?`)) {
      try {
        await coursesAPI.delete(course.id);
        showAlert('success', 'Componente excluído com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir componente');
        console.error(error);
      }
    }
  };

  const handleNivelChange = (nivel) => {
    setFormData({
      ...formData,
      nivel_ensino: nivel,
      grade_levels: [] // Limpa as séries ao mudar o nível
    });
  };

  const handleGradeLevelToggle = (gradeValue) => {
    const newGradeLevels = formData.grade_levels.includes(gradeValue)
      ? formData.grade_levels.filter(g => g !== gradeValue)
      : [...formData.grade_levels, gradeValue];
    
    setFormData({ ...formData, grade_levels: newGradeLevels });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const dataToSend = {
        ...formData,
        // Se school_id estiver vazio, envia null (componente para todas as escolas)
        school_id: formData.school_id || null,
        workload: formData.workload ? parseInt(formData.workload) : null,
        atendimento_programa: formData.atendimento_programa || null
      };
      
      if (editingCourse) {
        await coursesAPI.update(editingCourse.id, dataToSend);
        showAlert('success', 'Componente atualizado com sucesso');
      } else {
        await coursesAPI.create(dataToSend);
        showAlert('success', 'Componente criado com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar componente');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    { header: 'Nome', accessor: 'name' },
    { 
      header: 'Atendimento/Programa', 
      accessor: 'atendimento_programa',
      render: (row) => row.atendimento_programa 
        ? atendimentosProgramas[row.atendimento_programa] || row.atendimento_programa
        : <span className="text-gray-500 italic">Regular</span>
    },
    { 
      header: 'Nível de Ensino', 
      accessor: 'nivel_ensino',
      render: (row) => niveisEnsino[row.nivel_ensino] || row.nivel_ensino
    },
    { 
      header: 'Séries/Anos', 
      accessor: 'grade_levels',
      render: (row) => {
        if (!row.grade_levels || row.grade_levels.length === 0) {
          return <span className="text-gray-500 italic">Todas do nível</span>;
        }
        // Verifica se todas as séries do nível estão selecionadas
        const allGradesForLevel = GRADE_LEVELS_BY_EDUCATION[row.nivel_ensino] || [];
        if (allGradesForLevel.length > 0 && row.grade_levels.length >= allGradesForLevel.length) {
          // Verifica se realmente todas estão selecionadas
          const allSelected = allGradesForLevel.every(g => row.grade_levels.includes(g.value));
          if (allSelected) {
            return <span className="text-gray-500 italic">Todas do nível</span>;
          }
        }
        return row.grade_levels.join(', ');
      }
    },
    { 
      header: 'CH', 
      accessor: 'workload',
      render: (row) => row.workload ? `${row.workload}h` : '-'
    }
  ];

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Componentes Curriculares</h1>
              <p className="text-gray-600 text-sm">Gerencie os componentes curriculares por nível de ensino</p>
            </div>
          </div>
          {canEdit && (
            <button
              onClick={handleCreate}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            >
              <Plus size={20} />
              <span>Novo Componente</span>
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

        <DataTable
          columns={columns}
          data={courses}
          loading={loading}
          onView={handleView}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          canDelete={canDelete}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={viewMode ? 'Visualizar Componente' : (editingCourse ? 'Editar Componente' : 'Novo Componente')}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Escola
                <span className="text-gray-500 font-normal ml-2">(opcional)</span>
              </label>
              <select
                value={formData.school_id}
                onChange={(e) => setFormData({ ...formData, school_id: e.target.value })}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Todas as escolas (global)</option>
                {schools.map((school) => (
                  <option key={school.id} value={school.id}>
                    {school.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                {formData.school_id 
                  ? '✓ Componente exclusivo para a escola selecionada'
                  : '✓ Componente disponível para todas as escolas'}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nível de Ensino *</label>
              <select
                value={formData.nivel_ensino}
                onChange={(e) => handleNivelChange(e.target.value)}
                required
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Selecione o nível</option>
                {Object.entries(niveisEnsino).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {/* Séries/Anos - aparece quando nível é selecionado */}
            {formData.nivel_ensino && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Séries/Anos
                  {!requiresGradeSpecification && (
                    <span className="text-gray-500 font-normal ml-2">(opcional)</span>
                  )}
                </label>
                
                {/* Info box */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                  <div className="flex items-start gap-2">
                    <Info size={16} className="text-blue-600 mt-0.5 flex-shrink-0" />
                    <p className="text-sm text-blue-800">
                      {formData.nivel_ensino === 'fundamental_anos_iniciais' 
                        ? 'Para Anos Iniciais, os componentes são os mesmos para todas as séries. Não precisa selecionar.'
                        : formData.nivel_ensino === 'fundamental_anos_finais'
                        ? 'Para Anos Finais, selecione as séries que usam este componente com esta carga horária.'
                        : 'Selecione as séries/etapas específicas ou deixe vazio para aplicar a todas.'}
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 p-3 bg-gray-50 rounded-lg">
                  {availableGradeLevels.map((grade) => (
                    <label key={grade.value} className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.grade_levels.includes(grade.value)}
                        onChange={() => handleGradeLevelToggle(grade.value)}
                        disabled={viewMode}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-700">{grade.label}</span>
                    </label>
                  ))}
                </div>
                
                {formData.grade_levels.length === 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    Nenhuma série selecionada = aplica a todas do nível
                  </p>
                )}
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Atendimento/Programa
                <span className="text-gray-500 font-normal ml-2">(opcional)</span>
              </label>
              <select
                value={formData.atendimento_programa}
                onChange={(e) => setFormData({ ...formData, atendimento_programa: e.target.value })}
                disabled={viewMode}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Nenhum (componente regular)</option>
                {Object.entries(atendimentosProgramas).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nome do Componente *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                disabled={viewMode}
                placeholder="Ex: Matemática, Português, Ciências"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Código</label>
                <input
                  type="text"
                  value={formData.code}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                  disabled={viewMode}
                  placeholder="Ex: MAT, POR, CIE"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Carga Horária (h)</label>
                <input
                  type="number"
                  value={formData.workload}
                  onChange={(e) => setFormData({ ...formData, workload: e.target.value })}
                  disabled={viewMode}
                  min="0"
                  placeholder="Ex: 80"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                />
              </div>
            </div>

            {!viewMode && (
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
                >
                  {submitting ? 'Salvando...' : (editingCourse ? 'Atualizar' : 'Criar')}
                </button>
              </div>
            )}

            {viewMode && (
              <div className="flex justify-end mt-6 pt-4 border-t">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                >
                  Fechar
                </button>
              </div>
            )}
          </form>
        </Modal>
      </div>
    </Layout>
  );
};
