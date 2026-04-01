import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { DataTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { usersAPI, schoolsAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { extractErrorMessage } from '@/utils/errorHandler';
import { Plus, AlertCircle, CheckCircle, Home, Shield, ChevronDown, Check, X, Minus, Eye, Edit3 } from 'lucide-react';

// Dados da matriz de permissões por papel
const ROLE_MATRIX = {
  modules: [
    { key: 'schools', label: 'Escolas', category: 'Acadêmico' },
    { key: 'classes', label: 'Turmas', category: 'Acadêmico' },
    { key: 'students', label: 'Alunos', category: 'Acadêmico' },
    { key: 'staff', label: 'Servidores', category: 'Acadêmico' },
    { key: 'grades', label: 'Notas', category: 'Acadêmico' },
    { key: 'attendance', label: 'Frequência', category: 'Acadêmico' },
    { key: 'learning_objects', label: 'Reg. Conteúdos', category: 'Acadêmico' },
    { key: 'calendar', label: 'Calendário', category: 'Acadêmico' },
    { key: 'announcements', label: 'Avisos', category: 'Acadêmico' },
    { key: 'promotion', label: 'Livro de Promoção', category: 'Acadêmico' },
    { key: 'diary_dashboard', label: 'Acomp. Diários', category: 'Pedagógico' },
    { key: 'diario_aee', label: 'Diário AEE', category: 'Pedagógico' },
    { key: 'hr', label: 'RH / Folha', category: 'Gestão' },
    { key: 'analytics', label: 'Dashboard Analítico', category: 'Gestão' },
    { key: 'pre_matriculas', label: 'Pré-Matrículas', category: 'Gestão' },
    { key: 'users', label: 'Usuários', category: 'Sistema' },
    { key: 'online_users', label: 'Usuários Online', category: 'Sistema' },
    { key: 'audit_logs', label: 'Auditoria', category: 'Sistema' },
  ],
  roles: {
    admin: { label: 'Admin', color: 'red' },
    secretario: { label: 'Secretário', color: 'blue' },
    diretor: { label: 'Diretor', color: 'indigo' },
    coordenador: { label: 'Coordenador', color: 'purple' },
    professor: { label: 'Professor', color: 'green' },
    semed: { label: 'SEMED', color: 'teal' },
    semed1: { label: 'SEMED 1', color: 'teal' },
    semed2: { label: 'SEMED 2', color: 'teal' },
    semed3: { label: 'SEMED 3', color: 'teal' },
  },
  // access: 'full' = edita, 'view' = visualiza, 'analyst' = analista HR, null = sem acesso
  access: {
    admin:       { schools: 'full', classes: 'full', students: 'full', staff: 'full', grades: 'full', attendance: 'full', learning_objects: 'full', calendar: 'full', announcements: 'full', promotion: 'full', diary_dashboard: 'full', diario_aee: 'full', hr: 'full', analytics: 'full', pre_matriculas: 'full', users: 'full', online_users: 'full', audit_logs: 'full' },
    secretario:  { schools: 'full', classes: 'full', students: 'full', staff: 'full', grades: 'full', attendance: 'full', learning_objects: 'full', calendar: 'full', announcements: 'full', promotion: 'full', diary_dashboard: 'view', diario_aee: 'full', hr: 'full', analytics: 'view', pre_matriculas: 'full', users: 'full', online_users: null, audit_logs: null },
    diretor:     { schools: 'view', classes: 'view', students: 'view', staff: 'view', grades: 'view', attendance: 'view', learning_objects: 'view', calendar: 'view', announcements: 'full', promotion: 'view', diary_dashboard: 'view', diario_aee: 'view', hr: 'full', analytics: 'view', pre_matriculas: 'view', users: null, online_users: null, audit_logs: null },
    coordenador: { schools: null, classes: 'view', students: 'view', staff: null, grades: 'view', attendance: 'view', learning_objects: 'view', calendar: 'view', announcements: 'full', promotion: 'view', diary_dashboard: 'view', diario_aee: 'view', hr: null, analytics: 'view', pre_matriculas: null, users: null, online_users: null, audit_logs: null },
    professor:   { schools: null, classes: null, students: null, staff: null, grades: 'full', attendance: 'full', learning_objects: 'full', calendar: 'view', announcements: 'full', promotion: null, diary_dashboard: null, diario_aee: 'full', hr: null, analytics: null, pre_matriculas: null, users: null, online_users: null, audit_logs: null },
    semed:       { schools: 'view', classes: 'view', students: 'view', staff: 'view', grades: 'view', attendance: 'view', learning_objects: 'view', calendar: 'view', announcements: 'full', promotion: 'view', diary_dashboard: 'view', diario_aee: null, hr: null, analytics: null, pre_matriculas: null, users: 'view', online_users: null, audit_logs: null },
    semed1:      { schools: 'view', classes: 'view', students: 'view', staff: 'view', grades: 'view', attendance: 'view', learning_objects: 'view', calendar: 'view', announcements: 'full', promotion: 'view', diary_dashboard: 'view', diario_aee: 'view', hr: null, analytics: null, pre_matriculas: null, users: 'view', online_users: null, audit_logs: null },
    semed2:      { schools: 'view', classes: 'view', students: 'view', staff: 'view', grades: 'view', attendance: 'view', learning_objects: 'view', calendar: 'view', announcements: 'full', promotion: 'view', diary_dashboard: 'view', diario_aee: 'view', hr: 'analyst', analytics: null, pre_matriculas: null, users: 'view', online_users: null, audit_logs: null },
    semed3:      { schools: 'view', classes: 'view', students: 'view', staff: 'view', grades: 'view', attendance: 'view', learning_objects: 'view', calendar: 'view', announcements: 'full', promotion: 'view', diary_dashboard: 'view', diario_aee: 'view', hr: 'view', analytics: 'view', pre_matriculas: 'view', users: 'view', online_users: 'view', audit_logs: 'view' },
  }
};

const ADMIN_ONLY_ROLES = ['admin', 'admin_teste', 'semed', 'semed1', 'semed2', 'semed3', 'ass_social'];
const SEMED_ROLES_LIST = ['semed', 'semed1', 'semed2', 'semed3'];

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
  const [emailError, setEmailError] = useState('');
  const [activeTab, setActiveTab] = useState('users');
  const [semedDropdownUserId, setSemedDropdownUserId] = useState(null);
  
  // Restrições: todos SEMED são somente visualização no módulo de Usuários
  const canEdit = !SEMED_ROLES_LIST.includes(user?.role);
  const canDelete = user?.role === 'admin' || user?.role === 'admin_teste';
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
    setEmailError('');
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
    setEmailError('');
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

  const validateEmail = (email) => {
    if (!email) return 'O e-mail é obrigatório';
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!regex.test(email)) return 'E-mail inválido. O formato correto é nome@email.com';
    return '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const emailErr = validateEmail(formData.email);
    if (emailErr) {
      setEmailError(emailErr);
      return;
    }

    setSubmitting(true);

    try {
      const submitData = { ...formData };
      if (editingUser && !submitData.password) {
        delete submitData.password;
      }
      
      // Garante que o papel principal esteja sempre na lista de roles
      if (!submitData.roles.includes(submitData.role)) {
        submitData.roles = [submitData.role, ...submitData.roles].slice(0, 3);
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
    ass_social: 'Ass. Social',
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    apoio_pedagogico: 'Apoio Pedagógico',
    auxiliar_secretaria: 'Auxiliar de Secretaria',
    professor: 'Professor(a)',
    aluno: 'Aluno(a)',
    responsavel: 'Responsável(is)',
    semed: 'SEMED',
    semed1: 'SEMED 1',
    semed2: 'SEMED 2',
    semed3: 'SEMED 3'
  };

  // Verifica se o usuário atual é administrador
  const isCurrentUserAdmin = user?.role === 'admin' || user?.role === 'admin_teste';
  
  // Papéis admin/semed/ass_social só podem ser criados/selecionados por admins
  const availableRoles = Object.entries(roleLabels).filter(([value]) => {
    if (ADMIN_ONLY_ROLES.includes(value) && !isCurrentUserAdmin) return false;
    return true;
  });

  // Troca rápida de nível SEMED
  const handleQuickSemedChange = async (userId, currentUser, newRole) => {
    setSemedDropdownUserId(null);
    try {
      await usersAPI.update(userId, {
        role: newRole,
        roles: [newRole, ...(currentUser.roles || []).filter(r => !SEMED_ROLES_LIST.includes(r))].slice(0, 3)
      });
      showAlert('success', `Papel alterado para ${roleLabels[newRole]}`);
      reloadData();
    } catch (error) {
      showAlert('error', extractErrorMessage(error, 'Erro ao alterar papel'));
    }
  };

  const columns = [
    { header: 'Nome', accessor: 'full_name' },
    { header: 'E-mail', accessor: 'email' },
    {
      header: 'Papel',
      accessor: 'role',
      render: (row) => (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5">
            <span className="font-medium">{roleLabels[row.role] || row.role}</span>
            {isCurrentUserAdmin && SEMED_ROLES_LIST.includes(row.role) && (
              <div className="relative">
                <button
                  onClick={(e) => { e.stopPropagation(); setSemedDropdownUserId(semedDropdownUserId === row.id ? null : row.id); }}
                  className="text-xs px-1.5 py-0.5 bg-teal-100 text-teal-700 rounded hover:bg-teal-200 transition-colors"
                  title="Trocar nível SEMED"
                  data-testid={`semed-level-btn-${row.id}`}
                >
                  <ChevronDown size={12} />
                </button>
                {semedDropdownUserId === row.id && (
                  <div className="absolute left-0 top-full mt-1 w-32 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50">
                    {SEMED_ROLES_LIST.map(r => (
                      <button
                        key={r}
                        onClick={(e) => { e.stopPropagation(); handleQuickSemedChange(row.id, row, r); }}
                        className={`w-full text-left px-3 py-1.5 text-sm hover:bg-teal-50 flex items-center justify-between ${r === row.role ? 'bg-teal-50 text-teal-700 font-medium' : 'text-gray-700'}`}
                        data-testid={`semed-option-${r}`}
                      >
                        <span>{roleLabels[r]}</span>
                        {r === row.role && <Check size={14} className="text-teal-600" />}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          {row.roles && row.roles.length > 1 && (
            <div className="flex flex-wrap gap-1">
              {row.roles.filter(r => r !== row.role).map(r => (
                <span key={r} className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">
                  +{roleLabels[r] || r}
                </span>
              ))}
            </div>
          )}
        </div>
      )
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
          <div className="flex items-center gap-2">
            {isCurrentUserAdmin && (
              <button
                onClick={() => setActiveTab(activeTab === 'matrix' ? 'users' : 'matrix')}
                className={`px-4 py-2 rounded-lg flex items-center space-x-2 transition-colors border ${activeTab === 'matrix' ? 'bg-teal-600 text-white border-teal-600' : 'border-teal-300 text-teal-700 hover:bg-teal-50'}`}
                data-testid="toggle-matrix-btn"
              >
                <Shield size={18} />
                <span>Matriz de Permissões</span>
              </button>
            )}
            {canEdit && activeTab === 'users' && (
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

        {/* Aba: Matriz de Permissões */}
        {activeTab === 'matrix' && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden" data-testid="role-matrix-panel">
            <div className="p-4 border-b border-gray-100 bg-gradient-to-r from-teal-50 to-white">
              <h2 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
                <Shield size={20} className="text-teal-600" />
                Matriz de Permissões por Papel
              </h2>
              <p className="text-xs text-gray-500 mt-1">Visualize o acesso de cada papel aos módulos do sistema</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="text-left px-3 py-2.5 text-xs font-semibold text-gray-600 uppercase tracking-wide sticky left-0 bg-gray-50 z-10 min-w-[150px]">Módulo</th>
                    {Object.entries(ROLE_MATRIX.roles).map(([role, info]) => (
                      <th key={role} className="text-center px-2 py-2.5 text-xs font-semibold text-gray-600 uppercase tracking-wide min-w-[80px]">
                        <span className={`inline-block px-2 py-0.5 rounded text-${info.color}-700 bg-${info.color}-50`}>
                          {info.label}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    let lastCategory = '';
                    return ROLE_MATRIX.modules.map((mod) => {
                      const showCat = mod.category !== lastCategory;
                      lastCategory = mod.category;
                      return (
                        <tr key={mod.key} className="border-t border-gray-100 hover:bg-gray-50/50">
                          <td className="px-3 py-2 sticky left-0 bg-white z-10">
                            {showCat && <span className="text-[10px] font-bold text-gray-400 uppercase block -mb-0.5">{mod.category}</span>}
                            <span className="text-gray-800 font-medium">{mod.label}</span>
                          </td>
                          {Object.keys(ROLE_MATRIX.roles).map(role => {
                            const access = ROLE_MATRIX.access[role]?.[mod.key];
                            return (
                              <td key={role} className="text-center px-2 py-2">
                                {access === 'full' && (
                                  <span className="inline-flex items-center gap-0.5 text-xs font-medium text-green-700 bg-green-50 px-1.5 py-0.5 rounded" title="Edição completa">
                                    <Edit3 size={10} /> Edita
                                  </span>
                                )}
                                {access === 'view' && (
                                  <span className="inline-flex items-center gap-0.5 text-xs font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded" title="Somente visualização">
                                    <Eye size={10} /> Viz
                                  </span>
                                )}
                                {access === 'analyst' && (
                                  <span className="inline-flex items-center gap-0.5 text-xs font-medium text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded" title="Analista (aprova/devolve)">
                                    <Check size={10} /> Analista
                                  </span>
                                )}
                                {!access && (
                                  <span className="text-gray-300"><Minus size={14} /></span>
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    });
                  })()}
                </tbody>
              </table>
            </div>
            <div className="p-3 border-t border-gray-100 bg-gray-50 flex items-center gap-4 text-xs text-gray-500">
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded bg-green-500"></span> Edição completa</span>
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded bg-blue-500"></span> Somente visualização</span>
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded bg-amber-500"></span> Analista RH</span>
              <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded bg-gray-300"></span> Sem acesso</span>
            </div>
          </div>
        )}

        {/* Aba: Lista de Usuários */}
        {activeTab === 'users' && (
          <DataTable
            columns={columns}
            data={users}
            loading={loading}
            onEdit={handleEdit}
            onDelete={handleDelete}
            canEdit={canEdit}
            canDelete={canDelete}
          />
        )}

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
                onChange={(e) => {
                  setFormData({ ...formData, email: e.target.value });
                  if (emailError) setEmailError(validateEmail(e.target.value));
                }}
                onBlur={(e) => setEmailError(validateEmail(e.target.value))}
                required
                className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${emailError ? 'border-red-500 bg-red-50' : 'border-gray-300'}`}
                data-testid="user-email-input"
              />
              {emailError && (
                <p className="mt-1 text-sm text-red-600 flex items-center gap-1" data-testid="email-error-message">
                  <AlertCircle size={14} /> {emailError}
                </p>
              )}
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
                {availableRoles.map(([value, label]) => (
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
                {availableRoles.map(([value, label]) => (
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
