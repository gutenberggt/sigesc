import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { classesAPI, schoolsAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';

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
    grade_level: '',
    teacher_ids: []
  });
  
  // SEMED pode visualizar tudo, mas não pode editar/excluir
  const canEdit = user?.role !== 'semed';
  const canDelete = user?.role !== 'semed';
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [reloadTrigger, setReloadTrigger] = useState(0);

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

  const handleCreate = () => {
    setEditingClass(null);
    const defaultSchoolId = schools.length > 0 ? schools[0].id : '';
    setFormData({
      school_id: defaultSchoolId,
      academic_year: new Date().getFullYear(),
      name: '',
      shift: 'morning',
      grade_level: '',
      teacher_ids: []
    });
    setIsModalOpen(true);
  };

  const handleEdit = (classItem) => {
    setEditingClass(classItem);
    setFormData({
      school_id: classItem.school_id,
      academic_year: classItem.academic_year,
      name: classItem.name,
      shift: classItem.shift,
      grade_level: classItem.grade_level,
      teacher_ids: classItem.teacher_ids || []
    });
    setIsModalOpen(true);
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
      if (editingClass) {
        await classesAPI.update(editingClass.id, formData);
        showAlert('success', 'Turma atualizada com sucesso');
      } else {
        await classesAPI.create(formData);
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

  const columns = [
    { header: 'Nome', accessor: 'name' },
    {
      header: 'Escola',
      accessor: 'school_id',
      render: (row) => getSchoolName(row.school_id)
    },
    { header: 'Ano Letivo', accessor: 'academic_year' },
    { header: 'Série/Etapa', accessor: 'grade_level' },
    {
      header: 'Turno',
      accessor: 'shift',
      render: (row) => shiftLabels[row.shift]
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
            <h1 className="text-3xl font-bold text-gray-900" data-testid="classes-title">Turmas</h1>
            <p className="text-gray-600 mt-1">Gerencie as turmas das escolas</p>
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

        <DataTable
          columns={columns}
          data={classes}
          loading={loading}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          canDelete={canDelete}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={editingClass ? 'Editar Turma' : 'Nova Turma'}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Escola *</label>
              <select
                value={formData.school_id}
                onChange={(e) => setFormData({ ...formData, school_id: e.target.value })}
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
              <label className="block text-sm font-medium text-gray-700 mb-2">Série/Etapa *</label>
              <input
                type="text"
                value={formData.grade_level}
                onChange={(e) => setFormData({ ...formData, grade_level: e.target.value })}
                required
                placeholder="Ex: 1º Ano EF, 6º Ano"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="class-grade-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Turno *</label>
              <select
                value={formData.shift}
                onChange={(e) => setFormData({ ...formData, shift: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="class-shift-select"
              >
                {Object.entries(shiftLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
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
