import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import { Layout } from '@/components/Layout';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import { usePermissions } from '@/hooks/usePermissions';
import { inferEducationLevel, EDUCATION_LEVEL_LABELS, getAttendanceType } from '@/utils/educationLevel';
import { 
  ClipboardCheck, 
  Calendar,
  Users,
  Search,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  ChevronLeft,
  ChevronRight,
  Settings,
  FileText,
  Home,
  Trash2,
  Lock,
  CloudOff,
  Stethoscope,
  FileDown,
  Info
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { Modal } from '@/components/Modal';
import { schoolsAPI, classesAPI, coursesAPI, attendanceAPI, professorAPI, calendarAPI, medicalCertificatesAPI, teacherAssignmentAPI, vaccinesAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useBimestreEditStatus } from '@/hooks/useBimestreEditStatus';
import { BimestreBlockedAlert, BimestreDeadlineAlert } from '@/components/BimestreStatus';
import { OfflineManagementPanel } from '@/components/OfflineManagementPanel';
import { PainelSincronizacao } from '@/components/PainelSincronizacao';
import { extractErrorMessage } from '@/utils/errorHandler';
import { useOffline } from '@/contexts/OfflineContext';
import { db, SYNC_STATUS, addToSyncQueue, SYNC_OPERATIONS } from '@/db/database';
import { AttendanceContext } from '@/contexts/AttendanceContext';
const LancamentoTab = lazy(() => import('@/components/attendance/LancamentoTab').then(m => ({ default: m.LancamentoTab })));
const RegistrosTab = lazy(() => import('@/components/attendance/RegistrosTab').then(m => ({ default: m.RegistrosTab })));
const InformacoesTab = lazy(() => import('@/components/attendance/InformacoesTab').then(m => ({ default: m.InformacoesTab })));
const RelatoriosTab = lazy(() => import('@/components/attendance/RelatoriosTab').then(m => ({ default: m.RelatoriosTab })));
const AlertasTab = lazy(() => import('@/components/attendance/AlertasTab').then(m => ({ default: m.AlertasTab })));
// Formata data para exibição
const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}/${year}`;
};

// Dias da semana
const WEEKDAYS = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];

export const Attendance = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { isOnline } = useOffline();
  
  // Estados principais
  const [activeTab, setActiveTab] = useState('lancamento'); // lancamento, relatorios, alertas, config
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  
  // Filtros
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedCourse, setSelectedCourse] = useState('');
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [selectedPeriod, setSelectedPeriod] = useState('regular');
  const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
  
  // Estado para bimestre selecionado no relatório PDF
  const [selectedBimestre, setSelectedBimestre] = useState(1);
  const [reportCourseId, setReportCourseId] = useState('');
  
  // Anos disponíveis para seleção
  const currentYear = new Date().getFullYear();
  const availableYears = [currentYear - 1, currentYear, currentYear + 1];
  
  // Hook para verificar status de edição dos bimestres
  const { 
    editStatus, 
    loading: loadingEditStatus, 
    blockedBimestres 
  } = useBimestreEditStatus(academicYear);
  
  // Dados do professor (quando logado como professor)
  const [professorTurmas, setProfessorTurmas] = useState([]);
  const { isProfessor, canEditAttendance: canEdit, canConfigSettings } = usePermissions();
  
  // Dados de frequência
  const [attendanceData, setAttendanceData] = useState(null);
  const [dateCheck, setDateCheck] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  
  // Status vacinal dos alunos (para indicador visual)
  const [vaccineStatuses, setVaccineStatuses] = useState({});
  
  // Buscar status vacinal quando attendanceData muda
  useEffect(() => {
    if (!attendanceData?.students?.length) return;
    const ids = attendanceData.students.map(s => s.id).filter(Boolean);
    if (!ids.length) return;
    vaccinesAPI.getStatusBatch(ids, academicYear)
      .then(data => setVaccineStatuses(prev => ({ ...prev, ...data })))
      .catch(() => {});
  }, [attendanceData?.students?.length, academicYear]);

  // Alerta ao sair com alterações não salvas
  const { guardedNavigate } = useUnsavedChangesWarning(hasChanges, 'Há alterações de frequência não salvas. Deseja sair sem salvar?');
  
  // Configurações
  const [settings, setSettings] = useState({ allow_future_dates: false });
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  
  // Exclusão
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  
  // Atestados médicos
  const [medicalCertificates, setMedicalCertificates] = useState({});
  
  // Relatórios
  const [classReport, setClassReport] = useState(null);
  const [alertsData, setAlertsData] = useState(null);

  // Registros (calendário anual)
  const [registrosBlockedDates, setRegistrosBlockedDates] = useState(new Set());
  const [registrosSabLetivos, setRegistrosSabLetivos] = useState(new Set());
  const [registrosAttDates, setRegistrosAttDates] = useState(new Set());
  const [registrosLoading, setRegistrosLoading] = useState(false);
  const [registrosBimSummary, setRegistrosBimSummary] = useState([]);

  // Aba Informações
  const [infoStudents, setInfoStudents] = useState([]);
  const [infoLoading, setInfoLoading] = useState(false);
  const [infoSchool, setInfoSchool] = useState('');
  const [infoClass, setInfoClass] = useState('');
  const [infoClasses, setInfoClasses] = useState([]);

  // Detectar se turma é Anos Finais ou EJA (requer componente no relatório)
  const selectedClassInfo = classes.find(c => c.id === selectedClass) || professorTurmas.find(t => t.id === selectedClass);
  const isAnosFinaisOrEja = (() => {
    if (!selectedClassInfo) return false;
    const level = inferEducationLevel(selectedClassInfo);
    if (['eja_final', 'eja_inicial', 'eja'].includes(level)) return true;
    if (level === 'fundamental_anos_finais') return true;
    const grade = selectedClassInfo.grade_level || '';
    if (['6', '7', '8', '9'].includes(grade)) return true;
    return false;
  })();
  
  // Número de aulas e status por aula (anos finais)
  const [numberOfAulas, setNumberOfAulas] = useState(1);
  const [aulaStatuses, setAulaStatuses] = useState({}); // { studentId: { 1: 'P', 2: 'F', ... } }
  
  // Resumo de frequência (previstos/registrados/restantes)
  const [attendanceSummary, setAttendanceSummary] = useState(null);
  
  // Função para verificar se um aluno está bloqueado para edição pelo professor
  // Condições de bloqueio:
  // 2. Aluno "transferido" - bloqueado para professor
  // 3. Aluno "remanejado" para outra turma - bloqueado na turma de origem
  // 4. Aluno "progredido" para outra turma - bloqueado na turma de origem
  // 5. Aluno "falecido" - bloqueado para professor
  const isStudentBlockedForProfessor = useCallback((student) => {
    if (!isProfessor) return false; // Apenas bloqueia para professor
    
    const studentStatus = (student.student_status || '').toLowerCase();
    
    // Status que bloqueiam totalmente
    if (['transferred', 'transferido', 'deceased', 'falecido'].includes(studentStatus)) {
      return true;
    }
    
    // Verifica se foi remanejado/progredido para outra turma
    if (student.is_transferred_from_class) {
      return true;
    }
    
    return false;
  }, [isProfessor]);
  
  // Retorna mensagem de bloqueio
  const getBlockedMessage = useCallback((student) => {
    const studentStatus = (student.student_status || '').toLowerCase();
    
    if (['transferred', 'transferido'].includes(studentStatus)) {
      return 'Aluno transferido - edição bloqueada';
    }
    if (['deceased', 'falecido'].includes(studentStatus)) {
      return 'Aluno falecido - edição bloqueada';
    }
    if (student.is_transferred_from_class) {
      return 'Aluno remanejado/progredido - dados da turma de origem bloqueados';
    }
    return '';
  }, []);
  
  // Carrega escolas
  useEffect(() => {
    loadSchools();
    loadSettings();
  }, [isProfessor, academicYear]);
  
  // Recarrega turmas quando ano letivo muda
  useEffect(() => {
    if (selectedSchool) {
      loadClasses();
    }
    // Limpar seleções dependentes quando o ano muda
    setSelectedClass('');
    setSelectedCourse('');
    setAttendanceData(null);
  }, [academicYear]);
  
  // Carrega turmas quando escola muda
  useEffect(() => {
    if (selectedSchool) {
      loadClasses();
    } else {
      setClasses([]);
      setSelectedClass('');
    }
  }, [selectedSchool]);
  
  // Carrega componentes quando turma muda
  useEffect(() => {
    if (selectedClass) {
      loadCourses();
    } else {
      setCourses([]);
      setSelectedCourse('');
    }
  }, [selectedClass]);
  
  // Verifica data quando muda
  useEffect(() => {
    if (selectedDate) {
      checkDate();
      // Limpa atestados médicos quando a data muda
      setMedicalCertificates({});
    }
  }, [selectedDate]);
  
  // Carrega atestados médicos quando attendanceData muda (após carregar frequência)
  useEffect(() => {
    if (attendanceData?.students?.length > 0 && isOnline) {
      loadMedicalCertificates();
    }
  }, [attendanceData?.students?.length, selectedDate]);
  
  const loadSchools = async () => {
    try {
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
        const data = await schoolsAPI.getAll();
        setSchools(data);
      }
    } catch (error) {
      console.error('Erro ao carregar escolas:', error);
    }
  };
  
  const loadClasses = async () => {
    try {
      if (isProfessor) {
        // Para professor, filtra suas turmas pela escola selecionada e ano letivo
        const filtered = professorTurmas.filter(t => 
          t.school_id === selectedSchool && 
          t.academic_year === academicYear &&
          !(t.atendimento_programa || '').toLowerCase().includes('aee')
        );
        setClasses(filtered);
      } else {
        const data = await classesAPI.getAll();
        const filtered = data.filter(c => 
          c.school_id === selectedSchool && 
          c.academic_year === academicYear &&
          !(c.atendimento_programa || '').toLowerCase().includes('aee')
        );
        setClasses(filtered);
      }
    } catch (error) {
      console.error('Erro ao carregar turmas:', error);
    }
  };
  
  const loadCourses = async () => {
    try {
      if (isProfessor) {
        // Para professor, usa os componentes da turma selecionada
        const turma = professorTurmas.find(t => t.id === selectedClass);
        if (turma && turma.componentes) {
          setCourses(turma.componentes);
        } else {
          setCourses([]);
        }
      } else {
        // Para não-professores, buscar componentes via teacher_assignments da turma
        const assignments = await teacherAssignmentAPI.list({
          class_id: selectedClass,
          academic_year: academicYear
        });

        if (assignments && assignments.length > 0) {
          const courseIds = [...new Set(assignments.map(a => a.course_id).filter(Boolean))];
          const allCourses = await coursesAPI.getAll();
          const filtered = allCourses.filter(c => courseIds.includes(c.id));
          setCourses(filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
        } else {
          // Fallback: filtrar por nível de ensino
          const data = await coursesAPI.getAll();
          const turma = classes.find(c => c.id === selectedClass);
          if (turma) {
            const filtered = data.filter(c => 
              !c.nivel_ensino || c.nivel_ensino === turma.education_level
            );
            setCourses(filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '')));
          }
        }
      }
    } catch (error) {
      console.error('Erro ao carregar componentes:', error);
    }
  };
  
  const loadSettings = async () => {
    try {
      const data = await attendanceAPI.getSettings(academicYear);
      setSettings(data);
    } catch (error) {
      console.error('Erro ao carregar configurações:', error);
    }
  };
  
  const checkDate = useCallback(async () => {
    try {
      const data = await attendanceAPI.checkDate(selectedDate);
      setDateCheck(data);
    } catch (error) {
      console.error('Erro ao verificar data:', error);
    }
  }, [selectedDate]);
  
  const showAlertMessage = useCallback((type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 4000);
  }, []);
  
  // Carrega frequência da turma (com suporte offline)
  const loadAttendance = async () => {
    if (!selectedClass || !selectedDate) return;
    
    setLoading(true);
    try {
      const turma = classes.find(c => c.id === selectedClass);
      const attendanceType = getAttendanceType(turma?.education_level, selectedPeriod);
      
      // Se é por componente, precisa ter componente selecionado
      if (attendanceType === 'by_component' && !selectedCourse) {
        showAlertMessage('error', 'Selecione o componente curricular');
        setLoading(false);
        return;
      }
      
      if (isOnline) {
        // Online: busca da API
        const data = await attendanceAPI.getByClass(
          selectedClass, 
          selectedDate,
          attendanceType === 'by_component' ? selectedCourse : null,
          selectedPeriod
        );
        
        setAttendanceData(data);
        
        // Popular aulaStatuses a partir das sessões retornadas pela API
        if (data?.sessions && data.sessions.length > 0) {
          const maxAula = Math.max(...data.sessions.map(s => s.aula_numero));
          setNumberOfAulas(maxAula);
          // Montar mapa: { studentId: { 1: 'P', 2: 'F', ... } }
          const statusMap = {};
          if (data.students) {
            data.students.forEach(st => { statusMap[st.id] = {}; });
          }
          data.sessions.forEach(sess => {
            Object.entries(sess.records || {}).forEach(([sid, st]) => {
              if (!statusMap[sid]) statusMap[sid] = {};
              statusMap[sid][sess.aula_numero] = st;
            });
          });
          setAulaStatuses(statusMap);
        } else {
          setAulaStatuses({});
          // Anos Finais: buscar nº de aulas do Horário de Aulas para pré-definir
          if (isMultiAula && selectedCourse) {
            try {
              const scheduleData = await attendanceAPI.getScheduleClassesCount(
                selectedClass, selectedCourse, selectedDate, academicYear
              );
              if (scheduleData.has_schedule) {
                setNumberOfAulas(scheduleData.count);
              } else {
                setNumberOfAulas(1);
              }
            } catch {
              setNumberOfAulas(1);
            }
          }
        }
        // Atualiza cache local
        if (data) {
          const existingLocal = await db.attendance
            .where('[class_id+date]')
            .equals([selectedClass, selectedDate])
            .first();
          
          const dataToCache = {
            ...data,
            class_id: selectedClass,
            date: selectedDate,
            syncStatus: SYNC_STATUS.SYNCED
          };
          
          if (existingLocal) {
            await db.attendance.update(existingLocal.localId, dataToCache);
          } else {
            await db.attendance.add(dataToCache);
          }
        }
      } else {
        // Offline: busca do cache local
        const localData = await db.attendance
          .where('[class_id+date]')
          .equals([selectedClass, selectedDate])
          .first();
        
        if (localData) {
          setAttendanceData(localData);
          showAlertMessage('info', 'Dados carregados do cache local (modo offline)');
        } else {
          // Tenta montar dados básicos com alunos do cache
          const localStudents = await db.students
            .where('class_id').equals(selectedClass)
            .toArray();
          
          if (localStudents.length > 0) {
            setAttendanceData({
              class_id: selectedClass,
              class_name: turma?.name || 'Turma',
              date: selectedDate,
              students: localStudents.map(s => ({
                id: s.id,
                full_name: s.full_name,
                enrollment_number: s.enrollment_number,
                status: null
              }))
            });
            showAlertMessage('info', 'Lista de alunos carregada do cache. Nenhuma frequência registrada para esta data.');
          } else {
            showAlertMessage('error', 'Nenhum dado disponível offline. Sincronize quando houver conexão.');
          }
        }
      }
      
      setHasChanges(false);
      
      // Carrega atestados médicos para os alunos da turma na data selecionada
      if (isOnline && attendanceData?.students?.length > 0) {
        await loadMedicalCertificates();
      }
    } catch (error) {
      console.error('Erro ao carregar frequência:', error);
      showAlertMessage('error', 'Erro ao carregar frequência');
    } finally {
      setLoading(false);
    }
  };
  
  // Carrega atestados médicos para os alunos da turma na data selecionada
  const loadMedicalCertificates = useCallback(async () => {
    try {
      if (!attendanceData?.students?.length) return;
      
      const studentIds = attendanceData.students.map(s => s.id);
      const result = await medicalCertificatesAPI.checkBulk(selectedDate, studentIds);
      setMedicalCertificates(result.certificates || {});
    } catch (error) {
      console.error('Erro ao carregar atestados médicos:', error);
      // Não bloqueia a frequência se houver erro ao carregar atestados
    }
  }, [attendanceData, selectedDate]);
  
  // Verifica se um aluno tem atestado médico na data selecionada
  const hasActiveCertificate = useCallback((studentId) => {
    return medicalCertificates[studentId] !== undefined;
  }, [medicalCertificates]);
  
  // Obtém informações do atestado médico de um aluno
  const getCertificateInfo = useCallback((studentId) => {
    return medicalCertificates[studentId];
  }, [medicalCertificates]);
  
  // Atualiza status de um aluno (aulaNum para multi-aula, null para diário)
  const updateStudentStatus = (studentId, status, aulaNum = null) => {
    // Bloqueia se aluno tem atestado médico
    if (hasActiveCertificate(studentId)) {
      showAlertMessage('error', 'Este aluno possui atestado médico para esta data. O status não pode ser alterado.');
      return;
    }
    
    if (aulaNum !== null) {
      // Multi-aula: atualizar aulaStatuses (já functional)
      setAulaStatuses(prev => ({
        ...prev,
        [studentId]: { ...(prev[studentId] || {}), [aulaNum]: status }
      }));
    } else {
      // Diário: atualizar student.status com functional setState (evita stale em cliques rápidos)
      setAttendanceData(prev => {
        if (!prev) return prev;
        const newStudents = prev.students.map(s => {
          if (s.id !== studentId) return s;
          return { ...s, status };
        });
        return { ...prev, students: newStudents };
      });
    }
    setHasChanges(true);
  };
  
  // Marca todos com o mesmo status (exceto alunos com atestado)
  const markAll = (status) => {
    if (isMultiAula) {
      // Multi-aula: marcar todas as aulas de todos os alunos (functional setState)
      setAttendanceData(currentData => {
        if (!currentData) return currentData;
        setAulaStatuses(prevStatuses => {
          const newStatuses = { ...prevStatuses };
          currentData.students.forEach(s => {
            if (hasActiveCertificate(s.id)) return;
            if (!newStatuses[s.id]) newStatuses[s.id] = {};
            for (let a = 1; a <= numberOfAulas; a++) {
              newStatuses[s.id][a] = status;
            }
          });
          return newStatuses;
        });
        return currentData; // não muda attendanceData no multi-aula
      });
    } else {
      // Diário: usa functional setState para garantir consistência
      setAttendanceData(prev => {
        if (!prev) return prev;
        const newStudents = prev.students.map(s => {
          if (hasActiveCertificate(s.id)) return s;
          return { ...s, status };
        });
        return { ...prev, students: newStudents };
      });
    }
    setHasChanges(true);
  };
  
  // Salva frequência (com suporte offline)
  const saveAttendance = async () => {
    if (!attendanceData || !dateCheck?.can_record) return;
    
    setSaving(true);
    try {
      const turma = classes.find(c => c.id === selectedClass);
      const attendanceType = getAttendanceType(turma?.education_level, selectedPeriod);
      
      if (isMultiAula) {
        // Multi-aula: salvar cada aula separadamente
        let savedCount = 0;
        for (let aulaNum = 1; aulaNum <= numberOfAulas; aulaNum++) {
          const records = attendanceData.students
            .filter(s => aulaStatuses[s.id]?.[aulaNum])
            .map(s => ({
              student_id: s.id,
              status: aulaStatuses[s.id][aulaNum],
              ...(s.is_dependency && s.dependency_id ? { dependency_id: s.dependency_id } : {}),
            }));
          
          if (records.length === 0) continue;
          
          const payload = {
            class_id: selectedClass,
            date: selectedDate,
            academic_year: academicYear,
            attendance_type: attendanceType,
            course_id: attendanceType === 'by_component' ? selectedCourse : null,
            period: selectedPeriod,
            number_of_classes: 1,
            aula_numero: aulaNum,
            records
          };
          
          if (isOnline) {
            await attendanceAPI.save(payload);
            savedCount++;
          }
        }
        
        if (savedCount === 0) {
          showAlertMessage('error', 'Registre a frequência de pelo menos um aluno em pelo menos uma aula');
          setSaving(false);
          return;
        }
        
        showAlertMessage('success', `Frequência salva com sucesso! (${savedCount} aula${savedCount > 1 ? 's' : ''})`);
        // Atualizar resumo
        try {
          const summary = await attendanceAPI.getAttendanceSummary(selectedClass, academicYear, selectedCourse);
          setAttendanceSummary(summary);
        } catch {}
      } else {
        // Diário: salvar uma vez
        const records = attendanceData.students
          .filter(s => s.status)
          .map(s => ({
            student_id: s.id,
            status: s.status,
            ...(s.is_dependency && s.dependency_id ? { dependency_id: s.dependency_id } : {}),
          }));
        
        if (records.length === 0) {
          showAlertMessage('error', 'Registre a frequência de pelo menos um aluno');
          setSaving(false);
          return;
        }
        
        const attendancePayload = {
          class_id: selectedClass,
          date: selectedDate,
          academic_year: academicYear,
          attendance_type: attendanceType,
          course_id: attendanceType === 'by_component' ? selectedCourse : null,
          period: selectedPeriod,
          number_of_classes: 1,
          records
        };
        
        if (isOnline) {
          await attendanceAPI.save(attendancePayload);
          showAlertMessage('success', 'Frequência salva com sucesso!');
          try {
            const courseForSummary = isMultiAula ? selectedCourse : null;
            const summary = await attendanceAPI.getAttendanceSummary(selectedClass, academicYear, courseForSummary);
            setAttendanceSummary(summary);
          } catch {}
        } else {
          // Offline
          const now = new Date().toISOString();
          const dataWithMeta = {
            ...attendancePayload,
            updated_at: now,
            syncStatus: SYNC_STATUS.PENDING
          };
          
          const existingLocal = await db.attendance
            .where('[class_id+date]')
            .equals([selectedClass, selectedDate])
            .first();
          
          if (existingLocal) {
            await db.attendance.update(existingLocal.localId, dataWithMeta);
            await addToSyncQueue('attendance', SYNC_OPERATIONS.UPDATE, existingLocal.id || `temp_${Date.now()}`, dataWithMeta);
          } else {
            const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            await db.attendance.add({ ...dataWithMeta, id: tempId });
            await addToSyncQueue('attendance', SYNC_OPERATIONS.CREATE, tempId, dataWithMeta);
          }
          
          showAlertMessage('success', 'Frequência salva no aparelho ✓ — será enviada automaticamente quando a internet voltar.');
        }
      }
      
      setHasChanges(false);
      
      // Recarrega para atualizar os dados (se online)
      if (isOnline) {
        await loadAttendance();
      }
    } catch (error) {
      console.error('Erro ao salvar frequência:', error);
      showAlertMessage('error', extractErrorMessage(error, 'Erro ao salvar frequência'));
    } finally {
      setSaving(false);
    }
  };
  
  // Carrega relatório da turma
  const loadClassReport = async (courseIdOverride) => {
    if (!selectedClass) return;
    
    setLoading(true);
    try {
      const cid = courseIdOverride !== undefined ? courseIdOverride : reportCourseId;
      const data = await attendanceAPI.getClassReport(selectedClass, academicYear, cid || null, selectedBimestre);
      setClassReport(data);
    } catch (error) {
      console.error('Erro ao carregar relatório:', error);
      showAlertMessage('error', 'Erro ao carregar relatório');
    } finally {
      setLoading(false);
    }
  };
  
  // Gera PDF do relatório de frequência por bimestre
  const generateBimestrePdf = async () => {
    if (!selectedClass) {
      showAlertMessage('error', 'Selecione uma turma');
      return;
    }
    
    // Determinar course_id: usar reportCourseId se na aba relatórios, senão selectedCourse
    const courseForPdf = reportCourseId || selectedCourse;
    
    // Verificar se é EJA ou Anos Finais — componente obrigatório
    if (isAnosFinaisOrEja && !courseForPdf) {
      showAlertMessage('error', 'Para EJA e Anos Finais, selecione um componente curricular antes de gerar o PDF.');
      return;
    }
    
    setLoading(true);
    try {
      const blob = await attendanceAPI.getBimestrePdfBlob(selectedClass, selectedBimestre, academicYear, courseForPdf);

      // Criar blob e abrir em nova aba
      const pdfUrl = window.URL.createObjectURL(blob);
      window.open(pdfUrl, '_blank');

      // Limpar URL após um tempo
      setTimeout(() => window.URL.revokeObjectURL(pdfUrl), 30000);
    } catch (error) {
      console.error('Erro ao gerar PDF:', error);
      showAlertMessage('error', 'Erro ao gerar PDF de frequência');
    } finally {
      setLoading(false);
    }
  };
  
  // Carrega alertas
  const loadAlerts = async () => {
    setLoading(true);
    try {
      const data = await attendanceAPI.getAlerts(selectedSchool || null, academicYear);
      setAlertsData(data);
    } catch (error) {
      console.error('Erro ao carregar alertas:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // Salva configurações
  const saveSettings = async () => {
    try {
      await attendanceAPI.updateSettings(academicYear, settings.allow_future_dates);
      showAlertMessage('success', 'Configurações salvas!');
      setShowSettingsModal(false);
    } catch (error) {
      console.error('Erro ao salvar configurações:', error);
      showAlertMessage('error', 'Erro ao salvar configurações');
    }
  };
  
  // Excluir frequência
  const deleteAttendance = async () => {
    if (!attendanceData?.attendance_id) return;
    
    setDeleting(true);
    try {
      await attendanceAPI.delete(attendanceData.attendance_id);
      showAlertMessage('success', 'Frequência excluída com sucesso!');
      setShowDeleteModal(false);
      // Recarrega para limpar os dados
      await loadAttendance();
    } catch (error) {
      console.error('Erro ao excluir frequência:', error);
      showAlertMessage('error', extractErrorMessage(error, 'Erro ao excluir frequência'));
    } finally {
      setDeleting(false);
    }
  };
  
  // Navega data
  const navigateDate = useCallback((days) => {
    const date = new Date(selectedDate + 'T12:00:00');
    date.setDate(date.getDate() + days);
    setSelectedDate(date.toISOString().split('T')[0]);
  }, [selectedDate]);
  
  // Turma selecionada
  const selectedClassData = classes.find(c => c.id === selectedClass);
  const attendanceType = selectedClassData 
    ? getAttendanceType(inferEducationLevel(selectedClassData), selectedPeriod)
    : 'daily';
  
  // Turmas de anos finais/EJA final permitem múltiplas aulas por lançamento
  const isMultiAula = selectedClassData && 
    ['fundamental_anos_finais', 'eja_final'].includes(inferEducationLevel(selectedClassData));

  // Carregar resumo de frequência quando turma/componente muda
  useEffect(() => {
    if (!selectedClass) {
      setAttendanceSummary(null);
      return;
    }
    const fetchSummary = async () => {
      try {
        const courseForSummary = isMultiAula ? selectedCourse : null;
        const data = await attendanceAPI.getAttendanceSummary(selectedClass, academicYear, courseForSummary);
        setAttendanceSummary(data);
      } catch {
        setAttendanceSummary(null);
      }
    };
    fetchSummary();
  }, [selectedClass, selectedCourse, academicYear, isMultiAula]);

  // Carregar dados da aba Registros (calendário anual + datas com frequência)
  const loadRegistrosData = useCallback(async () => {
    if (!selectedClass) return;
    setRegistrosLoading(true);
    try {
      // 1. Carregar eventos do calendário (feriados, sábados letivos)
      const events = await calendarAPI.getEvents({ academic_year: academicYear });
      const blocked = new Set();
      const sabLet = new Set();
      if (events && Array.isArray(events)) {
        for (const ev of events) {
          const evType = ev.event_type || '';
          const start = (ev.start_date || '')?.substring(0, 10);
          const end = (ev.end_date || start)?.substring(0, 10);
          if (evType === 'sabado_letivo' || (ev.is_school_day && start)) {
            let d = new Date(start + 'T12:00:00');
            const endD = new Date((end || start) + 'T12:00:00');
            while (d <= endD) {
              if (d.getDay() === 6) sabLet.add(d.toISOString().split('T')[0]);
              d.setDate(d.getDate() + 1);
            }
          }
          if (evType.includes('feriado') || evType === 'recesso_escolar' || ev.is_school_day === false) {
            if (start) {
              let d = new Date(start + 'T12:00:00');
              const endD = new Date((end || start) + 'T12:00:00');
              while (d <= endD) {
                blocked.add(d.toISOString().split('T')[0]);
                d.setDate(d.getDate() + 1);
              }
            }
          }
        }
      }
      setRegistrosBlockedDates(blocked);
      setRegistrosSabLetivos(sabLet);

      // 2. Carregar datas com frequência registrada
      const turma = classes.find(c => c.id === selectedClass) || professorTurmas.find(t => t.id === selectedClass);
      const attendanceType = turma ? getAttendanceType(turma.education_level, selectedPeriod) : 'daily';
      const courseId = attendanceType === 'by_component' ? selectedCourse : null;

      try {
        const data = await attendanceAPI.getDatesWithRecords(selectedClass, academicYear, courseId);
        setRegistrosAttDates(new Set(data.dates || []));
      } catch {
        setRegistrosAttDates(new Set());
      }

      // 3. Carregar resumo por bimestre
      try {
        const data = await attendanceAPI.getBimestreSummary(selectedClass, academicYear, courseId);
        setRegistrosBimSummary(data);
      } catch {
        setRegistrosBimSummary([]);
      }
    } catch {
      // fallback
    } finally {
      setRegistrosLoading(false);
    }
  }, [selectedClass, selectedCourse, selectedPeriod, academicYear, classes, professorTurmas]);

  useEffect(() => {
    if (activeTab === 'registros' && selectedClass) {
      loadRegistrosData();
    }
  }, [activeTab, selectedClass, selectedCourse, academicYear, loadRegistrosData]);

  // === Aba Informações ===
  useEffect(() => {
    if (infoSchool) {
      const fetchInfoClasses = async () => {
        try {
          const data = await classesAPI.getAll();
          const filtered = data.filter(c => c.school_id === infoSchool && c.academic_year === academicYear);
          const sorted = [...filtered].sort((a, b) => {
            const aNum = parseInt(a.name) || Infinity;
            const bNum = parseInt(b.name) || Infinity;
            return aNum === bNum ? (a.name || '').localeCompare(b.name || '') : aNum - bNum;
          });
          setInfoClasses(sorted);
        } catch (e) {
          console.error('Erro ao carregar turmas da aba Informações:', e);
          setInfoClasses([]);
        }
      };
      fetchInfoClasses();
      setInfoClass('');
      setInfoStudents([]);
    } else {
      setInfoClasses([]);
      setInfoClass('');
      setInfoStudents([]);
    }
  }, [infoSchool, academicYear]);

  const loadInfoStudents = useCallback(async () => {
    if (!infoClass) { setInfoStudents([]); return; }
    setInfoLoading(true);
    try {
      const data = await attendanceAPI.getClassStudentsInfo(infoClass, academicYear);
      setInfoStudents(data.students || []);
    } catch (e) {
      console.error(e);
      setInfoStudents([]);
    }
    setInfoLoading(false);
  }, [infoClass, academicYear]);

  useEffect(() => {
    if (activeTab === 'informacoes' && infoClass) loadInfoStudents();
  }, [activeTab, infoClass, loadInfoStudents]);

  const attendanceContextValue = useMemo(() => ({
    academicYear, setAcademicYear, availableYears,
    schools, selectedSchool, setSelectedSchool,
    classes, selectedClass, setSelectedClass,
    courses, selectedCourse, setSelectedCourse,
    attendanceType, attendanceSummary, selectedClassData,
    selectedDate, setSelectedDate, dateCheck, navigateDate,
    loading, saving, attendanceData, hasChanges, canEdit,
    loadAttendance, markAll, saveAttendance,
    isMultiAula, numberOfAulas, setNumberOfAulas, setHasChanges,
    aulaStatuses, updateStudentStatus,
    vaccineStatuses, hasActiveCertificate, getCertificateInfo,
    isStudentBlockedForProfessor, getBlockedMessage,
    medicalCertificates, setShowDeleteModal,
    registrosLoading, registrosBimSummary, registrosBlockedDates,
    registrosSabLetivos, registrosAttDates,
    selectedBimestre, setSelectedBimestre, isAnosFinaisOrEja,
    reportCourseId, setReportCourseId, setClassReport,
    classReport, loadClassReport, generateBimestrePdf,
    infoSchool, setInfoSchool, infoClass, setInfoClass,
    infoClasses, infoLoading, infoStudents,
    loadAlerts, alertsData,
  }), [
    academicYear, availableYears,
    schools, selectedSchool, classes, selectedClass,
    courses, selectedCourse,
    attendanceType, attendanceSummary, selectedClassData,
    selectedDate, dateCheck, navigateDate,
    loading, saving, attendanceData, hasChanges, canEdit,
    loadAttendance, markAll, saveAttendance,
    isMultiAula, numberOfAulas,
    aulaStatuses, updateStudentStatus,
    vaccineStatuses, hasActiveCertificate, getCertificateInfo,
    isStudentBlockedForProfessor, getBlockedMessage,
    medicalCertificates,
    registrosLoading, registrosBimSummary, registrosBlockedDates,
    registrosSabLetivos, registrosAttDates,
    selectedBimestre, isAnosFinaisOrEja,
    reportCourseId, classReport, loadClassReport, generateBimestrePdf,
    infoSchool, infoClass, infoClasses, infoLoading, infoStudents,
    loadAlerts, alertsData,
  ]);

  return (
    <Layout>
      <div className="space-y-4">
        {/* Alert */}
        {alert && (
          <Alert variant={alert.type === 'error' ? 'destructive' : 'default'}>
            {alert.type === 'error' ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle className="h-4 w-4" />}
            <span className="ml-2">{alert.message}</span>
          </Alert>
        )}
        
        {/* Alerta de bimestres bloqueados */}
        <BimestreBlockedAlert blockedBimestres={blockedBimestres} />
        
        {/* Alerta de prazos de edição (para bimestres ABERTOS) */}
        <BimestreDeadlineAlert editStatus={editStatus} />
        
        {/* Painel de Sincronização — visibilidade dos lançamentos (núcleo offline) */}
        <PainelSincronizacao />
        
        {/* Painel de Gerenciamento Offline */}
        <OfflineManagementPanel 
          academicYear={academicYear} 
          classId={selectedClass}
        />
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => guardedNavigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
                <ClipboardCheck className="text-blue-600" />
                Controle de Frequência
              </h1>
              <p className="text-gray-600 text-sm">Registre e acompanhe a frequência dos alunos</p>
            </div>
          </div>
          
          {canConfigSettings && (
            <Button variant="outline" onClick={() => setShowSettingsModal(true)}>
              <Settings size={18} className="mr-2" />
              Configurações
            </Button>
          )}
        </div>
        
        {/* Tabs */}
        <div className="bg-white rounded-lg shadow-sm border">
          <div className="flex border-b">
            {[
              { id: 'lancamento', label: 'Lançamento', icon: ClipboardCheck },
              { id: 'registros', label: 'Registros', icon: Calendar },
              { id: 'informacoes', label: 'Informações', icon: Info },
              { id: 'relatorios', label: 'Relatórios', icon: FileText },
              { id: 'alertas', label: 'Alertas', icon: AlertTriangle }
            ].map(tab => (
              <button
                key={tab.id}
                className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-colors
                  ${activeTab === tab.id 
                    ? 'border-blue-500 text-blue-600' 
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                onClick={() => setActiveTab(tab.id)}
              >
                <tab.icon size={18} />
                {tab.label}
              </button>
            ))}
          </div>
          
          <div className="p-4">
            <AttendanceContext.Provider value={attendanceContextValue}>
              <Suspense fallback={
                <div className="flex justify-center items-center py-16" data-testid="tab-loading">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-gray-500 text-sm">Carregando...</span>
                </div>
              }>
                {activeTab === 'lancamento' && <LancamentoTab />}
                {activeTab === 'registros' && <RegistrosTab />}
                {activeTab === 'relatorios' && <RelatoriosTab />}
                {activeTab === 'informacoes' && <InformacoesTab />}
                {activeTab === 'alertas' && <AlertasTab />}
              </Suspense>
            </AttendanceContext.Provider>
          </div>
        </div>
        
        {/* Modal de Configurações */}
        <Modal
          isOpen={showSettingsModal}
          onClose={() => setShowSettingsModal(false)}
          title="Configurações de Frequência"
        >
          <div className="space-y-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings.allow_future_dates}
                  onChange={(e) => setSettings({ ...settings, allow_future_dates: e.target.checked })}
                  className="w-5 h-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <div>
                  <div className="font-medium">Permitir lançamento em datas futuras</div>
                  <div className="text-sm text-gray-500">
                    Quando ativado, administradores e secretários podem lançar frequência em datas futuras.
                  </div>
                </div>
              </label>
            </div>
            
            <div className="flex gap-2">
              <Button onClick={saveSettings} className="flex-1">Salvar</Button>
              <Button variant="outline" onClick={() => setShowSettingsModal(false)}>Cancelar</Button>
            </div>
          </div>
        </Modal>
        
        {/* Modal de Confirmação de Exclusão */}
        <Modal
          isOpen={showDeleteModal}
          onClose={() => setShowDeleteModal(false)}
          title="Excluir Frequência"
        >
          <div className="space-y-4">
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
              <div className="flex items-start gap-3">
                <AlertTriangle className="text-red-500 mt-0.5" size={20} />
                <div>
                  <div className="font-medium text-red-800">Tem certeza que deseja excluir esta frequência?</div>
                  <div className="text-sm text-red-600 mt-1">
                    Esta ação não pode ser desfeita. Todos os registros de frequência desta data serão removidos.
                  </div>
                </div>
              </div>
            </div>
            
            {attendanceData && (
              <div className="text-sm text-gray-600">
                <p><strong>Turma:</strong> {attendanceData.class_name}</p>
                <p><strong>Data:</strong> {formatDate(attendanceData.date)}</p>
                <p><strong>Alunos:</strong> {attendanceData.students?.length || 0}</p>
              </div>
            )}
            
            <div className="flex gap-2">
              <Button 
                onClick={deleteAttendance} 
                disabled={deleting}
                className="flex-1 bg-red-600 hover:bg-red-700"
              >
                {deleting ? 'Excluindo...' : 'Sim, Excluir'}
              </Button>
              <Button variant="outline" onClick={() => setShowDeleteModal(false)}>Cancelar</Button>
            </div>
          </div>
        </Modal>
      </div>
    </Layout>
  );
};

export default Attendance;
