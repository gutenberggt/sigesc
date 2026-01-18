import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useBimestreEditStatus } from '@/hooks/useBimestreEditStatus';
import { BimestreBlockedAlert, BimestreDeadlineAlert } from '@/components/BimestreStatus';
import { 
  BookOpen, 
  Calendar, 
  Search, 
  Plus,
  Edit,
  Trash2,
  Save,
  ChevronLeft,
  ChevronRight,
  FileText,
  Clock,
  CheckCircle,
  AlertCircle,
  Home,
  Lock
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { learningObjectsAPI, schoolsAPI, classesAPI, coursesAPI, professorAPI } from '@/services/api';

// Nomes dos meses
const MONTHS = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
];

// Dias da semana
const WEEKDAYS = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];

export const LearningObjects = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const currentYear = new Date().getFullYear();
  
  // Estados de filtros
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedCourse, setSelectedCourse] = useState('');
  const [academicYear, setAcademicYear] = useState(currentYear);
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  
  // Hook para verificar status de edição dos bimestres
  const { 
    editStatus, 
    loading: loadingEditStatus, 
    canEditBimestre, 
    blockedBimestres,
    getBimestreInfo 
  } = useBimestreEditStatus(academicYear);
  
  // Estados de dados
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [records, setRecords] = useState([]);
  
  // Dados do professor (quando logado como professor)
  const [professorTurmas, setProfessorTurmas] = useState([]);
  const isProfessor = user?.role === 'professor';
  
  // Estados de UI
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  
  // Estados do formulário
  const [formData, setFormData] = useState({
    content: '',
    observations: '',
    methodology: '',
    resources: '',
    number_of_classes: 1
  });
  
  // Alert
  const [alert, setAlert] = useState(null);
  
  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 4000);
  };

  // Verifica se usuário pode editar
  const canEdit = ['admin', 'secretario', 'diretor', 'coordenador', 'professor'].includes(user?.role);

  // Carrega dados iniciais
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        setLoading(true);
        
        if (isProfessor) {
          // Para professor, carrega apenas suas turmas alocadas
          const turmasData = await professorAPI.getTurmas(academicYear);
          setProfessorTurmas(turmasData);
          
          // Extrai escolas únicas das turmas do professor
          const uniqueSchools = [];
          const schoolIds = new Set();
          turmasData.forEach(turma => {
            if (turma.school_id && !schoolIds.has(turma.school_id)) {
              schoolIds.add(turma.school_id);
              uniqueSchools.push({
                id: turma.school_id,
                name: turma.school_name
              });
            }
          });
          setSchools(uniqueSchools);
          
          // Se só tem uma escola, seleciona automaticamente
          if (uniqueSchools.length === 1) {
            setSelectedSchool(uniqueSchools[0].id);
          }
        } else {
          // Para outros usuários, carrega todos os dados
          const [schoolsData, classesData, coursesData] = await Promise.all([
            schoolsAPI.getAll(),
            classesAPI.getAll(),
            coursesAPI.getAll()
          ]);
          setSchools(schoolsData);
          setClasses(classesData);
          setCourses(coursesData);
        }
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
        showAlert('error', 'Erro ao carregar dados iniciais');
      } finally {
        setLoading(false);
      }
    };
    loadInitialData();
  }, [isProfessor, academicYear]);

  // Atualiza turmas quando escola muda (para professor)
  useEffect(() => {
    if (isProfessor && selectedSchool) {
      const filtered = professorTurmas.filter(t => t.school_id === selectedSchool);
      setClasses(filtered);
      // Se só tem uma turma, seleciona automaticamente
      if (filtered.length === 1) {
        setSelectedClass(filtered[0].id);
      }
    }
  }, [isProfessor, selectedSchool, professorTurmas]);

  // Atualiza componentes quando turma muda (para professor)
  useEffect(() => {
    if (isProfessor && selectedClass) {
      const turma = professorTurmas.find(t => t.id === selectedClass);
      if (turma && turma.componentes) {
        setCourses(turma.componentes);
        // Se só tem um componente, seleciona automaticamente
        if (turma.componentes.length === 1) {
          setSelectedCourse(turma.componentes[0].id);
        }
      }
    }
  }, [isProfessor, selectedClass, professorTurmas]);

  // Carrega registros quando filtros mudam
  useEffect(() => {
    if (selectedClass && selectedCourse) {
      loadRecords();
    }
  }, [selectedClass, selectedCourse, academicYear, currentMonth]);

  const loadRecords = async () => {
    try {
      const data = await learningObjectsAPI.list({
        class_id: selectedClass,
        course_id: selectedCourse,
        academic_year: academicYear,
        month: currentMonth + 1
      });
      setRecords(data);
    } catch (error) {
      console.error('Erro ao carregar registros:', error);
    }
  };

  // Turmas filtradas por escola
  const filteredClasses = useMemo(() => {
    if (isProfessor) {
      // Para professor, já filtramos no estado classes
      return classes;
    }
    if (!selectedSchool) return classes;
    return classes.filter(c => c.school_id === selectedSchool);
  }, [classes, selectedSchool, isProfessor]);

  // Gera os dias do mês
  const calendarDays = useMemo(() => {
    const year = academicYear;
    const month = currentMonth;
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const daysInMonth = lastDay.getDate();
    const startingDay = firstDay.getDay();
    
    const days = [];
    
    // Dias vazios antes do primeiro dia
    for (let i = 0; i < startingDay; i++) {
      days.push({ day: null, date: null });
    }
    
    // Dias do mês
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const record = records.find(r => r.date === dateStr);
      const dayOfWeek = new Date(year, month, day).getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isToday = dateStr === new Date().toISOString().split('T')[0];
      
      days.push({
        day,
        date: dateStr,
        record,
        isWeekend,
        isToday,
        hasRecord: !!record
      });
    }
    
    return days;
  }, [academicYear, currentMonth, records]);

  // Handlers de navegação do calendário
  const previousMonth = () => {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setAcademicYear(academicYear - 1);
    } else {
      setCurrentMonth(currentMonth - 1);
    }
  };

  const nextMonth = () => {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setAcademicYear(academicYear + 1);
    } else {
      setCurrentMonth(currentMonth + 1);
    }
  };

  // Handler de clique no dia
  const handleDayClick = (dayInfo) => {
    if (!dayInfo.date || !selectedClass || !selectedCourse) return;
    
    setSelectedDate(dayInfo.date);
    
    if (dayInfo.record) {
      // Editar registro existente
      setEditingRecord(dayInfo.record);
      setFormData({
        content: dayInfo.record.content || '',
        observations: dayInfo.record.observations || '',
        methodology: dayInfo.record.methodology || '',
        resources: dayInfo.record.resources || '',
        number_of_classes: dayInfo.record.number_of_classes || 1
      });
    } else {
      // Novo registro
      setEditingRecord(null);
      setFormData({
        content: '',
        observations: '',
        methodology: '',
        resources: '',
        number_of_classes: 1
      });
    }
    setShowForm(true);
  };

  // Salvar registro
  const handleSave = async () => {
    if (!formData.content.trim()) {
      showAlert('error', 'O conteúdo é obrigatório');
      return;
    }
    
    try {
      setSaving(true);
      
      if (editingRecord) {
        // Atualizar
        await learningObjectsAPI.update(editingRecord.id, formData);
        showAlert('success', 'Registro atualizado com sucesso!');
      } else {
        // Criar
        await learningObjectsAPI.create({
          class_id: selectedClass,
          course_id: selectedCourse,
          date: selectedDate,
          academic_year: academicYear,
          ...formData
        });
        showAlert('success', 'Registro criado com sucesso!');
      }
      
      setShowForm(false);
      loadRecords();
    } catch (error) {
      console.error('Erro ao salvar:', error);
      showAlert('error', error.response?.data?.detail || 'Erro ao salvar registro');
    } finally {
      setSaving(false);
    }
  };

  // Excluir registro
  const handleDelete = async () => {
    if (!editingRecord) return;
    
    if (!window.confirm('Deseja realmente excluir este registro?')) return;
    
    try {
      setSaving(true);
      await learningObjectsAPI.delete(editingRecord.id);
      showAlert('success', 'Registro excluído com sucesso!');
      setShowForm(false);
      loadRecords();
    } catch (error) {
      console.error('Erro ao excluir:', error);
      showAlert('error', error.response?.data?.detail || 'Erro ao excluir registro');
    } finally {
      setSaving(false);
    }
  };

  // Estatísticas do mês
  const monthStats = useMemo(() => {
    const totalRecords = records.length;
    const totalClasses = records.reduce((sum, r) => sum + (r.number_of_classes || 1), 0);
    return { totalRecords, totalClasses };
  }, [records]);

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* Alert */}
        {alert && (
          <div className={`p-4 rounded-lg flex items-center gap-2 ${
            alert.type === 'success' ? 'bg-green-50 text-green-800 border border-green-200' :
            alert.type === 'error' ? 'bg-red-50 text-red-800 border border-red-200' :
            'bg-blue-50 text-blue-800 border border-blue-200'
          }`}>
            {alert.type === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
            {alert.message}
          </div>
        )}

        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <BookOpen className="text-purple-600" />
                Objetos de Conhecimento
              </h1>
              <p className="text-gray-600 text-sm">Registro de conteúdos ministrados</p>
            </div>
          </div>
        </div>

        {/* Filtros */}
        <Card>
          <CardContent className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Escola */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                <select
                  value={selectedSchool}
                  onChange={(e) => {
                    setSelectedSchool(e.target.value);
                    setSelectedClass('');
                  }}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                >
                  <option value="">Todas as escolas</option>
                  {schools.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>

              {/* Turma */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turma *</label>
                <select
                  value={selectedClass}
                  onChange={(e) => setSelectedClass(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                >
                  <option value="">Selecione a turma</option>
                  {filteredClasses.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              {/* Componente Curricular */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular *</label>
                <select
                  value={selectedCourse}
                  onChange={(e) => setSelectedCourse(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                >
                  <option value="">Selecione o componente</option>
                  {courses.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              {/* Ano Letivo */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label>
                <select
                  value={academicYear}
                  onChange={(e) => setAcademicYear(parseInt(e.target.value))}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                >
                  {[currentYear - 1, currentYear, currentYear + 1].map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Conteúdo principal */}
        {!selectedClass || !selectedCourse ? (
          <Card>
            <CardContent className="p-8 text-center text-gray-500">
              <BookOpen size={48} className="mx-auto mb-2 text-gray-300" />
              <p>Selecione a turma e o componente curricular para visualizar o calendário de registros.</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Calendário */}
            <div className="lg:col-span-2">
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <Button variant="ghost" size="sm" onClick={previousMonth}>
                      <ChevronLeft size={20} />
                    </Button>
                    <CardTitle className="text-lg">
                      {MONTHS[currentMonth]} {academicYear}
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={nextMonth}>
                      <ChevronRight size={20} />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {/* Cabeçalho dos dias da semana */}
                  <div className="grid grid-cols-7 gap-1 mb-2">
                    {WEEKDAYS.map(day => (
                      <div key={day} className="text-center text-xs font-medium text-gray-500 py-2">
                        {day}
                      </div>
                    ))}
                  </div>
                  
                  {/* Dias do mês */}
                  <div className="grid grid-cols-7 gap-1">
                    {calendarDays.map((dayInfo, index) => (
                      <div
                        key={index}
                        onClick={() => canEdit && dayInfo.date && handleDayClick(dayInfo)}
                        className={`
                          aspect-square p-1 rounded-lg text-center relative
                          ${!dayInfo.date ? 'bg-transparent' : ''}
                          ${dayInfo.isWeekend && dayInfo.date ? 'bg-gray-50' : ''}
                          ${dayInfo.isToday ? 'ring-2 ring-purple-500' : ''}
                          ${dayInfo.date && canEdit ? 'cursor-pointer hover:bg-purple-50' : ''}
                          ${dayInfo.hasRecord ? 'bg-green-100 hover:bg-green-200' : ''}
                          ${selectedDate === dayInfo.date ? 'ring-2 ring-purple-600 bg-purple-100' : ''}
                        `}
                      >
                        {dayInfo.date && (
                          <>
                            <span className={`text-sm ${dayInfo.isWeekend ? 'text-gray-400' : 'text-gray-700'}`}>
                              {dayInfo.day}
                            </span>
                            {dayInfo.hasRecord && (
                              <div className="absolute bottom-1 left-1/2 transform -translate-x-1/2">
                                <FileText size={12} className="text-green-600" />
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Legenda */}
                  <div className="mt-4 flex items-center gap-4 text-xs text-gray-500">
                    <div className="flex items-center gap-1">
                      <div className="w-4 h-4 bg-green-100 rounded"></div>
                      <span>Com registro</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-4 h-4 bg-gray-50 rounded"></div>
                      <span>Fim de semana</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <div className="w-4 h-4 ring-2 ring-purple-500 rounded"></div>
                      <span>Hoje</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Painel lateral - Estatísticas e Formulário */}
            <div className="space-y-4">
              {/* Estatísticas */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Estatísticas do Mês</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-purple-50 p-3 rounded-lg text-center">
                      <p className="text-2xl font-bold text-purple-700">{monthStats.totalRecords}</p>
                      <p className="text-xs text-purple-600">Dias com registro</p>
                    </div>
                    <div className="bg-blue-50 p-3 rounded-lg text-center">
                      <p className="text-2xl font-bold text-blue-700">{monthStats.totalClasses}</p>
                      <p className="text-xs text-blue-600">Total de aulas</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Formulário */}
              {showForm && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center justify-between">
                      <span>{editingRecord ? 'Editar Registro' : 'Novo Registro'}</span>
                      <span className="text-purple-600 font-normal">
                        {new Date(selectedDate + 'T12:00:00').toLocaleDateString('pt-BR')}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Conteúdo */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Conteúdo/Objeto de Conhecimento *
                      </label>
                      <textarea
                        value={formData.content}
                        onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 h-24 resize-none"
                        placeholder="Descreva o conteúdo ministrado..."
                      />
                    </div>

                    {/* Número de aulas */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Número de Aulas
                      </label>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        value={formData.number_of_classes}
                        onChange={(e) => setFormData({ ...formData, number_of_classes: parseInt(e.target.value) || 1 })}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                      />
                    </div>

                    {/* Metodologia */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Metodologia
                      </label>
                      <input
                        type="text"
                        value={formData.methodology}
                        onChange={(e) => setFormData({ ...formData, methodology: e.target.value })}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                        placeholder="Ex: Aula expositiva, Trabalho em grupo..."
                      />
                    </div>

                    {/* Recursos */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Recursos Utilizados
                      </label>
                      <input
                        type="text"
                        value={formData.resources}
                        onChange={(e) => setFormData({ ...formData, resources: e.target.value })}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                        placeholder="Ex: Livro didático, Datashow..."
                      />
                    </div>

                    {/* Observações */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Observações
                      </label>
                      <textarea
                        value={formData.observations}
                        onChange={(e) => setFormData({ ...formData, observations: e.target.value })}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 h-16 resize-none"
                        placeholder="Observações adicionais..."
                      />
                    </div>

                    {/* Botões */}
                    <div className="flex gap-2 pt-2">
                      <Button 
                        onClick={handleSave} 
                        disabled={saving}
                        className="flex-1"
                      >
                        <Save size={16} className="mr-1" />
                        {saving ? 'Salvando...' : 'Salvar'}
                      </Button>
                      {editingRecord && (
                        <Button 
                          variant="destructive" 
                          onClick={handleDelete}
                          disabled={saving}
                        >
                          <Trash2 size={16} />
                        </Button>
                      )}
                      <Button 
                        variant="outline" 
                        onClick={() => setShowForm(false)}
                      >
                        Cancelar
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Lista de registros do mês */}
              {!showForm && records.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Registros do Mês</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {records.map(record => (
                        <div 
                          key={record.id}
                          onClick={() => handleDayClick({ date: record.date, record })}
                          className="p-2 bg-gray-50 rounded-lg cursor-pointer hover:bg-purple-50 border border-transparent hover:border-purple-200"
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-purple-700">
                              {new Date(record.date + 'T12:00:00').toLocaleDateString('pt-BR')}
                            </span>
                            <span className="text-xs text-gray-500">
                              {record.number_of_classes} aula(s)
                            </span>
                          </div>
                          <p className="text-xs text-gray-600 line-clamp-2">
                            {record.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default LearningObjects;
