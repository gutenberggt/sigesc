import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { gradesAPI, schoolsAPI, classesAPI, coursesAPI, studentsAPI, professorAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { 
  Home, BookOpen, Users, User, Save, AlertCircle, CheckCircle, 
  Search, X, Calculator, TrendingUp, TrendingDown
} from 'lucide-react';

// Formata número com vírgula
const formatGrade = (value) => {
  if (value === null || value === undefined || value === '') return '';
  return Number(value).toFixed(1).replace('.', ',');
};

// Converte string com vírgula para número
const parseGrade = (value) => {
  if (!value || value === '') return null;
  const num = parseFloat(value.replace(',', '.'));
  return isNaN(num) ? null : Math.min(10, Math.max(0, num));
};

// Calcula média ponderada com recuperações por semestre
// Campos vazios são tratados como 0 para exibir média desde a 1ª nota
const calculateAverage = (b1, b2, b3, b4, rec_s1, rec_s2) => {
  // Converte null/undefined para 0
  const grades = { 
    b1: b1 ?? 0, 
    b2: b2 ?? 0, 
    b3: b3 ?? 0, 
    b4: b4 ?? 0 
  };
  
  // Aplica recuperações por semestre
  let finalGrades = { ...grades };
  
  // Recuperação 1º Semestre (substitui menor entre B1 e B2)
  if (rec_s1 !== null && rec_s1 !== undefined) {
    const keyS1 = grades.b1 <= grades.b2 ? 'b1' : 'b2';
    if (rec_s1 > finalGrades[keyS1]) {
      finalGrades[keyS1] = rec_s1;
    }
  }
  
  // Recuperação 2º Semestre (substitui menor entre B3 e B4)
  if (rec_s2 !== null && rec_s2 !== undefined) {
    const keyS2 = grades.b3 <= grades.b4 ? 'b3' : 'b4';
    if (rec_s2 > finalGrades[keyS2]) {
      finalGrades[keyS2] = rec_s2;
    }
  }
  
  // Calcula média: (B1×2 + B2×3 + B3×2 + B4×3) / 10
  const weights = { b1: 2, b2: 3, b3: 2, b4: 3 };
  const total = Object.keys(finalGrades).reduce((sum, k) => sum + (finalGrades[k] * weights[k]), 0);
  return Math.round(total / 10 * 10) / 10;
};

// Componente de input de nota
const GradeInput = ({ value, onChange, disabled, placeholder = '0,0' }) => {
  const [localValue, setLocalValue] = useState(formatGrade(value));
  
  useEffect(() => {
    setLocalValue(formatGrade(value));
  }, [value]);
  
  const handleBlur = () => {
    const parsed = parseGrade(localValue);
    onChange(parsed);
    setLocalValue(formatGrade(parsed));
  };
  
  return (
    <input
      type="text"
      value={localValue}
      onChange={(e) => setLocalValue(e.target.value)}
      onBlur={handleBlur}
      disabled={disabled}
      className="w-16 px-2 py-1 text-center border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
      placeholder={placeholder}
    />
  );
};

export function Grades() {
  const navigate = useNavigate();
  const { user } = useAuth();
  
  // Estados gerais
  const [activeTab, setActiveTab] = useState('turma'); // 'turma' ou 'aluno'
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [alert, setAlert] = useState(null);
  const [academicYear, setAcademicYear] = useState(new Date().getFullYear());
  
  // Dados base
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [students, setStudents] = useState([]);
  
  // Dados do professor (quando logado como professor)
  const [professorTurmas, setProfessorTurmas] = useState([]);
  const isProfessor = user?.role === 'professor';
  
  // Filtros - Por Turma
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedCourse, setSelectedCourse] = useState('');
  
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
  
  // SEMED pode visualizar, mas não editar
  const canEdit = user?.role !== 'semed';
  
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
          const studentsData = await studentsAPI.getAll();
          setStudents(studentsData);
        } else {
          // Para outros usuários, carrega todos os dados
          const [schoolsData, classesData, coursesData, studentsData] = await Promise.all([
            schoolsAPI.getAll(),
            classesAPI.getAll(),
            coursesAPI.getAll(),
            studentsAPI.getAll()
          ]);
          setSchools(schoolsData);
          setClasses(classesData);
          setCourses(coursesData);
          setStudents(studentsData);
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
  
  const showAlert = (type, message) => {
    setAlert({ type, message });
    setTimeout(() => setAlert(null), 5000);
  };
  
  // Turma selecionada (para obter nível de ensino e série)
  const selectedClassData = classes.find(c => c.id === selectedClass);
  
  // Filtros derivados
  const filteredClasses = classes.filter(c => c.school_id === selectedSchool);
  
  // Filtra componentes curriculares baseado na escola, nível de ensino e série/ano da turma
  const filteredCourses = courses.filter(course => {
    // Se o componente é global (sem school_id) ou é da mesma escola
    const matchesSchool = !course.school_id || course.school_id === selectedSchool;
    if (!matchesSchool) return false;
    
    // Se não tem turma selecionada, mostra todos os componentes compatíveis
    if (!selectedClassData) return true;
    
    // Deve ser do mesmo nível de ensino (se o componente tiver nível definido)
    if (course.nivel_ensino && course.nivel_ensino !== selectedClassData.education_level) return false;
    
    // Se o componente não tem séries específicas, aplica a todas do nível
    if (!course.grade_levels || course.grade_levels.length === 0) return true;
    
    // Verifica se a série da turma está nas séries do componente
    return course.grade_levels.includes(selectedClassData.grade_level);
  });
  
  // Sugestões de busca
  const nameSuggestions = searchName.length >= 3 
    ? students.filter(s => s.full_name?.toLowerCase().startsWith(searchName.toLowerCase())).slice(0, 10)
    : [];
  
  const cpfSuggestions = searchCpf.length >= 3
    ? students.filter(s => s.cpf?.replace(/\D/g, '').startsWith(searchCpf.replace(/\D/g, ''))).slice(0, 10)
    : [];
  
  // Carrega notas por turma
  const loadGradesByClass = async () => {
    if (!selectedClass || !selectedCourse) return;
    
    setLoading(true);
    try {
      const data = await gradesAPI.getByClass(selectedClass, selectedCourse, academicYear);
      setGradesData(data);
      setHasChanges(false);
    } catch (error) {
      console.error('Erro ao carregar notas:', error);
      showAlert('error', 'Erro ao carregar notas da turma');
    } finally {
      setLoading(false);
    }
  };
  
  // Carrega notas por aluno
  const loadGradesByStudent = async (studentId) => {
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
  };
  
  // Seleciona aluno
  const handleSelectStudent = (student) => {
    setSelectedStudent(student);
    setSearchName(student.full_name || '');
    setSearchCpf(student.cpf || '');
    setShowNameSuggestions(false);
    setShowCpfSuggestions(false);
    loadGradesByStudent(student.id);
  };
  
  // Limpa busca
  const handleClearSearch = () => {
    setSearchName('');
    setSearchCpf('');
    setSelectedStudent(null);
    setStudentGrades(null);
    setShowNameSuggestions(false);
    setShowCpfSuggestions(false);
  };
  
  // Atualiza nota local (por turma)
  const updateLocalGrade = (index, field, value) => {
    const newData = [...gradesData];
    newData[index].grade[field] = value;
    
    // Recalcula média com recuperações por semestre
    const g = newData[index].grade;
    g.final_average = calculateAverage(g.b1, g.b2, g.b3, g.b4, g.rec_s1, g.rec_s2);
    g.status = g.final_average !== null 
      ? (g.final_average >= 5 ? 'aprovado' : 'reprovado_nota')
      : 'cursando';
    
    setGradesData(newData);
    setHasChanges(true);
  };
  
  // Salva notas da turma
  const saveGrades = async () => {
    setSaving(true);
    try {
      const gradesToSave = gradesData.map(item => ({
        student_id: item.student.id,
        class_id: selectedClass,
        course_id: selectedCourse,
        academic_year: academicYear,
        b1: item.grade.b1,
        b2: item.grade.b2,
        b3: item.grade.b3,
        b4: item.grade.b4,
        rec_s1: item.grade.rec_s1,
        rec_s2: item.grade.rec_s2,
        observations: item.grade.observations
      }));
      
      await gradesAPI.updateBatch(gradesToSave);
      showAlert('success', 'Notas salvas com sucesso!');
      setHasChanges(false);
      
      // Recarrega dados atualizados
      await loadGradesByClass();
    } catch (error) {
      console.error('Erro ao salvar notas:', error);
      showAlert('error', 'Erro ao salvar notas');
    } finally {
      setSaving(false);
    }
  };
  
  // Atualiza nota individual do aluno
  const updateStudentGrade = async (gradeId, courseId, field, value) => {
    if (!selectedStudent) return;
    
    // Atualiza localmente primeiro
    const newGrades = { ...studentGrades };
    const gradeIndex = newGrades.grades.findIndex(g => g.course_id === courseId);
    
    if (gradeIndex >= 0) {
      newGrades.grades[gradeIndex][field] = value;
      const g = newGrades.grades[gradeIndex];
      g.final_average = calculateAverage(g.b1, g.b2, g.b3, g.b4, g.rec_s1, g.rec_s2);
      g.status = g.final_average !== null 
        ? (g.final_average >= 5 ? 'aprovado' : 'reprovado_nota')
        : 'cursando';
      setStudentGrades(newGrades);
    }
    
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
  };
  
  // Renderiza status com cor
  const renderStatus = (status, average) => {
    const config = {
      'cursando': { label: 'Cursando', class: 'bg-gray-100 text-gray-800' },
      'aprovado': { label: 'Aprovado', class: 'bg-green-100 text-green-800' },
      'reprovado_nota': { label: 'Reprovado', class: 'bg-red-100 text-red-800' },
      'reprovado_frequencia': { label: 'Rep. Freq.', class: 'bg-orange-100 text-orange-800' }
    };
    const c = config[status] || config['cursando'];
    
    return (
      <div className="flex items-center gap-2">
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${c.class}`}>
          {c.label}
        </span>
        {average !== null && (
          <span className={`font-bold ${average >= 5 ? 'text-green-600' : 'text-red-600'}`}>
            {formatGrade(average)}
          </span>
        )}
      </div>
    );
  };
  
  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <button
          onClick={() => navigate(user?.role === 'professor' ? '/professor' : '/dashboard')}
          className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <Home size={18} />
          <span>Início</span>
        </button>
        
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Lançamento de Notas</h1>
            <p className="text-gray-600 mt-1">Gerencie as notas dos alunos por turma ou individualmente</p>
          </div>
          
          {/* Seletor de Ano Letivo */}
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-gray-700">Ano Letivo:</label>
            <select
              value={academicYear}
              onChange={(e) => setAcademicYear(parseInt(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              {[2023, 2024, 2025, 2026].map(year => (
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
            {/* Tab: Por Turma */}
            {activeTab === 'turma' && (
              <div className="space-y-6">
                {/* Filtros */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                    <select
                      value={selectedSchool}
                      onChange={(e) => {
                        setSelectedSchool(e.target.value);
                        setSelectedClass('');
                        setSelectedCourse('');
                        setGradesData([]);
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Selecione a escola</option>
                      {schools.map(school => (
                        <option key={school.id} value={school.id}>{school.name}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
                    <select
                      value={selectedClass}
                      onChange={(e) => {
                        setSelectedClass(e.target.value);
                        setGradesData([]);
                      }}
                      disabled={!selectedSchool}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                    >
                      <option value="">Selecione a turma</option>
                      {filteredClasses.map(cls => (
                        <option key={cls.id} value={cls.id}>{cls.name} - {cls.grade_level}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Componente Curricular</label>
                    <select
                      value={selectedCourse}
                      onChange={(e) => {
                        setSelectedCourse(e.target.value);
                        setGradesData([]);
                      }}
                      disabled={!selectedSchool}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                    >
                      <option value="">Selecione o componente</option>
                      {filteredCourses.map(course => (
                        <option key={course.id} value={course.id}>{course.name}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div className="flex items-end">
                    <button
                      onClick={loadGradesByClass}
                      disabled={!selectedClass || !selectedCourse || loading}
                      className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      <Search size={18} />
                      Carregar Notas
                    </button>
                  </div>
                </div>
                
                {/* Tabela de Notas */}
                {loading ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-4 text-gray-600">Carregando notas...</p>
                  </div>
                ) : gradesData.length > 0 ? (
                  <div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Aluno</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B1 (×2)</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B2 (×3)</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 1º</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B3 (×2)</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B4 (×3)</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 2º</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Média</th>
                            <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                          {gradesData.map((item, index) => (
                            <tr key={item.student.id} className="hover:bg-gray-50">
                              <td className="px-4 py-3">
                                <div className="text-sm font-medium text-gray-900">{item.student.full_name}</div>
                                <div className="text-xs text-gray-500">{item.student.enrollment_number}</div>
                              </td>
                              <td className="px-4 py-3 text-center">
                                <GradeInput
                                  value={item.grade.b1}
                                  onChange={(v) => updateLocalGrade(index, 'b1', v)}
                                  disabled={!canEdit}
                                />
                              </td>
                              <td className="px-4 py-3 text-center">
                                <GradeInput
                                  value={item.grade.b2}
                                  onChange={(v) => updateLocalGrade(index, 'b2', v)}
                                  disabled={!canEdit}
                                />
                              </td>
                              <td className="px-4 py-3 text-center bg-blue-50">
                                <GradeInput
                                  value={item.grade.rec_s1}
                                  onChange={(v) => updateLocalGrade(index, 'rec_s1', v)}
                                  disabled={!canEdit}
                                  placeholder="-"
                                />
                              </td>
                              <td className="px-4 py-3 text-center">
                                <GradeInput
                                  value={item.grade.b3}
                                  onChange={(v) => updateLocalGrade(index, 'b3', v)}
                                  disabled={!canEdit}
                                />
                              </td>
                              <td className="px-4 py-3 text-center">
                                <GradeInput
                                  value={item.grade.b4}
                                  onChange={(v) => updateLocalGrade(index, 'b4', v)}
                                  disabled={!canEdit}
                                />
                              </td>
                              <td className="px-4 py-3 text-center bg-blue-50">
                                <GradeInput
                                  value={item.grade.rec_s2}
                                  onChange={(v) => updateLocalGrade(index, 'rec_s2', v)}
                                  disabled={!canEdit}
                                  placeholder="-"
                                />
                              </td>
                              <td className="px-4 py-3 text-center">
                                <span className={`font-bold ${
                                  item.grade.final_average !== null
                                    ? item.grade.final_average >= 5 ? 'text-green-600' : 'text-red-600'
                                    : 'text-gray-400'
                                }`}>
                                  {item.grade.final_average !== null ? formatGrade(item.grade.final_average) : '-'}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-center">
                                {renderStatus(item.grade.status, null)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    
                    {/* Botão Salvar */}
                    {canEdit && (
                      <div className="mt-4 flex justify-end">
                        <button
                          onClick={saveGrades}
                          disabled={saving || !hasChanges}
                          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          <Save size={18} />
                          {saving ? 'Salvando...' : 'Salvar Notas'}
                        </button>
                      </div>
                    )}
                  </div>
                ) : selectedClass && selectedCourse ? (
                  <div className="text-center py-8 text-gray-500">
                    <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
                    <p>Clique em &quot;Carregar Notas&quot; para visualizar</p>
                  </div>
                ) : (
                  <div className="text-center py-8 text-gray-500">
                    <Users size={48} className="mx-auto mb-4 text-gray-300" />
                    <p>Selecione a escola, turma e componente curricular</p>
                  </div>
                )}
              </div>
            )}
            
            {/* Tab: Por Aluno */}
            {activeTab === 'aluno' && (
              <div className="space-y-6">
                {/* Busca */}
                <div className="flex flex-wrap items-end gap-4">
                  {/* Busca por Nome */}
                  <div className="relative flex-1 min-w-[250px]" ref={nameInputRef}>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      <Search size={14} className="inline mr-1" />
                      Buscar por Nome
                    </label>
                    <input
                      type="text"
                      value={searchName}
                      onChange={(e) => {
                        setSearchName(e.target.value);
                        setShowNameSuggestions(e.target.value.length >= 3);
                      }}
                      onFocus={() => setShowNameSuggestions(searchName.length >= 3)}
                      placeholder="Digite pelo menos 3 letras..."
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                    {showNameSuggestions && nameSuggestions.length > 0 && (
                      <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                        {nameSuggestions.map((student) => (
                          <button
                            key={student.id}
                            type="button"
                            onClick={() => handleSelectStudent(student)}
                            className="w-full px-4 py-2 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                          >
                            <div className="font-medium text-gray-900">{student.full_name}</div>
                            <div className="text-xs text-gray-500">
                              Matrícula: {student.enrollment_number} | CPF: {student.cpf || '-'}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  {/* Busca por CPF */}
                  <div className="relative flex-1 min-w-[250px]" ref={cpfInputRef}>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      <Search size={14} className="inline mr-1" />
                      Buscar por CPF
                    </label>
                    <input
                      type="text"
                      value={searchCpf}
                      onChange={(e) => {
                        setSearchCpf(e.target.value);
                        setShowCpfSuggestions(e.target.value.length >= 3);
                      }}
                      onFocus={() => setShowCpfSuggestions(searchCpf.length >= 3)}
                      placeholder="Digite pelo menos 3 dígitos..."
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                    />
                    {showCpfSuggestions && cpfSuggestions.length > 0 && (
                      <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-y-auto">
                        {cpfSuggestions.map((student) => (
                          <button
                            key={student.id}
                            type="button"
                            onClick={() => handleSelectStudent(student)}
                            className="w-full px-4 py-2 text-left hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                          >
                            <div className="font-medium text-gray-900">{student.cpf}</div>
                            <div className="text-xs text-gray-500">
                              {student.full_name} | Matrícula: {student.enrollment_number}
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  
                  {/* Botão Limpar */}
                  {selectedStudent && (
                    <button
                      onClick={handleClearSearch}
                      className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 border border-gray-300"
                    >
                      <X size={18} />
                      Limpar
                    </button>
                  )}
                </div>
                
                {/* Dados do Aluno */}
                {selectedStudent && studentGrades && (
                  <div className="space-y-4">
                    {/* Card do Aluno */}
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-blue-200 rounded-full flex items-center justify-center">
                          <User className="text-blue-600" size={24} />
                        </div>
                        <div>
                          <h3 className="font-semibold text-lg text-gray-900">{studentGrades.student.full_name}</h3>
                          <p className="text-sm text-gray-600">
                            Matrícula: {studentGrades.student.enrollment_number} | 
                            CPF: {studentGrades.student.cpf || '-'}
                          </p>
                        </div>
                      </div>
                    </div>
                    
                    {/* Tabela de Notas por Componente */}
                    {loading ? (
                      <div className="text-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                      </div>
                    ) : studentGrades.grades.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 bg-white rounded-lg overflow-hidden">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Componente</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B1 (×2)</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B2 (×3)</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 1º</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B3 (×2)</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">B4 (×3)</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-blue-600 uppercase bg-blue-50">Rec. 2º</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Média</th>
                              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Status</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-200">
                            {studentGrades.grades.map((grade) => (
                              <tr key={grade.course_id} className="hover:bg-gray-50">
                                <td className="px-4 py-3 font-medium text-gray-900">{grade.course_name}</td>
                                <td className="px-4 py-3 text-center">
                                  <GradeInput
                                    value={grade.b1}
                                    onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b1', v)}
                                    disabled={!canEdit}
                                  />
                                </td>
                                <td className="px-4 py-3 text-center">
                                  <GradeInput
                                    value={grade.b2}
                                    onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b2', v)}
                                    disabled={!canEdit}
                                  />
                                </td>
                                <td className="px-4 py-3 text-center bg-blue-50">
                                  <GradeInput
                                    value={grade.rec_s1}
                                    onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'rec_s1', v)}
                                    disabled={!canEdit}
                                    placeholder="-"
                                  />
                                </td>
                                <td className="px-4 py-3 text-center">
                                  <GradeInput
                                    value={grade.b3}
                                    onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b3', v)}
                                    disabled={!canEdit}
                                  />
                                </td>
                                <td className="px-4 py-3 text-center">
                                  <GradeInput
                                    value={grade.b4}
                                    onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'b4', v)}
                                    disabled={!canEdit}
                                  />
                                </td>
                                <td className="px-4 py-3 text-center bg-blue-50">
                                  <GradeInput
                                    value={grade.rec_s2}
                                    onChange={(v) => updateStudentGrade(grade.id, grade.course_id, 'rec_s2', v)}
                                    disabled={!canEdit}
                                    placeholder="-"
                                  />
                                </td>
                                <td className="px-4 py-3 text-center">
                                  <span className={`font-bold ${
                                    grade.final_average !== null
                                      ? grade.final_average >= 5 ? 'text-green-600' : 'text-red-600'
                                      : 'text-gray-400'
                                  }`}>
                                    {grade.final_average !== null ? formatGrade(grade.final_average) : '-'}
                                  </span>
                                </td>
                                <td className="px-4 py-3 text-center">
                                  {renderStatus(grade.status, null)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-gray-500 bg-gray-50 rounded-lg">
                        <BookOpen size={48} className="mx-auto mb-4 text-gray-300" />
                        <p>Nenhuma nota lançada para este aluno</p>
                      </div>
                    )}
                  </div>
                )}
                
                {!selectedStudent && (
                  <div className="text-center py-12 text-gray-500">
                    <User size={48} className="mx-auto mb-4 text-gray-300" />
                    <p>Busque um aluno pelo nome ou CPF para visualizar suas notas</p>
                  </div>
                )}
              </div>
            )}
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
    </Layout>
  );
}
