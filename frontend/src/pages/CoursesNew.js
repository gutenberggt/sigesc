import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { coursesAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';

export const Courses = () => {
  const navigate = useNavigate();
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingCourse, setEditingCourse] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [formData, setFormData] = useState({
    nivel_ensino: '',
    atendimento_programa: '',
    name: '',
    code: '',
    workload: ''
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const niveisEnsino = {
    'educacao_infantil': 'Educação Infantil',
    'fundamental_anos_iniciais': 'Fundamental - Anos Iniciais',
    'fundamental_anos_finais': 'Fundamental - Anos Finais',
    'ensino_medio': 'Ensino Médio',
    'eja': 'EJA - Educação de Jovens e Adultos'
  };

  const atendimentosProgramas = {
    'aee': 'Atendimento Educacional Especializado - AEE',
    'atendimento_integral': 'Atendimento Integral',
    'reforco_escolar': 'Reforço Escolar',
    'aulas_complementares': 'Aulas Complementares'
  };

  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const coursesData = await coursesAPI.getAll();
        setCourses(coursesData);
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
    setViewMode(false);
    setFormData({
      nivel_ensino: '',
      atendimento_programa: '',
      name: '',
      code: '',
      workload: ''
    });
    setIsModalOpen(true);
  };

  const handleView = (course) => {
    setEditingCourse(course);
    setViewMode(true);
    setFormData(course);
    setIsModalOpen(true);
  };

  const handleEdit = (course) => {
    setEditingCourse(course);
    setViewMode(false);
    setFormData(course);
    setIsModalOpen(true);
  };

  const handleDelete = async (course) => {
    if (window.confirm(`Tem certeza que deseja excluir o componente curricular "${course.name}"?`)) {
      try {
        await coursesAPI.delete(course.id);
        showAlert('success', 'Componente curricular excluído com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir componente curricular');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const submitData = {
        nivel_ensino: formData.nivel_ensino,
        atendimento_programa: formData.atendimento_programa || null,
        name: formData.name,
        code: formData.code || null,
        workload: formData.workload ? parseInt(formData.workload) : null
      };

      if (editingCourse) {
        await coursesAPI.update(editingCourse.id, submitData);
        showAlert('success', 'Componente curricular atualizado com sucesso');
      } else {
        await coursesAPI.create(submitData);
        showAlert('success', 'Componente curricular criado com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar componente curricular');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const columns = [
    {
      header: 'Nível de Ensino',
      accessor: 'nivel_ensino',
      render: (row) => niveisEnsino[row.nivel_ensino] || row.nivel_ensino
    },
    {
      header: 'Atendimento/Programa',
      accessor: 'atendimento_programa',
      render: (row) => row.atendimento_programa ? atendimentosProgramas[row.atendimento_programa] : '-'
    },
    {
      header: 'Nome',
      accessor: 'name'
    },
    {
      header: 'Código',
      accessor: 'code',
      render: (row) => row.code || '-'
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
        {/* Botão Voltar */}
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
          data-testid="back-to-dashboard-button"
        >
          <ArrowLeft size={20} />
          <span>Voltar ao Dashboard</span>
        </button>

        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900" data-testid="courses-title">
              Componentes Curriculares
            </h1>
            <p className="text-gray-600 mt-1">Componentes globais disponíveis para todas as escolas</p>
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
          onView={handleView}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={viewMode ? 'Visualizar Componente Curricular' : (editingCourse ? 'Editar Componente Curricular' : 'Novo Componente Curricular')}
          size="lg"
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Informação importante */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
              <p className="text-sm text-blue-800">
                <strong>📌 Importante:</strong> Primeiro selecione o nível de ensino e, se necessário, o atendimento/programa. 
                A carga horária pode variar conforme essas escolhas.
              </p>
            </div>

            <div className="space-y-4">
              {/* Nível de Ensino */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Nível de Ensino * <span className="text-xs text-gray-500">(Selecione primeiro)</span>
                </label>
                <select
                  value={formData.nivel_ensino}
                  onChange={(e) => setFormData({ ...formData, nivel_ensino: e.target.value })}
                  required
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  data-testid="course-nivel-select"
                >
                  <option value="">Selecione um nível de ensino</option>
                  {Object.entries(niveisEnsino).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Atendimento/Programa */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Atendimento/Programa <span className="text-xs text-gray-500">(Opcional)</span>
                </label>
                <select
                  value={formData.atendimento_programa || ''}
                  onChange={(e) => setFormData({ ...formData, atendimento_programa: e.target.value })}
                  disabled={viewMode || !formData.nivel_ensino}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  data-testid="course-atendimento-select"
                >
                  <option value="">Nenhum (componente regular)</option>
                  {Object.entries(atendimentosProgramas).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                {!formData.nivel_ensino && (
                  <p className="text-xs text-gray-500 mt-1">Selecione primeiro o nível de ensino</p>
                )}
              </div>

              <hr className="my-4" />

              {/* Nome do Componente */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Nome do Componente Curricular *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  disabled={viewMode}
                  placeholder="Ex: Matemática, Língua Portuguesa, Ciências"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  data-testid="course-name-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                {/* Código */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Código</label>
                  <input
                    type="text"
                    value={formData.code || ''}
                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                    disabled={viewMode}
                    placeholder="Ex: MAT01, PORT01"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                    data-testid="course-code-input"
                  />
                </div>

                {/* Carga Horária */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Carga Horária (horas)
                  </label>
                  <input
                    type="number"
                    value={formData.workload || ''}
                    onChange={(e) => setFormData({ ...formData, workload: e.target.value })}
                    min="0"
                    disabled={viewMode}
                    placeholder="Ex: 80"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                    data-testid="course-workload-input"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end space-x-3 pt-4 border-t">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
                data-testid="cancel-button"
              >
                {viewMode ? 'Fechar' : 'Cancelar'}
              </button>
              {!viewMode && (
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400"
                  data-testid="submit-button"
                >
                  {submitting ? 'Salvando...' : 'Salvar'}
                </button>
              )}
            </div>
          </form>
        </Modal>
      </div>
    </Layout>
  );
};
