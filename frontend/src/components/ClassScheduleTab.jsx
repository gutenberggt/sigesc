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
  Settings
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

// Helper para obter segunda-feira da semana
const getMonday = (date) => {
  const d = new Date(date);
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.setDate(diff));
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
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  const [editingSlots, setEditingSlots] = useState([]);
  const [hasChanges, setHasChanges] = useState(false);
  const [conflictWarnings, setConflictWarnings] = useState([]);
  
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
        const weekStartStr = weekStart.toISOString().split('T')[0];
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
      dates[day] = date.toISOString().split('T')[0];
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
                            <div className="text-[9px] font-normal mt-1">
                              ({saturdayInfo.saturday_number}º - {saturdayInfo.corresponding_day})
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
    </div>
  );
}

export default ClassScheduleTab;
