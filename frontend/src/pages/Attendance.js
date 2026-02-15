import { useState, useEffect, useCallback } from 'react';
import { Layout } from '@/components/Layout';
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
  FileDown
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { Modal } from '@/components/Modal';
import { schoolsAPI, classesAPI, coursesAPI, attendanceAPI, professorAPI, calendarAPI, medicalCertificatesAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useBimestreEditStatus } from '@/hooks/useBimestreEditStatus';
import { BimestreBlockedAlert, BimestreDeadlineAlert } from '@/components/BimestreStatus';
import { OfflineManagementPanel } from '@/components/OfflineManagementPanel';
import { extractErrorMessage } from '@/utils/errorHandler';
import { useOffline } from '@/contexts/OfflineContext';
import { db, SYNC_STATUS, addToSyncQueue, SYNC_OPERATIONS } from '@/db/database';

// Labels para níveis de ensino
const EDUCATION_LEVEL_LABELS = {
  'fundamental_anos_iniciais': 'Fundamental - Anos Iniciais',
  'fundamental_anos_finais': 'Fundamental - Anos Finais',
  'eja': 'EJA - Anos Iniciais',
  'eja_final': 'EJA - Anos Finais',
  'educacao_infantil': 'Educação Infantil',
  'ensino_medio': 'Ensino Médio'
};

// Tipos de frequência por nível
const getAttendanceType = (educationLevel, period) => {
  // Para Escola Integral e Aulas Complementares, sempre por componente
  if (period === 'integral' || period === 'complementar') {
    return 'by_component';
  }
  
  // Anos Iniciais = frequência diária
  if (['fundamental_anos_iniciais', 'eja', 'educacao_infantil'].includes(educationLevel)) {
    return 'daily';
  }
  
  // Anos Finais = frequência por componente
  return 'by_component';
};

// Formata data para exibição
const formatDate = (dateStr) => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-');
  return `${day}/${month}/${year}`;
};

// Dias da semana
const WEEKDAYS = ['Domingo', 'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado'];

// URL da API
const API_URL = process.env.REACT_APP_BACKEND_URL;

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
  const isProfessor = user?.role === 'professor';
  
  // Dados de frequência
  const [attendanceData, setAttendanceData] = useState(null);
  const [dateCheck, setDateCheck] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  
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
  
  // Permissões
  const canEdit = user?.role === 'admin' || user?.role === 'admin_teste' || user?.role === 'secretario' || user?.role === 'professor';
  const canConfigSettings = user?.role === 'admin' || user?.role === 'admin_teste' || user?.role === 'secretario';
  
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
          t.academic_year === academicYear
        );
        setClasses(filtered);
      } else {
        const data = await classesAPI.getAll();
        const filtered = data.filter(c => 
          c.school_id === selectedSchool && 
          c.academic_year === academicYear
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
        const data = await coursesAPI.getAll();
        // Filtra por nível de ensino da turma
        const turma = classes.find(c => c.id === selectedClass);
        if (turma) {
          const filtered = data.filter(c => 
            !c.nivel_ensino || c.nivel_ensino === turma.education_level
          );
          setCourses(filtered);
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
  
  const checkDate = async () => {
    try {
      const data = await attendanceAPI.checkDate(selectedDate);
      setDateCheck(data);
    } catch (error) {
      console.error('Erro ao verificar data:', error);
    }
  };
  
  const showAlertMessage = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 4000);
  };
  
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
  const loadMedicalCertificates = async () => {
    try {
      if (!attendanceData?.students?.length) return;
      
      const studentIds = attendanceData.students.map(s => s.id);
      const result = await medicalCertificatesAPI.checkBulk(selectedDate, studentIds);
      setMedicalCertificates(result.certificates || {});
    } catch (error) {
      console.error('Erro ao carregar atestados médicos:', error);
      // Não bloqueia a frequência se houver erro ao carregar atestados
    }
  };
  
  // Verifica se um aluno tem atestado médico na data selecionada
  const hasActiveCertificate = (studentId) => {
    return medicalCertificates[studentId] !== undefined;
  };
  
  // Obtém informações do atestado médico de um aluno
  const getCertificateInfo = (studentId) => {
    return medicalCertificates[studentId];
  };
  
  // Atualiza status de um aluno
  const updateStudentStatus = (studentId, status) => {
    if (!attendanceData) return;
    
    // Bloqueia se aluno tem atestado médico
    if (hasActiveCertificate(studentId)) {
      showAlertMessage('error', 'Este aluno possui atestado médico para esta data. O status não pode ser alterado.');
      return;
    }
    
    const newStudents = attendanceData.students.map(s => 
      s.id === studentId ? { ...s, status } : s
    );
    
    setAttendanceData({ ...attendanceData, students: newStudents });
    setHasChanges(true);
  };
  
  // Marca todos com o mesmo status (exceto alunos com atestado)
  const markAll = (status) => {
    if (!attendanceData) return;
    
    const newStudents = attendanceData.students.map(s => {
      // Não altera alunos com atestado médico
      if (hasActiveCertificate(s.id)) {
        return s;
      }
      return { ...s, status };
    });
    setAttendanceData({ ...attendanceData, students: newStudents });
    setHasChanges(true);
  };
  
  // Salva frequência (com suporte offline)
  const saveAttendance = async () => {
    if (!attendanceData || !dateCheck?.can_record) return;
    
    setSaving(true);
    try {
      const turma = classes.find(c => c.id === selectedClass);
      const attendanceType = getAttendanceType(turma?.education_level, selectedPeriod);
      
      const records = attendanceData.students
        .filter(s => s.status)
        .map(s => ({
          student_id: s.id,
          status: s.status
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
        records
      };
      
      if (isOnline) {
        // Online: salva diretamente na API
        await attendanceAPI.save(attendancePayload);
        showAlertMessage('success', 'Frequência salva com sucesso!');
      } else {
        // Offline: salva no IndexedDB e adiciona à fila de sincronização
        const now = new Date().toISOString();
        const dataWithMeta = {
          ...attendancePayload,
          updated_at: now,
          syncStatus: SYNC_STATUS.PENDING
        };
        
        // Verifica se já existe registro para esta turma/data
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
        
        showAlertMessage('success', 'Frequência salva localmente! Será sincronizada quando houver conexão.');
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
  const loadClassReport = async () => {
    if (!selectedClass) return;
    
    setLoading(true);
    try {
      const data = await attendanceAPI.getClassReport(selectedClass, academicYear);
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
    
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_URL}/api/attendance/pdf/bimestre/${selectedClass}?bimestre=${selectedBimestre}&academic_year=${academicYear}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Erro ao gerar PDF');
      }
      
      // Criar blob e abrir em nova aba
      const blob = await response.blob();
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
  const navigateDate = (days) => {
    const date = new Date(selectedDate + 'T12:00:00');
    date.setDate(date.getDate() + days);
    setSelectedDate(date.toISOString().split('T')[0]);
  };
  
  // Turma selecionada
  const selectedClassData = classes.find(c => c.id === selectedClass);
  const attendanceType = selectedClassData 
    ? getAttendanceType(selectedClassData.education_level, selectedPeriod)
    : 'daily';
  
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
        
        {/* Painel de Gerenciamento Offline */}
        <OfflineManagementPanel 
          academicYear={academicYear} 
          classId={selectedClass}
        />
        
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
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
            {/* Tab: Lançamento */}
            {activeTab === 'lancamento' && (
              <div className="space-y-4">
                {/* Filtros */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label>
                    <select
                      value={academicYear}
                      onChange={(e) => setAcademicYear(parseInt(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      {availableYears.map(year => (
                        <option key={year} value={year}>{year}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                    <select
                      value={selectedSchool}
                      onChange={(e) => setSelectedSchool(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Selecione a escola</option>
                      {schools.map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
                    <select
                      value={selectedClass}
                      onChange={(e) => setSelectedClass(e.target.value)}
                      disabled={!selectedSchool}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                    >
                      <option value="">Selecione a turma</option>
                      {classes.map(c => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Período</label>
                    <select
                      value={selectedPeriod}
                      onChange={(e) => setSelectedPeriod(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="regular">Regular</option>
                      <option value="integral">Escola Integral</option>
                      <option value="complementar">Aulas Complementares</option>
                    </select>
                  </div>
                  
                  {attendanceType === 'by_component' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular</label>
                      <select
                        value={selectedCourse}
                        onChange={(e) => setSelectedCourse(e.target.value)}
                        disabled={!selectedClass}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                      >
                        <option value="">Selecione o componente</option>
                        {courses.map(c => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>
                
                {/* Seletor de Data */}
                <div className="flex items-center gap-4 bg-gray-50 p-4 rounded-lg">
                  <Button variant="outline" size="sm" onClick={() => navigateDate(-1)}>
                    <ChevronLeft size={18} />
                  </Button>
                  
                  <div className="flex items-center gap-2">
                    <Calendar size={18} className="text-gray-500" />
                    <Input
                      type="date"
                      value={selectedDate}
                      onChange={(e) => setSelectedDate(e.target.value)}
                      className="w-40"
                    />
                    <span className="text-sm text-gray-600">
                      {WEEKDAYS[new Date(selectedDate + 'T12:00:00').getDay()]}
                    </span>
                  </div>
                  
                  <Button variant="outline" size="sm" onClick={() => navigateDate(1)}>
                    <ChevronRight size={18} />
                  </Button>
                  
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => setSelectedDate(new Date().toISOString().split('T')[0])}
                  >
                    Hoje
                  </Button>
                  
                  {/* Status da data */}
                  {dateCheck && (
                    <div className={`ml-auto px-3 py-1 rounded-full text-sm ${
                      dateCheck.can_record 
                        ? 'bg-green-100 text-green-700' 
                        : 'bg-red-100 text-red-700'
                    }`}>
                      {dateCheck.message}
                    </div>
                  )}
                </div>
                
                {/* Info do tipo de frequência */}
                {selectedClassData && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-700">
                    <strong>{EDUCATION_LEVEL_LABELS[selectedClassData.education_level] || selectedClassData.education_level}</strong>
                    {' - '}
                    {attendanceType === 'daily' 
                      ? 'Frequência diária (uma por dia)'
                      : 'Frequência por componente curricular'
                    }
                  </div>
                )}
                
                {/* Botão Carregar */}
                <div className="flex gap-2">
                  <Button 
                    onClick={loadAttendance}
                    disabled={!selectedClass || !selectedDate || (attendanceType === 'by_component' && !selectedCourse)}
                  >
                    Carregar Frequência
                  </Button>
                  
                  {attendanceData && canEdit && (
                    <>
                      <Button variant="outline" onClick={() => markAll('P')}>
                        <CheckCircle size={16} className="mr-1 text-green-600" />
                        Todos Presentes
                      </Button>
                      <Button variant="outline" onClick={() => markAll('F')}>
                        <XCircle size={16} className="mr-1 text-red-600" />
                        Todos Ausentes
                      </Button>
                    </>
                  )}
                </div>
                
                {/* Tabela de Frequência */}
                {loading ? (
                  <div className="flex justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  </div>
                ) : attendanceData ? (
                  <div className="bg-white border rounded-lg overflow-hidden">
                    <div className="p-3 bg-gray-50 border-b flex justify-between items-center">
                      <div>
                        <span className="font-medium">{attendanceData.class_name}</span>
                        <span className="text-gray-500 ml-2">• {formatDate(attendanceData.date)}</span>
                        <span className="text-gray-500 ml-2">• {attendanceData.students.length} alunos</span>
                      </div>
                      <div className="flex gap-4 text-sm">
                        <span className="flex items-center gap-1">
                          <span className="w-3 h-3 rounded bg-green-500"></span>
                          P = Presente
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="w-3 h-3 rounded bg-red-500"></span>
                          F = Falta
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="w-3 h-3 rounded bg-yellow-500"></span>
                          J = Justificado
                        </span>
                      </div>
                    </div>
                    
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Matrícula</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Frequência</th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {attendanceData.students.map(student => {
                          const hasCertificate = hasActiveCertificate(student.id);
                          const certInfo = getCertificateInfo(student.id);
                          const isBlocked = isStudentBlockedForProfessor(student);
                          const blockedMessage = getBlockedMessage(student);
                          
                          return (
                            <tr key={student.id} className={`hover:bg-gray-50 ${hasCertificate ? 'bg-red-50' : ''} ${isBlocked ? 'bg-gray-100' : ''}`}>
                              <td className="px-4 py-3 font-medium text-gray-900">
                                <div className="flex items-center gap-2">
                                  {student.full_name}
                                  {hasCertificate && (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-100 text-red-700 text-xs font-medium rounded-full" title={certInfo?.period}>
                                      <Stethoscope size={12} />
                                      AM
                                    </span>
                                  )}
                                  {isBlocked && (
                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-200 text-gray-600 text-xs font-medium rounded-full" title={blockedMessage}>
                                      🔒 Bloqueado
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-500">{student.enrollment_number || '-'}</td>
                              <td className="px-4 py-3">
                                {hasCertificate ? (
                                  <div className="flex justify-center">
                                    <div className="px-4 py-2 bg-red-100 text-red-700 rounded-lg font-bold text-center" title={`${certInfo?.reason}: ${certInfo?.period}`}>
                                      <div className="flex items-center gap-1">
                                        <Stethoscope size={16} />
                                        <span>AM</span>
                                      </div>
                                      <span className="text-xs font-normal">Atestado Médico</span>
                                    </div>
                                  </div>
                                ) : isBlocked ? (
                                  <div className="flex justify-center">
                                    <div className="px-4 py-2 bg-gray-200 text-gray-600 rounded-lg text-center" title={blockedMessage}>
                                      <span className="text-sm">🔒</span>
                                      <span className="text-xs block">Edição bloqueada</span>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="flex justify-center gap-2">
                                    {['P', 'F', 'J'].map(status => (
                                      <button
                                        key={status}
                                        onClick={() => canEdit && dateCheck?.can_record && updateStudentStatus(student.id, status)}
                                        disabled={!canEdit || !dateCheck?.can_record}
                                        className={`w-10 h-10 rounded-lg font-bold transition-all
                                          ${student.status === status 
                                            ? status === 'P' ? 'bg-green-500 text-white ring-2 ring-green-300' 
                                              : status === 'F' ? 'bg-red-500 text-white ring-2 ring-red-300'
                                              : 'bg-yellow-500 text-white ring-2 ring-yellow-300'
                                            : 'bg-gray-300 text-gray-500 hover:bg-gray-400'
                                          }
                                          ${(!canEdit || !dateCheck?.can_record) ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
                                        `}
                                      >
                                        {status}
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    
                    {/* Legenda de status */}
                    {Object.keys(medicalCertificates).length > 0 && (
                      <div className="p-3 bg-red-50 border-t border-red-200 text-sm text-red-700">
                        <div className="flex items-center gap-2">
                          <Stethoscope size={16} />
                          <span><strong>AM = Atestado Médico</strong> - Alunos com atestado médico não podem ter a frequência alterada.</span>
                        </div>
                      </div>
                    )}
                    
                    {/* Botões Salvar e Excluir */}
                    {canEdit && dateCheck?.can_record && (
                      <div className="p-4 bg-gray-50 border-t flex justify-between items-center">
                        <div>
                          {attendanceData.attendance_id && (
                            <Button
                              variant="outline"
                              onClick={() => setShowDeleteModal(true)}
                              className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-300"
                            >
                              <Trash2 size={16} className="mr-2" />
                              Excluir Frequência
                            </Button>
                          )}
                        </div>
                        <Button
                          onClick={saveAttendance}
                          disabled={saving || !hasChanges}
                        >
                          {saving ? 'Salvando...' : 'Salvar Frequência'}
                        </Button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    <Users size={48} className="mx-auto mb-4 opacity-30" />
                    <p>Selecione os filtros e clique em "Carregar Frequência"</p>
                  </div>
                )}
              </div>
            )}
            
            {/* Tab: Relatórios */}
            {activeTab === 'relatorios' && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                    <select
                      value={selectedSchool}
                      onChange={(e) => setSelectedSchool(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="">Selecione a escola</option>
                      {schools.map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
                    <select
                      value={selectedClass}
                      onChange={(e) => setSelectedClass(e.target.value)}
                      disabled={!selectedSchool}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg disabled:bg-gray-100"
                    >
                      <option value="">Selecione a turma</option>
                      {classes.map(c => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Bimestre</label>
                    <select
                      value={selectedBimestre}
                      onChange={(e) => setSelectedBimestre(Number(e.target.value))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value={1}>1º Bimestre</option>
                      <option value={2}>2º Bimestre</option>
                      <option value={3}>3º Bimestre</option>
                      <option value={4}>4º Bimestre</option>
                    </select>
                  </div>
                  
                  <div className="flex items-end gap-2">
                    <Button onClick={loadClassReport} disabled={!selectedClass}>
                      <FileText size={18} className="mr-2" />
                      Ver na Tela
                    </Button>
                    <Button 
                      onClick={generateBimestrePdf} 
                      disabled={!selectedClass}
                      variant="outline"
                      className="border-green-500 text-green-600 hover:bg-green-50"
                    >
                      <FileDown size={18} className="mr-2" />
                      Gerar PDF
                    </Button>
                  </div>
                </div>
                
                {loading ? (
                  <div className="flex justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  </div>
                ) : classReport ? (
                  <div className="bg-white border rounded-lg overflow-hidden">
                    <div className="p-4 bg-gray-50 border-b">
                      <h3 className="font-semibold">{classReport.class?.name}</h3>
                      <p className="text-sm text-gray-500">
                        {classReport.total_school_days_recorded} dias com frequência registrada • 
                        {classReport.total_students} alunos
                      </p>
                    </div>
                    
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Presenças</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faltas</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Justificadas</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">% Frequência</th>
                          <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-200">
                        {classReport.students.map(student => (
                          <tr key={student.student_id} className="hover:bg-gray-50">
                            <td className="px-4 py-3 font-medium">{student.student_name}</td>
                            <td className="px-4 py-3 text-center text-green-600">{student.present}</td>
                            <td className="px-4 py-3 text-center text-red-600">{student.absent}</td>
                            <td className="px-4 py-3 text-center text-yellow-600">{student.justified}</td>
                            <td className="px-4 py-3 text-center font-bold">
                              <span className={student.attendance_percentage >= 75 ? 'text-green-600' : 'text-red-600'}>
                                {student.attendance_percentage}%
                              </span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              {student.status === 'regular' ? (
                                <span className="px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs">Regular</span>
                              ) : (
                                <span className="px-2 py-1 bg-red-100 text-red-700 rounded-full text-xs flex items-center gap-1 justify-center">
                                  <AlertTriangle size={12} />
                                  Alerta
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    <FileText size={48} className="mx-auto mb-4 opacity-30" />
                    <p>Selecione uma turma para gerar o relatório</p>
                  </div>
                )}
              </div>
            )}
            
            {/* Tab: Alertas */}
            {activeTab === 'alertas' && (
              <div className="space-y-4">
                <div className="flex gap-4">
                  <div className="flex-1">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Filtrar por Escola</label>
                    <select
                      value={selectedSchool}
                      onChange={(e) => setSelectedSchool(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="">Todas as escolas</option>
                      {schools.map(s => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-end">
                    <Button onClick={loadAlerts}>
                      <AlertTriangle size={18} className="mr-2" />
                      Buscar Alertas
                    </Button>
                  </div>
                </div>
                
                {loading ? (
                  <div className="flex justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  </div>
                ) : alertsData ? (
                  <div>
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                      <div className="flex items-center gap-2 text-red-700">
                        <AlertTriangle size={20} />
                        <span className="font-semibold">{alertsData.total_alerts} alunos com frequência abaixo de 75%</span>
                      </div>
                    </div>
                    
                    {alertsData.alerts.length > 0 ? (
                      <div className="bg-white border rounded-lg overflow-hidden">
                        <table className="min-w-full divide-y divide-gray-200">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turma</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Faltas</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">% Frequência</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {alertsData.alerts.map((alert, idx) => (
                              <tr key={idx} className="hover:bg-gray-50">
                                <td className="px-4 py-3 font-medium">{alert.student_name}</td>
                                <td className="px-4 py-3 text-sm text-gray-500">{alert.class_name}</td>
                                <td className="px-4 py-3 text-center text-red-600 font-bold">{alert.absent}</td>
                                <td className="px-4 py-3 text-center">
                                  <span className="px-2 py-1 bg-red-100 text-red-700 rounded-full font-bold">
                                    {alert.attendance_percentage}%
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="text-center py-12 text-green-600">
                        <CheckCircle size={48} className="mx-auto mb-4" />
                        <p>Nenhum aluno com frequência abaixo de 75%</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    <AlertTriangle size={48} className="mx-auto mb-4 opacity-30" />
                    <p>Clique em "Buscar Alertas" para ver alunos com baixa frequência</p>
                  </div>
                )}
              </div>
            )}
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
