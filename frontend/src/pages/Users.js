import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { usersAPI, schoolsAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { extractErrorMessage } from '@/utils/errorHandler';
import { Plus, AlertCircle, CheckCircle, Home } from 'lucide-react';

export const Users = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [schools, setSchools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [formData, setFormData] = useState({
    full_name: '',
    email: '',
    password: '',
    role: 'aluno',
    roles: [],  // Lista de papéis (até 3)
    status: 'active',
    school_links: []
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  
  // SEMED pode visualizar tudo, mas não pode editar/excluir
  // Secretário pode criar e editar, mas não excluir
  const canEdit = user?.role !== 'semed';
  const canDelete = user?.role === 'admin' || user?.role === 'admin_teste'; // Só admin pode excluir usuários
  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [usersData, schoolsData] = await Promise.all([
          usersAPI.getAll(),
          schoolsAPI.getAll()
        ]);
        setUsers(usersData);
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
    setEditingUser(null);
    setFormData({
      full_name: '',
      email: '',
      password: '',
      role: 'aluno',
      roles: [],
      status: 'active',
      school_links: []
    });
    setIsModalOpen(true);
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setFormData({
      full_name: user.full_name,
      email: user.email,
      password: '',
      role: user.role,
      roles: user.roles || [],
      status: user.status,
      school_links: user.school_links || []
    });
    setIsModalOpen(true);
  };

  const handleDelete = async (user) => {
    if (window.confirm(`Tem certeza que deseja excluir o usuário "${user.full_name}"?`)) {
      try {
        await usersAPI.delete(user.id);
        showAlert('success', 'Usuário excluído com sucesso');
        reloadData();
      } catch (error) {
        showAlert('error', 'Erro ao excluir usuário');
        console.error(error);
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const submitData = { ...formData };
      if (editingUser && !submitData.password) {
        delete submitData.password;
      }

      if (editingUser) {
        await usersAPI.update(editingUser.id, submitData);
        showAlert('success', 'Usuário atualizado com sucesso');
      } else {
        await usersAPI.create(submitData);
        showAlert('success', 'Usuário criado com sucesso');
      }
      setIsModalOpen(false);
      reloadData();
    } catch (error) {
      showAlert('error', extractErrorMessage(error, 'Erro ao salvar usuário'));
      console.error(error);
    } finally {
      setSubmitting(false);
    }
  };

  const roleLabels = {
    admin: 'Administrador',
    secretario: 'Secretário',
    diretor: 'Diretor',
    coordenador: 'Coordenador',
    professor: 'Professor',
    aluno: 'Aluno',
    responsavel: 'Responsável',
    semed: 'SEMED'
  };

  const columns = [
    { header: 'Nome', accessor: 'full_name' },
    { header: 'E-mail', accessor: 'email' },
    {
      header: 'Papel',
      accessor: 'role',
      render: (row) => roleLabels[row.role]
    },
    {
      header: 'Status',
      accessor: 'status',
      render: (row) => (
        <span
          className={`px-2 py-1 text-xs font-medium rounded-full ${
            row.status === 'active'
              ? 'bg-green-100 text-green-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          {row.status === 'active' ? 'Ativo' : 'Inativo'}
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
              data-testid="back-to-dashboard-button"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900" data-testid="users-title">Usuários</h1>
              <p className="text-gray-600 text-sm">Gerencie os usuários do sistema</p>
            </div>
          </div>
          {canEdit && (
            <button
              onClick={handleCreate}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
              data-testid="create-user-button"
            >
              <Plus size={20} />
              <span>Novo Usuário</span>
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
          data={users}
          loading={loading}
          onEdit={handleEdit}
          onDelete={handleDelete}
          canEdit={canEdit}
          canDelete={canDelete}
        />

        <Modal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          title={editingUser ? 'Editar Usuário' : 'Novo Usuário'}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Nome Completo *</label>
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="user-name-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">E-mail *</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="user-email-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Senha {editingUser ? '(deixe em branco para manter)' : '*'}
              </label>
              <input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required={!editingUser}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="user-password-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Papel Principal *</label>
              <select
                value={formData.role}
                onChange={(e) => {
                  const newRole = e.target.value;
                  // Adiciona automaticamente o papel principal à lista de papéis
                  const newRoles = formData.roles.includes(newRole) 
                    ? formData.roles 
                    : [newRole, ...formData.roles.filter(r => r !== formData.role)].slice(0, 3);
                  setFormData({ ...formData, role: newRole, roles: newRoles });
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="user-role-select"
              >
                {Object.entries(roleLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            {/* Papéis Adicionais (até 3 no total) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Papéis Adicionais
                <span className="text-xs text-gray-500 font-normal ml-2">(máx. 3 no total)</span>
              </label>
              <div className="border border-gray-300 rounded-lg p-3 max-h-40 overflow-y-auto bg-gray-50">
                {Object.entries(roleLabels).map(([value, label]) => (
                  <label 
                    key={value} 
                    className="flex items-center gap-2 py-1.5 px-2 hover:bg-white rounded cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={formData.roles.includes(value)}
                      disabled={!formData.roles.includes(value) && formData.roles.length >= 3}
                      onChange={(e) => {
                        let newRoles;
                        if (e.target.checked) {
                          newRoles = [...formData.roles, value].slice(0, 3);
                        } else {
                          // Não permite remover o papel principal
                          if (value === formData.role) return;
                          newRoles = formData.roles.filter(r => r !== value);
                        }
                        setFormData({ ...formData, roles: newRoles });
                      }}
                      className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className={`text-sm ${value === formData.role ? 'font-medium text-blue-700' : 'text-gray-700'}`}>
                      {label}
                      {value === formData.role && <span className="text-xs text-blue-500 ml-1">(Principal)</span>}
                    </span>
                  </label>
                ))}
              </div>
              {formData.roles.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {formData.roles.map((role, index) => (
                    <span 
                      key={role}
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        index === 0 ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-700'
                      }`}
                    >
                      {roleLabels[role] || role}
                      {role !== formData.role && (
                        <button
                          type="button"
                          onClick={() => setFormData({ 
                            ...formData, 
                            roles: formData.roles.filter(r => r !== role) 
                          })}
                          className="ml-1 text-gray-500 hover:text-gray-700"
                        >
                          ×
                        </button>
                      )}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
              <select
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                data-testid="user-status-select"
              >
                <option value="active">Ativo</option>
                <option value="inactive">Inativo</option>
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
