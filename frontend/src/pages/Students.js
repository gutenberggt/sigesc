import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { studentsAPI, schoolsAPI, classesAPI, usersAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, Home } from 'lucide-react';

export const Students = () => {
  const navigate = useNavigate();
  const [students, setStudents] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStudent, setEditingStudent] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [formData, setFormData] = useState({
    school_id: '',
    enrollment_number: '',
    class_id: '',
    user_id: null,
    birth_date: '',
    guardian_ids: []
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [studentsData, schoolsData, classesData] = await Promise.all([
          studentsAPI.getAll(),
          schoolsAPI.getAll(),
          classesAPI.getAll()
        ]);
        setStudents(studentsData);
        setSchools(schoolsData);
        setClasses(classesData);
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

  const generateEnrollmentNumber = () => {
    const year = new Date().getFullYear();
    const random = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
    return `${year}${random}`;
  };

  const handleCreate = () => {
    setEditingStudent(null);
    setViewMode(false);
    setFormData({
      school_id: schools.length > 0 ? schools[0].id : '',
      enrollment_number: generateEnrollmentNumber(),
      class_id: '',
      user_id: null,
      birth_date: '',
      guardian_ids: []
    });
    setIsModalOpen(true);
  };

  const handleView = (student) => {
    setEditingStudent(student);
    setViewMode(true);
    setFormData(student);
    setIsModalOpen(true);
  };

  const handleEdit = (student) => {
    setEditingStudent(student);
    setViewMode(false);
    setFormData(student);
    setIsModalOpen(true);
  };

  const handleDelete = async (student) => {
    if (window.confirm(`Tem certeza que deseja excluir o aluno com matrícula "${student.enrollment_number}"?`)) {
      try {
        await studentsAPI.delete(student.id);
        showAlert('success', 'Aluno excluído com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir aluno');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      if (editingStudent) {
        await studentsAPI.update(editingStudent.id, formData);
        showAlert('success', 'Aluno atualizado com sucesso');
      } else {
        await studentsAPI.create(formData);
        showAlert('success', 'Aluno criado com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar aluno');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const getSchoolName = (schoolId) => {
    const school = schools.find(s => s.id === schoolId);
    return school?.name || schoolId;
  };

  const getClassName = (classId) => {
    const classItem = classes.find(c => c.id === classId);
    return classItem?.name || classId;
  };

  const columns = [
    {
      header: 'Matrícula',
      accessor: 'enrollment_number'
    },
    {
      header: 'Escola',
      accessor: 'school_id',
      render: (row) => getSchoolName(row.school_id)
    },
    {
      header: 'Turma',
      accessor: 'class_id',
      render: (row) => getClassName(row.class_id)
    },
    {
      header: 'Data Nascimento',
      accessor: 'birth_date',
      render: (row) => row.birth_date || '-'
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
          <Home size={18} />
          <span>Início</span>
        </button>

        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900" data-testid="students-title">Alunos</h1>
            <p className="text-gray-600 mt-1">Gerencie os alunos das escolas</p>
          </div>
          <button
            onClick={handleCreate}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            data-testid="create-student-button"
          >
            <Plus size={20} />
            <span>Novo Aluno</span>
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
          data={students}
          loading={loading}
          onView={handleView}
          onEdit={handleEdit}
          onDelete={handleDelete}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={viewMode ? 'Visualizar Aluno' : (editingStudent ? 'Editar Aluno' : 'Novo Aluno')}
          size="lg"
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Escola *</label>
                <select
                  value={formData.school_id}
                  onChange={(e) => setFormData({ ...formData, school_id: e.target.value })}
                  required
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  data-testid="student-school-select"
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
                <label className="block text-sm font-medium text-gray-700 mb-2">Número de Matrícula *</label>
                <input
                  type="text"
                  value={formData.enrollment_number}
                  onChange={(e) => setFormData({ ...formData, enrollment_number: e.target.value })}
                  required
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  placeholder="Ex: 20240001"
                  data-testid="student-enrollment-input"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Turma *</label>
                <select
                  value={formData.class_id}
                  onChange={(e) => setFormData({ ...formData, class_id: e.target.value })}
                  required
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  data-testid="student-class-select"
                >
                  <option value="">Selecione uma turma</option>
                  {classes.filter(c => c.school_id === formData.school_id).map((classItem) => (
                    <option key={classItem.id} value={classItem.id}>
                      {classItem.name} - {classItem.grade_level}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Data de Nascimento</label>
                <input
                  type="date"
                  value={formData.birth_date || ''}
                  onChange={(e) => setFormData({ ...formData, birth_date: e.target.value })}
                  disabled={viewMode}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                  data-testid="student-birthdate-input"
                />
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
