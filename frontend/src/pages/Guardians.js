import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { Tabs } from '@/components/Tabs';
import { guardiansAPI, studentsAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { Plus, AlertCircle, CheckCircle, Home, UserPlus } from 'lucide-react';
import { formatPhone, formatCEP } from '@/utils/formatters';

const STATES = [
  'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 'MG',
  'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
];

const RELATIONSHIPS = {
  'pai': 'Pai',
  'mae': 'Mãe',
  'avo': 'Avô/Avó',
  'tio': 'Tio/Tia',
  'irmao': 'Irmão/Irmã',
  'responsavel': 'Responsável Legal',
  'outro': 'Outro'
};

const initialFormData = {
  full_name: '',
  cpf: '',
  rg: '',
  birth_date: '',
  phone: '',
  cell_phone: '',
  email: '',
  address: '',
  address_number: '',
  address_complement: '',
  neighborhood: '',
  city: '',
  state: '',
  zip_code: '',
  occupation: '',
  workplace: '',
  work_phone: '',
  relationship: 'responsavel',
  student_ids: [],
  user_id: null,
  status: 'active',
  observations: ''
};

export const Guardians = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [guardians, setGuardians] = useState([]);
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingGuardian, setEditingGuardian] = useState(null);
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
        const [guardiansData, studentsData] = await Promise.all([
          guardiansAPI.getAll(),
          studentsAPI.getAll()
        ]);
        setGuardians(guardiansData);
        setStudents(studentsData);
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
    setEditingGuardian(null);
    setViewMode(false);
    setFormData(initialFormData);
    setIsModalOpen(true);
  };

  const handleView = (guardian) => {
    setEditingGuardian(guardian);
    setViewMode(true);
    setFormData({ ...initialFormData, ...guardian });
    setIsModalOpen(true);
  };

  const handleEdit = (guardian) => {
    setEditingGuardian(guardian);
    setViewMode(false);
    setFormData({ ...initialFormData, ...guardian });
    setIsModalOpen(true);
  };

  const handleDelete = async (guardian) => {
    if (window.confirm(`Tem certeza que deseja excluir o responsável "${guardian.full_name}"?`)) {
      try {
        await guardiansAPI.delete(guardian.id);
        showAlert('success', 'Responsável excluído com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir responsável');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.full_name) {
      showAlert('error', 'O nome é obrigatório');
      return;
    }
    
    setSubmitting(true);

    try {
      if (editingGuardian) {
        await guardiansAPI.update(editingGuardian.id, formData);
        showAlert('success', 'Responsável atualizado com sucesso');
      } else {
        await guardiansAPI.create(formData);
        showAlert('success', 'Responsável cadastrado com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar responsável');
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const updateFormData = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleStudentToggle = (studentId) => {
    setFormData(prev => {
      const currentIds = prev.student_ids || [];
      if (currentIds.includes(studentId)) {
        return { ...prev, student_ids: currentIds.filter(id => id !== studentId) };
      } else {
        return { ...prev, student_ids: [...currentIds, studentId] };
      }
    });
  };

  const getStudentNames = (studentIds) => {
    if (!studentIds || studentIds.length === 0) return '-';
    return studentIds
      .map(id => students.find(s => s.id === id)?.full_name || id)
      .join(', ');
  };

  const columns = [
    { header: 'Nome', accessor: 'full_name' },
    { header: 'CPF', accessor: 'cpf', render: (row) => row.cpf || '-' },
    { header: 'Telefone', accessor: 'cell_phone', render: (row) => row.cell_phone || row.phone || '-' },
    { header: 'Parentesco', accessor: 'relationship', render: (row) => RELATIONSHIPS[row.relationship] || row.relationship },
    { 
      header: 'Alunos Vinculados', 
      accessor: 'student_ids', 
      render: (row) => {
        const count = row.student_ids?.length || 0;
        return <span className="text-blue-600 font-medium">{count} aluno(s)</span>;
      }
    },
    { 
      header: 'Status', 
      accessor: 'status',
      render: (row) => (
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
          row.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
        }`}>
          {row.status === 'active' ? 'Ativo' : 'Inativo'}
        </span>
      )
    }
  ];

  // ========== TABS CONTENT ==========
  
  const tabDadosPessoais = (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Dados Pessoais</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Nome Completo *</label>
          <input
            type="text"
            value={formData.full_name}
            onChange={(e) => updateFormData('full_name', e.target.value)}
            required
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">CPF</label>
          <input
            type="text"
            value={formData.cpf}
            onChange={(e) => updateFormData('cpf', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="000.000.000-00"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">RG</label>
          <input
            type="text"
            value={formData.rg}
            onChange={(e) => updateFormData('rg', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Data de Nascimento</label>
          <input
            type="date"
            value={formData.birth_date}
            onChange={(e) => updateFormData('birth_date', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Parentesco *</label>
          <select
            value={formData.relationship}
            onChange={(e) => updateFormData('relationship', e.target.value)}
            required
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            {Object.entries(RELATIONSHIPS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">Contato</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Telefone Fixo</label>
          <input
            type="text"
            value={formData.phone}
            onChange={(e) => updateFormData('phone', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="(00) 0000-0000"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Celular</label>
          <input
            type="text"
            value={formData.cell_phone}
            onChange={(e) => updateFormData('cell_phone', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="(00) 00000-0000"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
          <input
            type="email"
            value={formData.email}
            onChange={(e) => updateFormData('email', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
      </div>
    </div>
  );

  const tabEndereco = (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Endereço</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">CEP</label>
          <input
            type="text"
            value={formData.zip_code}
            onChange={(e) => updateFormData('zip_code', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
            placeholder="00000-000"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-sm font-medium text-gray-700 mb-1">Logradouro</label>
          <input
            type="text"
            value={formData.address}
            onChange={(e) => updateFormData('address', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Número</label>
          <input
            type="text"
            value={formData.address_number}
            onChange={(e) => updateFormData('address_number', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Complemento</label>
          <input
            type="text"
            value={formData.address_complement}
            onChange={(e) => updateFormData('address_complement', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Bairro</label>
          <input
            type="text"
            value={formData.neighborhood}
            onChange={(e) => updateFormData('neighborhood', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Cidade</label>
          <input
            type="text"
            value={formData.city}
            onChange={(e) => updateFormData('city', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Estado</label>
          <select
            value={formData.state}
            onChange={(e) => updateFormData('state', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          >
            <option value="">Selecione</option>
            {STATES.map(state => (
              <option key={state} value={state}>{state}</option>
            ))}
          </select>
        </div>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2 mt-6">Dados Profissionais</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Profissão</label>
          <input
            type="text"
            value={formData.occupation}
            onChange={(e) => updateFormData('occupation', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Local de Trabalho</label>
          <input
            type="text"
            value={formData.workplace}
            onChange={(e) => updateFormData('workplace', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Telefone Trabalho</label>
          <input
            type="text"
            value={formData.work_phone}
            onChange={(e) => updateFormData('work_phone', e.target.value)}
            disabled={viewMode}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          />
        </div>
      </div>
    </div>
  );

  const tabAlunos = (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Alunos Vinculados</h3>
      <p className="text-sm text-gray-600 mb-4">Selecione os alunos pelos quais este responsável é responsável:</p>
      
      {students.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <UserPlus size={48} className="mx-auto mb-4 text-gray-300" />
          <p>Nenhum aluno cadastrado</p>
          <button
            type="button"
            onClick={() => navigate('/admin/students')}
            className="mt-2 text-blue-600 hover:underline"
          >
            Cadastrar alunos
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-96 overflow-y-auto">
          {students.map(student => (
            <label
              key={student.id}
              className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${
                formData.student_ids?.includes(student.id)
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              } ${viewMode ? 'cursor-default' : ''}`}
            >
              <input
                type="checkbox"
                checked={formData.student_ids?.includes(student.id) || false}
                onChange={() => !viewMode && handleStudentToggle(student.id)}
                disabled={viewMode}
                className="h-4 w-4 text-blue-600 rounded mr-3"
              />
              <div>
                <p className="font-medium text-gray-900">{student.full_name || 'Sem nome'}</p>
                <p className="text-xs text-gray-500">Matrícula: {student.enrollment_number}</p>
              </div>
            </label>
          ))}
        </div>
      )}

      <div className="mt-6 p-4 bg-gray-50 rounded-lg">
        <p className="text-sm text-gray-700">
          <strong>Total selecionado:</strong> {formData.student_ids?.length || 0} aluno(s)
        </p>
      </div>
    </div>
  );

  const tabObservacoes = (
    <div className="space-y-4">
      <h3 className="text-lg font-semibold text-gray-900 border-b pb-2">Status e Observações</h3>
      
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
        <select
          value={formData.status}
          onChange={(e) => updateFormData('status', e.target.value)}
          disabled={viewMode}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
        >
          <option value="active">Ativo</option>
          <option value="inactive">Inativo</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Observações</label>
        <textarea
          value={formData.observations}
          onChange={(e) => updateFormData('observations', e.target.value)}
          disabled={viewMode}
          rows={5}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
          placeholder="Anotações adicionais sobre o responsável..."
        />
      </div>
    </div>
  );

  const tabs = [
    { id: 'dados', label: 'Dados Pessoais', content: tabDadosPessoais },
    { id: 'endereco', label: 'Endereço/Profissional', content: tabEndereco },
    { id: 'alunos', label: 'Alunos Vinculados', content: tabAlunos },
    { id: 'observacoes', label: 'Observações', content: tabObservacoes }
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
              <h1 className="text-2xl font-bold text-gray-900">Responsáveis</h1>
              <p className="text-gray-600 text-sm">Gerencie os responsáveis dos alunos</p>
            </div>
          </div>
          {canEdit && (
            <button
              onClick={handleCreate}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            >
              <Plus size={20} />
              <span>Novo Responsável</span>
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
          data={guardians}
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
          title={viewMode ? 'Visualizar Responsável' : (editingGuardian ? 'Editar Responsável' : 'Novo Responsável')}
          size="xl"
        >
          <form onSubmit={handleSubmit}>
            <Tabs tabs={tabs} />
            
            <div className="flex justify-end space-x-3 pt-4 border-t mt-6">
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
