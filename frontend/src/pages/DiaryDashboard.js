import { useState, useEffect, useMemo } from 'react';
import { Layout } from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { 
  BarChart3, 
  Home, 
  BookOpen, 
  ClipboardCheck, 
  FileText, 
  TrendingUp,
  School,
  Users,
  Calendar,
  Filter
} from 'lucide-react';
import { schoolsAPI, classesAPI, coursesAPI } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from 'recharts';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const COLORS = ['#10B981', '#F59E0B', '#EF4444', '#6366F1', '#8B5CF6', '#EC4899'];

export const DiaryDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const currentYear = new Date().getFullYear();

  // Estados dos filtros
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [courses, setCourses] = useState([]);
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedCourse, setSelectedCourse] = useState('');
  const [academicYear, setAcademicYear] = useState(currentYear);

  // Estados dos dados
  const [loading, setLoading] = useState(true);
  const [attendanceStats, setAttendanceStats] = useState(null);
  const [gradesStats, setGradesStats] = useState(null);
  const [contentStats, setContentStats] = useState(null);

  // Verificar permissão de acesso
  const allowedRoles = ['admin', 'admin_teste', 'diretor', 'coordenador', 'secretario', 'auxiliar_secretaria', 'semed_nivel_2', 'semed_nivel_3'];
  const hasAccess = allowedRoles.includes(user?.role);

  // Carregar escolas
  useEffect(() => {
    const loadSchools = async () => {
      try {
        const data = await schoolsAPI.getAll();
        // Filtrar escolas ativas (aceita status 'active' ou undefined/null)
        setSchools(data.filter(s => !s.status || s.status === 'active'));
      } catch (error) {
        console.error('Erro ao carregar escolas:', error);
      }
    };
    loadSchools();
  }, []);

  // Carregar turmas quando escola é selecionada
  useEffect(() => {
    const loadClasses = async () => {
      if (!selectedSchool) {
        setClasses([]);
        return;
      }
      try {
        const data = await classesAPI.getAll(selectedSchool);
        // Filtrar turmas ativas (aceita status 'active' ou undefined/null)
        setClasses(data.filter(c => !c.status || c.status === 'active'));
      } catch (error) {
        console.error('Erro ao carregar turmas:', error);
      }
    };
    loadClasses();
  }, [selectedSchool]);

  // Carregar componentes quando turma é selecionada
  useEffect(() => {
    const loadCourses = async () => {
      if (!selectedClass) {
        setCourses([]);
        return;
      }
      try {
        const classInfo = classes.find(c => c.id === selectedClass);
        const turmaLevel = classInfo?.nivel_ensino || classInfo?.education_level;
        const data = await coursesAPI.getAll(turmaLevel);
        setCourses(data);
      } catch (error) {
        console.error('Erro ao carregar componentes:', error);
      }
    };
    loadCourses();
  }, [selectedClass, classes]);

  // Carregar estatísticas
  useEffect(() => {
    const loadStats = async () => {
      setLoading(true);
      try {
        const token = localStorage.getItem('accessToken');
        const headers = { 'Authorization': `Bearer ${token}` };
        
        // Construir query params
        const params = new URLSearchParams({ academic_year: academicYear });
        if (selectedSchool) params.append('school_id', selectedSchool);
        if (selectedClass) params.append('class_id', selectedClass);
        if (selectedCourse) params.append('course_id', selectedCourse);

        // Buscar estatísticas de frequência
        try {
          const attResponse = await fetch(`${API_URL}/api/diary-dashboard/attendance?${params}`, { headers });
          if (attResponse.ok) {
            const attData = await attResponse.json();
            setAttendanceStats(attData);
          }
        } catch (e) {
          console.error('Erro ao carregar estatísticas de frequência:', e);
        }

        // Buscar estatísticas de notas
        try {
          const gradesResponse = await fetch(`${API_URL}/api/diary-dashboard/grades?${params}`, { headers });
          if (gradesResponse.ok) {
            const gradesData = await gradesResponse.json();
            setGradesStats(gradesData);
          }
        } catch (e) {
          console.error('Erro ao carregar estatísticas de notas:', e);
        }

        // Buscar estatísticas de conteúdos
        try {
          const contentResponse = await fetch(`${API_URL}/api/diary-dashboard/content?${params}`, { headers });
          if (contentResponse.ok) {
            const contentData = await contentResponse.json();
            setContentStats(contentData);
          }
        } catch (e) {
          console.error('Erro ao carregar estatísticas de conteúdos:', e);
        }

      } catch (error) {
        console.error('Erro ao carregar estatísticas:', error);
      } finally {
        setLoading(false);
      }
    };

    loadStats();
  }, [selectedSchool, selectedClass, selectedCourse, academicYear]);

  // Dados reais do backend
  const attendanceData = useMemo(() => {
    return attendanceStats?.by_month || [];
  }, [attendanceStats]);

  const gradesData = useMemo(() => {
    return gradesStats?.by_bimestre || [];
  }, [gradesStats]);

  const contentData = useMemo(() => {
    return contentStats?.by_month || [];
  }, [contentStats]);

  const pieData = useMemo(() => {
    return [
      { name: 'Frequência', value: attendanceStats?.completion_rate ?? 0, color: '#10B981' },
      { name: 'Notas', value: gradesStats?.completion_rate ?? 0, color: '#6366F1' },
      { name: 'Conteúdos', value: contentStats?.completion_rate ?? 0, color: '#F59E0B' },
    ];
  }, [attendanceStats, gradesStats, contentStats]);
  
  // Verifica se há dados para exibir
  const hasData = attendanceData.length > 0 || gradesData.length > 0 || contentData.length > 0;

  if (!hasAccess) {
    return (
      <Layout>
        <div className="flex items-center justify-center h-64">
          <p className="text-gray-500">Você não tem permissão para acessar esta página.</p>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6 p-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="flex items-center space-x-2 text-gray-600 hover:text-gray-900 transition-colors"
            >
              <Home size={18} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <BarChart3 className="text-indigo-600" />
                Acompanhamento de Diários
              </h1>
              <p className="text-gray-600 text-sm">Monitoramento de frequência, notas e conteúdos</p>
            </div>
          </div>
        </div>

        {/* Filtros */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Filter size={16} />
              Filtros
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Escola</label>
                <select
                  value={selectedSchool}
                  onChange={(e) => {
                    setSelectedSchool(e.target.value);
                    setSelectedClass('');
                    setSelectedCourse('');
                  }}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Todas as escolas</option>
                  {schools.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Turma</label>
                <select
                  value={selectedClass}
                  onChange={(e) => {
                    setSelectedClass(e.target.value);
                    setSelectedCourse('');
                  }}
                  disabled={!selectedSchool}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100"
                >
                  <option value="">Todas as turmas</option>
                  {classes.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Componente</label>
                <select
                  value={selectedCourse}
                  onChange={(e) => setSelectedCourse(e.target.value)}
                  disabled={!selectedClass}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-100"
                >
                  <option value="">Todos os componentes</option>
                  {courses.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Ano Letivo</label>
                <select
                  value={academicYear}
                  onChange={(e) => setAcademicYear(parseInt(e.target.value))}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-indigo-500"
                >
                  {[currentYear - 1, currentYear, currentYear + 1].map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-end">
                <Button 
                  variant="outline" 
                  onClick={() => {
                    setSelectedSchool('');
                    setSelectedClass('');
                    setSelectedCourse('');
                  }}
                  className="w-full"
                >
                  Limpar Filtros
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Cards de Resumo */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-gradient-to-br from-green-50 to-green-100 border-green-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-green-600 font-medium">Frequência</p>
                  <p className="text-3xl font-bold text-green-700">
                    {attendanceStats?.completion_rate ?? 0}%
                  </p>
                  <p className="text-xs text-green-600">de preenchimento</p>
                </div>
                <ClipboardCheck size={40} className="text-green-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-indigo-50 to-indigo-100 border-indigo-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-indigo-600 font-medium">Notas</p>
                  <p className="text-3xl font-bold text-indigo-700">
                    {gradesStats?.completion_rate ?? 0}%
                  </p>
                  <p className="text-xs text-indigo-600">de preenchimento</p>
                </div>
                <FileText size={40} className="text-indigo-500 opacity-50" />
              </div>
            </CardContent>
          </Card>

          <Card className="bg-gradient-to-br from-amber-50 to-amber-100 border-amber-200">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-amber-600 font-medium">Conteúdos</p>
                  <p className="text-3xl font-bold text-amber-700">
                    {contentStats?.completion_rate ?? 0}%
                  </p>
                  <p className="text-xs text-amber-600">de preenchimento</p>
                </div>
                <BookOpen size={40} className="text-amber-500 opacity-50" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Gráficos */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Gráfico de Frequência */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <ClipboardCheck size={16} className="text-green-600" />
                Frequência por Mês
              </CardTitle>
            </CardHeader>
            <CardContent>
              {attendanceData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={attendanceData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="preenchido" name="Preenchido (%)" fill="#10B981" />
                    <Bar dataKey="pendente" name="Pendente (%)" fill="#EF4444" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-gray-400">
                  <div className="text-center">
                    <ClipboardCheck size={32} className="mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Sem registros de frequência para o período</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Gráfico de Notas */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText size={16} className="text-indigo-600" />
                Notas por Bimestre
              </CardTitle>
            </CardHeader>
            <CardContent>
              {gradesData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={gradesData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="preenchido" name="Preenchido (%)" fill="#6366F1" />
                    <Bar dataKey="pendente" name="Pendente (%)" fill="#F59E0B" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-gray-400">
                  <div className="text-center">
                    <FileText size={32} className="mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Sem registros de notas para o período</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Gráfico de Conteúdos */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <BookOpen size={16} className="text-amber-600" />
                Registros de Conteúdo por Mês
              </CardTitle>
            </CardHeader>
            <CardContent>
              {contentData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={contentData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="registros" name="Registros" fill="#F59E0B" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-gray-400">
                  <div className="text-center">
                    <BookOpen size={32} className="mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Sem registros de conteúdo para o período</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Gráfico de Pizza - Visão Geral */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp size={16} className="text-purple-600" />
                Visão Geral de Preenchimento
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={5}
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}%`}
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Nota informativa */}
        <Card className="bg-blue-50 border-blue-200">
          <CardContent className="p-4">
            <p className="text-sm text-blue-700">
              <strong>Nota:</strong> Os dados apresentados são atualizados em tempo real conforme os registros são inseridos no sistema.
              {!selectedSchool && " Selecione uma escola para ver dados mais específicos."}
            </p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default DiaryDashboard;
