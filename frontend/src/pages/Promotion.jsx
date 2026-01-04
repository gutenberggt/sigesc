import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/contexts/AuthContext';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Loader2, Download, FileText, School, Users, BookOpen, Filter, RefreshCw, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { schoolsAPI, classesAPI, gradesAPI, enrollmentsAPI, coursesAPI, studentsAPI } from '@/services/api';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Componentes Curriculares abreviados (como no documento)
const COMPONENT_ABBREVIATIONS = {
  'Língua Portuguesa': 'Ling. Port.',
  'Arte': 'Arte',
  'Educação Física': 'Ed. Física',
  'Língua Inglesa': 'Ling. Ingl.',
  'Matemática': 'Matemát.',
  'Ciências': 'Ciências',
  'História': 'História',
  'Geografia': 'Geografia',
  'Ensino Religioso': 'Ens. Relig.',
  'Estudos Amazônicos': 'Est. Amaz.',
  'Literatura e Redação': 'Lit. e red.'
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

export function Promotion() {
  const navigate = useNavigate();
  const { accessToken, user } = useAuth();
  
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
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  
  // Processed data
  const [promotionData, setPromotionData] = useState([]);
  
  // Anos disponíveis
  const years = [2023, 2024, 2025, 2026];

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

  // Carregar turmas quando escola é selecionada
  useEffect(() => {
    const fetchClasses = async () => {
      if (!selectedSchool) {
        setClasses([]);
        return;
      }
      try {
        const data = await classesAPI.list({ school_id: selectedSchool });
        // Mostrar todas as turmas da escola (não filtrar por ano)
        setClasses(data || []);
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
      let enrollments = await enrollmentsAPI.list({ 
        class_id: selectedClass
      });
      
      // Filtrar por ano se houver ano na matrícula, ou considerar todas
      enrollments = (enrollments || []).filter(e => 
        !e.academic_year || e.academic_year === selectedYear
      );
      
      if (!enrollments || enrollments.length === 0) {
        // Tentar buscar todas as matrículas sem filtro de ano
        enrollments = await enrollmentsAPI.list({ class_id: selectedClass });
        if (!enrollments || enrollments.length === 0) {
          toast.info('Nenhum aluno matriculado nesta turma');
          setPromotionData([]);
          return;
        }
      }
      
      // Buscar dados dos alunos
      const studentIds = enrollments.map(e => e.student_id);
      const studentsData = await studentsAPI.list();
      const filteredStudents = (studentsData || []).filter(s => studentIds.includes(s.id));
      setStudents(filteredStudents);
      
      // Buscar componentes curriculares
      const coursesData = await coursesAPI.list({ nivel_ensino: classInfo.education_level });
      setCourses(coursesData || []);
      
      // Buscar notas de todos os alunos da turma
      const gradesPromises = studentIds.map(studentId => 
        gradesAPI.list({ student_id: studentId, academic_year: selectedYear })
      );
      const allGrades = await Promise.all(gradesPromises);
      
      // Processar dados de promoção
      const processed = filteredStudents.map((student, index) => {
        const studentEnrollment = enrollments.find(e => e.student_id === student.id);
        const studentGrades = allGrades[index] || [];
        
        // Organizar notas por componente
        const gradesByComponent = {};
        studentGrades.forEach(grade => {
          const course = (coursesData || []).find(c => c.id === grade.course_id);
          if (course) {
            if (!gradesByComponent[course.id]) {
              gradesByComponent[course.id] = {
                courseName: course.name,
                b1: null, b2: null, b3: null, b4: null,
                rec1: null, rec2: null,
                totalPoints: 0,
                finalAverage: null
              };
            }
            
            // Mapear período para bimestre
            if (grade.period === 'P1') gradesByComponent[course.id].b1 = grade.grade;
            if (grade.period === 'P2') gradesByComponent[course.id].b2 = grade.grade;
            if (grade.period === 'P3') gradesByComponent[course.id].b3 = grade.grade;
            if (grade.period === 'P4') gradesByComponent[course.id].b4 = grade.grade;
            if (grade.period === 'REC1') gradesByComponent[course.id].rec1 = grade.grade;
            if (grade.period === 'REC2') gradesByComponent[course.id].rec2 = grade.grade;
          }
        });
        
        // Calcular total de pontos e média final por componente
        Object.keys(gradesByComponent).forEach(courseId => {
          const comp = gradesByComponent[courseId];
          const grades = [comp.b1, comp.b2, comp.b3, comp.b4].filter(g => g !== null);
          if (grades.length > 0) {
            // Considerar recuperação se houver
            let total = grades.reduce((a, b) => a + b, 0);
            
            // Se tem recuperação, substitui a menor nota
            if (comp.rec1 !== null) {
              const sem1Grades = [comp.b1, comp.b2].filter(g => g !== null);
              if (sem1Grades.length > 0) {
                const minGrade = Math.min(...sem1Grades);
                if (comp.rec1 > minGrade) {
                  total = total - minGrade + comp.rec1;
                }
              }
            }
            if (comp.rec2 !== null) {
              const sem2Grades = [comp.b3, comp.b4].filter(g => g !== null);
              if (sem2Grades.length > 0) {
                const minGrade = Math.min(...sem2Grades);
                if (comp.rec2 > minGrade) {
                  total = total - minGrade + comp.rec2;
                }
              }
            }
            
            comp.totalPoints = total;
            comp.finalAverage = total / 4; // Média dos 4 bimestres
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
          // Verificar se todas as médias são >= 6
          const averages = Object.values(gradesByComponent).map(c => c.finalAverage).filter(a => a !== null);
          if (averages.length > 0) {
            const allApproved = averages.every(avg => avg >= 6);
            if (allApproved) {
              result = 'APROVADO';
            } else {
              // Verificar quantos componentes reprovados
              const failedCount = averages.filter(avg => avg < 6).length;
              if (failedCount >= 3) {
                result = 'REPROVADO';
              } else {
                result = 'CURSANDO'; // Aguardando recuperação ou análise
              }
            }
          }
        }
        
        return {
          number: index + 1,
          studentId: student.id,
          studentName: student.full_name,
          sex: student.gender === 'M' ? 'M' : 'F',
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
  }, [selectedClass, selectedYear, classes]);

  useEffect(() => {
    loadPromotionData();
  }, [loadPromotionData]);

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
    approved: promotionData.filter(p => p.result === 'APROVADO' || p.result === 'PROMOVIDO' || p.result === 'CONCLUIU').length,
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
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Livro de Promoção</h1>
            <p className="text-gray-500 mt-1">
              Visualize e gere o Livro de Promoção por turma
            </p>
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
                  Turma
                </label>
                <Select value={selectedClass} onValueChange={setSelectedClass} disabled={!selectedSchool}>
                  <SelectTrigger data-testid="class-select">
                    <SelectValue placeholder={selectedSchool ? "Selecione a turma" : "Selecione a escola primeiro"} />
                  </SelectTrigger>
                  <SelectContent>
                    {classes.map(cls => (
                      <SelectItem key={cls.id} value={cls.id}>
                        {cls.name} - {cls.grade_level} ({cls.shift})
                      </SelectItem>
                    ))}
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

        {/* Cabeçalho do documento */}
        {selectedClass && selectedSchoolInfo && selectedClassInfo && (
          <Card className="bg-slate-50 border-2 border-slate-200">
            <CardContent className="p-4">
              <div className="text-center space-y-1">
                <p className="text-xs text-gray-600">PREFEITURA MUNICIPAL DE FLORESTA DO ARAGUAIA</p>
                <p className="text-xs text-gray-600">SECRETARIA MUNICIPAL DE EDUCAÇÃO</p>
                <p className="font-semibold text-sm">{selectedSchoolInfo.name}</p>
                <p className="text-sm">TURMA: {selectedClassInfo.name} - {selectedClassInfo.grade_level} - {selectedClassInfo.shift?.toUpperCase()}</p>
                <p className="text-sm">ANO LETIVO: {selectedYear}</p>
                <p className="font-bold text-lg mt-2">LIVRO DE PROMOÇÃO</p>
              </div>
            </CardContent>
          </Card>
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
                      <th rowSpan={2} className="px-2 py-2 text-center font-semibold border-r w-10">SEXO</th>
                      
                      {/* 1º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-blue-50">
                        NOTAS 1º BIMESTRE
                      </th>
                      
                      {/* 2º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-green-50">
                        NOTAS 2º BIMESTRE
                      </th>
                      
                      {/* Recuperação 1º Semestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-yellow-50">
                        RECUPERAÇÃO 1º SEM
                      </th>
                      
                      {/* 3º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-blue-50">
                        NOTAS 3º BIMESTRE
                      </th>
                      
                      {/* 4º Bimestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-green-50">
                        NOTAS 4º BIMESTRE
                      </th>
                      
                      {/* Recuperação 2º Semestre */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-yellow-50">
                        RECUPERAÇÃO 2º SEM
                      </th>
                      
                      {/* Total Pontos Anuais */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-purple-50">
                        TOTAL PONTOS ANUAIS
                      </th>
                      
                      {/* Média Final */}
                      <th colSpan={courses.length || 11} className="px-2 py-1 text-center font-semibold border-r bg-orange-50">
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
                          <th key={`${sectionIdx}-${idx}`} className="px-1 py-1 text-center font-normal border-r text-[10px] whitespace-nowrap">
                            {abbreviateComponent(course.name)}
                          </th>
                        ))
                      ))}
                    </tr>
                  </thead>
                  
                  <tbody>
                    {promotionData.map((student, rowIdx) => (
                      <tr key={student.studentId} className={rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-2 py-2 border-r text-center sticky left-0 bg-inherit z-10">{student.number}</td>
                        <td className="px-2 py-2 border-r font-medium sticky left-8 bg-inherit z-10 whitespace-nowrap">
                          {student.studentName}
                        </td>
                        <td className="px-2 py-2 border-r text-center">{student.sex}</td>
                        
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
                            
                            return (
                              <td 
                                key={`${period}-${idx}`} 
                                className={`px-1 py-2 border-r text-center text-[10px] ${isLowGrade ? 'bg-red-100 text-red-700 font-bold' : ''}`}
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

        {/* Rodapé do documento */}
        {selectedClass && promotionData.length > 0 && (
          <Card className="bg-slate-50">
            <CardContent className="p-4">
              <div className="flex justify-between items-end">
                <div className="text-center flex-1">
                  <div className="border-t border-black w-48 mx-auto mt-8"></div>
                  <p className="text-sm mt-1">Secretário(a)</p>
                </div>
                <div className="text-center flex-1">
                  <p className="text-sm">Floresta do Araguaia - PA, {new Date().toLocaleDateString('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
                </div>
                <div className="text-center flex-1">
                  <div className="border-t border-black w-48 mx-auto mt-8"></div>
                  <p className="text-sm mt-1">Diretor(a)</p>
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
