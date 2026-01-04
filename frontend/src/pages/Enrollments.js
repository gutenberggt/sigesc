import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { enrollmentsAPI, studentsAPI, schoolsAPI, classesAPI, coursesAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { Plus, AlertCircle, CheckCircle, Home } from 'lucide-react';

const STATUS_LABELS = {
  'active': 'Ativa',
  'completed': 'Concluída',
  'cancelled': 'Cancelada',
  'transferred': 'Transferida'
};

const STATUS_COLORS = {
  'active': 'bg-green-100 text-green-800',
  'completed': 'bg-blue-100 text-blue-800',
  'cancelled': 'bg-red-100 text-red-800',
  'transferred': 'bg-yellow-100 text-yellow-800'
};

const initialFormData = {
  student_id: '',
  school_id: '',
  class_id: '',
  course_ids: [],
  academic_year: new Date().getFullYear(),
  enrollment_date: new Date().toISOString().split('T')[0],
  enrollment_number: '',
  status: 'active',
  observations: ''
};

export const Enrollments = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [enrollments, setEnrollments] = useState([]);
  const [students, setStudents] = useState([]);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingEnrollment, setEditingEnrollment] = useState(null);
  const [viewMode, setViewMode] = useState(false);
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);
  const [formData, setFormData] = useState(initialFormData);

  // SEMED pode visualizar tudo, mas não pode editar/excluir
  const canEdit = user?.role !== 'semed';
  const canDelete = user?.role !== 'semed';

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [enrollmentsData, studentsData, schoolsData, classesData, coursesData] = await Promise.all([
          enrollmentsAPI.getAll(),
          studentsAPI.getAll(),
          schoolsAPI.getAll(),
          classesAPI.getAll(),
          coursesAPI.getAll()
        ]);
        setEnrollments(enrollmentsData);
        setStudents(studentsData);
        setSchools(schoolsData);
        setClasses(classesData);
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

  const generateEnrollmentNumber = () => {
    const year = new Date().getFullYear();
    const random = Math.floor(Math.random() * 100000).toString().padStart(5, '0');
    return `MAT${year}${random}`;
  };

  const handleCreate = () => {
    setEditingEnrollment(null);
    setViewMode(false);
    setFormData({
      ...initialFormData,
      enrollment_number: generateEnrollmentNumber(),
      school_id: schools.length > 0 ? schools[0].id : ''
    });
    setIsModalOpen(true);
  };

  const handleView = (enrollment) => {
    setEditingEnrollment(enrollment);
    setViewMode(true);
    setFormData({ ...initialFormData, ...enrollment });
    setIsModalOpen(true);
  };

  const handleEdit = (enrollment) => {
    setEditingEnrollment(enrollment);
    setViewMode(false);
    setFormData({ ...initialFormData, ...enrollment });
    setIsModalOpen(true);
  };

  const handleDelete = async (enrollment) => {
    if (window.confirm(`Tem certeza que deseja excluir esta matrícula?`)) {
      try {
        await enrollmentsAPI.delete(enrollment.id);
        showAlert('success', 'Matrícula excluída com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir matrícula');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.student_id) {
      showAlert('error', 'Selecione um aluno');
      return;
    }
    if (!formData.class_id) {
      showAlert('error', 'Selecione uma turma');
      return;
    }
    
    setSubmitting(true);

    try {
      if (editingEnrollment) {
        await enrollmentsAPI.update(editingEnrollment.id, formData);
        showAlert('success', 'Matrícula atualizada com sucesso');
      } else {
        await enrollmentsAPI.create(formData);
        showAlert('success', 'Matrícula realizada com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar matrícula');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleCourseToggle = (courseId) => {
    setFormData(prev => {
      const currentIds = prev.course_ids || [];
      if (currentIds.includes(courseId)) {
        return { ...prev, course_ids: currentIds.filter(id => id !== courseId) };
      } else {
        return { ...prev, course_ids: [...currentIds, courseId] };
      }
    });
  };

  const getStudentName = (studentId) => {
    const student = students.find(s => s.id === studentId);
    return student?.full_name || student?.enrollment_number || '-';
  };

  const getSchoolName = (schoolId) => {
    const school = schools.find(s => s.id === schoolId);
    return school?.name || '-';
  };

  const getClassName = (classId) => {
    const classItem = classes.find(c => c.id === classId);
    return classItem ? `${classItem.name} - ${classItem.grade_level}` : '-';
  };

  // Filtra classes pela escola selecionada
  const filteredClasses = classes.filter(c => c.school_id === formData.school_id);
  
  // Filtra alunos pela escola selecionada
  const filteredStudents = students.filter(s => s.school_id === formData.school_id);

  const columns = [
    { header: 'Nº Matrícula', accessor: 'enrollment_number', render: (row) => row.enrollment_number || '-' },
    { header: 'Aluno', accessor: 'student_id', render: (row) => getStudentName(row.student_id) },
    { header: 'Escola', accessor: 'school_id', render: (row) => getSchoolName(row.school_id) },
    { header: 'Turma', accessor: 'class_id', render: (row) => getClassName(row.class_id) },
    { header: 'Ano Letivo', accessor: 'academic_year' },
    { 
      header: 'Componentes', 
      accessor: 'course_ids', 
      render: (row) => {
        const count = row.course_ids?.length || 0;
        return <span className="text-purple-600 font-medium">{count}</span>;
      }
    },
    { 
      header: 'Status', 
      accessor: 'status',
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[row.status] || 'bg-gray-100 text-gray-800'}`}>
          {STATUS_LABELS[row.status] || row.status}
        </span>
      )
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
              <h1 className="text-2xl font-bold text-gray-900">Matrículas</h1>
              <p className="text-gray-600 text-sm">Gerencie as matrículas dos alunos</p>
            </div>
          </div>
          {canEdit && (
            <button
              onClick={handleCreate}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            >
              <Plus size={20} />
              <span>Nova Matrícula</span>
            </button>
          )}
        </div>

        {alert && (
          <div className={`p-4 rounded-lg flex items-start ${
            alert.type === 'success' ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
          }`}>
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
          data={enrollments}
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
          title={viewMode ? 'Visualizar Matrícula' : (editingEnrollment ? 'Editar Matrícula' : 'Nova Matrícula')}
          size="xl"
        >
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Dados da Matrícula */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Dados da Matrícula</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Nº Matrícula</label>
                  <input
                    type="text"
                    value={formData.enrollment_number}
                    onChange={(e) => updateFormData('enrollment_number', e.target.value)}
                    disabled={viewMode}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo *</label>
                  <input
                    type="number"
                    value={formData.academic_year}
                    onChange={(e) => updateFormData('academic_year', parseInt(e.target.value))}
                    required
                    disabled={viewMode}
                    min="2020"
                    max="2030"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Data da Matrícula</label>
                  <input
                    type="date"
                    value={formData.enrollment_date}
                    onChange={(e) => updateFormData('enrollment_date', e.target.value)}
                    disabled={viewMode}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  />
                </div>
              </div>
            </div>

            {/* Escola e Aluno */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Escola e Aluno</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Escola *</label>
                  <select
                    value={formData.school_id}
                    onChange={(e) => {
                      updateFormData('school_id', e.target.value);
                      updateFormData('class_id', '');
                      updateFormData('student_id', '');
                    }}
                    required
                    disabled={viewMode || editingEnrollment}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  >
                    <option value="">Selecione uma escola</option>
                    {schools.map(school => (
                      <option key={school.id} value={school.id}>{school.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Aluno *</label>
                  <select
                    value={formData.student_id}
                    onChange={(e) => updateFormData('student_id', e.target.value)}
                    required
                    disabled={viewMode || editingEnrollment || !formData.school_id}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  >
                    <option value="">Selecione um aluno</option>
                    {filteredStudents.map(student => (
                      <option key={student.id} value={student.id}>
                        {student.full_name || student.enrollment_number}
                      </option>
                    ))}
                  </select>
                  {formData.school_id && filteredStudents.length === 0 && (
                    <p className="text-sm text-yellow-600 mt-1">Nenhum aluno cadastrado nesta escola</p>
                  )}
                </div>
              </div>
            </div>

            {/* Turma */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Turma</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Turma *</label>
                  <select
                    value={formData.class_id}
                    onChange={(e) => updateFormData('class_id', e.target.value)}
                    required
                    disabled={viewMode || !formData.school_id}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  >
                    <option value="">Selecione uma turma</option>
                    {filteredClasses.map(classItem => (
                      <option key={classItem.id} value={classItem.id}>
                        {classItem.name}
                      </option>
                    ))}
                  </select>
                  {formData.school_id && filteredClasses.length === 0 && (
                    <p className="text-sm text-yellow-600 mt-1">Nenhuma turma cadastrada nesta escola</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                  <select
                    value={formData.status}
                    onChange={(e) => updateFormData('status', e.target.value)}
                    disabled={viewMode}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  >
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Componentes Curriculares */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">
                Componentes Curriculares
                <span className="text-sm font-normal text-gray-500 ml-2">
                  ({formData.course_ids?.length || 0} selecionado(s))
                </span>
              </h3>
              
              {courses.length === 0 ? (
                <p className="text-gray-500 text-center py-4">Nenhum componente curricular cadastrado</p>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2 max-h-60 overflow-y-auto p-2 border rounded-lg">
                  {courses.map(course => (
                    <label
                      key={course.id}
                      className={`flex items-center p-2 border rounded cursor-pointer transition-colors text-sm ${
                        formData.course_ids?.includes(course.id)
                          ? 'border-purple-500 bg-purple-50'
                          : 'border-gray-200 hover:border-gray-300'
                      } ${viewMode ? 'cursor-default' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={formData.course_ids?.includes(course.id) || false}
                        onChange={() => !viewMode && handleCourseToggle(course.id)}
                        disabled={viewMode}
                        className="h-4 w-4 text-purple-600 rounded mr-2"
                      />
                      <span className="truncate" title={course.name}>{course.name}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Observações */}
            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Observações</h3>
              <textarea
                value={formData.observations}
                onChange={(e) => updateFormData('observations', e.target.value)}
                disabled={viewMode}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                placeholder="Observações sobre a matrícula..."
              />
            </div>
            
            <div className="flex justify-end space-x-3 pt-4 border-t">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
              >
                {viewMode ? 'Fechar' : 'Cancelar'}
              </button>
              {!viewMode && (
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:bg-gray-400"
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
