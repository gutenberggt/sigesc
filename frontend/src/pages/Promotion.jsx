import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Loader2, Download, FileText, School, Users, BookOpen, Filter, RefreshCw, CheckCircle, XCircle, AlertTriangle, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Home } from 'lucide-react';
import { schoolsAPI, classesAPI, gradesAPI, coursesAPI, studentsAPI, teacherAssignmentAPI } from '@/services/api';
import { usaAvaliacaoConceitual, valorParaConceito } from '@/components/grades/gradeHelpers';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Helper para buscar matrículas
const fetchEnrollments = async (filters = {}) => {
  const params = new URLSearchParams();
  if (filters.class_id) params.append('class_id', filters.class_id);
  if (filters.student_id) params.append('student_id', filters.student_id);
  const response = await fetch(`${API_URL}/api/enrollments?${params.toString()}`, {
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
    }
  });
  if (!response.ok) throw new Error('Erro ao buscar matrículas');
  return response.json();
};

// Componentes Curriculares abreviados (como no documento)
const COMPONENT_ABBREVIATIONS = {
  'Língua Portuguesa': 'L. PORT.',
  'Arte': 'ARTE',
  'Educação Física': 'ED. FÍS.',
  'Língua Inglesa': 'L. ING.',
  'Inglês': 'L. ING.',
  'Matemática': 'MAT.',
  'Ciências': 'CIÊN.',
  'História': 'HIST.',
  'Geografia': 'GEOG.',
  'Ensino Religioso': 'ENS. REL.',
  'Educação Ambiental e Clima': 'ED. AMB. CLI.',
  'Estudos Amazônicos': 'EST. AMAZ.',
  'Literatura e Redação': 'LIT. E RED.',
  'Arte e Cultura': 'ART. E CULT.',
  'Recreação e Lazer': 'REC. ESP. LAZ.',
  'Recreação, Esporte e Lazer': 'REC. ESP. LAZ.',
  'Linguagem Recreativa com Práticas de Esporte e Lazer': 'REC. ESP. LAZ.',
  'Tecnologia da Informação': 'TEC. E INFO.',
  'Tecnologia e Informática': 'TEC. E INFO.',
  'Acompanhamento Pedagógico de Língua Portuguesa': 'AC. PED. L. PORT.',
  'Acompanhamento Pedagógico de Matemática': 'AC. PED. MAT.',
  'Acomp. Ped. de Língua Portuguesa': 'AC. PED. L. PORT.',
  'Acomp. Ped. de Matemática': 'AC. PED. MAT.',
  'Contação de Histórias e Iniciação Musical': 'CONT. HIST.',
  'Corpo, gestos e movimentos': 'CORP. GEST.',
  'Escuta, fala, pensamento e imaginação': 'ESC. FALA',
  'Espaços, tempos, quantidades, relações e transformações': 'ESP. TEMP.',
  'Higiene e Saúde': 'HIG. SAÚDE',
  'O eu, o outro e nós': 'EU OUT. NÓS',
  'Traço, sons, cores e formas': 'TRAÇ. SONS'
};

// Ordem dos componentes - Anos Iniciais (1º ao 5º Ano) - Igual ao Boletim
const ORDEM_COMPONENTES_ANOS_INICIAIS = [
  'Língua Portuguesa',
  'Arte',
  'Arte e Cultura',
  'Educação Física',
  'Matemática',
  'Ciências',
  'História',
  'Geografia',
  'Ensino Religioso',
  'Recreação, Esporte e Lazer',
  'Linguagem Recreativa com Práticas de Esporte e Lazer',
  'Tecnologia e Informática',
  'Acompanhamento Pedagógico de Língua Portuguesa',
  'Acomp. Ped. de Língua Portuguesa',
  'Acompanhamento Pedagógico de Matemática',
  'Acomp. Ped. de Matemática',
  'Educação Ambiental e Clima'
];

// Ordem dos componentes - Anos Finais (6º ao 9º Ano) - Igual ao Boletim
const ORDEM_COMPONENTES_ANOS_FINAIS = [
  'Língua Portuguesa',
  'Arte',
  'Arte e Cultura',
  'Educação Física',
  'Língua Inglesa',
  'Inglês',
  'Matemática',
  'Ciências',
  'História',
  'Geografia',
  'Ensino Religioso',
  'Estudos Amazônicos',
  'Literatura e Redação',
  'Recreação, Esporte e Lazer',
  'Linguagem Recreativa com Práticas de Esporte e Lazer',
  'Tecnologia e Informática',
  'Acompanhamento Pedagógico de Língua Portuguesa',
  'Acomp. Ped. de Língua Portuguesa',
  'Acompanhamento Pedagógico de Matemática',
  'Acomp. Ped. de Matemática',
  'Educação Ambiental e Clima'
];

// Função para ordenar componentes por nível de ensino
const ordenarComponentes = (courses, gradeLevel) => {
  // Determinar se é Anos Iniciais ou Anos Finais
  const isAnosIniciais = ['1º Ano', '2º Ano', '3º Ano', '4º Ano', '5º Ano', 
                          '1º ano', '2º ano', '3º ano', '4º ano', '5º ano'].some(
    nivel => gradeLevel?.includes(nivel)
  );
  
  const ordemReferencia = isAnosIniciais ? ORDEM_COMPONENTES_ANOS_INICIAIS : ORDEM_COMPONENTES_ANOS_FINAIS;
  
  // Função para encontrar o índice do componente na ordem de referência
  const getOrdem = (nome) => {
    const nomeLower = (nome || '').toLowerCase().trim();
    
    // Primeiro, tentar match exato
    for (let i = 0; i < ordemReferencia.length; i++) {
      if (ordemReferencia[i].toLowerCase() === nomeLower) {
        return i;
      }
    }
    
    // Segundo, tentar match por início do nome (para variações)
    for (let i = 0; i < ordemReferencia.length; i++) {
      const refLower = ordemReferencia[i].toLowerCase();
      if (nomeLower.startsWith(refLower) || refLower.startsWith(nomeLower)) {
        // Evitar que "Acomp. Ped. de Língua Portuguesa" faça match com "Língua Portuguesa"
        if (nomeLower.includes('acomp') && !refLower.includes('acomp')) {
          continue;
        }
        return i;
      }
    }
    
    // Se não encontrar, colocar no final
    return 999;
  };
  
  return [...courses].sort((a, b) => {
    const ordemA = getOrdem(a.name);
    const ordemB = getOrdem(b.name);
    return ordemA - ordemB;
  });
};

// Função para abreviar nome do componente
const abbreviateComponent = (name) => {
  if (!name) return '';
  // Match exato primeiro
  if (COMPONENT_ABBREVIATIONS[name]) return COMPONENT_ABBREVIATIONS[name];
  // Match case-insensitive
  const nameLower = name.toLowerCase().trim();
  for (const [key, abbr] of Object.entries(COMPONENT_ABBREVIATIONS)) {
    if (key.toLowerCase().trim() === nameLower) return abbr;
  }
  // Match parcial (início do nome)
  for (const [key, abbr] of Object.entries(COMPONENT_ABBREVIATIONS)) {
    if (nameLower.startsWith(key.toLowerCase().trim()) || key.toLowerCase().trim().startsWith(nameLower)) return abbr;
  }
  return (name.substring(0, 10) + '.').toUpperCase();
};

// Cores do resultado
const RESULT_COLORS = {
  'APROVADO': 'bg-green-100 text-green-800 border-green-300',
  'REPROVADO': 'bg-red-100 text-red-800 border-red-300',
  'CURSANDO': 'bg-blue-100 text-blue-800 border-blue-300',
  'DESISTENTE': 'bg-gray-100 text-gray-800 border-gray-300',
  'TRANSFERIDO': 'bg-yellow-100 text-yellow-800 border-yellow-300',
  'PROMOVIDO': 'bg-green-100 text-green-800 border-green-300',
  'CONCLUIU': 'bg-green-100 text-green-800 border-green-300',
  'APROVADO COM DEPENDÊNCIA': 'bg-orange-100 text-orange-800 border-orange-300',
  'EM DEPENDÊNCIA': 'bg-purple-100 text-purple-800 border-purple-300'
};

// Quantidade de alunos por página
const STUDENTS_PER_PAGE = 10;

export function Promotion() {
  const navigate = useNavigate();
  const { accessToken, user } = useAuth();
  const { mantenedora } = useMantenedora();
  
  // Obter regras de aprovação da mantenedora
  const mediaAprovacao = mantenedora?.media_aprovacao ?? 5.0;
  const aprovacaoComDependencia = mantenedora?.aprovacao_com_dependencia ?? false;
  const maxComponentesDependencia = mantenedora?.max_componentes_dependencia ?? 2;
  
  // States
  const [loading, setLoading] = useState(false);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);
  const [courses, setCourses] = useState([]);
  const [gradesData, setGradesData] = useState([]);
  
  // Componentes formativos/Tempo Integral que NÃO entram no Livro de Promoção
  const FORMATIVOS_NOMES = [
    'arte e cultura',
    'contação de histórias e iniciação musical',
    'higiene e saúde',
    'linguagem recreativa com práticas de esporte e lazer',
    'recreação, esporte e lazer',
    'recreação e lazer',
  ];
  const isFormativoCourse = (c) => {
    const ap = (c.atendimento_programa || c.atendimento || '').toLowerCase().trim();
    if (ap.includes('integral')) return true;
    const nome = (c.name || '').toLowerCase().trim();
    return FORMATIVOS_NOMES.some(n => nome === n || nome.startsWith(n));
  };
  const regCourses = useMemo(() => courses.filter(c => !isFormativoCourse(c)), [courses]);
  
  // Filters
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);

  // Filtro de visualização rápida (resultado final)
  const [quickFilter, setQuickFilter] = useState('TODOS');

  // Processed data
  const [promotionData, setPromotionData] = useState([]);

  // Nº do Livro (gerado automaticamente ao selecionar turma+ano)
  const [bookNumber, setBookNumber] = useState('');
  
  // Anos disponíveis
  const years = [2025, 2026, 2027, 2028, 2029, 2030];

  // Séries elegíveis para o Livro de Promoção (Educação Infantil, 1º ao 9º Ano e EJA 1ª a 4ª Etapa)
  const SERIES_ELEGIVEIS = [
    // Educação Infantil
    'berçário', 'bercario', 'berçário i', 'berçário ii',
    'maternal', 'maternal i', 'maternal ii',
    'pré', 'pre', 'pré i', 'pré ii', 'pré-escola', 'pre-escola',
    // 1º e 2º Ano (conceitual)
    '1º ano', '1° ano', '1 ano', 'primeiro ano',
    '2º ano', '2° ano', '2 ano', 'segundo ano',
    // 3º ao 5º Ano (Anos Iniciais)
    '3º ano', '3° ano', '3 ano', 'terceiro ano',
    '4º ano', '4° ano', '4 ano', 'quarto ano',
    '5º ano', '5° ano', '5 ano', 'quinto ano',
    // 6º ao 9º Ano (Anos Finais)
    '6º ano', '6° ano', '6 ano', 'sexto ano',
    '7º ano', '7° ano', '7 ano', 'sétimo ano', 'setimo ano',
    '8º ano', '8° ano', '8 ano', 'oitavo ano',
    '9º ano', '9° ano', '9 ano', 'nono ano',
    // EJA (1ª a 4ª Etapa)
    '1ª etapa', '1° etapa', '1 etapa', 'primeira etapa',
    '2ª etapa', '2° etapa', '2 etapa', 'segunda etapa',
    '3ª etapa', '3° etapa', '3 etapa', 'terceira etapa',
    '4ª etapa', '4° etapa', '4 etapa', 'quarta etapa',
  ];

  // Função para verificar se a série é elegível
  const isSerieElegivel = (gradeLevel) => {
    if (!gradeLevel) return false;
    const gl = gradeLevel.toLowerCase();
    return SERIES_ELEGIVEIS.some(serie => gl.includes(serie.toLowerCase()));
  };

  // Carregar escolas
  useEffect(() => {
    const fetchSchools = async () => {
      try {
        const data = await schoolsAPI.list();
        setSchools(data || []);
      } catch (error) {
        console.error('Erro ao carregar escolas:', error);
        toast.error('Erro ao carregar escolas');
      }
    };
    fetchSchools();
  }, []);

  // Carregar turmas quando escola ou ano mudam (filtrar apenas séries elegíveis)
  useEffect(() => {
    const fetchClasses = async () => {
      if (!selectedSchool) {
        setClasses([]);
        return;
      }
      try {
        // Passar school_id diretamente (não como objeto)
        const data = await classesAPI.list(selectedSchool);
        // Filtrar apenas turmas elegíveis (Ed. Infantil, 1º-9º Ano, EJA) + excluir AEE + bater com o ano letivo selecionado
        const filteredClasses = (data || []).filter(c => {
          const isAEE = (c.atendimento_programa || c.atendimento || c.modalidade || '').toLowerCase().includes('aee');
          if (!isSerieElegivel(c.grade_level) || isAEE) return false;
          // Critical: turmas fora do ano letivo selecionado causam divergência com lista de alunos
          if (c.academic_year && c.academic_year !== selectedYear) return false;
          return true;
        });
        setClasses(filteredClasses);
        // Se a turma atual não pertence mais ao novo filtro, limpa a seleção
        setSelectedClass(prev => {
          if (!prev) return prev;
          return filteredClasses.some(c => c.id === prev) ? prev : '';
        });
      } catch (error) {
        console.error('Erro ao carregar turmas:', error);
        toast.error('Erro ao carregar turmas');
      }
    };
    fetchClasses();
  }, [selectedSchool, selectedYear]);

  // Carregar dados de promoção quando turma é selecionada
  const loadPromotionData = useCallback(async () => {
    if (!selectedClass) {
      setPromotionData([]);
      return;
    }
    
    setLoading(true);
    try {
      // Buscar dados da turma
      const classInfo = classes.find(c => c.id === selectedClass);
      if (!classInfo) {
        toast.error('Turma não encontrada');
        return;
      }
      
      // FONTE PRIMÁRIA: alunos pelo campo class_id (mesma base da tela de Cadastro de Alunos).
      // Garante que o Livro de Promoção mostre os mesmos alunos vinculados à turma.
      const studentsInClassResp = await studentsAPI.getAll({ class_id: selectedClass, page_size: 10000 });
      const studentsInClass = studentsInClassResp.items || [];

      // FONTE COMPLEMENTAR: matrículas (enrollments) para capturar histórico relevante
      // - Transferidos e desistentes (saíram da turma mas devem constar no livro anual)
      const STATUS_VALIDOS_LIVRO = new Set([
        'active', 'ativo',
        'transferred', 'transferencia', 'transferido',
        'dropout', 'desistencia', 'desistente',
      ]);
      let enrollments = await fetchEnrollments({ class_id: selectedClass });
      enrollments = (enrollments || []).filter(e => {
        const st = (e.status || 'active').toLowerCase();
        return STATUS_VALIDOS_LIVRO.has(st);
      });
      // Filtro por ano letivo (se campo existir na matrícula)
      enrollments = enrollments.filter(e => !e.academic_year || e.academic_year === selectedYear);

      // Unir alunos: primários (students.class_id) + complementares (via enrollments, ex: transferidos)
      const studentsMap = new Map();
      studentsInClass.forEach(s => studentsMap.set(s.id, s));

      const enrolledIds = enrollments.map(e => e.student_id);
      const missingIds = enrolledIds.filter(id => !studentsMap.has(id));
      if (missingIds.length > 0) {
        // Carregar os alunos faltantes (status transferred/dropout que já não têm class_id atual)
        const allStudentsResp = await studentsAPI.getAll({ page_size: 10000 });
        const allStudentsData = allStudentsResp.items || [];
        allStudentsData
          .filter(s => missingIds.includes(s.id))
          .forEach(s => studentsMap.set(s.id, s));
      }

      const filteredStudents = Array.from(studentsMap.values());
      setStudents(filteredStudents);

      if (filteredStudents.length === 0) {
        toast.info('Nenhum aluno vinculado a esta turma');
        setPromotionData([]);
        setLoading(false);
        return;
      }

      // Para os mapeamentos abaixo, manter enrollments indexadas por student_id
      // (se aluno não tem enrollment na turma, usamos um placeholder 'active')
      const studentIds = filteredStudents.map(s => s.id);
      
      // Buscar componentes curriculares filtrados pelas alocações de professores da turma
      const coursesData = await coursesAPI.getAll(classInfo.education_level);
      let filteredCourses = coursesData || [];
      
      // Filtrar por teacher_assignments (componentes efetivamente alocados na turma)
      let usedTeacherAssignments = false;
      try {
        const assignments = await teacherAssignmentAPI.list({
          class_id: selectedClass
        });
        if (assignments && assignments.length > 0) {
          const assignedCourseIds = [...new Set(assignments.map(a => a.course_id).filter(Boolean))];
          // Buscar TODOS os cursos para pegar também os de integral/AEE
          const allCourses = await coursesAPI.getAll();
          filteredCourses = (allCourses || []).filter(c => assignedCourseIds.includes(c.id));
          usedTeacherAssignments = true;
        }
      } catch (e) {
        console.warn('Erro ao buscar alocações:', e.message);
      }
      
      // Filtro por atendimento_programa (só no fallback, quando não há teacher_assignments)
      if (!usedTeacherAssignments) {
        const turmaAtendimento = (classInfo.atendimento_programa || '').toLowerCase();
        filteredCourses = filteredCourses.filter(course => {
          const courseAtendimento = (course.atendimento_programa || course.atendimento || '').toLowerCase();
          if (turmaAtendimento === 'atendimento_integral' || turmaAtendimento === 'integral') {
            return !courseAtendimento || courseAtendimento === 'atendimento_integral' || courseAtendimento === 'integral';
          } else if (turmaAtendimento === 'aee') {
            return courseAtendimento === 'aee';
          } else {
            return !courseAtendimento;
          }
        });
      }
      
      const orderedCourses = ordenarComponentes(filteredCourses, classInfo.grade_level);
      setCourses(orderedCourses);
      
      // Buscar notas de todos os alunos da turma
      const gradesPromises = studentIds.map(studentId => 
        gradesAPI.getAll({ student_id: studentId, academic_year: selectedYear })
      );
      const allGrades = await Promise.all(gradesPromises);
      
      // Processar dados de promoção
      const processed = filteredStudents.map((student) => {
        const studentEnrollment = enrollments.find(e => e.student_id === student.id);
        
        // Encontrar o índice correto das notas baseado no studentId
        const studentIdIndex = studentIds.indexOf(student.id);
        const studentGrades = studentIdIndex >= 0 ? (allGrades[studentIdIndex] || []) : [];
        
        // Organizar notas por componente
        const gradesByComponent = {};
        studentGrades.forEach(grade => {
          const course = (orderedCourses || []).find(c => c.id === grade.course_id);
          if (course) {
            // As notas já vêm no formato correto (b1, b2, b3, b4, rec_s1, rec_s2)
            gradesByComponent[course.id] = {
              courseName: course.name,
              b1: grade.b1 !== undefined ? grade.b1 : null,
              b2: grade.b2 !== undefined ? grade.b2 : null,
              b3: grade.b3 !== undefined ? grade.b3 : null,
              b4: grade.b4 !== undefined ? grade.b4 : null,
              rec1: grade.rec_s1 !== undefined ? grade.rec_s1 : null,
              rec2: grade.rec_s2 !== undefined ? grade.rec_s2 : null,
              totalPoints: 0,
              finalAverage: null
            };
          }
        });
        
        // Regime conceitual (Ed. Infantil, 1º/2º Ano): conceito final = MAIOR conceito entre os bimestres
        const classUsaConceito = usaAvaliacaoConceitual(classInfo.grade_level, classInfo.education_level);

        // Calcular total de pontos e média final por componente
        Object.keys(gradesByComponent).forEach(courseId => {
          const comp = gradesByComponent[courseId];

          const hasAnyGrade = comp.b1 !== null || comp.b2 !== null || comp.b3 !== null || comp.b4 !== null;
          if (!hasAnyGrade) return;

          if (classUsaConceito) {
            // Conceito final = MAIOR valor registrado (sem média ponderada, sem recuperação)
            const vals = [comp.b1, comp.b2, comp.b3, comp.b4].filter(v => v !== null && v !== undefined);
            comp.totalPoints = null; // não aplicável
            comp.finalAverage = vals.length > 0 ? Math.max(...vals) : null;
            return;
          }

          // Regime numérico: média ponderada com recuperações
          let b1 = comp.b1 !== null ? comp.b1 : 0;
          let b2 = comp.b2 !== null ? comp.b2 : 0;
          let b3 = comp.b3 !== null ? comp.b3 : 0;
          let b4 = comp.b4 !== null ? comp.b4 : 0;

          // Aplicar recuperação se houver (substitui a menor nota do semestre)
          if (comp.rec1 !== null) {
            if (comp.b1 !== null && comp.b2 !== null) {
              const minGrade = Math.min(b1, b2);
              if (comp.rec1 > minGrade) {
                if (b1 <= b2) b1 = comp.rec1; else b2 = comp.rec1;
              }
            }
          }
          if (comp.rec2 !== null) {
            if (comp.b3 !== null && comp.b4 !== null) {
              const minGrade = Math.min(b3, b4);
              if (comp.rec2 > minGrade) {
                if (b3 <= b4) b3 = comp.rec2; else b4 = comp.rec2;
              }
            }
          }

          // Calcular média ponderada: (B1×2 + B2×3 + B3×2 + B4×3) / 10
          const total = (b1 * 2) + (b2 * 3) + (b3 * 2) + (b4 * 3);
          comp.totalPoints = total;
          comp.finalAverage = total / 10;
        });
        
        // Determinar resultado final
        let result = 'CURSANDO';
        const status = studentEnrollment?.status?.toLowerCase();

        if (status === 'desistencia' || status === 'desistente' || status === 'dropout') {
          result = 'DESISTENTE';
        } else if (status === 'transferencia' || status === 'transferido' || status === 'transferred') {
          result = 'TRANSFERIDO';
        } else {
          // Só considerar componentes REGULARES (atendimento_programa diferente de regular é formativo)
          const regEntries = Object.entries(gradesByComponent)
            .filter(([courseId]) => {
              const course = courses.find(c => c.id === courseId);
              if (!course) return true;
              const ap = (course.atendimento_programa || course.atendimento || '').toLowerCase();
              return !ap.includes('integral') && !ap.includes('aee');
            });
          
          const regAverages = regEntries.map(([, c]) => c.finalAverage).filter(a => a !== null);
          
          // Verificar se B4 foi registrado para todos os componentes regulares
          const allB4Registered = regEntries.every(([, c]) => c.b4 !== null && c.b4 !== undefined);
          
          if (regAverages.length > 0) {
            const allApproved = regAverages.every(avg => avg >= mediaAprovacao);
            if (allApproved) {
              result = 'APROVADO';
            } else if (!allB4Registered) {
              // B4 não registrado: não pode reprovar ainda
              result = 'CURSANDO';
            } else {
              // B4 registrado: pode aplicar lógica completa
              const failedCount = regAverages.filter(avg => avg < mediaAprovacao).length;
              
              if (aprovacaoComDependencia && failedCount <= maxComponentesDependencia) {
                result = 'APROVADO COM DEPENDÊNCIA';
              } else if (failedCount > maxComponentesDependencia) {
                result = 'REPROVADO';
              } else {
                result = 'CURSANDO';
              }
            }
          }
        }
        
        return {
          number: 0, // Será renumerado depois da ordenação
          studentId: student.id,
          studentName: student.full_name,
          sex: (student.sex || '').toLowerCase() === 'masculino' ? 'M' : 'F',
          enrollment: studentEnrollment,
          grades: gradesByComponent,
          result
        };
      });
      
      // Ordenar por nome
      processed.sort((a, b) => a.studentName.localeCompare(b.studentName));
      
      // Renumerar
      processed.forEach((item, index) => {
        item.number = index + 1;
      });
      
      setPromotionData(processed);
      setGradesData(allGrades.flat());
      
    } catch (error) {
      console.error('Erro ao carregar dados de promoção:', error);
      toast.error('Erro ao carregar dados de promoção');
    } finally {
      setLoading(false);
    }
  }, [selectedClass, selectedYear, classes, mediaAprovacao, aprovacaoComDependencia, maxComponentesDependencia]);

  useEffect(() => {
    loadPromotionData();
  }, [loadPromotionData]);

  // Reset página quando turma muda
  useEffect(() => {
    setCurrentPage(1);
  }, [selectedClass]);

  // Reset página quando filtro rápido muda
  useEffect(() => {
    setCurrentPage(1);
  }, [quickFilter]);

  // Carregar (ou criar) Nº do Livro ao selecionar turma + ano
  useEffect(() => {
    if (!selectedClass) {
      setBookNumber('');
      return;
    }
    const token = localStorage.getItem('accessToken');
    fetch(`${API_URL}/api/documents/promotion/${selectedClass}/book-number?academic_year=${selectedYear}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => setBookNumber(data?.book_number || ''))
      .catch(() => setBookNumber(''));
  }, [selectedClass, selectedYear]);

  // Aplicar filtro de visualização rápida
  const filteredPromotionData = useMemo(() => {
    if (quickFilter === 'TODOS') return promotionData;
    if (quickFilter === 'APROVADOS') {
      return promotionData.filter(p =>
        p.result === 'APROVADO' ||
        p.result === 'APROVADO COM DEPENDÊNCIA' ||
        p.result === 'PROMOVIDO' ||
        p.result === 'CONCLUIU'
      );
    }
    return promotionData.filter(p => p.result === quickFilter);
  }, [promotionData, quickFilter]);

  // Calcular dados paginados
  const totalPages = Math.ceil(filteredPromotionData.length / STUDENTS_PER_PAGE);
  const startIndex = (currentPage - 1) * STUDENTS_PER_PAGE;
  const endIndex = startIndex + STUDENTS_PER_PAGE;
  const paginatedData = filteredPromotionData.slice(startIndex, endIndex);

  // Navegação de páginas
  const goToPage = (page) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  // Gerar PDF do Livro de Promoção
  const handleDownloadPDF = async () => {
    if (!selectedClass) {
      toast.error('Selecione uma turma');
      return;
    }
    
    try {
      setLoading(true);
      const response = await fetch(
        `${API_URL}/api/documents/promotion/${selectedClass}?academic_year=${selectedYear}`,
        {
          headers: {
            'Authorization': `Bearer ${accessToken}`
          }
        }
      );
      
      if (!response.ok) {
        throw new Error('Erro ao gerar PDF');
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `livro_promocao_${selectedYear}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      toast.success('PDF gerado com sucesso!');
    } catch (error) {
      console.error('Erro ao gerar PDF:', error);
      toast.error('Erro ao gerar PDF. Verifique se o endpoint está disponível.');
    } finally {
      setLoading(false);
    }
  };

  // Obter turma selecionada
  const selectedClassInfo = classes.find(c => c.id === selectedClass);
  const selectedSchoolInfo = schools.find(s => s.id === selectedSchool);

  // Regime de avaliação: conceitual (Ed. Infantil + 1º/2º Ano) ou numérico
  const usaConceito = !!selectedClassInfo && usaAvaliacaoConceitual(
    selectedClassInfo.grade_level,
    selectedClassInfo.education_level,
  );
  const gradeLevelForConc = selectedClassInfo?.grade_level || null;

  const fmtGrade = (val) => {
    if (val === null || val === undefined) return '-';
    if (usaConceito) {
      return valorParaConceito(val, gradeLevelForConc);
    }
    return typeof val === 'number' ? val.toFixed(1) : val;
  };

  // Estatísticas
  const stats = {
    total: promotionData.length,
    approved: promotionData.filter(p => p.result === 'APROVADO' || p.result === 'APROVADO COM DEPENDÊNCIA' || p.result === 'PROMOVIDO' || p.result === 'CONCLUIU').length,
    failed: promotionData.filter(p => p.result === 'REPROVADO').length,
    inProgress: promotionData.filter(p => p.result === 'CURSANDO').length,
    dropped: promotionData.filter(p => p.result === 'DESISTENTE').length,
    transferred: promotionData.filter(p => p.result === 'TRANSFERIDO').length
  };

  return (
    <Layout>
      <div className="space-y-6" data-testid="promotion-page">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
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
              <h1 className="text-2xl font-bold text-gray-900">Livro de Promoção</h1>
            </div>
          </div>
          
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={loadPromotionData}
              disabled={loading || !selectedClass}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
            <Button
              onClick={handleDownloadPDF}
              disabled={loading || !selectedClass || promotionData.length === 0}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              <Download className="h-4 w-4 mr-2" />
              Gerar PDF
            </Button>
          </div>
        </div>

        {/* Filtros */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Filter className="h-4 w-4" />
              Filtros
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Ano Letivo
                </label>
                <Select value={String(selectedYear)} onValueChange={(v) => setSelectedYear(Number(v))}>
                  <SelectTrigger data-testid="year-select">
                    <SelectValue placeholder="Selecione o ano" />
                  </SelectTrigger>
                  <SelectContent>
                    {years.map(year => (
                      <SelectItem key={year} value={String(year)}>{year}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Escola
                </label>
                <Select value={selectedSchool} onValueChange={setSelectedSchool}>
                  <SelectTrigger data-testid="school-select">
                    <SelectValue placeholder="Selecione a escola" />
                  </SelectTrigger>
                  <SelectContent>
                    {schools.map(school => (
                      <SelectItem key={school.id} value={school.id}>
                        {school.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Turma
                </label>
                <Select value={selectedClass} onValueChange={setSelectedClass} disabled={!selectedSchool}>
                  <SelectTrigger data-testid="class-select">
                    <SelectValue placeholder={
                      !selectedSchool 
                        ? "Selecione a escola primeiro" 
                        : classes.length === 0 
                          ? "Nenhuma turma elegível" 
                          : "Selecione a turma"
                    } />
                  </SelectTrigger>
                  <SelectContent>
                    {classes.length === 0 ? (
                      <SelectItem value="none" disabled>
                        Nenhuma turma da Ed. Infantil, 1º ao 9º Ano ou EJA
                      </SelectItem>
                    ) : (
                      classes.map(cls => (
                        <SelectItem key={cls.id} value={cls.id}>
                          {cls.name}
                        </SelectItem>
                      ))
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 mb-1 block">
                  Nº do Livro
                </label>
                <input
                  type="text"
                  value={bookNumber || (selectedClass ? '...' : '')}
                  readOnly
                  disabled
                  placeholder="Selecione uma turma"
                  data-testid="book-number-input"
                  className="w-full h-10 px-3 rounded-md border border-gray-300 bg-gray-50 text-gray-700 font-mono text-sm cursor-not-allowed"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Estatísticas */}
        {selectedClass && promotionData.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
            <Card className="bg-white">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <Users className="h-8 w-8 text-blue-500" />
                  <div>
                    <p className="text-sm text-gray-500">Total</p>
                    <p className="text-2xl font-bold">{stats.total}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card className="bg-green-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <CheckCircle className="h-8 w-8 text-green-500" />
                  <div>
                    <p className="text-sm text-gray-500">Aprovados</p>
                    <p className="text-2xl font-bold text-green-700">{stats.approved}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card className="bg-red-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <XCircle className="h-8 w-8 text-red-500" />
                  <div>
                    <p className="text-sm text-gray-500">Reprovados</p>
                    <p className="text-2xl font-bold text-red-700">{stats.failed}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card className="bg-blue-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <BookOpen className="h-8 w-8 text-blue-500" />
                  <div>
                    <p className="text-sm text-gray-500">Cursando</p>
                    <p className="text-2xl font-bold text-blue-700">{stats.inProgress}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card className="bg-gray-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <AlertTriangle className="h-8 w-8 text-gray-500" />
                  <div>
                    <p className="text-sm text-gray-500">Desistentes</p>
                    <p className="text-2xl font-bold text-gray-700">{stats.dropped}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card className="bg-yellow-50">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <School className="h-8 w-8 text-yellow-600" />
                  <div>
                    <p className="text-sm text-gray-500">Transferidos</p>
                    <p className="text-2xl font-bold text-yellow-700">{stats.transferred}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Tabela de Promoção */}
        {loading ? (
          <Card>
            <CardContent className="p-8 flex items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
              <span className="ml-2 text-gray-600">Carregando dados...</span>
            </CardContent>
          </Card>
        ) : !selectedClass ? (
          <Card>
            <CardContent className="p-8 text-center text-gray-500">
              <FileText className="h-12 w-12 mx-auto mb-4 text-gray-400" />
              <p>Selecione uma escola e turma para visualizar o Livro de Promoção</p>
            </CardContent>
          </Card>
        ) : promotionData.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-gray-500">
              <Users className="h-12 w-12 mx-auto mb-4 text-gray-400" />
              <p>Nenhum aluno matriculado nesta turma</p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            {/* Visualização rápida (filtros por resultado) */}
            <div className="px-4 pt-4 pb-3 border-b bg-slate-50 flex flex-wrap items-center gap-2" data-testid="quick-filter-bar">
              <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide mr-2">
                Visualização rápida:
              </span>
              {[
                { key: 'TODOS', label: `Todos (${stats.total})`, active: 'bg-slate-800 text-white border-slate-800' },
                { key: 'APROVADOS', label: `Aprovados (${stats.approved})`, active: 'bg-green-600 text-white border-green-600' },
                { key: 'REPROVADO', label: `Reprovados (${stats.failed})`, active: 'bg-red-600 text-white border-red-600' },
                { key: 'CURSANDO', label: `Cursando (${stats.inProgress})`, active: 'bg-blue-600 text-white border-blue-600' },
                { key: 'DESISTENTE', label: `Desistentes (${stats.dropped})`, active: 'bg-gray-500 text-white border-gray-500' },
                { key: 'TRANSFERIDO', label: `Transferidos (${stats.transferred})`, active: 'bg-yellow-500 text-white border-yellow-500' },
              ].map(chip => {
                const isActive = quickFilter === chip.key;
                return (
                  <button
                    key={chip.key}
                    onClick={() => setQuickFilter(chip.key)}
                    data-testid={`quick-filter-${chip.key.toLowerCase()}`}
                    className={`px-3 py-1 rounded-full border text-xs font-semibold transition-all ${
                      isActive
                        ? chip.active + ' shadow-sm'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-100'
                    }`}
                  >
                    {chip.label}
                  </button>
                );
              })}
              {quickFilter !== 'TODOS' && (
                <span className="ml-auto text-xs text-gray-500" data-testid="quick-filter-summary">
                  Exibindo {filteredPromotionData.length} de {promotionData.length} alunos
                </span>
              )}
            </div>
            <CardContent className="p-0">
              {paginatedData.length === 0 ? (
                <div className="p-8 text-center text-gray-500" data-testid="quick-filter-empty">
                  <Filter className="h-10 w-10 mx-auto mb-3 text-gray-400" />
                  <p>Nenhum aluno corresponde ao filtro selecionado.</p>
                  <button
                    onClick={() => setQuickFilter('TODOS')}
                    className="mt-3 text-sm text-emerald-700 hover:text-emerald-800 underline"
                  >
                    Mostrar todos os alunos
                  </button>
                </div>
              ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="bg-slate-100 border-b-2 border-slate-300">
                      <th rowSpan={2} className="px-2 py-2 text-left font-semibold border-r sticky left-0 bg-slate-100 z-10">N°</th>
                      <th rowSpan={2} className="px-2 py-2 text-left font-semibold border-r min-w-[200px] sticky left-8 bg-slate-100 z-10">LISTA DE ALUNOS</th>
                      <th rowSpan={2} className="px-2 py-2 text-center font-semibold border-r-2 border-slate-400 w-10">SEXO</th>
                      
                      {/* Bimestres 1-4 com NOTAS (somente regulares; integral ignorado por regra de negócio) */}
                      {['1º', '2º', '3º', '4º'].map((bim, bi) => (
                        <React.Fragment key={`bim-${bi}`}>
                          <th colSpan={regCourses.length} className={`px-2 py-1 text-center font-semibold border-r-2 border-slate-400 ${bi % 2 === 0 ? 'bg-blue-50' : 'bg-green-50'}`}>
                            {usaConceito ? `CONCEITOS ${bim} BIMESTRE` : `NOTAS ${bim} BIMESTRE`}
                          </th>
                          {/* Recuperação — apenas turmas com avaliação numérica (Ed. Infantil, 1º/2º Ano não têm) */}
                          {!usaConceito && (bi === 1) && (
                            <th colSpan={regCourses.length} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-yellow-50">
                              RECUPERAÇÃO 1º SEM
                            </th>
                          )}
                          {!usaConceito && (bi === 3) && (
                            <th colSpan={regCourses.length} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-yellow-50">
                              RECUPERAÇÃO 2º SEM
                            </th>
                          )}
                        </React.Fragment>
                      ))}

                      {/* Total (só em regime numérico) */}
                      {!usaConceito && (
                        <th colSpan={regCourses.length} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-purple-50">
                          TOTAL PONTOS ANUAIS
                        </th>
                      )}
                      {/* Média */}
                      <th colSpan={regCourses.length} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-orange-50">
                        {usaConceito ? 'CONCEITO FINAL' : 'MÉDIA FINAL'}
                      </th>
                      {/* Resultado */}
                      <th rowSpan={2} className="px-2 py-2 text-center font-semibold min-w-[100px] bg-slate-200">
                        RESULTADO FINAL
                      </th>
                    </tr>
                    
                    {/* Sub-cabeçalho com nomes dos componentes */}
                    <tr className="bg-slate-50 border-b">
                      {/* Sub-cabeçalho: somente componentes regulares; Rec e Total ocultos em turmas conceituais */}
                      {(usaConceito
                        ? ['b1', 'b2', 'b3', 'b4', 'finalAverage']
                        : ['b1', 'b2', 'rec1', 'b3', 'b4', 'rec2', 'totalPoints', 'finalAverage']
                      ).map((section) => (
                        <React.Fragment key={`sub-${section}`}>
                          {regCourses.map((course, idx) => (
                            <th key={`${section}-${course.id}`} className={`px-1 py-1 text-center font-normal text-[10px] whitespace-nowrap ${idx === regCourses.length - 1 ? 'border-r-2 border-slate-400' : 'border-r'}`}>
                              {abbreviateComponent(course.name)}
                            </th>
                          ))}
                        </React.Fragment>
                      ))}
                    </tr>
                  </thead>
                  
                  <tbody>
                    {paginatedData.map((student, rowIdx) => (
                      <tr key={student.studentId} className={rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-2 py-2 border-r text-center sticky left-0 bg-inherit z-10">{student.number}</td>
                        <td className="px-2 py-2 border-r font-medium sticky left-8 bg-inherit z-10 whitespace-nowrap">
                          {student.studentName}
                        </td>
                        <td className="px-2 py-2 border-r-2 border-slate-400 text-center">{student.sex}</td>
                        
                        {/* Notas por seção (regulares; Rec/Total ocultos em turmas conceituais) */}
                        {(usaConceito
                          ? ['b1', 'b2', 'b3', 'b4', 'finalAverage']
                          : ['b1', 'b2', 'rec1', 'b3', 'b4', 'rec2', 'totalPoints', 'finalAverage']
                        ).map((period) => (
                          <React.Fragment key={`data-${period}`}>
                            {regCourses.map((course, idx) => {
                              const gradeData = student.grades[course.id];
                              let value = '-';
                              if (gradeData) {
                                if (period === 'totalPoints') {
                                  value = gradeData.totalPoints ? (usaConceito ? '-' : gradeData.totalPoints.toFixed(1)) : '-';
                                } else if (period === 'finalAverage') {
                                  value = gradeData.finalAverage !== null && gradeData.finalAverage !== undefined ? fmtGrade(gradeData.finalAverage) : '-';
                                } else {
                                  value = gradeData[period] !== null && gradeData[period] !== undefined ? fmtGrade(gradeData[period]) : '-';
                                }
                              }
                              const isLowGrade = !usaConceito && period === 'finalAverage' && gradeData?.finalAverage !== null && gradeData?.finalAverage < 6;
                              const isLast = idx === regCourses.length - 1;
                              return (
                                <td key={`${period}-${course.id}`} className={`px-1 py-2 text-center text-[10px] ${isLast ? 'border-r-2 border-slate-400' : 'border-r'} ${isLowGrade ? 'bg-red-100 text-red-700 font-bold' : ''}`}>
                                  {value}
                                </td>
                              );
                            })}
                          </React.Fragment>
                        ))}
                        
                        {/* Resultado Final */}
                        <td className="px-2 py-2 text-center">
                          <Badge className={`${RESULT_COLORS[student.result] || 'bg-gray-100'} text-[10px] font-semibold`}>
                            {student.result}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Paginação */}
        {selectedClass && filteredPromotionData.length > STUDENTS_PER_PAGE && (
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  Mostrando {startIndex + 1} a {Math.min(endIndex, filteredPromotionData.length)} de {filteredPromotionData.length} alunos
                </div>
                
                <div className="flex items-center gap-2">
                  {/* Primeira página */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => goToPage(1)}
                    disabled={currentPage === 1}
                    className="h-8 w-8 p-0"
                  >
                    <ChevronsLeft className="h-4 w-4" />
                  </Button>
                  
                  {/* Página anterior */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => goToPage(currentPage - 1)}
                    disabled={currentPage === 1}
                    className="h-8 w-8 p-0"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  
                  {/* Indicador de página */}
                  <div className="flex items-center gap-1 mx-2">
                    {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                      <Button
                        key={page}
                        variant={currentPage === page ? "default" : "outline"}
                        size="sm"
                        onClick={() => goToPage(page)}
                        className={`h-8 w-8 p-0 ${currentPage === page ? 'bg-emerald-600 hover:bg-emerald-700' : ''}`}
                      >
                        {page}
                      </Button>
                    ))}
                  </div>
                  
                  {/* Próxima página */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => goToPage(currentPage + 1)}
                    disabled={currentPage === totalPages}
                    className="h-8 w-8 p-0"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                  
                  {/* Última página */}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => goToPage(totalPages)}
                    disabled={currentPage === totalPages}
                    className="h-8 w-8 p-0"
                  >
                    <ChevronsRight className="h-4 w-4" />
                  </Button>
                </div>
                
                <div className="text-sm text-gray-600">
                  Página {currentPage} de {totalPages}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}

export default Promotion;
