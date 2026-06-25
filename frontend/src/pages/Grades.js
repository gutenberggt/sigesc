import { useState, useEffect, useRef, useCallback, useMemo, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useUnsavedChangesWarning } from '@/hooks/useUnsavedChangesWarning';
import { usePermissions } from '@/hooks/usePermissions';
import { gradesAPI, schoolsAPI, classesAPI, coursesAPI, studentsAPI, professorAPI, teacherAssignmentAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { useBimestreEditStatus } from '@/hooks/useBimestreEditStatus';
import { BimestreBlockedAlert, BimestreDeadlineAlert, BimestreFieldIndicator } from '@/components/BimestreStatus';
import { OfflineManagementPanel, OfflineDataBadge } from '@/components/OfflineManagementPanel';
import { PainelSincronizacao } from '@/components/PainelSincronizacao';
import { useOffline } from '@/contexts/OfflineContext';
import { db, SYNC_STATUS, addToSyncQueue, SYNC_OPERATIONS } from '@/db/database';
import { GradesContext } from '@/contexts/GradesContext';
import { useAutoSaveDraft } from '@/hooks/useAutoSaveDraft';
const TurmaTab = lazy(() => import('@/components/grades/TurmaTab').then(m => ({ default: m.TurmaTab })));
const AlunoTab = lazy(() => import('@/components/grades/AlunoTab').then(m => ({ default: m.AlunoTab })));
import { 
  Home, BookOpen, Users, User, Save, AlertCircle, CheckCircle, 
  Search, X, Calculator, TrendingUp, TrendingDown, Lock, CloudOff, FileText
} from 'lucide-react';

import {
  GradeInput, ConceitoSelect,
  isEducacaoInfantil, isAnosIniciaisConceitual, usaAvaliacaoConceitual,
  valorParaConceito, conceitoParaValor, calcularMaiorConceito,
  formatGrade, parseGrade, calculateAverage,
  CONCEITOS_EDUCACAO_INFANTIL, CONCEITOS_ANOS_INICIAIS,
} from '@/components/grades/gradeHelpers';

export function Grades() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { isOnline, pendingSyncCount } = useOffline();
  
  // Estados gerais
  const [activeTab, setActiveTab] = useState('turma'); // 'turma' ou 'aluno'
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
  
  // Hook para verificar status de edição dos bimestres
  const { 
    editStatus, 
    loading: loadingEditStatus, 
    canEditBimestre, 
    blockedBimestres,
    getBimestreInfo 
  } = useBimestreEditStatus(academicYear);
  
  // Dados base
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [students, setStudents] = useState([]);
  
  // Dados do professor (quando logado como professor)
  const [professorTurmas, setProfessorTurmas] = useState([]);
  const { isProfessor, canEditGrades: canEdit, isAdminOrSecretary } = usePermissions();
  
  // Filtros - Por Turma
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedSeries, setSelectedSeries] = useState('');
  const [selectedCourse, setSelectedCourse] = useState('');
  const [classCourseIds, setClassCourseIds] = useState(null); // null = não carregou, [] = sem alocações
  
  // Filtros - Por Aluno
  const [searchName, setSearchName] = useState('');
  const [searchCpf, setSearchCpf] = useState('');
  const [showNameSuggestions, setShowNameSuggestions] = useState(false);
  const [showCpfSuggestions, setShowCpfSuggestions] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const nameInputRef = useRef(null);
  const cpfInputRef = useRef(null);
  
  // Dados de notas
  const [gradesData, setGradesData] = useState([]);
  const [studentGrades, setStudentGrades] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  // AutoSave (P1): persiste as notas em edição no IndexedDB. formId só fica
  // ativo quando turma+disciplina selecionadas (lançamento por turma).
  const gradesFormId = useMemo(() => (
    (activeTab === 'turma' && selectedClass && selectedCourse)
      ? `grades:${selectedClass}:${selectedSeries || '-'}:${selectedCourse}:${academicYear}`
      : null
  ), [activeTab, selectedClass, selectedSeries, selectedCourse, academicYear]);
  const {
    draft: gradesDraft, clearDraft: clearGradesDraft, dismissDraft: dismissGradesDraft,
  } = useAutoSaveDraft({
    formId: gradesFormId, data: gradesData, enabled: hasChanges,
    userId: user?.id, route: 'grades',
  });
  const restoreGradesDraft = useCallback(() => {
    if (gradesDraft?.data && Array.isArray(gradesDraft.data)) {
      setGradesData(gradesDraft.data);
      setHasChanges(true);
      dismissGradesDraft();
    }
  }, [gradesDraft, dismissGradesDraft]);
  const discardGradesDraft = useCallback(() => { clearGradesDraft(); }, [clearGradesDraft]);
  
  // Alerta ao sair com alterações não salvas
  const { guardedNavigate } = useUnsavedChangesWarning(hasChanges, 'Há alterações de notas não salvas. Deseja sair sem salvar?');

  // Modal PDF de notas
  const [showPdfModal, setShowPdfModal] = useState(false);
  const [pdfBimestres, setPdfBimestres] = useState([1, 2, 3, 4]);
  const [pdfLoading, setPdfLoading] = useState(false);
  
  const handleGeneratePdf = async () => {
    if (!selectedClass || !selectedCourse || pdfBimestres.length === 0) return;
    setPdfLoading(true);
    try {
      const blob = await gradesAPI.getPdfBlob(
        selectedClass,
        selectedCourse,
        pdfBimestres,
        academicYear,
        isMultiGrade ? selectedSeries : null
      );
      const pdfUrl = window.URL.createObjectURL(blob);
      window.open(pdfUrl, '_blank');
      setShowPdfModal(false);
    } catch (err) {
      alert('Erro ao gerar PDF de notas: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setPdfLoading(false);
    }
  };

  const togglePdfBimestre = (b) => {
    setPdfBimestres(prev => 
      prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b].sort()
    );
  };

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
  
  // Função auxiliar para verificar se pode editar um bimestre específico
  const canEditField = (bimestre) => {
    return canEdit && canEditBimestre(bimestre);
  };
  
  // Função para verificar se pode editar notas de um aluno específico em um bimestre
  // Regras:
  // - blocked_after_action: bloqueado para TODOS (transferência/desistência/remanejamento)
  // - blocked_before_enrollment: bloqueado para professor, liberado para admin/secretário
  // - migrated_from_class_id: registro migrado da turma origem → só admin/secretário/gerente/super_admin editam
  const canEditStudentGrade = useCallback((student, bimestre, gradeRecord) => {
    if (isStudentBlockedForProfessor(student)) {
      return false;
    }
    // Bloqueio pós-ação (transferência/desistência/remanejamento) → bloqueio absoluto
    if (student.blocked_after_action && student.blocked_after_action.includes(bimestre)) {
      return false;
    }
    // Bloqueio pré-matrícula → bloqueio apenas para professor
    if (student.blocked_before_enrollment && student.blocked_before_enrollment.includes(bimestre)) {
      if (!isAdminOrSecretary) {
        return false;
      }
    }
    // Jun/2026 — Granular: registro migrado da turma origem → na turma de DESTINO
    // apenas os bimestres MIGRADOS (congelados) ficam somente leitura para professor.
    // Os demais bimestres (lançados após a data da ação) permanecem editáveis.
    if (gradeRecord && gradeRecord.migrated_from_class_id && !isAdminOrSecretary) {
      const frozen = student.migrated_bimesters || [];
      if (frozen.includes(bimestre)) {
        return false;
      }
    }
    return canEditField(bimestre);
  }, [isStudentBlockedForProfessor, canEditField, isAdminOrSecretary]);
  
  // Carrega dados iniciais
  useEffect(() => {
    const loadData = async () => {
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
          
          // Carrega alunos para busca por aluno (se necessário)
          const studentsResponse = await studentsAPI.getAll({page_size: 10000});
          setStudents(studentsResponse.items || []);
        } else {
          // Para outros usuários, carrega todos os dados
          const [schoolsData, classesData, coursesData, studentsResponse2] = await Promise.all([
            schoolsAPI.getAll(),
            classesAPI.getAll(),
            coursesAPI.getAll(),
            studentsAPI.getAll({page_size: 10000})
          ]);
          setSchools(schoolsData);
          setClasses(classesData);
          setCourses(coursesData);
          setStudents(studentsResponse2.items || []);
        }
      } catch (error) {
        console.error('Erro ao carregar dados:', error);
        showAlert('error', 'Erro ao carregar dados');
      }
    };
    loadData();
  }, [isProfessor, academicYear]);
  
  // Fecha dropdowns ao clicar fora
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (nameInputRef.current && !nameInputRef.current.contains(event.target)) {
        setShowNameSuggestions(false);
      }
      if (cpfInputRef.current && !cpfInputRef.current.contains(event.target)) {
        setShowCpfSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  const showAlert = useCallback((type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  }, []);
  
  // Turma selecionada (para obter nível de ensino e série)
  const selectedClassData = isProfessor 
    ? professorTurmas.find(t => t.id === selectedClass)
    : classes.find(c => c.id === selectedClass);
  
  // Verifica se é turma multisseriada
  const isMultiGrade = selectedClassData?.is_multi_grade === true;
  
  // Séries disponíveis para turmas multisseriadas
  const [availableSeries, setAvailableSeries] = useState([]);
  
  // Busca séries disponíveis quando seleciona turma multisseriada
  useEffect(() => {
    if (!isMultiGrade || !selectedClass) {
      setAvailableSeries([]);
      return;
    }
    const fetchSeries = async () => {
      try {
        const details = await classesAPI.getDetails(selectedClass);
        const seriesSet = new Set();
        (details.students || []).forEach(s => {
          if (s.student_series) seriesSet.add(s.student_series);
        });
        setAvailableSeries(Array.from(seriesSet).sort());
      } catch {
        setAvailableSeries([]);
      }
    };
    fetchSeries();
  }, [selectedClass, isMultiGrade]);
  
  // Grade level: usa selectedSeries para multisseriada, senão grade_level da turma
  const currentGradeLevel = isMultiGrade && selectedSeries
    ? selectedSeries
    : (selectedClassData?.grade_level || '');
  
  // Verifica se é Educação Infantil
  const isEdInfantil = selectedClassData 
    ? isEducacaoInfantil(selectedClassData.grade_level, selectedClassData.nivel_ensino || selectedClassData.education_level)
    : false;
  
  // Verifica se é 1º ou 2º ano (usa conceitos específicos)
  const isAnosIniciaisConc = isAnosIniciaisConceitual(currentGradeLevel);
  
  // Verifica se usa avaliação conceitual (Educação Infantil OU 1º/2º ano)
  const usaConceito = isEdInfantil || isAnosIniciaisConc;
  
  // Filtros derivados - para professor usa as turmas alocadas
  const filteredClasses = isProfessor
    ? professorTurmas.filter(t => t.school_id === selectedSchool)
    : classes.filter(c => c.school_id === selectedSchool);
  
  // Carregar componentes vinculados à turma via teacher_assignments (para não-professores)
  useEffect(() => {
    const loadClassAssignments = async () => {
      if (isProfessor || !selectedClass) {
        setClassCourseIds(null);
        return;
      }
      try {
        const assignments = await teacherAssignmentAPI.list({
          class_id: selectedClass,
          academic_year: academicYear
        });
        if (assignments && assignments.length > 0) {
          const ids = [...new Set(assignments.map(a => a.course_id).filter(Boolean))];
          setClassCourseIds(ids);
        } else {
          setClassCourseIds([]);
        }
      } catch (error) {
        console.error('Erro ao carregar alocações:', error);
        setClassCourseIds([]);
      }
    };
    loadClassAssignments();
  }, [selectedClass, isProfessor, academicYear]);

  // Filtra componentes curriculares (só quando turma selecionada)
  const filteredCourses = isProfessor
    ? (selectedClassData?.componentes || []).filter(c => {
        const ap = (c.atendimento_programa || c.atendimento || '').toLowerCase();
        return !ap.includes('integral') && !ap.includes('aee');
      })
    : !selectedClassData ? [] : (() => {
        // Se há alocações de professor, usar apenas os componentes alocados
        if (classCourseIds && classCourseIds.length > 0) {
          return courses
            .filter(c => classCourseIds.includes(c.id))
            .filter(c => {
              const ap = (c.atendimento_programa || c.atendimento || '').toLowerCase();
              return !ap.includes('integral') && !ap.includes('aee');
            })
            .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        }
        // Fallback: filtrar por nível/atendimento (comportamento anterior)
        return courses.filter(course => {
        const matchesSchool = !course.school_id || course.school_id === selectedSchool;
        if (!matchesSchool) return false;
        if (course.nivel_ensino && course.nivel_ensino !== selectedClassData.education_level) return false;
        
        // Excluir componentes formativos (integral, AEE) do lançamento de notas
        const courseAtendimento = (course.atendimento_programa || course.atendimento || '').toLowerCase();
        if (courseAtendimento.includes('integral') || courseAtendimento.includes('aee')) return false;
        
        // Turma regular: só componentes regulares
        if (courseAtendimento) return false;
        
        // Para multisseriada com série selecionada, filtra pelo ano/série
        if (isMultiGrade && selectedSeries) {
          if (course.grade_levels && course.grade_levels.length > 0) {
            return course.grade_levels.includes(selectedSeries);
          }
          return true;
        }
        
        // Se o componente não tem séries específicas, aplica a todas do nível
        if (!course.grade_levels || course.grade_levels.length === 0) return true;
        
        // Verifica se a série da turma está nas séries do componente
        return course.grade_levels.includes(selectedClassData.grade_level);
      }).sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      })();
  
  // Sugestões de busca
  const nameSuggestions = searchName.length >= 3 
    ? students.filter(s => s.full_name?.toLowerCase().startsWith(searchName.toLowerCase())).slice(0, 10)
    : [];
  
  const cpfSuggestions = searchCpf.length >= 3
    ? students.filter(s => s.cpf?.replace(/\D/g, '').startsWith(searchCpf.replace(/\D/g, ''))).slice(0, 10)
    : [];
  
  // Carrega notas por turma
  // Carrega notas por turma (com suporte offline)
  const loadGradesByClass = useCallback(async () => {
    if (!selectedClass || !selectedCourse) return;
    
    setLoading(true);
    try {
      if (isOnline) {
        // Online: busca da API e atualiza cache local
        const data = await gradesAPI.getByClass(selectedClass, selectedCourse, academicYear);
        // Para turmas multisseriadas, filtra apenas alunos da série selecionada
        // (comparação normalizada para evitar sumiço por divergência de case/espaços)
        const _normSerie = (v) => (v || '').toString().trim().toLowerCase();
        const filteredData = (isMultiGrade && selectedSeries)
          ? data.filter(item => _normSerie(item.student?.student_series) === _normSerie(selectedSeries))
          : data;
        setGradesData(filteredData);
        
        // Atualiza cache local com dados do servidor
        if (data && data.length > 0) {
          await db.transaction('rw', db.grades, async () => {
            for (const item of data) {
              if (item.grade && item.grade.id) {
                const existing = await db.grades.where('id').equals(item.grade.id).first();
                if (existing) {
                  await db.grades.update(existing.localId, {
                    ...item.grade,
                    student_id: item.student.id,
                    class_id: selectedClass,
                    course_id: selectedCourse,
                    syncStatus: SYNC_STATUS.SYNCED
                  });
                } else {
                  await db.grades.add({
                    ...item.grade,
                    student_id: item.student.id,
                    class_id: selectedClass,
                    course_id: selectedCourse,
                    syncStatus: SYNC_STATUS.SYNCED
                  });
                }
              }
            }
          });
        }
      } else {
        // Offline: busca do cache local
        const localGrades = await db.grades
          .where('class_id').equals(selectedClass)
          .and(g => g.course_id === selectedCourse && g.academic_year === academicYear)
          .toArray();
        
        // Busca alunos do cache para montar estrutura esperada
        const localStudents = await db.students
          .where('class_id').equals(selectedClass)
          .toArray();
        
        // Monta estrutura compatível com o formato da API
        const offlineData = localStudents.map(student => {
          const grade = localGrades.find(g => g.student_id === student.id) || {
            b1: null, b2: null, b3: null, b4: null,
            rec_s1: null, rec_s2: null,
            final_average: null, status: 'cursando'
          };
          return { student, grade };
        });
        
        if (offlineData.length > 0) {
          setGradesData(offlineData);
          showAlert('info', 'Dados carregados do cache local (modo offline)');
        } else {
          showAlert('error', 'Nenhum dado disponível offline. Sincronize quando houver conexão.');
        }
      }
      setHasChanges(false);
    } catch (error) {
      console.error('Erro ao carregar notas:', error);
      showAlert('error', 'Erro ao carregar notas da turma');
    } finally {
      setLoading(false);
    }
  }, [selectedClass, selectedCourse, isOnline, academicYear, isMultiGrade, selectedSeries, showAlert]);
  
  // Carrega notas por aluno
  const loadGradesByStudent = useCallback(async (studentId) => {
    setLoading(true);
    try {
      const data = await gradesAPI.getByStudent(studentId, academicYear);
      setStudentGrades(data);
    } catch (error) {
      console.error('Erro ao carregar notas:', error);
      showAlert('error', 'Erro ao carregar notas do aluno');
    } finally {
      setLoading(false);
    }
  }, [academicYear, showAlert]);
  
  // Seleciona aluno
  const handleSelectStudent = useCallback((student) => {
    setSelectedStudent(student);
    setSearchName(student.full_name || '');
    setSearchCpf(student.cpf || '');
    setShowNameSuggestions(false);
    setShowCpfSuggestions(false);
    loadGradesByStudent(student.id);
  }, [loadGradesByStudent]);
  
  // Limpa busca
  const handleClearSearch = useCallback(() => {
    setSearchName('');
    setSearchCpf('');
    setSelectedStudent(null);
    setStudentGrades(null);
    setShowNameSuggestions(false);
    setShowCpfSuggestions(false);
  }, []);
  
  // Atualiza nota local (por turma)
  const updateLocalGrade = useCallback((index, field, value) => {
    setGradesData(prevData => {
      const newData = [...prevData];
      newData[index] = { ...newData[index], grade: { ...newData[index].grade, [field]: value } };
      const g = newData[index].grade;
      
      if (usaConceito) {
        // Educação Infantil ou 1º/2º Ano: média é o MAIOR conceito alcançado
        g.final_average = calcularMaiorConceito(g.b1, g.b2, g.b3, g.b4);
        // Se não há nenhum conceito lançado, status é cursando
        g.status = g.final_average !== null ? 'aprovado' : 'cursando';
      } else {
        // Outros níveis: Recalcula média com recuperações por semestre
        g.final_average = calculateAverage(g.b1, g.b2, g.b3, g.b4, g.rec_s1, g.rec_s2);
        g.status = g.final_average !== null 
          ? (g.final_average >= 5 ? 'aprovado' : 'reprovado_nota')
          : 'cursando';
      }
      
      return newData;
    });
    setHasChanges(true);
  }, [usaConceito]);
  
  // Salva notas da turma (com suporte offline)
  const saveGrades = useCallback(async () => {
    setSaving(true);
    try {
      const gradesToSave = gradesData.map(item => ({
        student_id: item.student.id,
        class_id: selectedClass,
        course_id: selectedCourse,
        academic_year: academicYear,
        // Fase 2 — Dependência de Estudos: backend valida coerência (anti-spoof)
        ...(item.student?.is_dependency && item.student?.dependency_id
          ? { dependency_id: item.student.dependency_id }
          : {}),
        b1: item.grade.b1,
        b2: item.grade.b2,
        b3: item.grade.b3,
        b4: item.grade.b4,
        rec_s1: item.grade.rec_s1,
        rec_s2: item.grade.rec_s2,
        observations: item.grade.observations
      }));
      
      if (isOnline) {
        // Online: salva diretamente na API
        await gradesAPI.updateBatch(gradesToSave);
        showAlert('success', 'Notas salvas com sucesso!');
      } else {
        // Offline: salva no IndexedDB e adiciona à fila de sincronização
        for (const grade of gradesToSave) {
          const existingLocal = await db.grades
            .where('[student_id+course_id+academic_year]')
            .equals([grade.student_id, grade.course_id, grade.academic_year])
            .first();
          
          const now = new Date().toISOString();
          const gradeWithMeta = {
            ...grade,
            updated_at: now,
            syncStatus: SYNC_STATUS.PENDING
          };
          
          if (existingLocal) {
            await db.grades.update(existingLocal.localId, gradeWithMeta);
            await addToSyncQueue('grades', SYNC_OPERATIONS.UPDATE, existingLocal.id || `temp_${Date.now()}`, gradeWithMeta);
          } else {
            const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            await db.grades.add({ ...gradeWithMeta, id: tempId });
            await addToSyncQueue('grades', SYNC_OPERATIONS.CREATE, tempId, gradeWithMeta);
          }
        }
        showAlert('success', 'Notas salvas no aparelho ✓ — serão enviadas automaticamente quando a internet voltar.');
      }
      
      setHasChanges(false);
      clearGradesDraft();
      
      // Recarrega dados atualizados (se online)
      if (isOnline) {
        await loadGradesByClass();
      }
    } catch (error) {
      console.error('Erro ao salvar notas:', error);
      showAlert('error', 'Erro ao salvar notas');
    } finally {
      setSaving(false);
    }
  }, [gradesData, selectedClass, selectedCourse, academicYear, isOnline, loadGradesByClass, showAlert]);
  
  // Atualiza nota individual do aluno
  const updateStudentGrade = useCallback(async (gradeId, courseId, field, value) => {
    if (!selectedStudent) return;
    
    // Atualiza localmente primeiro (functional update evita stale closure)
    setStudentGrades(prev => {
      if (!prev) return prev;
      const newGrades = { ...prev, grades: [...prev.grades] };
      const gradeIndex = newGrades.grades.findIndex(g => g.course_id === courseId);
      if (gradeIndex >= 0) {
        const updatedGrade = { ...newGrades.grades[gradeIndex], [field]: value };
        updatedGrade.final_average = calculateAverage(
          updatedGrade.b1, updatedGrade.b2, updatedGrade.b3, updatedGrade.b4,
          updatedGrade.rec_s1, updatedGrade.rec_s2
        );
        updatedGrade.status = updatedGrade.final_average !== null
          ? (updatedGrade.final_average >= 5 ? 'aprovado' : 'reprovado_nota')
          : 'cursando';
        newGrades.grades[gradeIndex] = updatedGrade;
      }
      return newGrades;
    });
    
    // Salva no servidor
    try {
      if (gradeId) {
        await gradesAPI.update(gradeId, { [field]: value });
      } else {
        // Cria nova nota
        await gradesAPI.create({
          student_id: selectedStudent.id,
          class_id: selectedStudent.class_id,
          course_id: courseId,
          academic_year: academicYear,
          [field]: value
        });
        // Recarrega dados
        await loadGradesByStudent(selectedStudent.id);
      }
    } catch (error) {
      console.error('Erro ao salvar nota:', error);
      showAlert('error', 'Erro ao salvar nota');
    }
  }, [selectedStudent, academicYear, loadGradesByStudent, showAlert]);
  
  const gradesContextValue = useMemo(() => ({
    // Base lists
    schools, filteredClasses, filteredCourses, availableSeries,
    // Selection - Por Turma
    selectedSchool, setSelectedSchool,
    selectedClass, setSelectedClass,
    selectedSeries, setSelectedSeries,
    selectedCourse, setSelectedCourse,
    setGradesData,
    // Loading / saving
    loading, saving, hasChanges,
    // Data
    gradesData, currentGradeLevel,
    // Flags
    isMultiGrade, usaConceito, isAnosIniciaisConc, canEdit,
    // Handlers - Por Turma
    loadGradesByClass, updateLocalGrade, saveGrades,
    canEditField, canEditStudentGrade,
    isStudentBlockedForProfessor, getBlockedMessage,
    setShowPdfModal,
    user,
    // Por Aluno
    searchName, setSearchName,
    searchCpf, setSearchCpf,
    nameInputRef, cpfInputRef,
    showNameSuggestions, setShowNameSuggestions, nameSuggestions,
    showCpfSuggestions, setShowCpfSuggestions, cpfSuggestions,
    selectedStudent,
    handleSelectStudent, handleClearSearch,
    studentGrades, updateStudentGrade,
    // AutoSave (P1)
    gradesDraft, restoreGradesDraft, discardGradesDraft,
  }), [
    schools, filteredClasses, filteredCourses, availableSeries,
    selectedSchool, selectedClass, selectedSeries, selectedCourse,
    loading, saving, hasChanges,
    gradesData, currentGradeLevel,
    isMultiGrade, usaConceito, isAnosIniciaisConc, canEdit,
    loadGradesByClass, updateLocalGrade, saveGrades,
    canEditField, canEditStudentGrade,
    isStudentBlockedForProfessor, getBlockedMessage,
    user,
    searchName, searchCpf,
    showNameSuggestions, nameSuggestions,
    showCpfSuggestions, cpfSuggestions,
    selectedStudent,
    handleSelectStudent, handleClearSearch,
    studentGrades, updateStudentGrade,
    gradesDraft, restoreGradesDraft, discardGradesDraft,
  ]);

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-4">
            <button
              onClick={() => guardedNavigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <BookOpen className="text-blue-600" />
                Lançamento de Notas
              </h1>
              <p className="text-gray-600 text-sm">Gerencie as notas dos alunos por turma ou individualmente</p>
            </div>
          </div>
          
          {/* Seletor de Ano Letivo */}
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">Ano Letivo:</label>
            <select
              value={academicYear}
              onChange={(e) => setAcademicYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {(() => { const cy = new Date().getFullYear(); return [cy - 2, cy - 1, cy, cy + 1]; })().map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
        </div>
        
        {/* Alert */}
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
          </div>
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
        
        {/* Tabs */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('turma')}
                className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'turma'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <Users className="inline mr-2" size={18} />
                Por Turma
              </button>
              <button
                onClick={() => setActiveTab('aluno')}
                className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'aluno'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <User className="inline mr-2" size={18} />
                Por Aluno
              </button>
            </nav>
          </div>
          
          <div className="p-6">
            <GradesContext.Provider value={gradesContextValue}>
              <Suspense fallback={
                <div className="flex justify-center items-center py-16" data-testid="grades-tab-loading">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-3 text-gray-500 text-sm">Carregando...</span>
                </div>
              }>
                {activeTab === 'turma' && <TurmaTab />}
                {activeTab === 'aluno' && <AlunoTab />}
              </Suspense>
            </GradesContext.Provider>
          </div>
        </div>
        
        {/* Legenda */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Legenda</h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <div className="flex items-center gap-2">
              <Calculator size={16} className="text-gray-500" />
              <span>Fórmula: (B1×2 + B2×3 + B3×2 + B4×3) / 10</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs">Rec. 1º</span>
              <span>Recuperação substitui menor nota do 1º semestre (B1/B2)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs">Rec. 2º</span>
              <span>Recuperação substitui menor nota do 2º semestre (B3/B4)</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp size={16} className="text-green-500" />
              <span>Média ≥ 5,0 = Aprovado</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingDown size={16} className="text-red-500" />
              <span>Média &lt; 5,0 = Reprovado</span>
            </div>
          </div>
        </div>
      </div>

      {/* Modal de seleção de bimestres para PDF */}
      {showPdfModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm mx-4">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Gerar PDF de Notas</h3>
            <p className="text-sm text-gray-600 mb-4">Selecione os bimestres:</p>
            <div className="grid grid-cols-2 gap-3 mb-6">
              {[1, 2, 3, 4].map(b => (
                <button
                  key={b}
                  onClick={() => togglePdfBimestre(b)}
                  className={`px-4 py-3 rounded-lg border-2 font-medium transition-colors ${
                    pdfBimestres.includes(b)
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'
                  }`}
                  data-testid={`pdf-bimestre-${b}`}
                >
                  {b}º Bimestre
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setShowPdfModal(false)}
                className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleGeneratePdf}
                disabled={pdfBimestres.length === 0 || pdfLoading}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 flex items-center justify-center gap-2"
                data-testid="btn-confirm-grades-pdf"
              >
                {pdfLoading ? (
                  <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></span>
                ) : (
                  <FileText size={18} />
                )}
                {pdfLoading ? 'Gerando...' : 'Gerar PDF'}
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}
