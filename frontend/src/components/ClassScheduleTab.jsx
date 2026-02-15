import { useState, useEffect, useMemo } from 'react';
import { 
  ChevronLeft, 
  ChevronRight, 
  Clock, 
  BookOpen,
  Save,
  Plus,
  Trash2,
  AlertCircle,
  CheckCircle,
  Settings,
  AlertTriangle,
  Users,
  Building2,
  X
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Modal } from '@/components/Modal';
import { classScheduleAPI, schoolsAPI, classesAPI, coursesAPI, calendarAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';

// Dias da semana
const DAYS = [
  { id: 'segunda', label: 'Segunda' },
  { id: 'terca', label: 'Terça' },
  { id: 'quarta', label: 'Quarta' },
  { id: 'quinta', label: 'Quinta' },
  { id: 'sexta', label: 'Sexta' }
];

// Tradução dos turnos
const SHIFT_LABELS = {
  morning: 'Matutino',
  afternoon: 'Vespertino',
  evening: 'Noturno',
  full_time: 'Integral'
};

// Helper para formatar data
const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}`;
};

// Helper para formatar data como YYYY-MM-DD sem problemas de timezone
const formatDateYYYYMMDD = (date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Helper para obter segunda-feira da semana
const getMonday = (date) => {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  d.setDate(diff);
  return d;
};

// Componente do Painel de Conflitos da Rede
const NetworkConflictsPanel = ({ academicYear, isOpen, onClose }) => {
  const [loading, setLoading] = useState(true);
  const [conflictsData, setConflictsData] = useState(null);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [schools, setSchools] = useState([]);
  const [expandedTeacher, setExpandedTeacher] = useState(null);
  
  useEffect(() => {
    const loadSchools = async () => {
      try {
        const data = await schoolsAPI.getAll();
        setSchools(data.filter(s => s.status === 'active' || !s.status));
      } catch (error) {
        console.error('Erro ao carregar escolas:', error);
      }
    };
    if (isOpen) loadSchools();
  }, [isOpen]);
  
  useEffect(() => {
    const loadConflicts = async () => {
      if (!isOpen) return;
      setLoading(true);
      try {
        const data = await classScheduleAPI.getAllConflicts(academicYear, selectedSchool || null);
        setConflictsData(data);
      } catch (error) {
        console.error('Erro ao carregar conflitos:', error);
        setConflictsData({ total_conflicts: 0, conflicts_by_teacher: [], summary: 'Erro ao carregar dados' });
      } finally {
        setLoading(false);
      }
    };
    loadConflicts();
  }, [isOpen, academicYear, selectedSchool]);
  
  if (!isOpen) return null;
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-5 border-b flex items-center justify-between bg-gradient-to-r from-orange-500 to-red-500 rounded-t-xl">
          <div className="flex items-center gap-3 text-white">
            <AlertTriangle size={24} />
            <div>
              <h2 className="text-lg font-bold">Conflitos de Horário na Rede</h2>
              <p className="text-sm opacity-90">Professores(as) com aulas sobrepostas</p>
            </div>
          </div>
          <button onClick={onClose} className="text-white hover:bg-white/20 rounded-lg p-2">
            <X size={20} />
          </button>
        </div>
        
        {/* Filtro e Resumo */}
        <div className="p-4 border-b bg-gray-50">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs font-medium text-gray-500 mb-1">Filtrar por Escola</label>
              <select
                value={selectedSchool}
                onChange={(e) => setSelectedSchool(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              >
                <option value="">Todas as escolas</option>
                {schools.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            
            {conflictsData && !loading && (
              <div className="flex gap-4">
                <div className="text-center px-4 py-2 bg-white rounded-lg border">
                  <div className={`text-2xl font-bold ${conflictsData.total_conflicts > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {conflictsData.total_conflicts}
                  </div>
                  <div className="text-xs text-gray-500">Conflitos</div>
                </div>
                <div className="text-center px-4 py-2 bg-white rounded-lg border">
                  <div className={`text-2xl font-bold ${conflictsData.teachers_with_conflicts > 0 ? 'text-orange-600' : 'text-green-600'}`}>
                    {conflictsData.teachers_with_conflicts || 0}
                  </div>
                  <div className="text-xs text-gray-500">Professores(as)</div>
                </div>
              </div>
            )}
          </div>
          
          {/* Gráfico por dia */}
          {conflictsData && conflictsData.conflicts_by_day && !loading && (
            <div className="mt-4 flex gap-2">
              {DAYS.map(day => {
                const count = conflictsData.conflicts_by_day[day.id] || 0;
                return (
                  <div key={day.id} className="flex-1 text-center">
                    <div className={`h-8 rounded flex items-center justify-center text-xs font-medium
                      ${count > 0 ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'}`}>
                      {count}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">{day.label.substring(0, 3)}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        
        {/* Lista de Conflitos */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-orange-600"></div>
              <span className="ml-3 text-gray-500">Analisando horários...</span>
            </div>
          ) : conflictsData?.total_conflicts === 0 ? (
            <div className="text-center py-12">
              <CheckCircle className="mx-auto text-green-500 mb-3" size={48} />
              <p className="text-lg font-medium text-green-700">Nenhum conflito encontrado!</p>
              <p className="text-sm text-gray-500 mt-1">
                Todos os horários estão consistentes na rede de ensino.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {conflictsData?.conflicts_by_teacher?.map((teacher, idx) => (
                <div key={teacher.staff_id} className="border rounded-lg overflow-hidden">
                  {/* Teacher Header */}
                  <button
                    onClick={() => setExpandedTeacher(expandedTeacher === idx ? null : idx)}
                    className="w-full p-4 flex items-center justify-between bg-white hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-orange-100 flex items-center justify-center">
                        <Users className="text-orange-600" size={20} />
                      </div>
                      <div className="text-left">
                        <div className="font-medium text-gray-900">{teacher.staff_name}</div>
                        {teacher.staff_cpf && (
                          <div className="text-xs text-gray-500">CPF: {teacher.staff_cpf}</div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="px-3 py-1 bg-red-100 text-red-700 text-sm font-medium rounded-full">
                        {teacher.conflicts_count} conflito(s)
                      </span>
                      <ChevronRight 
                        className={`text-gray-400 transition-transform ${expandedTeacher === idx ? 'rotate-90' : ''}`} 
                        size={20} 
                      />
                    </div>
                  </button>
                  
                  {/* Conflict Details */}
                  {expandedTeacher === idx && (
                    <div className="border-t bg-gray-50 p-4">
                      <div className="space-y-4">
                        {teacher.conflicts.map((conflict, cIdx) => (
                          <div key={cIdx} className="bg-white rounded-lg border p-3">
                            <div className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2">
                              <Clock size={14} />
                              {DAYS.find(d => d.id === conflict.day)?.label} - {conflict.slot_number}ª Aula
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                              {conflict.conflicting_classes.map((cls, clsIdx) => (
                                <div 
                                  key={clsIdx} 
                                  className="p-2 rounded bg-red-50 border border-red-200 text-sm"
                                >
                                  <div className="flex items-center gap-1 text-red-800 font-medium">
                                    <Building2 size={12} />
                                    {cls.school_name}
                                  </div>
                                  <div className="text-red-700 mt-1">
                                    {cls.class_name} ({SHIFT_LABELS[cls.class_shift] || cls.class_shift})
                                  </div>
                                  <div className="text-red-600 text-xs mt-1">
                                    {cls.course_name}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Footer */}
        <div className="p-4 border-t bg-gray-50 rounded-b-xl">
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-500">
              Ano Letivo: <strong>{academicYear}</strong>
            </p>
            <Button variant="outline" onClick={onClose}>
              Fechar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Componente principal
export function ClassScheduleTab({ academicYear }) {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [schedule, setSchedule] = useState(null);
  const [weekStart, setWeekStart] = useState(getMonday(new Date()));
  const [weekData, setWeekData] = useState(null);
  const [slotsPerDay, setSlotsPerDay] = useState(4);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showConflictsPanel, setShowConflictsPanel] = useState(false);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  const [editingSlots, setEditingSlots] = useState([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [conflictWarnings, setConflictWarnings] = useState([]);
  const [slotTimes, setSlotTimes] = useState({}); // {slotNumber: {start: '07:00', end: '07:45'}}
  const [teacherAllocations, setTeacherAllocations] = useState([]); // Alocações de professores
  
  // Permissões
  const canEdit = ['admin', 'admin_teste', 'secretario'].includes(user?.role);
  
  // IDs das escolas vinculadas ao usuário
  const userSchoolIds = useMemo(() => {
    return user?.school_ids || user?.school_links?.map(link => link.school_id) || [];
  }, [user]);
  
  // Carregar escolas
  useEffect(() => {
    const loadSchools = async () => {
      try {
        let data = await schoolsAPI.getAll();
        
        // Filtrar por escolas vinculadas se não for admin/semed
        if (!['admin', 'admin_teste', 'semed'].includes(user?.role) && userSchoolIds.length > 0) {
          data = data.filter(s => userSchoolIds.includes(s.id));
        }
        
        // Filtrar apenas escolas ativas
        data = data.filter(s => s.status === 'active' || !s.status);
        
        setSchools(data);
        
        // Se só tem uma escola, seleciona automaticamente
        if (data.length === 1) {
          setSelectedSchool(data[0].id);
        }
      } catch (error) {
        console.error('Erro ao carregar escolas:', error);
      }
    };
    loadSchools();
  }, [user?.role, userSchoolIds]);
  
  // Carregar turmas quando escola é selecionada
  useEffect(() => {
    const loadClasses = async () => {
      if (!selectedSchool) {
        setClasses([]);
        return;
      }
      
      try {
        const data = await classesAPI.getAll();
        const filtered = data.filter(c => 
          c.school_id === selectedSchool &&
          (c.academic_year === academicYear || String(c.academic_year) === String(academicYear))
        );
        setClasses(filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
      } catch (error) {
        console.error('Erro ao carregar turmas:', error);
      }
    };
    loadClasses();
  }, [selectedSchool, academicYear]);
  
  // Carregar componentes curriculares quando turma é selecionada
  useEffect(() => {
    const loadCourses = async () => {
      if (!selectedClass) {
        setCourses([]);
        return;
      }
      
      try {
        // Buscar a turma para saber o nível de ensino
        const classInfo = classes.find(c => c.id === selectedClass);
        if (!classInfo) return;
        
        const allCourses = await coursesAPI.getAll();
        
        // Filtrar componentes pelo nível de ensino da turma
        const filtered = allCourses.filter(c => 
          c.nivel_ensino === classInfo.level ||
          !c.nivel_ensino // Componentes sem nível específico
        );
        
        setCourses(filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
      } catch (error) {
        console.error('Erro ao carregar componentes:', error);
      }
    };
    loadCourses();
  }, [selectedClass, classes]);
  
  // Carregar horário da turma
  useEffect(() => {
    const loadSchedule = async () => {
      if (!selectedClass) {
        setSchedule(null);
        setEditingSlots([]);
        setLoading(false);
        return;
      }
      
      setLoading(true);
      try {
        const data = await classScheduleAPI.getByClass(selectedClass, academicYear);
        setSchedule(data);
        
        if (data) {
          setSlotsPerDay(data.slots_per_day || 4);
          setEditingSlots(data.schedule_slots || []);
        } else {
          setEditingSlots([]);
        }
        
        setHasChanges(false);
      } catch (error) {
        console.error('Erro ao carregar horário:', error);
        setSchedule(null);
        setEditingSlots([]);
      } finally {
        setLoading(false);
      }
    };
    loadSchedule();
  }, [selectedClass, academicYear]);
  
  // Carregar dados da semana (incluindo sábados letivos)
  useEffect(() => {
    const loadWeekData = async () => {
      if (!selectedClass || !weekStart) return;
      
      try {
        const weekStartStr = formatDateYYYYMMDD(weekStart);
        const data = await classScheduleAPI.getWeekView(selectedClass, weekStartStr, academicYear);
        setWeekData(data);
      } catch (error) {
        console.error('Erro ao carregar dados da semana:', error);
      }
    };
    loadWeekData();
  }, [selectedClass, weekStart, academicYear]);
  
  // Calcular datas da semana
  const weekDates = useMemo(() => {
    const dates = {};
    const days = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado'];
    
    days.forEach((day, i) => {
      const date = new Date(weekStart);
      date.setDate(date.getDate() + i);
      dates[day] = formatDateYYYYMMDD(date);
    });
    
    return dates;
  }, [weekStart]);
  
  // Navegar semanas
  const navigateWeek = (direction) => {
    const newDate = new Date(weekStart);
    newDate.setDate(newDate.getDate() + (direction * 7));
    setWeekStart(newDate);
  };
  
  // Ir para semana atual
  const goToCurrentWeek = () => {
    setWeekStart(getMonday(new Date()));
  };
  
  // Obter slot do horário
  const getSlot = (day, slotNumber) => {
    return editingSlots.find(s => s.day === day && s.slot_number === slotNumber);
  };
  
  // Atualizar slot
  const updateSlot = async (day, slotNumber, courseId) => {
    // Remover slot existente
    const newSlots = editingSlots.filter(s => !(s.day === day && s.slot_number === slotNumber));
    
    // Adicionar novo slot se courseId não for vazio
    if (courseId) {
      const course = courses.find(c => c.id === courseId);
      newSlots.push({
        day,
        slot_number: slotNumber,
        course_id: courseId,
        course_name: course?.name || ''
      });
      
      // Verificar conflitos
      if (canEdit) {
        try {
          const conflict = await classScheduleAPI.validateConflicts(
            selectedClass, day, slotNumber, courseId, academicYear
          );
          
          if (conflict.has_conflict) {
            setConflictWarnings(prev => [
              ...prev.filter(w => !(w.day === day && w.slot_number === slotNumber)),
              { day, slot_number: slotNumber, message: conflict.message, conflicts: conflict.conflicts }
            ]);
          } else {
            setConflictWarnings(prev => 
              prev.filter(w => !(w.day === day && w.slot_number === slotNumber))
            );
          }
        } catch (error) {
          console.error('Erro ao verificar conflitos:', error);
        }
      }
    }
    
    setEditingSlots(newSlots);
    setHasChanges(true);
  };
  
  // Salvar horário
  const saveSchedule = async () => {
    if (!selectedClass || !selectedSchool) return;
    
    setSaving(true);
    try {
      const scheduleData = {
        school_id: selectedSchool,
        class_id: selectedClass,
        academic_year: academicYear,
        slots_per_day: slotsPerDay,
        schedule_slots: editingSlots
      };
      
      if (schedule?.id) {
        // Atualizar existente
        await classScheduleAPI.update(schedule.id, {
          slots_per_day: slotsPerDay,
          schedule_slots: editingSlots
        });
      } else {
        // Criar novo
        await classScheduleAPI.create(scheduleData);
      }
      
      setAlert({ type: 'success', message: 'Horário salvo com sucesso!' });
      setHasChanges(false);
      
      // Recarregar
      const data = await classScheduleAPI.getByClass(selectedClass, academicYear);
      setSchedule(data);
    } catch (error) {
      console.error('Erro ao salvar horário:', error);
      setAlert({ type: 'error', message: error.response?.data?.detail || 'Erro ao salvar horário' });
    } finally {
      setSaving(false);
    }
  };
  
  // Obter turma selecionada
  const selectedClassInfo = classes.find(c => c.id === selectedClass);
  
  // Verificar se há sábado letivo na semana
  const hasSaturdayThisWeek = weekData?.has_saturday;
  const saturdayInfo = weekData?.saturday_info;
  
  return (
    <div className="space-y-4">
      {/* Alertas */}
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
          <button onClick={() => setAlert(null)} className="ml-auto text-gray-400 hover:text-gray-600">×</button>
        </div>
      )}
      
      {/* Filtros */}
      <div className="bg-white rounded-lg shadow-sm border p-4">
        <div className="flex flex-wrap items-end gap-4">
          {/* Escola */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
            <select
              value={selectedSchool}
              onChange={(e) => {
                setSelectedSchool(e.target.value);
                setSelectedClass('');
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Selecione uma escola</option>
              {schools.map(school => (
                <option key={school.id} value={school.id}>{school.name}</option>
              ))}
            </select>
          </div>
          
          {/* Turma */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
            <select
              value={selectedClass}
              onChange={(e) => setSelectedClass(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
              disabled={!selectedSchool}
            >
              <option value="">Selecione uma turma</option>
              {classes.map(cls => (
                <option key={cls.id} value={cls.id}>
                  {cls.name} ({SHIFT_LABELS[cls.shift] || cls.shift})
                </option>
              ))}
            </select>
          </div>
          
          {/* Configurações */}
          {canEdit && selectedClass && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSettingsModal(true)}
              className="flex items-center gap-1"
            >
              <Settings size={16} />
              Configurar
            </Button>
          )}
          
          {/* Botão Ver Conflitos da Rede */}
          {['admin', 'admin_teste', 'semed', 'secretario'].includes(user?.role) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowConflictsPanel(true)}
              className="flex items-center gap-1 text-orange-600 border-orange-300 hover:bg-orange-50"
            >
              <AlertTriangle size={16} />
              Ver Conflitos da Rede
            </Button>
          )}
        </div>
        
        {/* Info da turma */}
        {selectedClassInfo && (
          <div className="mt-3 pt-3 border-t flex items-center gap-4 text-sm text-gray-600">
            <span className="flex items-center gap-1">
              <Clock size={14} />
              Turno: <strong>{SHIFT_LABELS[selectedClassInfo.shift] || selectedClassInfo.shift}</strong>
            </span>
            <span className="flex items-center gap-1">
              <BookOpen size={14} />
              Aulas por dia: <strong>{slotsPerDay}</strong>
            </span>
          </div>
        )}
      </div>
      
      {/* Navegação de Semana */}
      {selectedClass && (
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <div className="flex items-center justify-between">
            <Button variant="outline" size="sm" onClick={() => navigateWeek(-1)}>
              <ChevronLeft size={18} />
              Semana Anterior
            </Button>
            
            <div className="text-center">
              <div className="font-medium text-lg">
                {formatDate(weekDates.segunda)} - {formatDate(weekDates.sexta)}
                {hasSaturdayThisWeek && (
                  <span className="ml-2 text-sm text-green-600">(+ Sábado Letivo)</span>
                )}
              </div>
              <div className="text-sm text-gray-500">
                Ano Letivo {academicYear}
              </div>
            </div>
            
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={goToCurrentWeek}>
                Hoje
              </Button>
              <Button variant="outline" size="sm" onClick={() => navigateWeek(1)}>
                Próxima Semana
                <ChevronRight size={18} />
              </Button>
            </div>
          </div>
        </div>
      )}
      
      {/* Grade de Horários */}
      {selectedClass && (
        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          {loading ? (
            <div className="flex justify-center items-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <span className="ml-3 text-gray-500">Carregando horário...</span>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px]">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="px-3 py-3 text-left text-xs font-medium text-gray-500 uppercase w-20">
                        Aula
                      </th>
                      {DAYS.map(day => (
                        <th key={day.id} className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase">
                          <div>{day.label}</div>
                          <div className="text-[10px] font-normal text-gray-400">
                            {formatDate(weekDates[day.id])}
                          </div>
                        </th>
                      ))}
                      {hasSaturdayThisWeek && (
                        <th className="px-3 py-3 text-center text-xs font-medium text-green-600 uppercase bg-green-50">
                          <div>Sábado</div>
                          <div className="text-[10px] font-normal">
                            {formatDate(weekDates.sabado)}
                          </div>
                          {saturdayInfo && (
                            <div className="text-[9px] font-normal mt-1 bg-green-200 px-2 py-0.5 rounded">
                              {saturdayInfo.saturday_number}º Sábado Letivo
                              <br/>
                              (Aulas de {DAYS.find(d => d.id === saturdayInfo.corresponding_day)?.label || saturdayInfo.corresponding_day})
                            </div>
                          )}
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {Array.from({ length: slotsPerDay }, (_, i) => i + 1).map(slotNumber => (
                      <tr key={slotNumber} className="hover:bg-gray-50">
                        <td className="px-3 py-3 text-sm font-medium text-gray-900 bg-gray-50">
                          {slotNumber}ª
                        </td>
                        {DAYS.map(day => {
                          const slot = getSlot(day.id, slotNumber);
                          const conflict = conflictWarnings.find(
                            w => w.day === day.id && w.slot_number === slotNumber
                          );
                          
                          return (
                            <td 
                              key={day.id} 
                              className={`px-2 py-2 text-center ${conflict ? 'bg-yellow-50' : ''}`}
                            >
                              {canEdit ? (
                                <select
                                  value={slot?.course_id || ''}
                                  onChange={(e) => updateSlot(day.id, slotNumber, e.target.value)}
                                  className={`w-full px-2 py-1.5 text-xs border rounded text-center
                                    ${conflict ? 'border-yellow-400 bg-yellow-50' : 'border-gray-300'}
                                    focus:ring-2 focus:ring-blue-500`}
                                  title={conflict ? conflict.message : ''}
                                >
                                  <option value="">-</option>
                                  {courses.map(course => (
                                    <option key={course.id} value={course.id}>
                                      {course.name}
                                    </option>
                                  ))}
                                </select>
                              ) : (
                                <span className={`text-xs px-2 py-1 rounded ${
                                  slot?.course_name ? 'bg-blue-100 text-blue-800' : 'text-gray-400'
                                }`}>
                                  {slot?.course_name || '-'}
                                </span>
                              )}
                              {conflict && (
                                <div className="text-[10px] text-yellow-600 mt-1" title={conflict.message}>
                                  ⚠️ Conflito
                                </div>
                              )}
                            </td>
                          );
                        })}
                        {hasSaturdayThisWeek && (
                          <td className="px-2 py-2 text-center bg-green-50">
                            {weekData?.saturday_slots?.find(s => s.slot_number === slotNumber) ? (
                              <span className="text-xs px-2 py-1 rounded bg-green-100 text-green-800">
                                {weekData.saturday_slots.find(s => s.slot_number === slotNumber)?.course_name || '-'}
                              </span>
                            ) : (
                              <span className="text-xs text-gray-400">-</span>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {/* Botão Salvar */}
              {canEdit && hasChanges && (
                <div className="p-4 bg-gray-50 border-t flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setEditingSlots(schedule?.schedule_slots || []);
                      setHasChanges(false);
                      setConflictWarnings([]);
                    }}
                  >
                    Cancelar
                  </Button>
                  <Button
                    onClick={saveSchedule}
                    disabled={saving}
                    className="flex items-center gap-2"
                  >
                    <Save size={16} />
                    {saving ? 'Salvando...' : 'Salvar Horário'}
                  </Button>
                </div>
              )}
              
              {/* Avisos de Conflito */}
              {conflictWarnings.length > 0 && (
                <div className="p-4 bg-yellow-50 border-t">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="text-yellow-600 flex-shrink-0" size={20} />
                    <div>
                      <p className="font-medium text-yellow-800">Conflitos Detectados</p>
                      <ul className="text-sm text-yellow-700 mt-1 space-y-1">
                        {conflictWarnings.map((w, i) => (
                          <li key={i}>
                            {DAYS.find(d => d.id === w.day)?.label} {w.slot_number}ª aula: {w.message}
                            {w.conflicts?.map((c, j) => (
                              <span key={j} className="block text-xs pl-4">
                                → {c.staff_name} já está em {c.class_name} ({c.school_name})
                              </span>
                            ))}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
      
      {/* Mensagem quando não há turma selecionada */}
      {!selectedClass && (
        <div className="bg-white rounded-lg shadow-sm border p-8 text-center">
          <Clock className="mx-auto text-gray-400 mb-3" size={48} />
          <p className="text-gray-500">Selecione uma escola e turma para visualizar o horário de aulas</p>
        </div>
      )}
      
      {/* Modal de Configurações */}
      <Modal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        title="Configurar Horário"
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Número de Aulas por Dia
            </label>
            <select
              value={slotsPerDay}
              onChange={(e) => {
                setSlotsPerDay(Number(e.target.value));
                setHasChanges(true);
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {[3, 4, 5, 6, 7, 8].map(n => (
                <option key={n} value={n}>{n} aulas</option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Cada aula corresponde a 1 hora
            </p>
          </div>
          
          <div className="flex justify-end gap-2 pt-4 border-t">
            <Button variant="outline" onClick={() => setShowSettingsModal(false)}>
              Fechar
            </Button>
          </div>
        </div>
      </Modal>
      
      {/* Painel de Conflitos da Rede */}
      <NetworkConflictsPanel 
        academicYear={academicYear}
        isOpen={showConflictsPanel}
        onClose={() => setShowConflictsPanel(false)}
      />
    </div>
  );
}

export default ClassScheduleTab;
