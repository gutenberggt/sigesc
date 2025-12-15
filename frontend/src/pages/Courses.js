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
    name: '',
    code: '',
    workload: ''
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
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

  const handleCreate = () => {
    setEditingCourse(null);
    const defaultSchoolId = schools.length > 0 ? schools[0].id : '';
    setFormData({
      school_id: defaultSchoolId,
      name: '',
      code: '',
      workload: ''
    });
    setIsModalOpen(true);
  };

  const handleEdit = (course) => {
    setEditingCourse(course);
    setFormData({
      school_id: course.school_id,
      name: course.name,
      code: course.code || '',
      workload: course.workload || ''
    });
    setIsModalOpen(true);
  };

  const handleDelete = async (course) => {
    if (window.confirm(`Tem certeza que deseja excluir a disciplina "${course.name}"?`)) {
      try {
        await coursesAPI.delete(course.id);
        showAlert('success', 'Disciplina excluída com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir disciplina');
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
        workload: formData.workload ? parseInt(formData.workload) : null
      };

      if (editingCourse) {
        await coursesAPI.update(editingCourse.id, submitData);
        showAlert('success', 'Disciplina atualizada com sucesso');
      } else {
        await coursesAPI.create(submitData);
        showAlert('success', 'Disciplina criada com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar disciplina');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const getSchoolName = (schoolId) => {
    const school = schools.find(s => s.id === schoolId);
    return school?.name || schoolId;
  };

  const columns = [
    { header: 'Nome', accessor: 'name' },
    {
      header: 'Escola',
      accessor: 'school_id',
      render: (row) => getSchoolName(row.school_id)
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
              <h1 className="text-2xl font-bold text-gray-900" data-testid="courses-title">Disciplinas</h1>
              <p className="text-gray-600 text-sm">Gerencie as disciplinas das escolas</p>
            </div>
          </div>
          <button
            onClick={handleCreate}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            data-testid="create-course-button"
          >
            <Plus size={20} />
            <span>Nova Disciplina</span>
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
          title={editingCourse ? 'Editar Disciplina' : 'Nova Disciplina'}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Escola *</label>
              <select
                value={formData.school_id}
                onChange={(e) => setFormData({ ...formData, school_id: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="course-school-select"
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
              <label className="block text-sm font-medium text-gray-700 mb-2">Nome da Disciplina *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                placeholder="Ex: Matemática, Português"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="course-name-input"
              />
            </div>

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

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Carga Horária (horas)</label>
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
