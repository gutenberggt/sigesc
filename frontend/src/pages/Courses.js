import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { coursesAPI, schoolsAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, Home } from 'lucide-react';

export const Courses = () => {
  const navigate = useNavigate();
  const [courses, setCourses] = useState([]);
  const [schools, setSchools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState(null);
  const [formData, setFormData] = useState({
    school_id: '',
    nivel_ensino: '',
    atendimento_programa: '',
    name: '',
    optativo: false,
    code: '',
    workload: '',
    grade_levels: []
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);

  const NIVEL_ENSINO_OPTIONS = [
    { value: '', label: 'Selecione o nível' },
    { value: 'educacao_infantil', label: 'Educação Infantil' },
    { value: 'fundamental_anos_iniciais', label: 'Fundamental - Anos Iniciais' },
    { value: 'fundamental_anos_finais', label: 'Fundamental - Anos Finais' },
    { value: 'ensino_medio', label: 'Ensino Médio' },
    { value: 'eja', label: 'EJA - Anos Iniciais' },
    { value: 'eja_final', label: 'EJA - Anos Finais' }
  ];

  const ATENDIMENTO_OPTIONS = [
    { value: '', label: 'Regular (Base Comum)' },
    { value: 'atendimento_integral', label: 'Escola Integral' },
    { value: 'aee', label: 'AEE - Atendimento Educacional Especializado' },
    { value: 'reforco_escolar', label: 'Reforço Escolar' },
    { value: 'aulas_complementares', label: 'Aulas Complementares' }
  ];

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

  const handleCreate = () => {
    setEditingCourse(null);
    setFormData({
      school_id: '',
      nivel_ensino: '',
      atendimento_programa: '',
      name: '',
      optativo: false,
      code: '',
      workload: '',
      grade_levels: []
    });
    setIsModalOpen(true);
  };

  const handleEdit = (course) => {
    setEditingCourse(course);
    setFormData({
      school_id: course.school_id || '',
      nivel_ensino: course.nivel_ensino || '',
      atendimento_programa: course.atendimento_programa || '',
      name: course.name || '',
      optativo: course.optativo || false,
      code: course.code || '',
      workload: course.workload || '',
      grade_levels: course.grade_levels || []
    });
    setIsModalOpen(true);
  };

  const handleDelete = async (course) => {
    if (window.confirm(`Tem certeza que deseja excluir o componente "${course.name}"?`)) {
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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const submitData = {
        ...formData,
        school_id: formData.school_id || null,
        nivel_ensino: formData.nivel_ensino || null,
        atendimento_programa: formData.atendimento_programa || null,
        workload: formData.workload ? parseInt(formData.workload) : null,
        // Se for Regular (atendimento vazio), optativo deve ser false
        optativo: formData.atendimento_programa ? formData.optativo : false
      };

      if (editingCourse) {
        await coursesAPI.update(editingCourse.id, submitData);
        showAlert('success', 'Componente atualizado com sucesso');
      } else {
        await coursesAPI.create(submitData);
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

  const getNivelLabel = (nivel) => {
    const opt = NIVEL_ENSINO_OPTIONS.find(o => o.value === nivel);
    return opt?.label || nivel || '-';
  };

  const getAtendimentoLabel = (atend) => {
    const opt = ATENDIMENTO_OPTIONS.find(o => o.value === atend);
    return opt?.label || 'Regular';
  };

  const columns = [
    { header: 'Nome', accessor: 'name' },
    {
      header: 'Nível de Ensino',
      accessor: 'nivel_ensino',
      render: (row) => getNivelLabel(row.nivel_ensino)
    },
    {
      header: 'Atendimento',
      accessor: 'atendimento_programa',
      render: (row) => (
        <div className="flex items-center gap-2">
          <span>{getAtendimentoLabel(row.atendimento_programa)}</span>
          {row.optativo && (
            <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full">
              Optativo
            </span>
          )}
        </div>
      )
    },
    {
      header: 'Carga Horária',
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
              data-testid="back-to-dashboard-button"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900" data-testid="courses-title">Componentes Curriculares</h1>
              <p className="text-gray-600 text-sm">Gerencie os componentes curriculares por nível de ensino</p>
            </div>
          </div>
          <button
            onClick={handleCreate}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            data-testid="create-course-button"
          >
            <Plus size={20} />
            <span>Novo Componente</span>
          </button>
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

        <DataTable
          columns={columns}
          data={courses}
          loading={loading}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={editingCourse ? 'Editar Componente Curricular' : 'Novo Componente Curricular'}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Nível de Ensino */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nível de Ensino *</label>
              <select
                value={formData.nivel_ensino}
                onChange={(e) => setFormData({ ...formData, nivel_ensino: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {NIVEL_ENSINO_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Atendimento/Programa */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Atendimento/Programa</label>
              <select
                value={formData.atendimento_programa}
                onChange={(e) => setFormData({ 
                  ...formData, 
                  atendimento_programa: e.target.value,
                  // Reset optativo quando mudar para Regular
                  optativo: e.target.value ? formData.optativo : false
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {ATENDIMENTO_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Nome do Componente */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nome do Componente *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                placeholder="Ex: Matemática, Língua Portuguesa"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="course-name-input"
              />
            </div>

            {/* Optativo - só aparece quando NÃO é Regular */}
            {formData.atendimento_programa && (
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.optativo}
                    onChange={(e) => setFormData({ ...formData, optativo: e.target.checked })}
                    className="mt-1 w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
                  />
                  <div>
                    <span className="font-medium text-gray-900">Componente Optativo</span>
                    <p className="text-sm text-gray-600 mt-1">
                      Se marcado, este componente não interferirá na aprovação, frequência ou carga horária obrigatória da série/ano. 
                      A carga horária será contabilizada separadamente.
                    </p>
                  </div>
                </label>
              </div>
            )}

            {/* Código */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Código</label>
              <input
                type="text"
                value={formData.code}
                onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                placeholder="Ex: MAT01, PORT01"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="course-code-input"
              />
            </div>

            {/* Carga Horária */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Carga Horária Anual (horas)</label>
              <input
                type="number"
                value={formData.workload}
                onChange={(e) => setFormData({ ...formData, workload: e.target.value })}
                min="0"
                placeholder="Ex: 80"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="course-workload-input"
              />
            </div>

            {/* Escola (opcional) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Escola (opcional)</label>
              <select
                value={formData.school_id}
                onChange={(e) => setFormData({ ...formData, school_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="course-school-select"
              >
                <option value="">Todas as escolas</option>
                {schools.map((school) => (
                  <option key={school.id} value={school.id}>
                    {school.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Deixe em branco para aplicar a todas as escolas do nível de ensino
              </p>
            </div>

            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
                data-testid="cancel-button"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={submitting}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400"
                data-testid="submit-button"
              >
                {submitting ? 'Salvando...' : 'Salvar'}
              </button>
            </div>
          </form>
        </Modal>
      </div>
    </Layout>
  );
};
