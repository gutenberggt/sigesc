import { useState, useEffect } from 'react';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { usersAPI, schoolsAPI } from '@/services/api';
import { Plus, AlertCircle, CheckCircle } from 'lucide-react';

export const Users = () => {
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
    status: 'active',
    school_links: []
  });
  const [alert, setAlert] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [usersData, schoolsData] = await Promise.all([
        usersAPI.getAll(),
        schoolsAPI.getAll()
      ]);
      setUsers(usersData);
      setSchools(schoolsData);
    } catch (error) {
      showAlert('error', 'Erro ao carregar dados');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

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
        loadData();
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
      loadData();
    } catch (error) {
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar usuário');
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
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900" data-testid="users-title">Usuários</h1>
            <p className="text-gray-600 mt-1">Gerencie os usuários do sistema</p>
          </div>
          <button
            onClick={handleCreate}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors flex items-center space-x-2"
            data-testid="create-user-button"
          >
            <Plus size={20} />
            <span>Novo Usuário</span>
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
          data={users}
          loading={loading}
          onEdit={handleEdit}
          onDelete={handleDelete}
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
              <label className="block text-sm font-medium text-gray-700 mb-2">Papel *</label>
              <select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
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
