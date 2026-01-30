import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { 
  Bell, Plus, Edit2, Trash2, Check, X, Search, 
  Users, Building, BookOpen, User, ChevronDown, Filter, Home
} from 'lucide-react';
import { announcementsAPI, schoolsAPI, classesAPI, usersAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/Modal';

const Announcements = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const highlightId = searchParams.get('id');
  
  const [announcements, setAnnouncements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingAnnouncement, setEditingAnnouncement] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [filter, setFilter] = useState('all'); // all, unread, sent
  const [searchQuery, setSearchQuery] = useState('');
  
  // Form state
  const [formData, setFormData] = useState({
    title: '',
    content: '',
    recipientType: 'role',
    targetRoles: [],
    schoolIds: [],
    classIds: [],
    userIds: []
  });
  const [formLoading, setFormLoading] = useState(false);
  
  // Data for selectors
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [allUsers, setAllUsers] = useState([]);

  // Fetch announcements
  const fetchAnnouncements = async () => {
    setLoading(true);
    try {
      const data = await announcementsAPI.list(0, 100);
      setAnnouncements(data);
    } catch (error) {
      console.error('Erro ao buscar avisos:', error);
    } finally {
      setLoading(false);
    }
  };

  // Fetch data for selectors
  const fetchSelectorData = async () => {
    try {
      const [schoolsData, classesData, usersData] = await Promise.all([
        schoolsAPI.list(),
        classesAPI.list(),
        usersAPI.getAll()
      ]);
      setSchools(schoolsData);
      setClasses(classesData);
      // Filtrar apenas usuários ativos
      setAllUsers(usersData.filter(u => u.status === 'active'));
    } catch (error) {
      console.error('Erro ao buscar dados:', error);
    }
  };

  useEffect(() => {
    fetchAnnouncements();
    fetchSelectorData();
  }, []);

  // Marcar como lido quando destacado
  useEffect(() => {
    if (highlightId) {
      const announcement = announcements.find(a => a.id === highlightId);
      if (announcement && !announcement.is_read) {
        announcementsAPI.markAsRead(highlightId).then(fetchAnnouncements);
      }
    }
  }, [highlightId, announcements]);

  // Filter announcements
  const filteredAnnouncements = announcements.filter(a => {
    // Search filter
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      if (!a.title.toLowerCase().includes(query) && 
          !a.content.toLowerCase().includes(query) &&
          !a.sender_name.toLowerCase().includes(query)) {
        return false;
      }
    }
    
    // Status filter
    if (filter === 'unread' && a.is_read) return false;
    if (filter === 'sent' && a.sender_id !== user?.id) return false;
    
    return true;
  });

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    
    try {
      const recipient = {
        type: formData.recipientType,
        target_roles: formData.recipientType === 'role' ? formData.targetRoles : 
                      formData.recipientType === 'semed' ? ['semed'] : [],
        school_ids: formData.recipientType === 'school' ? formData.schoolIds : [],
        class_ids: formData.recipientType === 'class' ? formData.classIds : [],
        user_ids: formData.recipientType === 'individual' ? formData.userIds : []
      };
      
      const payload = {
        title: formData.title,
        content: formData.content,
        recipient
      };
      
      if (editingAnnouncement) {
        await announcementsAPI.update(editingAnnouncement.id, payload);
      } else {
        await announcementsAPI.create(payload);
      }
      
      setShowModal(false);
      setEditingAnnouncement(null);
      resetForm();
      fetchAnnouncements();
    } catch (error) {
      console.error('Erro ao salvar aviso:', error);
      alert(error.response?.data?.detail || 'Erro ao salvar aviso');
    } finally {
      setFormLoading(false);
    }
  };

  const resetForm = () => {
    setFormData({
      title: '',
      content: '',
      recipientType: 'role',
      targetRoles: [],
      schoolIds: [],
      classIds: [],
      userIds: []
    });
  };

  const handleEdit = (announcement) => {
    setEditingAnnouncement(announcement);
    setFormData({
      title: announcement.title,
      content: announcement.content,
      recipientType: announcement.recipient.type,
      targetRoles: announcement.recipient.target_roles || [],
      schoolIds: announcement.recipient.school_ids || [],
      classIds: announcement.recipient.class_ids || [],
      userIds: announcement.recipient.user_ids || []
    });
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Tem certeza que deseja excluir este aviso?')) return;
    
    setDeleting(id);
    try {
      await announcementsAPI.delete(id);
      fetchAnnouncements();
    } catch (error) {
      console.error('Erro ao excluir:', error);
      alert('Erro ao excluir aviso');
    } finally {
      setDeleting(null);
    }
  };

  const handleMarkAsRead = async (id) => {
    try {
      await announcementsAPI.markAsRead(id);
      fetchAnnouncements();
    } catch (error) {
      console.error('Erro ao marcar como lido:', error);
    }
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
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

  const availableRoles = () => {
    // Admin e SEMED podem enviar para todos
    if (user?.role === 'admin' || user?.role === 'semed') {
      return ['secretario', 'diretor', 'coordenador', 'professor', 'aluno', 'responsavel'];
    }
    // Secretário, Diretor, Coordenador podem enviar para professores e alunos
    if (['secretario', 'diretor', 'coordenador'].includes(user?.role)) {
      return ['professor', 'aluno', 'responsavel'];
    }
    // Professor pode enviar para alunos e responsáveis
    if (user?.role === 'professor') {
      return ['aluno', 'responsavel'];
    }
    return [];
  };

  const getRecipientTypeIcon = (type) => {
    switch (type) {
      case 'role': return <Users size={16} />;
      case 'school': return <Building size={16} />;
      case 'class': return <BookOpen size={16} />;
      case 'individual': return <User size={16} />;
      default: return null;
    }
  };

  const getRecipientDescription = (recipient) => {
    switch (recipient.type) {
      case 'role':
        return `Para: ${recipient.target_roles?.map(r => roleLabels[r] || r).join(', ') || 'Todos'}`;
      case 'semed':
        return 'Para: Usuários SEMED';
      case 'school':
        const schoolNames = recipient.school_ids?.map(id => 
          schools.find(s => s.id === id)?.name || id
        ).join(', ');
        return `Escolas: ${schoolNames || 'N/A'}`;
      case 'class':
        const classNames = recipient.class_ids?.map(id => 
          classes.find(c => c.id === id)?.name || id
        ).join(', ');
        return `Turmas: ${classNames || 'N/A'}`;
      case 'individual':
        return `${recipient.user_ids?.length || 0} usuário(s) específico(s)`;
      default:
        return 'Destinatário desconhecido';
    }
  };

  // Verificar se pode criar avisos
  const canCreate = ['admin', 'semed', 'secretario', 'diretor', 'coordenador', 'professor'].includes(user?.role);

  return (
    <Layout>
      <div className="space-y-6">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <button 
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-1 hover:text-blue-600 transition-colors"
          >
            <Home size={16} />
            Dashboard
          </button>
          <span>/</span>
          <span className="text-gray-900 font-medium">Avisos</span>
        </div>

        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Bell className="text-blue-600" />
              Avisos
            </h1>
            <p className="text-gray-500 mt-1">Gerencie os avisos e comunicados</p>
          </div>
          
          {canCreate && (
            <Button
              onClick={() => {
                resetForm();
                setEditingAnnouncement(null);
                setShowModal(true);
              }}
              className="flex items-center gap-2"
            >
              <Plus size={18} />
              Novo Aviso
            </Button>
          )}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            {/* Search */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input
                type="text"
                placeholder="Buscar avisos..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            
            {/* Filter buttons */}
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'all' 
                    ? 'bg-blue-100 text-blue-700' 
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Todos
              </button>
              <button
                onClick={() => setFilter('unread')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'unread' 
                    ? 'bg-blue-100 text-blue-700' 
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Não lidos
              </button>
              <button
                onClick={() => setFilter('sent')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  filter === 'sent' 
                    ? 'bg-blue-100 text-blue-700' 
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                Enviados
              </button>
            </div>
          </div>
        </div>

        {/* Announcements List */}
        <div className="space-y-4">
          {loading ? (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
              <p className="mt-2 text-gray-500">Carregando avisos...</p>
            </div>
          ) : filteredAnnouncements.length === 0 ? (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
              <Bell className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">Nenhum aviso encontrado</h3>
              <p className="mt-1 text-sm text-gray-500">
                {filter === 'unread' ? 'Você está em dia!' : 'Os avisos aparecerão aqui.'}
              </p>
            </div>
          ) : (
            filteredAnnouncements.map((announcement) => (
              <div
                key={announcement.id}
                className={`bg-white rounded-lg shadow-sm border transition-all ${
                  announcement.id === highlightId 
                    ? 'border-blue-500 ring-2 ring-blue-200' 
                    : !announcement.is_read 
                      ? 'border-blue-200 bg-blue-50/30' 
                      : 'border-gray-200'
                }`}
              >
                <div className="p-4 sm:p-6">
                  {/* Header */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      {/* Avatar */}
                      {announcement.sender_foto_url ? (
                        <img
                          src={announcement.sender_foto_url}
                          alt={announcement.sender_name}
                          className="w-12 h-12 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                          <Bell size={20} className="text-blue-600" />
                        </div>
                      )}
                      
                      {/* Info */}
                      <div>
                        <h3 className="font-semibold text-gray-900">{announcement.title}</h3>
                        <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-gray-500">
                          <span className="font-medium text-gray-700">{announcement.sender_name}</span>
                          <span>•</span>
                          <span>{roleLabels[announcement.sender_role]}</span>
                          <span>•</span>
                          <span>{formatDate(announcement.created_at)}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                          {getRecipientTypeIcon(announcement.recipient.type)}
                          <span>{getRecipientDescription(announcement.recipient)}</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      {!announcement.is_read && (
                        <button
                          onClick={() => handleMarkAsRead(announcement.id)}
                          className="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          title="Marcar como lido"
                        >
                          <Check size={18} />
                        </button>
                      )}
                      
                      {announcement.sender_id === user?.id && (
                        <>
                          <button
                            onClick={() => handleEdit(announcement)}
                            className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                            title="Editar"
                          >
                            <Edit2 size={18} />
                          </button>
                          <button
                            onClick={() => handleDelete(announcement.id)}
                            disabled={deleting === announcement.id}
                            className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                            title="Excluir"
                          >
                            <Trash2 size={18} />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  
                  {/* Content */}
                  <div className="mt-4 pl-16">
                    <p className="text-gray-700 whitespace-pre-wrap">{announcement.content}</p>
                  </div>
                  
                  {/* Read indicator */}
                  {!announcement.is_read && (
                    <div className="mt-4 pl-16">
                      <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 bg-blue-100 px-2 py-1 rounded-full">
                        <div className="w-1.5 h-1.5 bg-blue-600 rounded-full" />
                        Novo
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Create/Edit Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setEditingAnnouncement(null);
          resetForm();
        }}
        title={editingAnnouncement ? 'Editar Aviso' : 'Novo Aviso'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Título *
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              required
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Título do aviso"
            />
          </div>

          {/* Content */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Conteúdo *
            </label>
            <textarea
              value={formData.content}
              onChange={(e) => setFormData({ ...formData, content: e.target.value })}
              required
              rows={5}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Conteúdo do aviso..."
            />
          </div>

          {/* Recipient Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Enviar para *
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {[
                { value: 'role', label: 'Por Cargo', icon: Users },
                { value: 'semed', label: 'SEMED', icon: Building },
                { value: 'school', label: 'Por Escola', icon: Building },
                { value: 'class', label: 'Por Turma', icon: BookOpen },
                { value: 'individual', label: 'Individual', icon: User }
              ].map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFormData({ ...formData, recipientType: value })}
                  className={`flex items-center justify-center gap-2 px-4 py-3 rounded-lg border transition-colors ${
                    formData.recipientType === value
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <Icon size={18} />
                  <span className="text-sm font-medium">{label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Recipient Selection based on type */}
          {formData.recipientType === 'role' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Selecione os cargos
              </label>
              <div className="flex flex-wrap gap-2">
                {availableRoles().map(role => (
                  <button
                    key={role}
                    type="button"
                    onClick={() => {
                      const newRoles = formData.targetRoles.includes(role)
                        ? formData.targetRoles.filter(r => r !== role)
                        : [...formData.targetRoles, role];
                      setFormData({ ...formData, targetRoles: newRoles });
                    }}
                    className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                      formData.targetRoles.includes(role)
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {roleLabels[role]}
                  </button>
                ))}
              </div>
            </div>
          )}

          {formData.recipientType === 'school' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Selecione as escolas
              </label>
              <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg">
                {schools.map(school => (
                  <label
                    key={school.id}
                    className="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={formData.schoolIds.includes(school.id)}
                      onChange={(e) => {
                        const newIds = e.target.checked
                          ? [...formData.schoolIds, school.id]
                          : formData.schoolIds.filter(id => id !== school.id);
                        setFormData({ ...formData, schoolIds: newIds });
                      }}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm">{school.name}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {formData.recipientType === 'class' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Selecione as turmas
              </label>
              <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg">
                {classes.map(cls => (
                  <label
                    key={cls.id}
                    className="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={formData.classIds.includes(cls.id)}
                      onChange={(e) => {
                        const newIds = e.target.checked
                          ? [...formData.classIds, cls.id]
                          : formData.classIds.filter(id => id !== cls.id);
                        setFormData({ ...formData, classIds: newIds });
                      }}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm">{cls.name}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {formData.recipientType === 'individual' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Selecione os usuários
              </label>
              {allUsers.length === 0 ? (
                <p className="text-sm text-gray-500 p-4 border border-gray-200 rounded-lg">
                  Nenhum usuário disponível
                </p>
              ) : (
                <div className="max-h-48 overflow-y-auto border border-gray-200 rounded-lg">
                  {allUsers.map(person => (
                    <label
                      key={person.id}
                      className="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={formData.userIds.includes(person.id)}
                        onChange={(e) => {
                          const newIds = e.target.checked
                            ? [...formData.userIds, person.id]
                            : formData.userIds.filter(id => id !== person.id);
                          setFormData({ ...formData, userIds: newIds });
                        }}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="text-sm">{person.full_name} - {roleLabels[person.role] || person.role}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setShowModal(false);
                setEditingAnnouncement(null);
                resetForm();
              }}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={formLoading}>
              {formLoading ? 'Salvando...' : editingAnnouncement ? 'Salvar Alterações' : 'Criar Aviso'}
            </Button>
          </div>
        </form>
      </Modal>
    </Layout>
  );
};

export default Announcements;
