import { useState, useEffect, useMemo, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Layout } from '@/components/Layout';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import { usePermissions } from '@/hooks/usePermissions';
import { inferEducationLevel } from '@/utils/educationLevel';
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
import { learningObjectsAPI, schoolsAPI, classesAPI, coursesAPI, professorAPI, teacherAssignmentAPI, attendanceAPI, calendarAPI } from '@/services/api';


// Infere o nível de ensino da turma a partir de education_level, nivel_ensino, grade_level ou name

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
  const [selectedCourses, setSelectedCourses] = useState([]);
  const [showCoursesDropdown, setShowCoursesDropdown] = useState(false);
  const [academicYear, setAcademicYear] = useState(currentYear);
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const coursesDropdownRef = useRef(null);

  // PDF
  const [showPdfModal, setShowPdfModal] = useState(false);
  const [pdfBimestre, setPdfBimestre] = useState(1);
  const [pdfCourseId, setPdfCourseId] = useState('');
  const [generatingPdf, setGeneratingPdf] = useState(false);

  // Fechar dropdown de campos de experiência ao clicar fora
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (coursesDropdownRef.current && !coursesDropdownRef.current.contains(e.target)) {
        setShowCoursesDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
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
  const { isProfessor, canEditLearningObjects: canEdit } = usePermissions();
  
  // Estados de UI
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedDate, setSelectedDate] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  
  // Calendário letivo (feriados, sábados letivos)
  const [blockedDates, setBlockedDates] = useState(new Set());
  const [saturdayLetivoDates, setSaturdayLetivoDates] = useState(new Set());
  
  // Curso selecionado no formulário (para infantil com multi-seleção)
  const [formCourseId, setFormCourseId] = useState('');

  // Estados do formulário
  const [formData, setFormData] = useState({
    content: '',
    observations: '',
    methodology: '',
    resources: '',
    number_of_classes: 1
  });
  
  // Tracking de alterações não salvas
  const [hasChanges, setHasChanges] = useState(false);
  const { guardedNavigate } = useUnsavedChangesWarning(hasChanges, 'Há alterações de conteúdo não salvas. Deseja sair sem salvar?');

  // Alert
  const [alert, setAlert] = useState(null);
  
  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 4000);
  };

  // Verificar se a turma requer seleção de componente para PDF (EJA e Fundamental Anos Finais)
  const selectedClassInfo = classes.find(c => c.id === selectedClass);
  const isAnosFinaisOrEja = (() => {
    if (!selectedClassInfo) return false;
    const level = inferEducationLevel(selectedClassInfo);
    const name = (selectedClassInfo.name || '').toUpperCase();
    if (level === 'eja') return true;
    if (level === 'fundamental' || level === 'fundamental_anos_finais') {
      const grade = selectedClassInfo.grade_level || '';
      if (['6', '7', '8', '9'].includes(grade)) return true;
      if (name.match(/6|7|8|9|ANOS?\s*FINAIS/i)) return true;
    }
    return false;
  })();

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

  // Carrega calendário letivo (feriados, sábados letivos)
  useEffect(() => {
    const loadCalendar = async () => {
      try {
        const cal = await calendarAPI.getCalendarioLetivo(academicYear);
        if (!cal) return;
        
        const blocked = new Set();
        const sabLetivos = new Set();
        const tiposNaoLetivos = ['feriado_nacional', 'feriado_estadual', 'feriado_municipal', 'recesso_escolar'];
        
        for (const ev of (cal.eventos || [])) {
          if (tiposNaoLetivos.includes(ev.tipo)) {
            const start = ev.data_inicio?.substring(0, 10);
            const end = (ev.data_fim || ev.data_inicio)?.substring(0, 10);
            if (start) {
              let d = new Date(start + 'T12:00:00');
              const endDate = new Date((end || start) + 'T12:00:00');
              while (d <= endDate) {
                blocked.add(d.toISOString().split('T')[0]);
                d.setDate(d.getDate() + 1);
              }
            }
          }
          if (ev.tipo === 'sabado_letivo' && ev.data_inicio) {
            sabLetivos.add(ev.data_inicio.substring(0, 10));
          }
        }
        
        setBlockedDates(blocked);
        setSaturdayLetivoDates(sabLetivos);
      } catch {
        setBlockedDates(new Set());
        setSaturdayLetivoDates(new Set());
      }
    };
    loadCalendar();
  }, [academicYear]);

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

  // Turmas filtradas por escola
  const filteredClasses = useMemo(() => {
    if (isProfessor) {
      return classes;
    }
    if (!selectedSchool) return [];
    return classes.filter(c => c.school_id === selectedSchool);
  }, [classes, selectedSchool, isProfessor]);

  // Detectar se turma selecionada é Educação Infantil
  const isInfantilLevel = useMemo(() => {
    if (!selectedClass) return false;
    const classInfo = classes.find(c => c.id === selectedClass);
    const level = inferEducationLevel(classInfo);
    return level === 'educacao_infantil';
  }, [selectedClass, classes]);

  // Multi-select: infantil + anos iniciais (fundamental e EJA)
  const isMultiSelectMode = useMemo(() => {
    if (!selectedClass) return false;
    const classInfo = classes.find(c => c.id === selectedClass);
    const level = inferEducationLevel(classInfo);
    return ['educacao_infantil', 'fundamental_anos_iniciais', 'eja_inicial', 'eja'].includes(level);
  }, [selectedClass, classes]);

  // Ed. Infantil, Anos Iniciais e EJA Iniciais: ocultar campos extras (Nº Aulas, Recursos, Observações)
  const isDiasLevel = useMemo(() => {
    if (!selectedClass) return false;
    const classInfo = classes.find(c => c.id === selectedClass);
    const level = inferEducationLevel(classInfo);
    return ['educacao_infantil', 'fundamental_anos_iniciais', 'eja_inicial', 'eja'].includes(level);
  }, [selectedClass, classes]);

  // Anos Finais: ocultar Recursos/Observações, renomear Metodologia, buscar Nº Aulas do horário
  const isAnosFinais = useMemo(() => {
    if (!selectedClass) return false;
    const classInfo = classes.find(c => c.id === selectedClass);
    const level = inferEducationLevel(classInfo);
    return ['fundamental_anos_finais', 'eja_final'].includes(level);
  }, [selectedClass, classes]);

  // Determina o número padrão de aulas baseado no nível de ensino da turma
  const defaultNumberOfClasses = useMemo(() => {
    if (!selectedClass) return 1;
    const classInfo = classes.find(c => c.id === selectedClass);
    const level = inferEducationLevel(classInfo);
    if (level === 'educacao_infantil') return 4;
    if (['fundamental_anos_iniciais', 'eja_inicial'].includes(level)) return 5;
    return 1;
  }, [selectedClass, classes]);

  // Curso(s) efetivamente selecionado(s) para carregamento
  const hasValidSelection = useMemo(() => {
    if (isDiasLevel) return true; // Ed. Infantil / Anos Iniciais: turma basta
    if (isMultiSelectMode) return selectedCourses.length > 0;
    return !!selectedCourse;
  }, [isDiasLevel, isMultiSelectMode, selectedCourses, selectedCourse]);

  // Carrega registros quando filtros mudam
  useEffect(() => {
    if (selectedClass && hasValidSelection) {
      loadRecords();
    }
  }, [selectedClass, selectedCourse, academicYear, currentMonth, isMultiSelectMode, isDiasLevel]);

  // Para isDiasLevel: recarregar quando selectedCourses muda APENAS se NÃO estiver com form aberto
  // (evita re-fetch ao sincronizar cursos ao clicar numa data)
  useEffect(() => {
    if (selectedClass && isMultiSelectMode && !isDiasLevel && selectedCourses.length > 0) {
      loadRecords();
    }
  }, [selectedCourses]);

  const loadRecords = async () => {
    try {
      if (isDiasLevel) {
        // Ed. Infantil / Anos Iniciais: SEMPRE buscar TODOS os registros da turma
        const data = await learningObjectsAPI.list({
          class_id: selectedClass,
          academic_year: academicYear,
          month: currentMonth + 1
        });
        setRecords(data);
      } else if (isMultiSelectMode && selectedCourses.length > 0) {
        const promises = selectedCourses.map(courseId =>
          learningObjectsAPI.list({
            class_id: selectedClass,
            course_id: courseId,
            academic_year: academicYear,
            month: currentMonth + 1
          })
        );
        const results = await Promise.all(promises);
        const merged = results.flat();
        setRecords(merged);
      } else if (selectedCourse) {
        const data = await learningObjectsAPI.list({
          class_id: selectedClass,
          course_id: selectedCourse,
          academic_year: academicYear,
          month: currentMonth + 1
        });
        setRecords(data);
      }
    } catch (error) {
      console.error('Erro ao carregar registros:', error);
    }
  };

  // Carregar componentes curriculares da turma selecionada (para não-professores)
  useEffect(() => {
    const loadClassCourses = async () => {
      if (isProfessor || !selectedClass) {
        // Para professor, os componentes já são filtrados pelo professorTurmas
        if (!isProfessor) {
          setCourses([]);
          setSelectedCourse('');
          setSelectedCourses([]);
          setFormCourseId('');
        }
        return;
      }
      
      try {
        // Buscar alocações de professor da turma para saber quais componentes estão vinculados
        const classInfo = classes.find(c => c.id === selectedClass);
        if (!classInfo) return;

        const assignments = await teacherAssignmentAPI.list({
          class_id: selectedClass,
          academic_year: academicYear
        });

        if (assignments && assignments.length > 0) {
          // Extrair course_ids únicos das alocações
          const courseIds = [...new Set(assignments.map(a => a.course_id).filter(Boolean))];
          
          // Buscar dados completos dos componentes alocados
          const allCourses = await coursesAPI.getAll();
          const filtered = allCourses.filter(c => courseIds.includes(c.id));
          
          setCourses(filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
        } else {
          // Fallback: se não há alocações, buscar por nível de ensino (comportamento anterior)
          const turmaLevel = inferEducationLevel(classInfo);
          const turmaGradeLevel = classInfo.grade_level;
          const turmaAtendimento = (classInfo.atendimento_programa || '').toLowerCase();
          
          const allCourses = await coursesAPI.getAll(turmaLevel || null);
          
          let filtered = allCourses.filter(c => {
            const courseAtendimento = (c.atendimento_programa || c.atendimento || '').toLowerCase();
            if (turmaAtendimento === 'atendimento_integral') {
              return !courseAtendimento || courseAtendimento === 'atendimento_integral';
            } else if (turmaAtendimento) {
              return courseAtendimento === turmaAtendimento;
            } else {
              return !courseAtendimento;
            }
          });
          
          if (turmaGradeLevel) {
            const gradeFiltered = filtered.filter(c => 
              !c.grade_levels || c.grade_levels.length === 0 || c.grade_levels.includes(turmaGradeLevel)
            );
            if (gradeFiltered.length > 0) {
              filtered = gradeFiltered;
            }
          }
          
          if (filtered.length === 0 && allCourses.length > 0) {
            filtered = allCourses;
          } else if (filtered.length === 0) {
            const fallbackCourses = await coursesAPI.getAll();
            filtered = fallbackCourses;
          }
          
          setCourses(filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
        }
        
        setSelectedCourse('');
        setSelectedCourses([]);
        setFormCourseId('');
      } catch (error) {
        console.error('Erro ao carregar componentes da turma:', error);
      }
    };
    
    loadClassCourses();
  }, [selectedClass, classes, isProfessor, academicYear]);

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
      const isSunday = dayOfWeek === 0;
      const isSaturday = dayOfWeek === 6;
      const isWeekend = isSunday || isSaturday;
      const isToday = dateStr === new Date().toISOString().split('T')[0];
      const isHoliday = blockedDates.has(dateStr);
      const isSabadoLetivo = saturdayLetivoDates.has(dateStr);
      // Bloqueado: domingos, feriados, sábados não letivos
      const isBlocked = isSunday || isHoliday || (isSaturday && !isSabadoLetivo);
      
      days.push({
        day,
        date: dateStr,
        record,
        isWeekend,
        isToday,
        hasRecord: !!record,
        isBlocked,
        isHoliday
      });
    }
    
    return days;
  }, [academicYear, currentMonth, records, blockedDates, saturdayLetivoDates]);

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
  const handleDayClick = async (dayInfo) => {
    if (!dayInfo.date || !selectedClass) return;
    
    setSelectedDate(dayInfo.date);
    
    if (isMultiSelectMode) {
      // Ed. Infantil / Anos Iniciais: buscar TODOS os registros do dia
      const dayRecords = records.filter(r => r.date === dayInfo.date);
      
      if (dayRecords.length > 0) {
        // Sincronizar selectedCourses com os cursos salvos no dia
        const savedCourseIds = dayRecords.map(r => r.course_id);
        setSelectedCourses(savedCourseIds);
        
        // Editar: carregar conteúdo do primeiro registro como base
        setEditingRecord(dayRecords[0]);
        setFormData({
          content: dayRecords[0].content || '',
          observations: dayRecords[0].observations || '',
          methodology: dayRecords[0].methodology || '',
          resources: dayRecords[0].resources || '',
          number_of_classes: dayRecords[0].number_of_classes || 1
        });
      } else {
        // Novo registro: manter seleção atual
        setEditingRecord(null);
        setFormData({
          content: '',
          observations: '',
          methodology: '',
          resources: '',
          number_of_classes: defaultNumberOfClasses
        });
      }
    } else {
      // Anos Finais / EJA: fluxo original (1 registro por vez)
      if (dayInfo.record) {
        setEditingRecord(dayInfo.record);
        setFormCourseId(dayInfo.record.course_id || '');
        setFormData({
          content: dayInfo.record.content || '',
          observations: dayInfo.record.observations || '',
          methodology: dayInfo.record.methodology || '',
          resources: dayInfo.record.resources || '',
          number_of_classes: dayInfo.record.number_of_classes || 1
        });
      } else {
        setEditingRecord(null);
        setFormCourseId(selectedCourse);
        
        // Anos Finais: buscar nº de aulas do Horário de Aulas
        let numClasses = defaultNumberOfClasses;
        if (isAnosFinais && selectedCourse) {
          try {
            const scheduleData = await attendanceAPI.getScheduleClassesCount(
              selectedClass, selectedCourse, dayInfo.date, academicYear
            );
            numClasses = scheduleData.has_schedule ? scheduleData.count : 1;
          } catch {
            numClasses = 1;
          }
        }
        
        setFormData({
          content: '',
          observations: '',
          methodology: '',
          resources: '',
          number_of_classes: numClasses
        });
      }
    }
    setShowForm(true);
    setHasChanges(false);
  };

  // Função para determinar o bimestre de uma data
  const getBimestreFromDate = (dateStr) => {
    if (!dateStr) return null;
    const month = new Date(dateStr).getMonth() + 1; // 1-12
    if (month <= 3) return 1;
    if (month <= 6) return 2;
    if (month <= 9) return 3;
    return 4;
  };

  // Salvar registro
  const handleSave = async () => {
    if (!formData.content.trim()) {
      showAlert('error', 'O conteúdo é obrigatório');
      return;
    }
    
    // Práticas Pedagógicas obrigatório para isDiasLevel e isAnosFinais
    if ((isDiasLevel || isAnosFinais) && !formData.methodology.trim()) {
      showAlert('error', 'Práticas Pedagógicas é obrigatório');
      return;
    }

    // Verificar seleção de curso
    if (!isMultiSelectMode && !selectedCourse) {
      showAlert('error', 'Selecione o componente curricular');
      return;
    }
    if (isMultiSelectMode && selectedCourses.length === 0) {
      showAlert('error', isInfantilLevel ? 'Selecione ao menos um campo de experiência' : 'Selecione ao menos um componente curricular');
      return;
    }
    
    // Verificar se o bimestre está bloqueado
    const bimestre = getBimestreFromDate(selectedDate);
    if (bimestre && !canEditBimestre(bimestre)) {
      const info = getBimestreInfo(bimestre);
      showAlert('error', `O ${bimestre}º Bimestre está bloqueado para edição. Data limite: ${info?.dataLimite || 'N/A'}`);
      return;
    }
    
    try {
      setSaving(true);
      
      if (isMultiSelectMode) {
        // Ed. Infantil / Anos Iniciais: sincronizar registros com a seleção de cursos
        const dayRecords = records.filter(r => r.date === selectedDate);
        const existingCourseIds = dayRecords.map(r => r.course_id);
        
        // Cursos a CRIAR (selecionados mas sem registro)
        const toCreate = selectedCourses.filter(id => !existingCourseIds.includes(id));
        // Cursos a EXCLUIR (tinham registro mas foram desmarcados)
        const toDelete = dayRecords.filter(r => !selectedCourses.includes(r.course_id));
        // Cursos a ATUALIZAR (já existem e continuam selecionados)
        const toUpdate = dayRecords.filter(r => selectedCourses.includes(r.course_id));
        
        // Criar novos
        for (const courseId of toCreate) {
          await learningObjectsAPI.create({
            class_id: selectedClass,
            course_id: courseId,
            date: selectedDate,
            academic_year: academicYear,
            ...formData
          }).catch(() => null);
        }
        
        // Atualizar existentes
        for (const rec of toUpdate) {
          await learningObjectsAPI.update(rec.id, formData).catch(() => null);
        }
        
        // Excluir removidos
        for (const rec of toDelete) {
          await learningObjectsAPI.delete(rec.id).catch(() => null);
        }
        
        const actions = [];
        if (toCreate.length > 0) actions.push(`${toCreate.length} criado(s)`);
        if (toUpdate.length > 0) actions.push(`${toUpdate.length} atualizado(s)`);
        if (toDelete.length > 0) actions.push(`${toDelete.length} excluído(s)`);
        showAlert('success', `Registros: ${actions.join(', ')}`);
      } else if (editingRecord) {
        // Anos Finais / EJA: atualizar registro individual
        const updatePayload = { ...formData };
        if (formCourseId && formCourseId !== editingRecord.course_id) {
          updatePayload.course_id = formCourseId;
        }
        await learningObjectsAPI.update(editingRecord.id, updatePayload);
        showAlert('success', 'Registro atualizado com sucesso!');
      } else {
        // Anos Finais / EJA: criar registro individual
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
      setHasChanges(false);
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
    // Verificar se o bimestre está bloqueado
    const dateForBimestre = editingRecord?.date || selectedDate;
    const bimestre = getBimestreFromDate(dateForBimestre);
    if (bimestre && !canEditBimestre(bimestre)) {
      showAlert('error', `O ${bimestre}º Bimestre está bloqueado para edição. Não é possível excluir.`);
      return;
    }
    
    if (isMultiSelectMode && selectedDate) {
      // Ed. Infantil / Anos Iniciais: excluir TODOS os registros do dia
      const dayRecords = records.filter(r => r.date === selectedDate);
      if (dayRecords.length === 0) return;
      if (!window.confirm(`Deseja realmente excluir ${dayRecords.length} registro(s) desta data?`)) return;
      
      try {
        setSaving(true);
        for (const rec of dayRecords) {
          await learningObjectsAPI.delete(rec.id).catch(() => null);
        }
        showAlert('success', `${dayRecords.length} registro(s) excluído(s)!`);
        setShowForm(false);
        setHasChanges(false);
        loadRecords();
      } catch (error) {
        showAlert('error', 'Erro ao excluir registros');
      } finally {
        setSaving(false);
      }
    } else {
      // Anos Finais / EJA: excluir registro individual
      if (!editingRecord) return;
      if (!window.confirm('Deseja realmente excluir este registro?')) return;
      
      try {
        setSaving(true);
        await learningObjectsAPI.delete(editingRecord.id);
        showAlert('success', 'Registro excluído com sucesso!');
        setShowForm(false);
        setHasChanges(false);
        loadRecords();
      } catch (error) {
        console.error('Erro ao excluir:', error);
        showAlert('error', error.response?.data?.detail || 'Erro ao excluir registro');
      } finally {
        setSaving(false);
      }
    }
  };

  // Estatísticas do mês
  const monthStats = useMemo(() => {
    const totalRecords = records.length;
    const totalClasses = records.reduce((sum, r) => sum + (r.number_of_classes || 1), 0);
    return { totalRecords, totalClasses };
  }, [records]);

  // Gerar PDF de objetos de conhecimento
  const handleGeneratePdf = async () => {
    if (!selectedClass) {
      showAlert('error', 'Selecione uma turma antes de gerar o PDF.');
      return;
    }
    if (isAnosFinaisOrEja && !pdfCourseId) {
      showAlert('error', 'Para EJA e Anos Finais, selecione um componente curricular.');
      return;
    }
    setGeneratingPdf(true);
    try {
      const API = process.env.REACT_APP_BACKEND_URL;
      const token = localStorage.getItem('accessToken');
      const params = new URLSearchParams({
        bimestre: pdfBimestre,
        academic_year: academicYear
      });
      if (pdfCourseId) {
        params.append('course_id', pdfCourseId);
      }
      const response = await fetch(
        `${API}/api/learning-objects/pdf/bimestre/${selectedClass}?${params}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Erro ao gerar PDF');
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      setShowPdfModal(false);
      showAlert('success', 'PDF gerado com sucesso!');
    } catch (err) {
      showAlert('error', 'Erro ao gerar PDF: ' + err.message);
    } finally {
      setGeneratingPdf(false);
    }
  };

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

        {/* Alertas de Bimestre Bloqueado e Prazo Próximo */}
        <BimestreBlockedAlert blockedBimestres={blockedBimestres} />
        <BimestreDeadlineAlert editStatus={editStatus} />

        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => guardedNavigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
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
          {selectedClass && (
            <Button
              onClick={() => setShowPdfModal(true)}
              variant="outline"
              className="flex items-center gap-2"
              data-testid="btn-gerar-pdf-lo"
            >
              <FileText size={16} />
              Gerar PDF
            </Button>
          )}
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
                  disabled={!selectedSchool}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 disabled:bg-gray-100"
                >
                  <option value="">Selecione a turma</option>
                  {filteredClasses.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              {/* Componente Curricular / Campo de experiência */}
              <div className="relative" ref={coursesDropdownRef}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {isInfantilLevel ? 'Campo de experiência *' : 'Componente Curricular *'}
                </label>
                {isMultiSelectMode ? (
                  <>
                    <button
                      type="button"
                      onClick={() => selectedClass && setShowCoursesDropdown(!showCoursesDropdown)}
                      disabled={!selectedClass}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 text-left bg-white flex items-center justify-between disabled:bg-gray-100 disabled:cursor-not-allowed"
                      data-testid="campo-experiencia-toggle"
                    >
                      <span className={selectedCourses.length === 0 ? 'text-gray-400' : 'text-gray-900 truncate'}>
                        {selectedCourses.length === 0
                          ? 'Selecione'
                          : selectedCourses.length === courses.length
                            ? 'Todos'
                            : `${selectedCourses.length} selecionado(s)`}
                      </span>
                      <svg className={`w-4 h-4 transition-transform ${showCoursesDropdown ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                    </button>
                    {showCoursesDropdown && (
                      <div className="absolute z-50 mt-1 w-full bg-white border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                        <label className="flex items-center gap-2 px-3 py-2 hover:bg-purple-50 cursor-pointer border-b font-medium">
                          <input
                            type="checkbox"
                            checked={selectedCourses.length === courses.length && courses.length > 0}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedCourses(courses.map(c => c.id));
                              } else {
                                setSelectedCourses([]);
                              }
                            }}
                            className="rounded text-purple-600"
                          />
                          Todos
                        </label>
                        {courses.map(c => (
                          <label key={c.id} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedCourses.includes(c.id)}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setSelectedCourses(prev => [...prev, c.id]);
                                } else {
                                  setSelectedCourses(prev => prev.filter(id => id !== c.id));
                                }
                              }}
                              className="rounded text-purple-600"
                            />
                            {c.name}
                          </label>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <select
                    value={selectedCourse}
                    onChange={(e) => setSelectedCourse(e.target.value)}
                    disabled={!selectedClass}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 disabled:bg-gray-100"
                  >
                    <option value="">Selecione o componente</option>
                    {courses.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                )}
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
        {!selectedClass || !hasValidSelection ? (
          <Card>
            <CardContent className="p-8 text-center text-gray-500">
              <BookOpen size={48} className="mx-auto mb-2 text-gray-300" />
              <p>{!selectedClass 
                ? 'Selecione a turma para visualizar o calendário de registros.'
                : `Selecione ${isInfantilLevel ? 'o campo de experiência' : 'o componente curricular'} para visualizar o calendário de registros.`
              }</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            {/* Calendário - Reduzido para 1/4 */}
            <div className="lg:col-span-1">
              <Card>
                <CardHeader className="pb-1 p-2">
                  <div className="flex items-center justify-between">
                    <Button variant="ghost" size="sm" onClick={previousMonth} className="h-6 w-6 p-0">
                      <ChevronLeft size={14} />
                    </Button>
                    <CardTitle className="text-xs font-medium">
                      {MONTHS[currentMonth]} {academicYear}
                    </CardTitle>
                    <Button variant="ghost" size="sm" onClick={nextMonth} className="h-6 w-6 p-0">
                      <ChevronRight size={14} />
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="p-2 pt-0">
                  {/* Cabeçalho dos dias da semana */}
                  <div className="grid grid-cols-7 gap-0.5 mb-1">
                    {WEEKDAYS.map(day => (
                      <div key={day} className="text-center text-[8px] font-medium text-gray-500 py-0.5">
                        {day.charAt(0)}
                      </div>
                    ))}
                  </div>
                  
                  {/* Dias do mês */}
                  <div className="grid grid-cols-7 gap-0.5">
                    {calendarDays.map((dayInfo, index) => (
                      <div
                        key={index}
                        onClick={() => canEdit && dayInfo.date && !dayInfo.isBlocked && handleDayClick(dayInfo)}
                        className={`
                          aspect-square p-0.5 rounded text-center relative flex items-center justify-center
                          ${!dayInfo.date ? 'bg-transparent' : ''}
                          ${dayInfo.isBlocked && dayInfo.date ? 'bg-gray-200 opacity-50 cursor-not-allowed' : ''}
                          ${!dayInfo.isBlocked && dayInfo.isWeekend && dayInfo.date ? 'bg-gray-50' : ''}
                          ${dayInfo.isToday && !dayInfo.isBlocked ? 'ring-1 ring-purple-500' : ''}
                          ${dayInfo.date && canEdit && !dayInfo.isBlocked ? 'cursor-pointer hover:bg-purple-50' : ''}
                          ${dayInfo.hasRecord && !dayInfo.isBlocked ? 'bg-green-100 hover:bg-green-200' : ''}
                          ${selectedDate === dayInfo.date ? 'ring-1 ring-purple-600 bg-purple-100' : ''}
                        `}
                        title={dayInfo.isBlocked ? (dayInfo.isHoliday ? 'Feriado / Recesso' : 'Dia não letivo') : ''}
                      >
                        {dayInfo.date && (
                          <span className={`text-[9px] ${dayInfo.isBlocked ? 'text-gray-400 line-through' : dayInfo.isWeekend ? 'text-gray-400' : 'text-gray-700'} ${dayInfo.hasRecord ? 'font-medium' : ''}`}>
                            {dayInfo.day}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Legenda compacta */}
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[8px] text-gray-500">
                    <div className="flex items-center gap-0.5">
                      <div className="w-2 h-2 bg-green-100 rounded"></div>
                      <span>Registro</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <div className="w-2 h-2 ring-1 ring-purple-500 rounded"></div>
                      <span>Hoje</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              {/* Estatísticas compactas */}
              <Card className="mt-2">
                <CardContent className="p-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-purple-50 p-2 rounded text-center">
                      <p className="text-lg font-bold text-purple-700">{monthStats.totalRecords}</p>
                      <p className="text-[8px] text-purple-600">Registros</p>
                    </div>
                    {!isDiasLevel && (
                    <div className="bg-blue-50 p-2 rounded text-center">
                      <p className="text-lg font-bold text-blue-700">{monthStats.totalClasses}</p>
                      <p className="text-[8px] text-blue-600">Aulas</p>
                    </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Painel de Formulário/Detalhes - Expandido */}
            <div className="lg:col-span-3 space-y-4">
              {/* Formulário */}
              {showForm && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center justify-between">
                      <span>{isMultiSelectMode && editingRecord ? 'Editar Registro' : isMultiSelectMode ? 'Novo Registro' : editingRecord ? 'Editar Registro' : 'Novo Registro'}</span>
                      <span className="text-purple-600 font-normal">
                        {new Date(selectedDate + 'T12:00:00').toLocaleDateString('pt-BR')}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Multi-select: exibir cursos selecionados para o dia */}
                    {isMultiSelectMode && (
                      <div className="text-sm bg-purple-50 px-3 py-2 rounded-lg" data-testid="form-campos-experiencia-display">
                        <span className="font-medium text-purple-700">{isInfantilLevel ? 'Campos de Experiência' : 'Componentes Curriculares'}: </span>
                        <span className="text-purple-600">
                          {selectedCourses.length > 0
                            ? courses.filter(c => selectedCourses.includes(c.id)).map(c => c.name).join(' • ')
                            : 'Nenhum selecionado'}
                        </span>
                      </div>
                    )}

                    {/* Conteúdo */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Conteúdo/Objeto de Conhecimento *
                      </label>
                      <textarea
                        value={formData.content}
                        onChange={(e) => { setFormData({ ...formData, content: e.target.value }); setHasChanges(true); }}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 h-24 resize-none"
                        placeholder="Descreva o conteúdo ministrado..."
                      />
                    </div>

                    {/* Número de aulas — oculto para Ed. Infantil e Anos Iniciais */}
                    {!isDiasLevel && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Número de Aulas
                      </label>
                      <select
                        value={formData.number_of_classes}
                        onChange={(e) => { setFormData({ ...formData, number_of_classes: parseInt(e.target.value) || 0 }); setHasChanges(true); }}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                        data-testid="number-of-classes-select"
                      >
                        {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
                          <option key={n} value={n}>{n}</option>
                        ))}
                      </select>
                      {formData.number_of_classes === 0 && (
                        <p className="mt-1 text-sm font-bold text-orange-500">
                          Conforme o horário de aulas, não há aulas previstas para esta data.
                        </p>
                      )}
                    </div>
                    )}

                    {/* Práticas Pedagógicas (todos os níveis) */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Práticas Pedagógicas {(isDiasLevel || isAnosFinais) ? '*' : ''}
                      </label>
                      <input
                        type="text"
                        value={formData.methodology}
                        onChange={(e) => { setFormData({ ...formData, methodology: e.target.value }); setHasChanges(true); }}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                        placeholder="Ex: Aula expositiva, Trabalho em grupo, Roda de conversa..."
                      />
                    </div>

                    {/* Recursos — oculto para Ed. Infantil, Anos Iniciais e Anos Finais */}
                    {!isDiasLevel && !isAnosFinais && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Recursos Utilizados
                      </label>
                      <input
                        type="text"
                        value={formData.resources}
                        onChange={(e) => { setFormData({ ...formData, resources: e.target.value }); setHasChanges(true); }}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500"
                        placeholder="Ex: Livro didático, Datashow..."
                      />
                    </div>
                    )}

                    {/* Observações — oculto para Ed. Infantil, Anos Iniciais e Anos Finais */}
                    {!isDiasLevel && !isAnosFinais && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Observações
                      </label>
                      <textarea
                        value={formData.observations}
                        onChange={(e) => { setFormData({ ...formData, observations: e.target.value }); setHasChanges(true); }}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 h-16 resize-none"
                        placeholder="Observações adicionais..."
                      />
                    </div>
                    )}

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
                      {(editingRecord || (isMultiSelectMode && records.some(r => r.date === selectedDate))) && (
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
                        onClick={() => { setShowForm(false); setHasChanges(false); }}
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
                            <div className="flex items-center gap-2">
                              {isMultiSelectMode && selectedCourses.length > 1 && (
                                <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
                                  {record.course_name || courses.find(c => c.id === record.course_id)?.name || ''}
                                </span>
                              )}
                              {!isDiasLevel && (
                              <span className="text-xs text-gray-500">
                                {record.number_of_classes} aula(s)
                              </span>
                              )}
                            </div>
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

      {/* Modal de seleção de bimestre para PDF */}
      {showPdfModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowPdfModal(false)}>
          <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-lg font-semibold mb-4">Gerar PDF - Objetos de Conhecimento</h3>
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">Selecione o Bimestre</label>
              <div className="grid grid-cols-4 gap-2">
                {[1, 2, 3, 4].map(b => (
                  <button
                    key={b}
                    onClick={() => setPdfBimestre(b)}
                    className={`py-2 px-3 rounded-lg border text-sm font-medium transition-colors ${
                      pdfBimestre === b
                        ? 'bg-purple-600 text-white border-purple-600'
                        : 'bg-white text-gray-700 border-gray-300 hover:border-purple-400'
                    }`}
                    data-testid={`pdf-bimestre-${b}`}
                  >
                    {b}º Bim
                  </button>
                ))}
              </div>
            </div>
            {isAnosFinaisOrEja && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Componente Curricular <span className="text-red-500">*</span>
                </label>
                <select
                  value={pdfCourseId}
                  onChange={(e) => setPdfCourseId(e.target.value)}
                  className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-purple-500 ${!pdfCourseId ? 'border-orange-300' : 'border-gray-300'}`}
                  data-testid="pdf-course-select"
                >
                  <option value="">Selecione o componente</option>
                  {courses.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500">
                  Para EJA e Anos Finais, cada componente gera um PDF separado.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowPdfModal(false)}>Cancelar</Button>
              <Button
                onClick={handleGeneratePdf}
                disabled={generatingPdf || (isAnosFinaisOrEja && !pdfCourseId)}
                className="bg-purple-600 text-white hover:bg-purple-700"
                data-testid="btn-confirmar-pdf-lo"
              >
                {generatingPdf ? 'Gerando...' : 'Gerar PDF'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
};

export default LearningObjects;
