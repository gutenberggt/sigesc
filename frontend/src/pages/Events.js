import { useState, useEffect } from 'react';
import { Layout } from '@/components/Layout';
import { 
  Calendar,
  Plus,
  Edit,
  Trash2,
  Eye,
  Search,
  Filter,
  Sun,
  Moon,
  Sunrise,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  ArrowLeft
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal } from '@/components/Modal';
import { Alert } from '@/components/ui/alert';
import { calendarAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

// Tipos de eventos
const EVENT_TYPES = [
  { value: 'feriado_nacional', label: 'Feriado Nacional', color: '#EF4444' },
  { value: 'feriado_estadual', label: 'Feriado Estadual', color: '#F97316' },
  { value: 'feriado_municipal', label: 'Feriado Municipal', color: '#EAB308' },
  { value: 'sabado_letivo', label: 'Sábado Letivo', color: '#22C55E' },
  { value: 'recesso_escolar', label: 'Recesso Escolar', color: '#3B82F6' },
  { value: 'evento_escolar', label: 'Evento Escolar', color: '#8B5CF6' },
  { value: 'outros', label: 'Outros', color: '#6B7280' }
];

// Períodos do dia
const PERIODS = [
  { value: 'integral', label: 'Integral (Dia todo)', icon: Calendar },
  { value: 'manha', label: 'Manhã (7h - 12h)', icon: Sunrise },
  { value: 'tarde', label: 'Tarde (13h - 18h)', icon: Sun },
  { value: 'noite', label: 'Noite (18h - 22h)', icon: Moon },
  { value: 'personalizado', label: 'Horário Personalizado', icon: Clock }
];

// Formulário inicial
const initialFormData = {
  name: '',
  description: '',
  event_type: 'evento_escolar',
  is_school_day: false,
  start_date: '',
  end_date: '',
  period: 'integral',
  start_time: '',
  end_time: '',
  academic_year: new Date().getFullYear(),
  color: ''
};

// Formata data para exibição
const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}/${year}`;
};

export const Events = () => {
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingEvent, setEditingEvent] = useState(null);
  const [formData, setFormData] = useState(initialFormData);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterYear, setFilterYear] = useState(new Date().getFullYear());
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(null);
  
  // Verifica permissões
  const canEdit = user?.role === 'admin' || user?.role === 'admin_teste' || user?.role === 'secretario';
  
  // Carrega eventos
  useEffect(() => {
    loadEvents();
  }, [filterYear, filterType]);
  
  // Verifica parâmetro de edição na URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const editId = params.get('edit');
    if (editId && events.length > 0) {
      const event = events.find(e => e.id === editId);
      if (event) {
        handleEdit(event);
      }
    }
  }, [events]);
  
  const loadEvents = async () => {
    setLoading(true);
    try {
      const params = { academic_year: filterYear };
      if (filterType) params.event_type = filterType;
      const data = await calendarAPI.getEvents(params);
      setEvents(data);
    } catch (error) {
      console.error('Erro ao carregar eventos:', error);
      showAlert('error', 'Erro ao carregar eventos');
    } finally {
      setLoading(false);
    }
  };
  
  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 4000);
  };
  
  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };
  
  const handleAdd = () => {
    setEditingEvent(null);
    setFormData({
      ...initialFormData,
      academic_year: filterYear
    });
    setShowModal(true);
  };
  
  const handleEdit = (event) => {
    setEditingEvent(event);
    setFormData({
      name: event.name || '',
      description: event.description || '',
      event_type: event.event_type || 'evento_escolar',
      is_school_day: event.is_school_day || false,
      start_date: event.start_date || '',
      end_date: event.end_date || '',
      period: event.period || 'integral',
      start_time: event.start_time || '',
      end_time: event.end_time || '',
      academic_year: event.academic_year || filterYear,
      color: event.color || ''
    });
    setShowModal(true);
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validações
    if (!formData.name.trim()) {
      showAlert('error', 'Nome do evento é obrigatório');
      return;
    }
    if (!formData.start_date) {
      showAlert('error', 'Data de início é obrigatória');
      return;
    }
    if (!formData.end_date) {
      showAlert('error', 'Data de fim é obrigatória');
      return;
    }
    if (formData.start_date > formData.end_date) {
      showAlert('error', 'Data de início não pode ser maior que data de fim');
      return;
    }
    if (formData.period === 'personalizado') {
      if (!formData.start_time || !formData.end_time) {
        showAlert('error', 'Horário personalizado requer hora de início e fim');
        return;
      }
    }
    
    setSaving(true);
    try {
      const dataToSave = {
        ...formData,
        // Remove campos de hora se não for personalizado
        start_time: formData.period === 'personalizado' ? formData.start_time : null,
        end_time: formData.period === 'personalizado' ? formData.end_time : null,
        // Define cor padrão se não especificada
        color: formData.color || EVENT_TYPES.find(t => t.value === formData.event_type)?.color
      };
      
      if (editingEvent) {
        await calendarAPI.update(editingEvent.id, dataToSave);
        showAlert('success', 'Evento atualizado com sucesso!');
      } else {
        await calendarAPI.create(dataToSave);
        showAlert('success', 'Evento criado com sucesso!');
      }
      
      setShowModal(false);
      loadEvents();
    } catch (error) {
      console.error('Erro ao salvar evento:', error);
      showAlert('error', 'Erro ao salvar evento');
    } finally {
      setSaving(false);
    }
  };
  
  const handleDelete = async (event) => {
    try {
      await calendarAPI.delete(event.id);
      showAlert('success', 'Evento removido com sucesso!');
      setShowDeleteConfirm(null);
      loadEvents();
    } catch (error) {
      console.error('Erro ao remover evento:', error);
      showAlert('error', 'Erro ao remover evento');
    }
  };
  
  // Filtra eventos
  const filteredEvents = events.filter(event => {
    const matchesSearch = !searchTerm || 
      event.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      event.description?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesSearch;
  });
  
  // Anos disponíveis
  const availableYears = [];
  const currentYear = new Date().getFullYear();
  for (let y = currentYear - 2; y <= currentYear + 2; y++) {
    availableYears.push(y);
  }
  
  return (
    <Layout>
      <div className="space-y-4">
        {/* Alert */}
        {alert && (
          <Alert variant={alert.type === 'error' ? 'destructive' : 'default'} className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <span className="ml-2">{alert.message}</span>
          </Alert>
        )}
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => window.location.href = '/admin/calendar'}
              >
                <ArrowLeft size={18} className="mr-1" />
                Voltar ao Calendário
              </Button>
            </div>
            <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
              <Calendar className="text-blue-600" />
              Gerenciamento de Eventos
            </h1>
            <p className="text-gray-600">Cadastre feriados, sábados letivos e eventos do calendário</p>
          </div>
          
          {canEdit && (
            <Button onClick={handleAdd}>
              <Plus size={18} className="mr-2" />
              Novo Evento
            </Button>
          )}
        </div>
        
        {/* Filtros */}
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <Input
                type="text"
                placeholder="Buscar eventos..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Todos os tipos</option>
              {EVENT_TYPES.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
            
            <select
              value={filterYear}
              onChange={(e) => setFilterYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {availableYears.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
        </div>
        
        {/* Lista de Eventos */}
        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          {loading ? (
            <div className="flex justify-center items-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
          ) : filteredEvents.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Calendar size={48} className="mx-auto mb-4 opacity-30" />
              <p>Nenhum evento encontrado</p>
              {canEdit && (
                <Button className="mt-4" onClick={handleAdd}>
                  <Plus size={18} className="mr-2" />
                  Adicionar Primeiro Evento
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Evento</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tipo</th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Letivo</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Período</th>
                    {canEdit && (
                      <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Ações</th>
                    )}
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {filteredEvents.map(event => {
                    const eventType = EVENT_TYPES.find(t => t.value === event.event_type);
                    const period = PERIODS.find(p => p.value === event.period);
                    const PeriodIcon = period?.icon || Calendar;
                    
                    return (
                      <tr key={event.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div 
                              className="w-3 h-3 rounded-full flex-shrink-0"
                              style={{ backgroundColor: event.color || eventType?.color }}
                            />
                            <div>
                              <div className="font-medium text-gray-900">{event.name}</div>
                              {event.description && (
                                <div className="text-sm text-gray-500 truncate max-w-xs">{event.description}</div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span 
                            className="px-2 py-1 text-xs rounded-full"
                            style={{ 
                              backgroundColor: `${eventType?.color}20`,
                              color: eventType?.color
                            }}
                          >
                            {eventType?.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-center">
                          {event.is_school_day ? (
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs">
                              <CheckCircle size={12} />
                              Sim
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs">
                              <XCircle size={12} />
                              Não
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          {event.start_date === event.end_date ? (
                            formatDate(event.start_date)
                          ) : (
                            `${formatDate(event.start_date)} - ${formatDate(event.end_date)}`
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1 text-sm text-gray-600">
                            <PeriodIcon size={14} />
                            {period?.label?.split(' ')[0]}
                            {event.period === 'personalizado' && event.start_time && (
                              <span className="text-xs text-gray-400 ml-1">
                                ({event.start_time}-{event.end_time})
                              </span>
                            )}
                          </div>
                        </td>
                        {canEdit && (
                          <td className="px-4 py-3 text-center">
                            <div className="flex justify-center gap-2">
                              <button
                                onClick={() => handleEdit(event)}
                                className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                                title="Editar"
                              >
                                <Edit size={16} />
                              </button>
                              <button
                                onClick={() => setShowDeleteConfirm(event)}
                                className="p-1 text-red-600 hover:bg-red-50 rounded"
                                title="Excluir"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
        
        {/* Resumo */}
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <h3 className="font-semibold text-gray-700 mb-3">Resumo do Ano {filterYear}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {EVENT_TYPES.map(type => {
              const count = filteredEvents.filter(e => e.event_type === type.value).length;
              return (
                <div key={type.value} className="flex items-center gap-2">
                  <div 
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: type.color }}
                  />
                  <span className="text-sm text-gray-600">{type.label}:</span>
                  <span className="font-semibold">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
        
        {/* Modal de Formulário */}
        <Modal
          isOpen={showModal}
          onClose={() => setShowModal(false)}
          title={editingEvent ? 'Editar Evento' : 'Novo Evento'}
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Nome */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Nome do Evento *
              </label>
              <Input
                type="text"
                name="name"
                value={formData.name}
                onChange={handleInputChange}
                placeholder="Ex: Feriado de Natal"
                required
              />
            </div>
            
            {/* Descrição */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Descrição
              </label>
              <textarea
                name="description"
                value={formData.description}
                onChange={handleInputChange}
                placeholder="Descrição opcional do evento..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 resize-none"
                rows={2}
              />
            </div>
            
            {/* Tipo e Letivo */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Tipo de Evento *
                </label>
                <select
                  name="event_type"
                  value={formData.event_type}
                  onChange={handleInputChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  {EVENT_TYPES.map(type => (
                    <option key={type.value} value={type.value}>{type.label}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Dia Letivo
                </label>
                <div className="flex gap-4 mt-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="is_school_day"
                      checked={formData.is_school_day === true}
                      onChange={() => setFormData(prev => ({ ...prev, is_school_day: true }))}
                      className="text-green-600"
                    />
                    <CheckCircle size={16} className="text-green-600" />
                    <span>Letivo</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="is_school_day"
                      checked={formData.is_school_day === false}
                      onChange={() => setFormData(prev => ({ ...prev, is_school_day: false }))}
                      className="text-red-600"
                    />
                    <XCircle size={16} className="text-red-600" />
                    <span>Não Letivo</span>
                  </label>
                </div>
              </div>
            </div>
            
            {/* Datas */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Data Início *
                </label>
                <Input
                  type="date"
                  name="start_date"
                  value={formData.start_date}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Data Fim *
                </label>
                <Input
                  type="date"
                  name="end_date"
                  value={formData.end_date}
                  onChange={handleInputChange}
                  required
                />
              </div>
            </div>
            
            {/* Período */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Período do Dia
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {PERIODS.map(period => {
                  const Icon = period.icon;
                  return (
                    <label 
                      key={period.value}
                      className={`flex items-center gap-2 p-2 border rounded-lg cursor-pointer transition-colors
                        ${formData.period === period.value ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}
                      `}
                    >
                      <input
                        type="radio"
                        name="period"
                        value={period.value}
                        checked={formData.period === period.value}
                        onChange={handleInputChange}
                        className="sr-only"
                      />
                      <Icon size={16} className={formData.period === period.value ? 'text-blue-600' : 'text-gray-400'} />
                      <span className="text-sm">{period.label.split(' ')[0]}</span>
                    </label>
                  );
                })}
              </div>
            </div>
            
            {/* Horário personalizado */}
            {formData.period === 'personalizado' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Hora Início *
                  </label>
                  <Input
                    type="time"
                    name="start_time"
                    value={formData.start_time}
                    onChange={handleInputChange}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Hora Fim *
                  </label>
                  <Input
                    type="time"
                    name="end_time"
                    value={formData.end_time}
                    onChange={handleInputChange}
                  />
                </div>
              </div>
            )}
            
            {/* Cor e Ano */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Cor (opcional)
                </label>
                <div className="flex gap-2">
                  <Input
                    type="color"
                    name="color"
                    value={formData.color || EVENT_TYPES.find(t => t.value === formData.event_type)?.color || '#6B7280'}
                    onChange={handleInputChange}
                    className="w-12 h-10 p-1 cursor-pointer"
                  />
                  <Input
                    type="text"
                    name="color"
                    value={formData.color}
                    onChange={handleInputChange}
                    placeholder="Cor padrão do tipo"
                    className="flex-1"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Ano Letivo
                </label>
                <select
                  name="academic_year"
                  value={formData.academic_year}
                  onChange={handleInputChange}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  {availableYears.map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>
            </div>
            
            {/* Botões */}
            <div className="flex gap-3 pt-4 border-t">
              <Button 
                type="submit" 
                className="flex-1"
                disabled={saving}
              >
                {saving ? 'Salvando...' : (editingEvent ? 'Atualizar' : 'Criar Evento')}
              </Button>
              <Button 
                type="button"
                variant="outline"
                onClick={() => setShowModal(false)}
              >
                Cancelar
              </Button>
            </div>
          </form>
        </Modal>
        
        {/* Modal de confirmação de exclusão */}
        <Modal
          isOpen={!!showDeleteConfirm}
          onClose={() => setShowDeleteConfirm(null)}
          title="Confirmar Exclusão"
        >
          <div className="space-y-4">
            <p className="text-gray-600">
              Tem certeza que deseja excluir o evento <strong>{showDeleteConfirm?.name}</strong>?
            </p>
            <p className="text-sm text-red-600">
              Esta ação não pode ser desfeita.
            </p>
            <div className="flex gap-3 pt-4">
              <Button 
                variant="destructive"
                className="flex-1"
                onClick={() => handleDelete(showDeleteConfirm)}
              >
                <Trash2 size={16} className="mr-2" />
                Excluir
              </Button>
              <Button 
                variant="outline"
                onClick={() => setShowDeleteConfirm(null)}
              >
                Cancelar
              </Button>
            </div>
          </div>
        </Modal>
      </div>
    </Layout>
  );
};

export default Events;
