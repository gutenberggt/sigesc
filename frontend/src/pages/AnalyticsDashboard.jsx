import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/contexts/AuthContext';
import { schoolsAPI, classesAPI, studentsAPI } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import {
  Home, TrendingUp, Users, GraduationCap, School, BookOpen,
  Filter, RefreshCw, Award, Target, AlertTriangle, CheckCircle,
  BarChart3, PieChart as PieChartIcon, Activity, UserMinus, LogOut
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const COLORS = {
  primary: '#3b82f6',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  purple: '#8b5cf6'
};

const CHART_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

export function AnalyticsDashboard() {
  const navigate = useNavigate();
  const { user, accessToken } = useAuth();
  const token = accessToken;
  
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [selectedSchool, setSelectedSchool] = useState('');
  const [selectedClass, setSelectedClass] = useState('');
  const [selectedStudent, setSelectedStudent] = useState('');
  
  const [schools, setSchools] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  
  const [overview, setOverview] = useState({
    schools: { total: 0 },
    classes: { total: 0 },
    students: { active: 0, total: 0 },
    enrollments: { total: 0, active: 0, by_status: {} },
    transfers: { total: 0, rate: 0 },
    dropouts: { total: 0, rate: 0 },
    attendance: { total_records: 0, present: 0, absent: 0, justified: 0, rate: 0 },
    grades: { average: 0, total: 0, approved: 0, failed: 0, approval_rate: 0 }
  });
  const [enrollmentsTrend, setEnrollmentsTrend] = useState([]);
  const [attendanceMonthly, setAttendanceMonthly] = useState([]);
  const [gradesBySubject, setGradesBySubject] = useState([]);
  const [gradesByPeriod, setGradesByPeriod] = useState([]);
  const [schoolsRanking, setSchoolsRanking] = useState([]);
  const [studentsPerformance, setStudentsPerformance] = useState([]);
  const [gradesDistribution, setGradesDistribution] = useState([]);
  
  const isGlobal = ['admin', 'admin_teste', 'semed'].includes(user?.role);
  const userSchoolIds = useMemo(() => {
    return user?.school_ids || user?.school_links?.map(link => link.school_id) || [];
  }, [user]);
  
  const years = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 6 }, (_, i) => currentYear - 2 + i);
  }, []);

  const filteredClasses = useMemo(() => {
    if (!selectedSchool) return classes;
    return classes.filter(c => c.school_id === selectedSchool);
  }, [selectedSchool, classes]);

  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const [schoolsData, classesData] = await Promise.all([
          schoolsAPI.getAll(),
          classesAPI.getAll()
        ]);
        
        let filteredSchools = schoolsData;
        let filteredClasses = classesData;
        
        if (!isGlobal && userSchoolIds.length > 0) {
          filteredSchools = schoolsData.filter(s => userSchoolIds.includes(s.id));
          filteredClasses = classesData.filter(c => userSchoolIds.includes(c.school_id));
        }
        
        setSchools(filteredSchools);
        setClasses(filteredClasses);
      } catch (error) {
        console.error('Erro ao carregar dados iniciais:', error);
      }
    };
    loadInitialData();
  }, [isGlobal, userSchoolIds]);

  useEffect(() => {
    const loadAnalytics = async () => {
      console.log('[Analytics] loadAnalytics chamado, token:', token ? 'presente' : 'ausente');
      
      if (!token) {
        console.log('[Analytics] Token ausente, aguardando...');
        // Não seta loading false imediatamente - espera o token
        return;
      }
      
      setLoading(true);
      try {
        const params = new URLSearchParams();
        params.append('academic_year', selectedYear);
        if (selectedSchool) params.append('school_id', selectedSchool);
        if (selectedClass) params.append('class_id', selectedClass);
        if (selectedStudent) params.append('student_id', selectedStudent);
        
        const headers = { 'Authorization': `Bearer ${token}` };
        
        const safeFetch = async (url) => {
          try {
            const res = await fetch(url, { headers });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
          } catch (e) {
            console.error(`Erro ao buscar ${url}:`, e);
            return null;
          }
        };
        
        const [ovRes, trendRes, monthlyRes, subjectRes, periodRes, rankingRes, perfRes, distRes] = await Promise.all([
          safeFetch(`${API_URL}/api/analytics/overview?${params}`),
          safeFetch(`${API_URL}/api/analytics/enrollments/trend?${params}`),
          safeFetch(`${API_URL}/api/analytics/attendance/monthly?${params}`),
          safeFetch(`${API_URL}/api/analytics/grades/by-subject?${params}`),
          safeFetch(`${API_URL}/api/analytics/grades/by-period?${params}`),
          safeFetch(`${API_URL}/api/analytics/schools/ranking?${params}`),
          safeFetch(`${API_URL}/api/analytics/students/performance?${params}`),
          safeFetch(`${API_URL}/api/analytics/distribution/grades?${params}`)
        ]);
        
        console.log('[Analytics] Overview response:', ovRes);
        if (ovRes) setOverview(ovRes);
        if (trendRes) setEnrollmentsTrend(trendRes);
        if (monthlyRes) setAttendanceMonthly(monthlyRes);
        if (subjectRes) setGradesBySubject(subjectRes);
        if (periodRes) setGradesByPeriod(periodRes);
        if (rankingRes) setSchoolsRanking(rankingRes);
        if (perfRes) setStudentsPerformance(perfRes);
        if (distRes) setGradesDistribution(distRes);
      } catch (error) {
        console.error('Erro ao carregar analytics:', error);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    };
    
    loadAnalytics();
  }, [selectedYear, selectedSchool, selectedClass, selectedStudent, token]);

  useEffect(() => {
    if (selectedClass) {
      studentsAPI.getAll().then(allStudents => {
        const filtered = allStudents.filter(s => s.class_id === selectedClass || s.turma_id === selectedClass);
        setStudents(filtered);
      }).catch(() => setStudents([]));
    } else {
      setStudents([]);
      setSelectedStudent('');
    }
  }, [selectedClass]);

  const handleRefresh = () => {
    setRefreshing(true);
    window.location.reload();
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="flex flex-col items-center gap-4">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            <p className="text-gray-600">Carregando dashboard analítico...</p>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/dashboard')} className="flex items-center gap-2 text-gray-600 hover:text-gray-900">
              <Home size={20} />
              <span>Início</span>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                <BarChart3 className="text-blue-600" />
                Dashboard Analítico
              </h1>
              <p className="text-gray-600 text-sm">Acompanhamento de desempenho do município</p>
            </div>
          </div>
        </div>
        
        {/* Filtros */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2 text-gray-600">
              <Filter size={18} />
              <span className="font-medium">Filtros:</span>
            </div>
            
            <div className="flex-1 min-w-[140px] max-w-[180px]">
              <label className="block text-xs text-gray-500 mb-1">Ano Letivo</label>
              <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                {years.map(year => <option key={year} value={year}>{year}</option>)}
              </select>
            </div>
            
            <div className="flex-1 min-w-[200px] max-w-[300px]">
              <label className="block text-xs text-gray-500 mb-1">Escola</label>
              <select value={selectedSchool} onChange={(e) => { setSelectedSchool(e.target.value); setSelectedClass(''); setSelectedStudent(''); }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                <option value="">{isGlobal ? 'Todas as escolas' : 'Selecione'}</option>
                {schools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            
            <div className="flex-1 min-w-[180px] max-w-[250px]">
              <label className="block text-xs text-gray-500 mb-1">Turma</label>
              <select value={selectedClass} onChange={(e) => { setSelectedClass(e.target.value); setSelectedStudent(''); }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" disabled={!filteredClasses.length}>
                <option value="">Todas as turmas</option>
                {filteredClasses.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            
            {selectedClass && (
              <div className="flex-1 min-w-[200px] max-w-[300px]">
                <label className="block text-xs text-gray-500 mb-1">Aluno</label>
                <select value={selectedStudent} onChange={(e) => setSelectedStudent(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                  <option value="">Todos os alunos</option>
                  {students.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            )}
            
            <button onClick={handleRefresh} disabled={refreshing}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
              <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
              Atualizar
            </button>
          </div>
        </div>
        
        {/* Cards de Overview */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <Card className="bg-gradient-to-br from-blue-500 to-blue-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-blue-100 text-sm">Escolas</p>
                  <p className="text-3xl font-bold">{overview?.schools?.total || 0}</p>
                </div>
                <School className="h-10 w-10 text-blue-200" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gradient-to-br from-purple-500 to-purple-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-purple-100 text-sm">Turmas</p>
                  <p className="text-3xl font-bold">{overview?.classes?.total || 0}</p>
                </div>
                <BookOpen className="h-10 w-10 text-purple-200" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gradient-to-br from-teal-500 to-teal-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-teal-100 text-sm">Alunos Ativos</p>
                  <p className="text-3xl font-bold">{overview?.students?.active || 0}</p>
                  {overview?.students?.total > 0 && overview?.students?.active !== overview?.students?.total && (
                    <p className="text-teal-200 text-xs">de {overview?.students?.total} cadastrados</p>
                  )}
                </div>
                <Users className="h-10 w-10 text-teal-200" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gradient-to-br from-green-500 to-green-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-green-100 text-sm">Matrículas {selectedYear}</p>
                  <p className="text-3xl font-bold">{overview?.enrollments?.total || 0}</p>
                  {overview?.enrollments?.active > 0 && overview?.enrollments?.active !== overview?.enrollments?.total && (
                    <p className="text-green-200 text-xs">{overview?.enrollments?.active} ativas</p>
                  )}
                </div>
                <GraduationCap className="h-10 w-10 text-green-200" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gradient-to-br from-cyan-500 to-cyan-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-cyan-100 text-sm">Frequência</p>
                  <p className="text-3xl font-bold">{overview?.attendance?.rate || 0}%</p>
                </div>
                <Activity className="h-10 w-10 text-cyan-200" />
              </div>
            </CardContent>
          </Card>
          
          <Card className="bg-gradient-to-br from-amber-500 to-amber-600 text-white">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-amber-100 text-sm">Média Geral</p>
                  <p className="text-3xl font-bold">{overview?.grades?.average || 0}</p>
                </div>
                <Award className="h-10 w-10 text-amber-200" />
              </div>
            </CardContent>
          </Card>
        </div>
        
        {/* Indicadores de Performance */}
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <div className={`p-3 rounded-full ${(overview?.grades?.approval_rate || 0) >= 70 ? 'bg-green-100' : (overview?.grades?.approval_rate || 0) >= 50 ? 'bg-yellow-100' : 'bg-red-100'}`}>
                  {(overview?.grades?.approval_rate || 0) >= 70 ? <CheckCircle className="h-6 w-6 text-green-600" /> : 
                   (overview?.grades?.approval_rate || 0) >= 50 ? <Target className="h-6 w-6 text-yellow-600" /> : 
                   <AlertTriangle className="h-6 w-6 text-red-600" />}
                </div>
                <div>
                  <p className="text-sm text-gray-500">Taxa de Aprovação</p>
                  <p className="text-2xl font-bold text-gray-900">{overview?.grades?.approval_rate || 0}%</p>
                  <p className="text-xs text-gray-400">{overview?.grades?.approved || 0} aprovados de {overview?.grades?.total || 0}</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <div className={`p-3 rounded-full ${(overview?.attendance?.rate || 0) >= 75 ? 'bg-green-100' : (overview?.attendance?.rate || 0) >= 60 ? 'bg-yellow-100' : 'bg-red-100'}`}>
                  <Users className={`h-6 w-6 ${(overview?.attendance?.rate || 0) >= 75 ? 'text-green-600' : (overview?.attendance?.rate || 0) >= 60 ? 'text-yellow-600' : 'text-red-600'}`} />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Presença Média</p>
                  <p className="text-2xl font-bold text-gray-900">{overview?.attendance?.rate || 0}%</p>
                  <p className="text-xs text-gray-400">{overview?.attendance?.present || 0} presenças</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-full bg-red-100">
                  <AlertTriangle className="h-6 w-6 text-red-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Total de Faltas</p>
                  <p className="text-2xl font-bold text-gray-900">{overview?.attendance?.absent || 0}</p>
                  <p className="text-xs text-gray-400">{overview?.attendance?.justified || 0} justificadas</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-full bg-orange-100">
                  <LogOut className="h-6 w-6 text-orange-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Transferências</p>
                  <p className="text-2xl font-bold text-gray-900">{overview?.transfers?.total || 0}</p>
                  <p className="text-xs text-gray-400">{overview?.transfers?.rate || 0}% do total</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <div className="p-3 rounded-full bg-rose-100">
                  <UserMinus className="h-6 w-6 text-rose-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-500">Desistências</p>
                  <p className="text-2xl font-bold text-gray-900">{overview?.dropouts?.total || 0}</p>
                  <p className="text-xs text-gray-400">{overview?.dropouts?.rate || 0}% do total</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
        
        {/* Gráficos - Primeira Linha */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <Activity className="h-5 w-5 text-cyan-600" />
                Frequência Mensal
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={attendanceMonthly}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} domain={[0, 100]} />
                  <Tooltip formatter={(value, name) => [name === 'rate' ? `${value}%` : value, name === 'rate' ? 'Taxa' : name]} />
                  <Legend />
                  <Area type="monotone" dataKey="rate" name="Taxa %" stroke={COLORS.success} fill={COLORS.success} fillOpacity={0.3} />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-blue-600" />
                Desempenho por Bimestre
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={gradesByPeriod}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="period_name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 12 }} domain={[0, 10]} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="avg_grade" name="Média" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
        
        {/* Gráficos - Segunda Linha */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <BookOpen className="h-5 w-5 text-purple-600" />
                Média por Componente Curricular
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={gradesBySubject.slice(0, 10)} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis type="number" domain={[0, 10]} tick={{ fontSize: 12 }} />
                  <YAxis dataKey="abbreviation" type="category" tick={{ fontSize: 11 }} width={60} />
                  <Tooltip formatter={(value) => [value, 'Média']} />
                  <Bar dataKey="avg_grade" fill={COLORS.purple} radius={[0, 4, 4, 0]}>
                    {gradesBySubject.slice(0, 10).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <PieChartIcon className="h-5 w-5 text-amber-600" />
                Distribuição de Notas
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie data={gradesDistribution} cx="50%" cy="50%" outerRadius={100} dataKey="count" nameKey="range"
                    label={({ range, percent }) => `${range}: ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                    {gradesDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.boundary >= 6 ? COLORS.success : entry.boundary >= 5 ? COLORS.warning : COLORS.danger} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => [value, 'Quantidade']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
        
        {/* Ranking de Escolas */}
        {isGlobal && !selectedSchool && schoolsRanking.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <Award className="h-5 w-5 text-amber-600" />
                Ranking de Escolas
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">#</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Escola</th>
                      <th className="text-center py-3 px-4 text-sm font-medium text-gray-500">Matrículas</th>
                      <th className="text-center py-3 px-4 text-sm font-medium text-gray-500">Frequência</th>
                      <th className="text-center py-3 px-4 text-sm font-medium text-gray-500">Média</th>
                      <th className="text-center py-3 px-4 text-sm font-medium text-gray-500">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schoolsRanking.map((school, index) => (
                      <tr key={school.school_id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-3 px-4">
                          <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                            index === 0 ? 'bg-yellow-100 text-yellow-700' : index === 1 ? 'bg-gray-100 text-gray-700' :
                            index === 2 ? 'bg-amber-100 text-amber-700' : 'bg-gray-50 text-gray-500'}`}>
                            {index + 1}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-medium text-gray-900">{school.school_name}</td>
                        <td className="py-3 px-4 text-center text-gray-600">{school.enrollments}</td>
                        <td className="py-3 px-4 text-center">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            school.avg_attendance >= 75 ? 'bg-green-100 text-green-700' :
                            school.avg_attendance >= 60 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                            {school.avg_attendance}%
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            school.avg_grade >= 7 ? 'bg-green-100 text-green-700' :
                            school.avg_grade >= 5 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                            {school.avg_grade}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center font-bold text-blue-600">{school.score}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
        
        {/* Desempenho dos Alunos */}
        {studentsPerformance.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <Users className="h-5 w-5 text-green-600" />
                Desempenho dos Alunos (Top {studentsPerformance.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">#</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Aluno</th>
                      <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Turma</th>
                      <th className="text-center py-3 px-4 text-sm font-medium text-gray-500">Média</th>
                      <th className="text-center py-3 px-4 text-sm font-medium text-gray-500">Frequência</th>
                    </tr>
                  </thead>
                  <tbody>
                    {studentsPerformance.map((student, index) => (
                      <tr key={student.student_id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-3 px-4 text-gray-500">{index + 1}</td>
                        <td className="py-3 px-4 font-medium text-gray-900">{student.student_name}</td>
                        <td className="py-3 px-4 text-gray-600">{student.class_name}</td>
                        <td className="py-3 px-4 text-center">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            student.avg_grade >= 7 ? 'bg-green-100 text-green-700' :
                            student.avg_grade >= 5 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                            {student.avg_grade}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            student.attendance_rate >= 75 ? 'bg-green-100 text-green-700' :
                            student.attendance_rate >= 60 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                            {student.attendance_rate}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
        
        {/* Tendência de Matrículas */}
        {enrollmentsTrend.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <TrendingUp className="h-5 w-5 text-blue-600" />
                Evolução de Matrículas por Ano
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={enrollmentsTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="year" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="total" name="Total" stroke={COLORS.primary} strokeWidth={2} dot={{ r: 4 }} />
                  <Line type="monotone" dataKey="active" name="Ativos" stroke={COLORS.success} strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}

export default AnalyticsDashboard;
