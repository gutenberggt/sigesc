import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Loader2, Download, FileText, School, Users, BookOpen, Filter, RefreshCw, CheckCircle, XCircle, AlertTriangle, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Home } from 'lucide-react';
import { schoolsAPI, classesAPI, gradesAPI, coursesAPI, studentsAPI } from '@/services/api';
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
  'Língua Portuguesa': 'Lin. Port.',
  'Arte': 'Arte',
  'Educação Física': 'Ed. Fís.',
  'Língua Inglesa': 'Lin. Ingl.',
  'Inglês': 'Lin. Ingl.',
  'Matemática': 'Mat.',
  'Ciências': 'Ciênc.',
  'História': 'Hist.',
  'Geografia': 'Geo.',
  'Ensino Religioso': 'Ed. Rel.',
  'Educação Ambiental e Clima': 'Ed. A. Cl.',
  'Estudos Amazônicos': 'Est. Amaz.',
  'Literatura e Redação': 'Lit. e red.',
  'Recreação e Lazer': 'R. E. Laz.',
  'Recreação, Esporte e Lazer': 'R. E. Laz.',
  'Linguagem Recreativa com Práticas de Esporte e Lazer': 'R. E. Laz.',
  'Arte e Cultura': 'Art. e Cul.',
  'Tecnologia da Informação': 'Tec. Inf.',
  'Tecnologia e Informática': 'Tec. Inf.',
  'Acompanhamento Pedagógico de Língua Portuguesa': 'APL Port.',
  'Acompanhamento Pedagógico de Matemática': 'AP Mat.',
  'Acomp. Ped. de Língua Portuguesa': 'APL Port.',
  'Acomp. Ped. de Matemática': 'AP Mat.',
  'Contação de Histórias e Iniciação Musical': 'Cont. Hist.',
  'Corpo, gestos e movimentos': 'Corp. Gest.',
  'Escuta, fala, pensamento e imaginação': 'Esc. Fala',
  'Espaços, tempos, quantidades, relações e transformações': 'Esp. Temp.',
  'Higiene e Saúde': 'Hig. Saúde',
  'O eu, o outro e nós': 'Eu Out. Nós',
  'Traço, sons, cores e formas': 'Traç. Sons'
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
  return COMPONENT_ABBREVIATIONS[name] || name.substring(0, 10) + '.';
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
  const mediaAprovacao = mantenedora?.media_aprovacao || 5.0;
  const aprovacaoComDependencia = mantenedora?.aprovacao_com_dependencia || false;
  const maxComponentesDependencia = mantenedora?.max_componentes_dependencia || 2;
  
  // States
  const [loading, setLoading] = useState(false);
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);
  const [courses, setCourses] = useState([]);
  const [gradesData, setGradesData] = useState([]);
  
  // Filters
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedYear, setSelectedYear] = useState(2025);
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  
  // Processed data
  const [promotionData, setPromotionData] = useState([]);
  
  // Anos disponíveis
  const years = [2025, 2026, 2027, 2028, 2029, 2030];

  // Séries elegíveis para o Livro de Promoção (3º ao 9º Ano e EJA 1ª a 4ª Etapa)
  const SERIES_ELEGIVEIS = [
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

  // Carregar turmas quando escola é selecionada (filtrar apenas séries elegíveis)
  useEffect(() => {
    const fetchClasses = async () => {
      if (!selectedSchool) {
        setClasses([]);
        return;
      }
      try {
        // Passar school_id diretamente (não como objeto)
        const data = await classesAPI.list(selectedSchool);
        // Filtrar apenas turmas do 3º ao 9º Ano e EJA
        const filteredClasses = (data || []).filter(c => isSerieElegivel(c.grade_level));
        setClasses(filteredClasses);
      } catch (error) {
        console.error('Erro ao carregar turmas:', error);
        toast.error('Erro ao carregar turmas');
      }
    };
    fetchClasses();
  }, [selectedSchool]);

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
      
      // Buscar matrículas da turma (buscar todas, depois filtrar)
      let enrollments = await fetchEnrollments({ class_id: selectedClass });
      
      // Filtrar por ano se houver ano na matrícula, ou considerar todas
      enrollments = (enrollments || []).filter(e => 
        !e.academic_year || e.academic_year === selectedYear
      );
      
      if (!enrollments || enrollments.length === 0) {
        // Tentar buscar todas as matrículas sem filtro de ano
        enrollments = await fetchEnrollments({ class_id: selectedClass });
        if (!enrollments || enrollments.length === 0) {
          toast.info('Nenhum aluno matriculado nesta turma');
          setPromotionData([]);
          setLoading(false);
          return;
        }
      }
      
      // Buscar dados dos alunos
      const studentIds = enrollments.map(e => e.student_id);
      const studentsData = await studentsAPI.getAll();
      const filteredStudents = (studentsData || []).filter(s => studentIds.includes(s.id));
      setStudents(filteredStudents);
      
      // Buscar componentes curriculares e ordenar conforme o nível de ensino
      const coursesData = await coursesAPI.getAll(classInfo.education_level);
      const orderedCourses = ordenarComponentes(coursesData || [], classInfo.grade_level);
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
        
        // Calcular total de pontos e média final por componente (usando média ponderada)
        Object.keys(gradesByComponent).forEach(courseId => {
          const comp = gradesByComponent[courseId];
          
          // Obter notas bimestrais (usar 0 se null)
          let b1 = comp.b1 !== null ? comp.b1 : 0;
          let b2 = comp.b2 !== null ? comp.b2 : 0;
          let b3 = comp.b3 !== null ? comp.b3 : 0;
          let b4 = comp.b4 !== null ? comp.b4 : 0;
          
          // Verificar se tem pelo menos uma nota registrada
          const hasAnyGrade = comp.b1 !== null || comp.b2 !== null || comp.b3 !== null || comp.b4 !== null;
          
          if (hasAnyGrade) {
            // Aplicar recuperação se houver (substitui a menor nota do semestre)
            if (comp.rec1 !== null) {
              // Recuperação do 1º semestre - substitui a menor nota entre B1 e B2
              if (comp.b1 !== null && comp.b2 !== null) {
                const minGrade = Math.min(b1, b2);
                if (comp.rec1 > minGrade) {
                  if (b1 <= b2) {
                    b1 = comp.rec1;
                  } else {
                    b2 = comp.rec1;
                  }
                }
              }
            }
            if (comp.rec2 !== null) {
              // Recuperação do 2º semestre - substitui a menor nota entre B3 e B4
              if (comp.b3 !== null && comp.b4 !== null) {
                const minGrade = Math.min(b3, b4);
                if (comp.rec2 > minGrade) {
                  if (b3 <= b4) {
                    b3 = comp.rec2;
                  } else {
                    b4 = comp.rec2;
                  }
                }
              }
            }
            
            // Calcular média ponderada: (B1×2 + B2×3 + B3×2 + B4×3) / 10
            const total = (b1 * 2) + (b2 * 3) + (b3 * 2) + (b4 * 3);
            comp.totalPoints = total;
            comp.finalAverage = total / 10;
          }
        });
        
        // Determinar resultado final
        let result = 'CURSANDO';
        const status = studentEnrollment?.status?.toLowerCase();
        
        if (status === 'desistencia' || status === 'desistente') {
          result = 'DESISTENTE';
        } else if (status === 'transferencia' || status === 'transferido') {
          result = 'TRANSFERIDO';
        } else {
          // Verificar se todas as médias são >= média de aprovação configurada na mantenedora
          const averages = Object.values(gradesByComponent).map(c => c.finalAverage).filter(a => a !== null);
          if (averages.length > 0) {
            const allApproved = averages.every(avg => avg >= mediaAprovacao);
            if (allApproved) {
              result = 'APROVADO';
            } else {
              // Verificar quantos componentes reprovados (abaixo da média de aprovação)
              const failedCount = averages.filter(avg => avg < mediaAprovacao).length;
              
              // Aplicar regras de aprovação com dependência
              if (aprovacaoComDependencia && failedCount <= maxComponentesDependencia) {
                result = 'APROVADO COM DEPENDÊNCIA';
              } else if (failedCount > maxComponentesDependencia) {
                result = 'REPROVADO';
              } else {
                result = 'CURSANDO'; // Aguardando recuperação ou análise
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

  // Calcular dados paginados
  const totalPages = Math.ceil(promotionData.length / STUDENTS_PER_PAGE);
  const startIndex = (currentPage - 1) * STUDENTS_PER_PAGE;
  const endIndex = startIndex + STUDENTS_PER_PAGE;
  const paginatedData = promotionData.slice(startIndex, endIndex);

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
              <p className="text-gray-500 mt-1">
                3º ao 9º Ano e EJA (1ª a 4ª Etapa)
              </p>
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
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                  Turma (3º ao 9º Ano / EJA)
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
                        Nenhuma turma do 3º ao 9º Ano ou EJA
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
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="bg-slate-100 border-b-2 border-slate-300">
                      <th rowSpan={2} className="px-2 py-2 text-left font-semibold border-r sticky left-0 bg-slate-100 z-10">N°</th>
                      <th rowSpan={2} className="px-2 py-2 text-left font-semibold border-r min-w-[200px] sticky left-8 bg-slate-100 z-10">LISTA DE ALUNOS</th>
                      <th rowSpan={2} className="px-2 py-2 text-center font-semibold border-r-2 border-slate-400 w-10">SEXO</th>
                      
                      {/* 1º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-blue-50">
                        NOTAS 1º BIMESTRE
                      </th>
                      
                      {/* 2º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-green-50">
                        NOTAS 2º BIMESTRE
                      </th>
                      
                      {/* Recuperação 1º Semestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-yellow-50">
                        RECUPERAÇÃO 1º SEM
                      </th>
                      
                      {/* 3º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-blue-50">
                        NOTAS 3º BIMESTRE
                      </th>
                      
                      {/* 4º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-green-50">
                        NOTAS 4º BIMESTRE
                      </th>
                      
                      {/* Recuperação 2º Semestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-yellow-50">
                        RECUPERAÇÃO 2º SEM
                      </th>
                      
                      {/* Total Pontos Anuais */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-purple-50">
                        TOTAL PONTOS ANUAIS
                      </th>
                      
                      {/* Média Final */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r-2 border-slate-400 bg-orange-50">
                        MÉDIA FINAL
                      </th>
                      
                      {/* Resultado */}
                      <th rowSpan={2} className="px-2 py-2 text-center font-semibold min-w-[100px] bg-slate-200">
                        RESULTADO FINAL
                      </th>
                    </tr>
                    
                    {/* Sub-cabeçalho com componentes */}
                    <tr className="bg-slate-50 border-b">
                      {/* Repetir componentes para cada seção */}
                      {[...Array(8)].map((_, sectionIdx) => (
                        courses.map((course, idx) => (
                          <th 
                            key={`${sectionIdx}-${idx}`} 
                            className={`px-1 py-1 text-center font-normal text-[10px] whitespace-nowrap ${
                              idx === courses.length - 1 ? 'border-r-2 border-slate-400' : 'border-r'
                            }`}
                          >
                            {abbreviateComponent(course.name)}
                          </th>
                        ))
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
                        
                        {/* Notas por seção */}
                        {['b1', 'b2', 'rec1', 'b3', 'b4', 'rec2', 'totalPoints', 'finalAverage'].map((period, periodIdx) => (
                          courses.map((course, idx) => {
                            const gradeData = student.grades[course.id];
                            let value = '-';
                            
                            if (gradeData) {
                              if (period === 'totalPoints') {
                                value = gradeData.totalPoints ? gradeData.totalPoints.toFixed(1) : '-';
                              } else if (period === 'finalAverage') {
                                value = gradeData.finalAverage ? gradeData.finalAverage.toFixed(1) : '-';
                              } else {
                                value = gradeData[period] !== null && gradeData[period] !== undefined 
                                  ? gradeData[period].toFixed(1) 
                                  : '-';
                              }
                            }
                            
                            // Destacar médias abaixo de 6
                            const isLowGrade = period === 'finalAverage' && gradeData?.finalAverage !== null && gradeData?.finalAverage < 6;
                            
                            // Última coluna de cada bloco tem borda mais grossa
                            const isLastInSection = idx === courses.length - 1;
                            
                            return (
                              <td 
                                key={`${period}-${idx}`} 
                                className={`px-1 py-2 text-center text-[10px] ${
                                  isLastInSection ? 'border-r-2 border-slate-400' : 'border-r'
                                } ${isLowGrade ? 'bg-red-100 text-red-700 font-bold' : ''}`}
                              >
                                {value}
                              </td>
                            );
                          })
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
            </CardContent>
          </Card>
        )}

        {/* Paginação */}
        {selectedClass && promotionData.length > STUDENTS_PER_PAGE && (
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-600">
                  Mostrando {startIndex + 1} a {Math.min(endIndex, promotionData.length)} de {promotionData.length} alunos
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
