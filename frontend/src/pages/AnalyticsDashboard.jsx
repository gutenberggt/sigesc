import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/contexts/AuthContext';
import { schoolsAPI, classesAPI, studentsAPI } from '@/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, PieChart, Pie, Cell, AreaChart, Area,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar
} from 'recharts';
import {
  Home, TrendingUp, Users, GraduationCap, School, BookOpen,
  Filter, RefreshCw, Award, Target, AlertTriangle, CheckCircle,
  BarChart3, PieChart as PieChartIcon, Activity, UserMinus, LogOut, Radar as RadarIcon,
  X, Info, TrendingDown, Minus, Download, FileSpreadsheet, FileText
} from 'lucide-react';
import * as XLSX from 'xlsx';
import { saveAs } from 'file-saver';
import jsPDF from 'jspdf';
import 'jspdf-autotable';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const COLORS = {
  primary: '#3b82f6',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  purple: '#8b5cf6'
};

/**
 * Exporta o ranking completo de todas as escolas para Excel
 */
const exportRankingToExcel = (schools, year) => {
  const data = [
    ['RANKING DE ESCOLAS - SCORE V2.1'],
    [`Ano Letivo: ${year}`],
    [`Data de Geração: ${new Date().toLocaleDateString('pt-BR')}`],
    [''],
    ['#', 'Escola', 'Matrículas', 'Nota', 'Aprovação', 'Evolução', 'Frequência', 'Retenção', 'Cobertura', 'SLA Freq', 'SLA Notas', 'Distorção', 'Aprend.', 'Perman.', 'Gestão', 'SCORE'],
  ];
  
  schools.forEach((school, index) => {
    const ind = school.indicators || {};
    data.push([
      index + 1,
      school.school_name,
      school.raw_data?.enrollments_active || 0,
      ind.nota_media || 0,
      `${ind.aprovacao_pct || 0}%`,
      ind.ganho_100 || 50,
      `${ind.frequencia_pct || 0}%`,
      `${ind.retencao_pct || 0}%`,
      `${ind.cobertura_pct || 0}%`,
      `${ind.sla_frequencia_pct || 0}%`,
      `${ind.sla_notas_pct || 0}%`,
      `${ind.distorcao_idade_serie_pct || 0}%`,
      school.score_aprendizagem || 0,
      school.score_permanencia || 0,
      school.score_gestao || 0,
      school.score,
    ]);
  });
  
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(data);
  
  ws['!cols'] = [
    { wch: 5 }, { wch: 35 }, { wch: 10 }, { wch: 8 }, { wch: 10 },
    { wch: 10 }, { wch: 12 }, { wch: 10 }, { wch: 10 }, { wch: 10 },
    { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 8 },
  ];
  
  XLSX.utils.book_append_sheet(wb, ws, 'Ranking');
  
  const fileName = `Ranking_Escolas_${year}.xlsx`;
  const excelBuffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  const blob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  saveAs(blob, fileName);
};

const CHART_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

// ============================================
// FUNÇÕES DE EXPORTAÇÃO
// ============================================

/**
 * Exporta o relatório da escola para Excel
 */
const exportToExcel = (school, year) => {
  const ind = school.indicators || {};
  const raw = school.raw_data || {};
  const evolution = school.grade_evolution || {};
  
  // Dados do resumo
  const resumoData = [
    ['RELATÓRIO DE DESEMPENHO ESCOLAR - SCORE V2.1'],
    [''],
    ['Escola:', school.school_name],
    ['Ano Letivo:', year],
    ['Data de Geração:', new Date().toLocaleDateString('pt-BR')],
    [''],
    ['SCORE TOTAL:', school.score, 'pontos'],
    [''],
    ['COMPOSIÇÃO POR BLOCO:'],
    ['Bloco', 'Pontuação', 'Máximo', '% Aproveitamento'],
    ['Aprendizagem', school.score_aprendizagem || 0, 45, `${((school.score_aprendizagem || 0) / 45 * 100).toFixed(1)}%`],
    ['Permanência', school.score_permanencia || 0, 35, `${((school.score_permanencia || 0) / 35 * 100).toFixed(1)}%`],
    ['Gestão', school.score_gestao || 0, 20, `${((school.score_gestao || 0) / 20 * 100).toFixed(1)}%`],
  ];
  
  // Dados dos indicadores
  const indicadoresData = [
    [''],
    ['DETALHAMENTO DOS INDICADORES:'],
    ['Indicador', 'Valor', 'Peso (pts)', 'Contribuição (pts)'],
    ['Nota Média', `${ind.nota_media || 0} / 10`, 25, ((ind.nota_100 || 0) * 0.25).toFixed(1)],
    ['Taxa de Aprovação', `${ind.aprovacao_pct || 0}%`, 10, ((ind.aprovacao_pct || 0) * 0.10).toFixed(1)],
    ['Evolução Bimestral', `${ind.ganho_100 || 50} / 100`, 10, ((ind.ganho_100 || 50) * 0.10).toFixed(1)],
    ['Frequência Média', `${ind.frequencia_pct || 0}%`, 25, ((ind.frequencia_pct || 0) * 0.25).toFixed(1)],
    ['Retenção (Anti-evasão)', `${ind.retencao_pct || 0}%`, 10, ((ind.retencao_pct || 0) * 0.10).toFixed(1)],
    ['Cobertura Curricular', `${ind.cobertura_pct || 0}%`, 10, ((ind.cobertura_pct || 0) * 0.10).toFixed(1)],
    ['SLA Frequência', `${ind.sla_frequencia_pct || 0}%`, 5, ((ind.sla_frequencia_pct || 0) * 0.05).toFixed(1)],
    ['SLA Notas', `${ind.sla_notas_pct || 0}%`, 5, ((ind.sla_notas_pct || 0) * 0.05).toFixed(1)],
    [''],
    ['INDICADOR INFORMATIVO (não entra no score):'],
    ['Distorção Idade-Série', `${ind.distorcao_idade_serie_pct || 0}%`],
  ];
  
  // Dados de evolução
  const evolucaoData = [
    [''],
    ['EVOLUÇÃO DAS NOTAS POR BIMESTRE:'],
    ['Bimestre', 'Média', 'Variação'],
    ['1º Bimestre', evolution.b1 || '-', '-'],
    ['2º Bimestre', evolution.b2 || '-', evolution.b1 && evolution.b2 ? (evolution.b2 - evolution.b1).toFixed(2) : '-'],
    ['3º Bimestre', evolution.b3 || '-', evolution.b2 && evolution.b3 ? (evolution.b3 - evolution.b2).toFixed(2) : '-'],
    ['4º Bimestre', evolution.b4 || '-', evolution.b3 && evolution.b4 ? (evolution.b4 - evolution.b3).toFixed(2) : '-'],
  ];
  
  // Dados brutos
  const dadosBrutosData = [
    [''],
    ['DADOS BRUTOS:'],
    ['Indicador', 'Valor'],
    ['Matrículas Ativas', raw.enrollments_active || 0],
    ['Matrículas Início do Ano', raw.enrollments_start || 0],
    ['Alunos Aprovados', raw.approved_count || 0],
    ['Alunos Avaliados', raw.evaluated_count || 0],
    ['Evasões', raw.dropouts || 0],
    ['Presenças Registradas', raw.attendance_present || 0],
    ['Total Registros Frequência', raw.attendance_total || 0],
    ['Objetos de Conhecimento', raw.learning_objects_count || 0],
    ['Alunos com Distorção', raw.age_distortion_count || 0],
  ];
  
  // Combinar todos os dados
  const allData = [...resumoData, ...indicadoresData, ...evolucaoData, ...dadosBrutosData];
  
  // Criar workbook
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(allData);
  
  // Ajustar largura das colunas
  ws['!cols'] = [
    { wch: 25 },
    { wch: 15 },
    { wch: 15 },
    { wch: 18 },
  ];
  
  XLSX.utils.book_append_sheet(wb, ws, 'Score V2.1');
  
  // Gerar arquivo
  const fileName = `Score_${school.school_name.replace(/[^a-zA-Z0-9]/g, '_')}_${year}.xlsx`;
  const excelBuffer = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
  const blob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  saveAs(blob, fileName);
};

/**
 * Exporta o relatório da escola para PDF
 */
const exportToPDF = (school, year) => {
  const ind = school.indicators || {};
  const raw = school.raw_data || {};
  const evolution = school.grade_evolution || {};
  
  // Criar documento PDF
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.getWidth();
  
  // Cabeçalho
  doc.setFillColor(79, 70, 229); // Indigo
  doc.rect(0, 0, pageWidth, 35, 'F');
  
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(18);
  doc.setFont('helvetica', 'bold');
  doc.text('RELATÓRIO DE DESEMPENHO ESCOLAR', pageWidth / 2, 15, { align: 'center' });
  
  doc.setFontSize(12);
  doc.setFont('helvetica', 'normal');
  doc.text(`Score V2.1 - ${school.school_name}`, pageWidth / 2, 25, { align: 'center' });
  doc.text(`Ano Letivo: ${year}`, pageWidth / 2, 32, { align: 'center' });
  
  // Score Total
  doc.setTextColor(0, 0, 0);
  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.text('SCORE TOTAL:', 14, 50);
  
  doc.setFontSize(28);
  doc.setTextColor(59, 130, 246); // Blue
  doc.text(`${school.score}`, 60, 50);
  
  doc.setFontSize(12);
  doc.setTextColor(100, 100, 100);
  doc.text('pontos', 85, 50);
  
  // Composição por Bloco
  doc.setTextColor(0, 0, 0);
  doc.setFontSize(12);
  doc.setFont('helvetica', 'bold');
  doc.text('COMPOSIÇÃO POR BLOCO:', 14, 65);
  
  doc.autoTable({
    startY: 70,
    head: [['Bloco', 'Pontuação', 'Máximo', '% Aproveitamento']],
    body: [
      ['Aprendizagem', `${school.score_aprendizagem || 0}`, '45', `${((school.score_aprendizagem || 0) / 45 * 100).toFixed(1)}%`],
      ['Permanência', `${school.score_permanencia || 0}`, '35', `${((school.score_permanencia || 0) / 35 * 100).toFixed(1)}%`],
      ['Gestão', `${school.score_gestao || 0}`, '20', `${((school.score_gestao || 0) / 20 * 100).toFixed(1)}%`],
    ],
    theme: 'striped',
    headStyles: { fillColor: [79, 70, 229], textColor: 255 },
    styles: { fontSize: 10 },
    columnStyles: {
      0: { fontStyle: 'bold' },
      1: { halign: 'center' },
      2: { halign: 'center' },
      3: { halign: 'center' },
    },
  });
  
  // Detalhamento dos Indicadores
  let yPos = doc.lastAutoTable.finalY + 15;
  doc.setFont('helvetica', 'bold');
  doc.text('DETALHAMENTO DOS INDICADORES:', 14, yPos);
  
  doc.autoTable({
    startY: yPos + 5,
    head: [['Indicador', 'Valor', 'Peso', 'Contribuição']],
    body: [
      ['Nota Média', `${ind.nota_media || 0} / 10`, '25 pts', `${((ind.nota_100 || 0) * 0.25).toFixed(1)} pts`],
      ['Taxa de Aprovação', `${ind.aprovacao_pct || 0}%`, '10 pts', `${((ind.aprovacao_pct || 0) * 0.10).toFixed(1)} pts`],
      ['Evolução Bimestral', `${ind.ganho_100 || 50} / 100`, '10 pts', `${((ind.ganho_100 || 50) * 0.10).toFixed(1)} pts`],
      ['Frequência Média', `${ind.frequencia_pct || 0}%`, '25 pts', `${((ind.frequencia_pct || 0) * 0.25).toFixed(1)} pts`],
      ['Retenção', `${ind.retencao_pct || 0}%`, '10 pts', `${((ind.retencao_pct || 0) * 0.10).toFixed(1)} pts`],
      ['Cobertura Curricular', `${ind.cobertura_pct || 0}%`, '10 pts', `${((ind.cobertura_pct || 0) * 0.10).toFixed(1)} pts`],
      ['SLA Frequência', `${ind.sla_frequencia_pct || 0}%`, '5 pts', `${((ind.sla_frequencia_pct || 0) * 0.05).toFixed(1)} pts`],
      ['SLA Notas', `${ind.sla_notas_pct || 0}%`, '5 pts', `${((ind.sla_notas_pct || 0) * 0.05).toFixed(1)} pts`],
    ],
    theme: 'striped',
    headStyles: { fillColor: [59, 130, 246], textColor: 255 },
    styles: { fontSize: 9 },
    columnStyles: {
      1: { halign: 'center' },
      2: { halign: 'center' },
      3: { halign: 'center' },
    },
  });
  
  // Evolução por Bimestre
  yPos = doc.lastAutoTable.finalY + 15;
  doc.setFont('helvetica', 'bold');
  doc.text('EVOLUÇÃO DAS NOTAS POR BIMESTRE:', 14, yPos);
  
  doc.autoTable({
    startY: yPos + 5,
    head: [['1º Bimestre', '2º Bimestre', '3º Bimestre', '4º Bimestre']],
    body: [
      [
        evolution.b1 ? evolution.b1.toFixed(2) : '-',
        evolution.b2 ? evolution.b2.toFixed(2) : '-',
        evolution.b3 ? evolution.b3.toFixed(2) : '-',
        evolution.b4 ? evolution.b4.toFixed(2) : '-',
      ],
    ],
    theme: 'grid',
    headStyles: { fillColor: [34, 197, 94], textColor: 255 },
    styles: { fontSize: 11, halign: 'center' },
  });
  
  // Indicador Informativo
  yPos = doc.lastAutoTable.finalY + 15;
  doc.setFillColor(255, 243, 205); // Amber light
  doc.rect(14, yPos - 5, pageWidth - 28, 20, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(146, 64, 14); // Amber dark
  doc.text('INDICADOR INFORMATIVO (não entra no score):', 18, yPos + 3);
  doc.setFont('helvetica', 'normal');
  doc.text(`Distorção Idade-Série: ${ind.distorcao_idade_serie_pct || 0}% dos alunos com 2+ anos acima da idade esperada`, 18, yPos + 11);
  
  // Dados Brutos
  yPos = yPos + 25;
  doc.setTextColor(0, 0, 0);
  doc.setFont('helvetica', 'bold');
  doc.text('DADOS BRUTOS:', 14, yPos);
  
  doc.autoTable({
    startY: yPos + 5,
    head: [['Indicador', 'Valor']],
    body: [
      ['Matrículas Ativas', raw.enrollments_active || 0],
      ['Alunos Aprovados', raw.approved_count || 0],
      ['Evasões', raw.dropouts || 0],
      ['Objetos de Conhecimento', raw.learning_objects_count || 0],
    ],
    theme: 'striped',
    headStyles: { fillColor: [107, 114, 128], textColor: 255 },
    styles: { fontSize: 10 },
    columnStyles: {
      1: { halign: 'center' },
    },
  });
  
  // Rodapé
  const pageCount = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(8);
    doc.setTextColor(150, 150, 150);
    doc.text(
      `SIGESC - Sistema de Gestão Escolar | Gerado em ${new Date().toLocaleDateString('pt-BR')} às ${new Date().toLocaleTimeString('pt-BR')}`,
      pageWidth / 2,
      doc.internal.pageSize.getHeight() - 10,
      { align: 'center' }
    );
  }
  
  // Salvar PDF
  const fileName = `Score_${school.school_name.replace(/[^a-zA-Z0-9]/g, '_')}_${year}.pdf`;
  doc.save(fileName);
};

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
  const [selectedSchoolDetail, setSelectedSchoolDetail] = useState(null); // Para o modal de drill-down
  const [showSemedTerms, setShowSemedTerms] = useState(false); // Modal do termo SEMED
  const [semedTermsAccepted, setSemedTermsAccepted] = useState(false); // Status do termo
  const [performanceRestricted, setPerformanceRestricted] = useState(false); // Restrição de dados de alunos
  
  const userRole = (user?.role || '').toLowerCase();
  const isAdmin = ['admin', 'admin_teste'].includes(userRole);
  const isSemed = userRole === 'semed';
  const isGlobal = isAdmin || isSemed;
  const isSchoolStaff = ['diretor', 'coordenador', 'secretario', 'secretário'].includes(userRole);
  const isProfessor = userRole === 'professor';
  
  // Determina se pode ver ranking (apenas admin/semed)
  const canViewRanking = isAdmin || (isSemed && semedTermsAccepted);
  
  // Determina se pode ver dados de alunos
  const canViewStudentData = isGlobal || isSchoolStaff || isProfessor;
  
  const userSchoolIds = useMemo(() => {
    return user?.school_ids || user?.school_links?.map(link => link.school_id) || [];
  }, [user]);
  
  const userClassIds = useMemo(() => {
    return user?.class_ids || user?.class_links?.map(link => link.class_id) || [];
  }, [user]);
  
  const years = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 6 }, (_, i) => currentYear - 2 + i);
  }, []);

  // Filtrar turmas por escola E ano letivo
  const filteredClasses = useMemo(() => {
    let filtered = classes;
    
    // Filtrar por escola se selecionada
    if (selectedSchool) {
      filtered = filtered.filter(c => c.school_id === selectedSchool);
    }
    
    // Filtrar por ano letivo (aceita int ou string)
    filtered = filtered.filter(c => {
      const classYear = c.academic_year;
      return classYear === selectedYear || classYear === String(selectedYear) || String(classYear) === String(selectedYear);
    });
    
    // Ordenar alfabeticamente por nome
    return filtered.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'pt-BR'));
  }, [selectedSchool, selectedYear, classes]);
  
  // Ordenar escolas alfabeticamente
  const sortedSchools = useMemo(() => {
    return [...schools].sort((a, b) => (a.name || '').localeCompare(b.name || '', 'pt-BR'));
  }, [schools]);
  
  // Ordenar alunos alfabeticamente
  const sortedStudents = useMemo(() => {
    return [...students].sort((a, b) => (a.full_name || a.name || '').localeCompare(b.full_name || b.name || '', 'pt-BR'));
  }, [students]);

  // Verificar termo de responsabilidade para SEMED
  useEffect(() => {
    const checkSemedTerms = async () => {
      if (!isSemed || !token) return;
      
      try {
        const response = await fetch(`${API_URL}/api/analytics/semed/check-terms`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        
        if (data.needs_acceptance) {
          setShowSemedTerms(true);
          setSemedTermsAccepted(false);
        } else {
          setSemedTermsAccepted(true);
        }
      } catch (error) {
        console.error('Erro ao verificar termo SEMED:', error);
      }
    };
    
    checkSemedTerms();
  }, [isSemed, token]);

  // Função para aceitar o termo SEMED
  const handleAcceptSemedTerms = async () => {
    try {
      const response = await fetch(`${API_URL}/api/analytics/semed/accept-terms`, {
        method: 'POST',
        headers: { 
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });
      
      if (response.ok) {
        setSemedTermsAccepted(true);
        setShowSemedTerms(false);
      }
    } catch (error) {
      console.error('Erro ao aceitar termo:', error);
    }
  };

  useEffect(() => {
    const loadInitialData = async () => {
      try {
        const [schoolsData, classesData] = await Promise.all([
          schoolsAPI.getAll(),
          classesAPI.getAll()
        ]);
        
        // Filtra apenas escolas ATIVAS
        let filteredSchools = schoolsData.filter(s => s.status === 'active' || !s.status);
        let filteredClasses = classesData;
        
        if (!isGlobal && userSchoolIds.length > 0) {
          filteredSchools = filteredSchools.filter(s => userSchoolIds.includes(s.id));
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
          // Ranking sempre busca TODAS as escolas ativas (sem filtro de school_id)
          canViewRanking ? safeFetch(`${API_URL}/api/analytics/schools/ranking?academic_year=${selectedYear}`) : null,
          canViewStudentData ? safeFetch(`${API_URL}/api/analytics/students/performance?${params}`) : null,
          safeFetch(`${API_URL}/api/analytics/distribution/grades?${params}`)
        ]);
        
        console.log('[Analytics] Overview response:', ovRes);
        if (ovRes) setOverview(ovRes);
        if (trendRes) {
          // Zera o ano de 2025 no gráfico de evolução de matrículas
          const adjustedTrend = trendRes.map(item => {
            if (item.year === 2025 || item.year === '2025') {
              return { ...item, total: 0, active: 0 };
            }
            return item;
          });
          setEnrollmentsTrend(adjustedTrend);
        }
        if (monthlyRes) setAttendanceMonthly(monthlyRes);
        if (subjectRes) setGradesBySubject(subjectRes);
        if (periodRes) setGradesByPeriod(periodRes);
        
        // Ranking - trata resposta com restrição
        if (rankingRes && !rankingRes.restricted) {
          setSchoolsRanking(Array.isArray(rankingRes) ? rankingRes : (rankingRes.data || []));
        } else {
          setSchoolsRanking([]);
        }
        
        // Performance de alunos - trata resposta com restrição
        if (perfRes) {
          if (perfRes.restricted) {
            setPerformanceRestricted(true);
            setStudentsPerformance([]);
          } else {
            setPerformanceRestricted(false);
            setStudentsPerformance(Array.isArray(perfRes) ? perfRes : (perfRes.data || []));
          }
        }
        
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

  // Carregar alunos da turma selecionada via matrículas (enrollments)
  useEffect(() => {
    const loadStudentsByClass = async () => {
      if (!selectedClass || !token) {
        setStudents([]);
        setSelectedStudent('');
        return;
      }
      
      try {
        // Buscar detalhes da turma que inclui a lista de alunos matriculados
        const response = await fetch(`${API_URL}/api/classes/${selectedClass}/details`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
          const data = await response.json();
          // Os alunos já vêm filtrados pela turma através das matrículas ativas
          setStudents(data.students || []);
        } else {
          // Fallback: buscar todos e filtrar localmente
          const allStudents = await studentsAPI.getAll();
          const filtered = allStudents.filter(s => 
            s.class_id === selectedClass || s.turma_id === selectedClass
          );
          setStudents(filtered);
        }
      } catch (error) {
        console.error('Erro ao carregar alunos da turma:', error);
        setStudents([]);
      }
    };
    
    loadStudentsByClass();
  }, [selectedClass, token]);

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
              <select value={selectedYear} onChange={(e) => { setSelectedYear(Number(e.target.value)); setSelectedClass(''); setSelectedStudent(''); }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                {years.map(year => <option key={year} value={year}>{year}</option>)}
              </select>
            </div>
            
            <div className="flex-1 min-w-[200px] max-w-[300px]">
              <label className="block text-xs text-gray-500 mb-1">Escola</label>
              <select value={selectedSchool} onChange={(e) => { setSelectedSchool(e.target.value); setSelectedClass(''); setSelectedStudent(''); }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                <option value="">{isGlobal ? 'Todas as escolas' : 'Selecione'}</option>
                {sortedSchools.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
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
                  {sortedStudents.map(s => <option key={s.id} value={s.id}>{s.full_name || s.name}</option>)}
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
        
        {/* Ranking de Escolas - Score V2.1 */}
        {canViewRanking && schoolsRanking.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Award className="h-5 w-5 text-amber-600" />
                  Ranking de Escolas - Score V2.1
                </CardTitle>
                <button 
                  onClick={() => exportRankingToExcel(schoolsRanking, selectedYear)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-medium transition-colors"
                  data-testid="export-ranking-excel-btn"
                  title="Exportar Ranking para Excel"
                >
                  <Download className="h-4 w-4" />
                  Exportar Ranking
                </button>
              </div>
              <div className="mt-2 p-3 bg-gray-50 rounded-lg">
                <p className="text-xs text-gray-600 font-medium mb-2">Composição do Score (0-100 pontos):</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-blue-500"></span>
                    <span><strong>Aprendizagem (45 pts):</strong> Nota (25) + Aprovação (10) + Evolução (10)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-green-500"></span>
                    <span><strong>Permanência (35 pts):</strong> Frequência (25) + Retenção (10)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-purple-500"></span>
                    <span><strong>Gestão (20 pts):</strong> Cobertura (10) + SLA Freq (5) + SLA Notas (5)</span>
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="border-b border-gray-200">
                      <th className="text-left py-3 px-2 text-xs font-medium text-gray-500">#</th>
                      <th className="text-left py-3 px-2 text-xs font-medium text-gray-500">Escola</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500">Matr.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-blue-50" title="Nota Média (0-10)">Nota</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-blue-50" title="Taxa de Aprovação">Aprov.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-blue-50" title="Evolução Bimestral">Evol.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-green-50" title="Frequência Média">Freq.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-green-50" title="Retenção (anti-evasão)">Ret.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-purple-50" title="Cobertura Curricular">Cob.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 bg-amber-50" title="Distorção Idade-Série (informativo)">Dist.</th>
                      <th className="text-center py-3 px-2 text-xs font-medium text-gray-500 border-l-2 border-gray-300" title="Pontuação Total">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schoolsRanking.map((school, index) => {
                      const ind = school.indicators || {};
                      const raw = school.raw_data || {};
                      return (
                        <tr 
                          key={school.school_id} 
                          className="border-b border-gray-100 hover:bg-blue-50 cursor-pointer transition-colors"
                          onClick={() => setSelectedSchoolDetail(school)}
                          data-testid={`ranking-row-${index}`}
                        >
                          <td className="py-2 px-2">
                            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                              index === 0 ? 'bg-yellow-100 text-yellow-700' : index === 1 ? 'bg-gray-100 text-gray-700' :
                              index === 2 ? 'bg-amber-100 text-amber-700' : 'bg-gray-50 text-gray-500'}`}>
                              {index + 1}
                            </span>
                          </td>
                          <td className="py-2 px-2">
                            <div className="font-medium text-gray-900 text-sm flex items-center gap-1">
                              {school.school_name}
                              <Info className="h-3 w-3 text-gray-400" />
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5">
                              Blocos: 
                              <span className="text-blue-600 ml-1">{school.score_aprendizagem || 0}</span> | 
                              <span className="text-green-600 ml-1">{school.score_permanencia || 0}</span> | 
                              <span className="text-purple-600 ml-1">{school.score_gestao || 0}</span>
                            </div>
                          </td>
                          <td className="py-2 px-2 text-center text-gray-600 text-sm">{raw.enrollments_active || 0}</td>
                          <td className="py-2 px-2 text-center bg-blue-50/30">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.nota_media || 0) >= 7 ? 'bg-green-100 text-green-700' :
                              (ind.nota_media || 0) >= 5 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.nota_media || 0}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center bg-blue-50/30">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.aprovacao_pct || 0) >= 70 ? 'bg-green-100 text-green-700' :
                              (ind.aprovacao_pct || 0) >= 50 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.aprovacao_pct || 0}%
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center bg-blue-50/30">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.ganho_100 || 0) >= 60 ? 'bg-green-100 text-green-700' :
                              (ind.ganho_100 || 0) >= 40 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.ganho_100 || 0}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center bg-green-50/30">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.frequencia_pct || 0) >= 75 ? 'bg-green-100 text-green-700' :
                              (ind.frequencia_pct || 0) >= 60 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.frequencia_pct || 0}%
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center bg-green-50/30">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.retencao_pct || 0) >= 95 ? 'bg-green-100 text-green-700' :
                              (ind.retencao_pct || 0) >= 85 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.retencao_pct || 0}%
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center bg-purple-50/30">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.cobertura_pct || 0) >= 70 ? 'bg-green-100 text-green-700' :
                              (ind.cobertura_pct || 0) >= 40 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.cobertura_pct || 0}%
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center bg-amber-50/30" title="Distorção idade-série (2+ anos acima da idade esperada)">
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              (ind.distorcao_idade_serie_pct || 0) <= 10 ? 'bg-green-100 text-green-700' :
                              (ind.distorcao_idade_serie_pct || 0) <= 25 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>
                              {ind.distorcao_idade_serie_pct || 0}%
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center border-l-2 border-gray-300">
                            <span className="text-lg font-bold text-blue-600">{school.score}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 p-3 bg-amber-50 rounded-lg text-xs text-amber-800">
                <strong>Legenda:</strong> 
                <span className="ml-2">Nota = Média (0-10)</span> |
                <span className="ml-2">Aprov. = Taxa de Aprovação</span> |
                <span className="ml-2">Evol. = Evolução Bimestral (50=estável)</span> |
                <span className="ml-2">Freq. = Frequência Média</span> |
                <span className="ml-2">Ret. = Retenção (100-evasão%)</span> |
                <span className="ml-2">Cob. = Cobertura Curricular</span> |
                <span className="ml-2">Dist. = Distorção Idade-Série (informativo, não entra no score)</span>
              </div>
            </CardContent>
          </Card>
        )}
        
        {/* Gráfico de Radar - Comparativo de Escolas por Bloco */}
        {canViewRanking && !selectedSchool && schoolsRanking.length > 0 && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <RadarIcon className="h-5 w-5 text-indigo-600" />
                Análise Comparativa por Bloco - Top {Math.min(5, schoolsRanking.length)} Escolas
              </CardTitle>
              <p className="text-xs text-gray-500 mt-1">
                Visualização dos pontos fortes e fracos de cada escola nos 3 blocos do Score V2.1
              </p>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Gráfico de Radar Principal */}
                <div>
                  <ResponsiveContainer width="100%" height={350}>
                    <RadarChart 
                      data={[
                        { 
                          bloco: 'Aprendizagem', 
                          maximo: 45,
                          ...Object.fromEntries(
                            schoolsRanking.slice(0, 5).map((s, i) => [`escola${i}`, s.score_aprendizagem || 0])
                          )
                        },
                        { 
                          bloco: 'Permanência', 
                          maximo: 35,
                          ...Object.fromEntries(
                            schoolsRanking.slice(0, 5).map((s, i) => [`escola${i}`, s.score_permanencia || 0])
                          )
                        },
                        { 
                          bloco: 'Gestão', 
                          maximo: 20,
                          ...Object.fromEntries(
                            schoolsRanking.slice(0, 5).map((s, i) => [`escola${i}`, s.score_gestao || 0])
                          )
                        }
                      ]}
                    >
                      <PolarGrid stroke="#e5e7eb" />
                      <PolarAngleAxis 
                        dataKey="bloco" 
                        tick={{ fontSize: 12, fill: '#374151' }}
                      />
                      <PolarRadiusAxis 
                        angle={90} 
                        domain={[0, 45]} 
                        tick={{ fontSize: 10 }}
                        tickCount={5}
                      />
                      {schoolsRanking.slice(0, 5).map((school, index) => (
                        <Radar
                          key={school.school_id}
                          name={school.school_name.length > 20 ? school.school_name.substring(0, 20) + '...' : school.school_name}
                          dataKey={`escola${index}`}
                          stroke={CHART_COLORS[index]}
                          fill={CHART_COLORS[index]}
                          fillOpacity={0.15}
                          strokeWidth={2}
                        />
                      ))}
                      <Legend 
                        wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }}
                      />
                      <Tooltip 
                        formatter={(value, name) => [`${value} pts`, name]}
                        contentStyle={{ fontSize: '12px' }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                
                {/* Resumo por Escola */}
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-gray-700 mb-3">
                    Resumo por Escola 
                    <span className="text-xs font-normal text-gray-500 ml-2">(clique para detalhes)</span>
                  </h4>
                  {schoolsRanking.slice(0, 5).map((school, index) => {
                    const aprendPct = ((school.score_aprendizagem || 0) / 45 * 100).toFixed(0);
                    const permanPct = ((school.score_permanencia || 0) / 35 * 100).toFixed(0);
                    const gestaoPct = ((school.score_gestao || 0) / 20 * 100).toFixed(0);
                    
                    return (
                      <div 
                        key={school.school_id} 
                        className="p-3 bg-gray-50 rounded-lg cursor-pointer hover:bg-gray-100 hover:shadow-md transition-all"
                        onClick={() => setSelectedSchoolDetail(school)}
                        data-testid={`school-radar-item-${index}`}
                      >
                        <div className="flex items-center gap-2 mb-2">
                          <div 
                            className="w-3 h-3 rounded-full" 
                            style={{ backgroundColor: CHART_COLORS[index] }}
                          />
                          <span className="font-medium text-sm text-gray-800 truncate">
                            {school.school_name}
                          </span>
                          <Info className="h-3 w-3 text-gray-400 ml-1" />
                          <span className="ml-auto text-sm font-bold text-blue-600">
                            {school.score} pts
                          </span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-xs">
                          <div className="text-center">
                            <div className="text-gray-500 mb-1">Aprendizagem</div>
                            <div className="flex items-center justify-center gap-1">
                              <div className="w-full bg-gray-200 rounded-full h-2">
                                <div 
                                  className="bg-blue-500 h-2 rounded-full transition-all"
                                  style={{ width: `${aprendPct}%` }}
                                />
                              </div>
                              <span className="text-gray-700 font-medium w-8">{aprendPct}%</span>
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-gray-500 mb-1">Permanência</div>
                            <div className="flex items-center justify-center gap-1">
                              <div className="w-full bg-gray-200 rounded-full h-2">
                                <div 
                                  className="bg-green-500 h-2 rounded-full transition-all"
                                  style={{ width: `${permanPct}%` }}
                                />
                              </div>
                              <span className="text-gray-700 font-medium w-8">{permanPct}%</span>
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-gray-500 mb-1">Gestão</div>
                            <div className="flex items-center justify-center gap-1">
                              <div className="w-full bg-gray-200 rounded-full h-2">
                                <div 
                                  className="bg-purple-500 h-2 rounded-full transition-all"
                                  style={{ width: `${gestaoPct}%` }}
                                />
                              </div>
                              <span className="text-gray-700 font-medium w-8">{gestaoPct}%</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  
                  {/* Legenda dos Blocos */}
                  <div className="mt-4 p-3 bg-indigo-50 rounded-lg text-xs">
                    <div className="font-semibold text-indigo-800 mb-2">Máximo por Bloco:</div>
                    <div className="grid grid-cols-3 gap-2 text-indigo-700">
                      <div className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                        <span>Aprendizagem: 45 pts</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-green-500"></span>
                        <span>Permanência: 35 pts</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-2 h-2 rounded-full bg-purple-500"></span>
                        <span>Gestão: 20 pts</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
        
        {/* Modal de Drill-Down - Detalhes da Escola */}
        {selectedSchoolDetail && (
          <div 
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
            onClick={() => setSelectedSchoolDetail(null)}
          >
            <div 
              className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header do Modal */}
              <div className="sticky top-0 bg-gradient-to-r from-indigo-600 to-blue-600 text-white p-4 rounded-t-xl">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold">{selectedSchoolDetail.school_name}</h2>
                    <p className="text-indigo-100 text-sm">Análise Detalhada do Score V2.1</p>
                  </div>
                  <div className="flex items-center gap-4">
                    {/* Botões de Exportação */}
                    <div className="flex items-center gap-2">
                      <button 
                        onClick={() => exportToExcel(selectedSchoolDetail, selectedYear)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500 hover:bg-green-600 rounded-lg text-sm font-medium transition-colors"
                        data-testid="export-excel-btn"
                        title="Exportar para Excel"
                      >
                        <FileSpreadsheet className="h-4 w-4" />
                        Excel
                      </button>
                      <button 
                        onClick={() => exportToPDF(selectedSchoolDetail, selectedYear)}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500 hover:bg-red-600 rounded-lg text-sm font-medium transition-colors"
                        data-testid="export-pdf-btn"
                        title="Exportar para PDF"
                      >
                        <FileText className="h-4 w-4" />
                        PDF
                      </button>
                    </div>
                    <div className="text-center border-l border-white/30 pl-4">
                      <div className="text-3xl font-bold">{selectedSchoolDetail.score}</div>
                      <div className="text-xs text-indigo-200">Score Total</div>
                    </div>
                    <button 
                      onClick={() => setSelectedSchoolDetail(null)}
                      className="p-2 hover:bg-white/20 rounded-full transition-colors"
                      data-testid="close-school-detail-modal"
                    >
                      <X className="h-6 w-6" />
                    </button>
                  </div>
                </div>
              </div>
              
              <div className="p-6 space-y-6">
                {/* Resumo dos Blocos */}
                <div className="grid grid-cols-3 gap-4">
                  <div className="bg-blue-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-blue-600">
                      {selectedSchoolDetail.score_aprendizagem || 0}
                      <span className="text-sm font-normal text-blue-400">/45</span>
                    </div>
                    <div className="text-sm text-blue-700 font-medium">Aprendizagem</div>
                    <div className="text-xs text-blue-500 mt-1">
                      {((selectedSchoolDetail.score_aprendizagem || 0) / 45 * 100).toFixed(0)}% do máximo
                    </div>
                  </div>
                  <div className="bg-green-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-green-600">
                      {selectedSchoolDetail.score_permanencia || 0}
                      <span className="text-sm font-normal text-green-400">/35</span>
                    </div>
                    <div className="text-sm text-green-700 font-medium">Permanência</div>
                    <div className="text-xs text-green-500 mt-1">
                      {((selectedSchoolDetail.score_permanencia || 0) / 35 * 100).toFixed(0)}% do máximo
                    </div>
                  </div>
                  <div className="bg-purple-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-purple-600">
                      {selectedSchoolDetail.score_gestao || 0}
                      <span className="text-sm font-normal text-purple-400">/20</span>
                    </div>
                    <div className="text-sm text-purple-700 font-medium">Gestão</div>
                    <div className="text-xs text-purple-500 mt-1">
                      {((selectedSchoolDetail.score_gestao || 0) / 20 * 100).toFixed(0)}% do máximo
                    </div>
                  </div>
                </div>
                
                {/* Detalhamento dos 8 Indicadores */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <BarChart3 className="h-5 w-5 text-gray-600" />
                    Detalhamento dos Indicadores
                  </h3>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* BLOCO APRENDIZAGEM */}
                    <div className="space-y-3">
                      <div className="text-sm font-semibold text-blue-700 bg-blue-50 px-3 py-1 rounded-md inline-block">
                        Bloco Aprendizagem (45 pts)
                      </div>
                      
                      {/* Nota Média */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-sm font-medium text-gray-700">Nota Média</span>
                          <span className="text-sm font-bold text-gray-900">
                            {selectedSchoolDetail.indicators?.nota_media || 0} / 10
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className="bg-blue-500 h-2.5 rounded-full transition-all"
                            style={{ width: `${selectedSchoolDetail.indicators?.nota_100 || 0}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-1">
                          <span>Peso: 25 pts</span>
                          <span>Contribuição: {((selectedSchoolDetail.indicators?.nota_100 || 0) * 0.25).toFixed(1)} pts</span>
                        </div>
                      </div>
                      
                      {/* Taxa de Aprovação */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-sm font-medium text-gray-700">Taxa de Aprovação</span>
                          <span className="text-sm font-bold text-gray-900">
                            {selectedSchoolDetail.indicators?.aprovacao_pct || 0}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className="bg-blue-400 h-2.5 rounded-full transition-all"
                            style={{ width: `${selectedSchoolDetail.indicators?.aprovacao_pct || 0}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-1">
                          <span>Peso: 10 pts</span>
                          <span>Contribuição: {((selectedSchoolDetail.indicators?.aprovacao_pct || 0) * 0.10).toFixed(1)} pts</span>
                        </div>
                      </div>
                      
                      {/* Evolução Bimestral */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-sm font-medium text-gray-700 flex items-center gap-1">
                            Evolução Bimestral
                            {(selectedSchoolDetail.indicators?.ganho_100 || 50) > 50 ? (
                              <TrendingUp className="h-4 w-4 text-green-500" />
                            ) : (selectedSchoolDetail.indicators?.ganho_100 || 50) < 50 ? (
                              <TrendingDown className="h-4 w-4 text-red-500" />
                            ) : (
                              <Minus className="h-4 w-4 text-gray-400" />
                            )}
                          </span>
                          <span className="text-sm font-bold text-gray-900">
                            {selectedSchoolDetail.indicators?.ganho_100 || 50} / 100
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className={`h-2.5 rounded-full transition-all ${
                              (selectedSchoolDetail.indicators?.ganho_100 || 50) >= 60 ? 'bg-green-500' :
                              (selectedSchoolDetail.indicators?.ganho_100 || 50) >= 40 ? 'bg-yellow-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${selectedSchoolDetail.indicators?.ganho_100 || 50}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-1">
                          <span>Peso: 10 pts (50 = estável)</span>
                          <span>Contribuição: {((selectedSchoolDetail.indicators?.ganho_100 || 50) * 0.10).toFixed(1)} pts</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* BLOCO PERMANÊNCIA + GESTÃO */}
                    <div className="space-y-3">
                      <div className="text-sm font-semibold text-green-700 bg-green-50 px-3 py-1 rounded-md inline-block">
                        Bloco Permanência (35 pts)
                      </div>
                      
                      {/* Frequência */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-sm font-medium text-gray-700">Frequência Média</span>
                          <span className="text-sm font-bold text-gray-900">
                            {selectedSchoolDetail.indicators?.frequencia_pct || 0}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className="bg-green-500 h-2.5 rounded-full transition-all"
                            style={{ width: `${selectedSchoolDetail.indicators?.frequencia_pct || 0}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-1">
                          <span>Peso: 25 pts</span>
                          <span>Contribuição: {((selectedSchoolDetail.indicators?.frequencia_pct || 0) * 0.25).toFixed(1)} pts</span>
                        </div>
                      </div>
                      
                      {/* Retenção */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-sm font-medium text-gray-700">Retenção (Anti-evasão)</span>
                          <span className="text-sm font-bold text-gray-900">
                            {selectedSchoolDetail.indicators?.retencao_pct || 0}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className="bg-green-400 h-2.5 rounded-full transition-all"
                            style={{ width: `${selectedSchoolDetail.indicators?.retencao_pct || 0}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-1">
                          <span>Peso: 10 pts</span>
                          <span>Contribuição: {((selectedSchoolDetail.indicators?.retencao_pct || 0) * 0.10).toFixed(1)} pts</span>
                        </div>
                      </div>
                      
                      <div className="text-sm font-semibold text-purple-700 bg-purple-50 px-3 py-1 rounded-md inline-block mt-2">
                        Bloco Gestão (20 pts)
                      </div>
                      
                      {/* Cobertura Curricular */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-sm font-medium text-gray-700">Cobertura Curricular</span>
                          <span className="text-sm font-bold text-gray-900">
                            {selectedSchoolDetail.indicators?.cobertura_pct || 0}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5">
                          <div 
                            className="bg-purple-500 h-2.5 rounded-full transition-all"
                            style={{ width: `${Math.min(100, selectedSchoolDetail.indicators?.cobertura_pct || 0)}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 mt-1">
                          <span>Peso: 10 pts</span>
                          <span>Contribuição: {((selectedSchoolDetail.indicators?.cobertura_pct || 0) * 0.10).toFixed(1)} pts</span>
                        </div>
                      </div>
                      
                      {/* SLA Frequência + Notas (agrupados) */}
                      <div className="bg-white border rounded-lg p-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <div className="text-xs font-medium text-gray-600 mb-1">SLA Frequência (3 dias)</div>
                            <div className="text-lg font-bold text-purple-600">
                              {selectedSchoolDetail.indicators?.sla_frequencia_pct || 0}%
                            </div>
                            <div className="text-xs text-gray-500">Peso: 5 pts</div>
                          </div>
                          <div>
                            <div className="text-xs font-medium text-gray-600 mb-1">SLA Notas (7 dias)</div>
                            <div className="text-lg font-bold text-purple-600">
                              {selectedSchoolDetail.indicators?.sla_notas_pct || 0}%
                            </div>
                            <div className="text-xs text-gray-500">Peso: 5 pts</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Evolução das Notas por Bimestre */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <TrendingUp className="h-5 w-5 text-gray-600" />
                    Evolução das Notas por Bimestre
                  </h3>
                  
                  <div className="bg-gray-50 rounded-lg p-4">
                    <ResponsiveContainer width="100%" height={200}>
                      <AreaChart
                        data={[
                          { bimestre: '1º Bim', nota: selectedSchoolDetail.grade_evolution?.b1 || 0 },
                          { bimestre: '2º Bim', nota: selectedSchoolDetail.grade_evolution?.b2 || 0 },
                          { bimestre: '3º Bim', nota: selectedSchoolDetail.grade_evolution?.b3 || 0 },
                          { bimestre: '4º Bim', nota: selectedSchoolDetail.grade_evolution?.b4 || 0 },
                        ]}
                        margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                      >
                        <defs>
                          <linearGradient id="colorNota" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                        <XAxis dataKey="bimestre" tick={{ fontSize: 12 }} />
                        <YAxis domain={[0, 10]} tick={{ fontSize: 12 }} />
                        <Tooltip 
                          formatter={(value) => [`${value.toFixed(2)}`, 'Média']}
                          contentStyle={{ fontSize: '12px' }}
                        />
                        <Area 
                          type="monotone" 
                          dataKey="nota" 
                          stroke="#3b82f6" 
                          fillOpacity={1} 
                          fill="url(#colorNota)"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                    
                    {/* Análise da Evolução */}
                    <div className="mt-4 grid grid-cols-4 gap-2 text-center">
                      {[
                        { label: '1º Bim', value: selectedSchoolDetail.grade_evolution?.b1 },
                        { label: '2º Bim', value: selectedSchoolDetail.grade_evolution?.b2 },
                        { label: '3º Bim', value: selectedSchoolDetail.grade_evolution?.b3 },
                        { label: '4º Bim', value: selectedSchoolDetail.grade_evolution?.b4 },
                      ].map((bim, idx, arr) => {
                        const prevValue = idx > 0 ? arr[idx - 1].value : null;
                        const diff = prevValue !== null && bim.value ? (bim.value - prevValue).toFixed(2) : null;
                        return (
                          <div key={bim.label} className="bg-white rounded-lg p-2 border">
                            <div className="text-xs text-gray-500">{bim.label}</div>
                            <div className="text-lg font-bold text-gray-800">
                              {bim.value ? bim.value.toFixed(1) : '-'}
                            </div>
                            {diff !== null && (
                              <div className={`text-xs font-medium ${
                                parseFloat(diff) > 0 ? 'text-green-600' : 
                                parseFloat(diff) < 0 ? 'text-red-600' : 'text-gray-400'
                              }`}>
                                {parseFloat(diff) > 0 ? '+' : ''}{diff}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
                
                {/* Indicador Informativo - Distorção */}
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="h-6 w-6 text-amber-600" />
                    <div>
                      <div className="text-sm font-semibold text-amber-800">
                        Distorção Idade-Série (Indicador Informativo)
                      </div>
                      <div className="text-xs text-amber-600">
                        Este indicador não entra no cálculo do score, mas é importante para análise
                      </div>
                    </div>
                    <div className="ml-auto text-right">
                      <div className="text-2xl font-bold text-amber-700">
                        {selectedSchoolDetail.indicators?.distorcao_idade_serie_pct || 0}%
                      </div>
                      <div className="text-xs text-amber-600">
                        dos alunos com 2+ anos acima da idade esperada
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Dados Brutos */}
                <div>
                  <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <Activity className="h-5 w-5 text-gray-600" />
                    Dados Brutos
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-gray-500 text-xs">Matrículas Ativas</div>
                      <div className="text-xl font-bold text-gray-800">
                        {selectedSchoolDetail.raw_data?.enrollments_active || 0}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-gray-500 text-xs">Aprovados</div>
                      <div className="text-xl font-bold text-green-600">
                        {selectedSchoolDetail.raw_data?.approved_count || 0}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-gray-500 text-xs">Evasões</div>
                      <div className="text-xl font-bold text-red-600">
                        {selectedSchoolDetail.raw_data?.dropouts || 0}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-gray-500 text-xs">Objetos de Conhecimento</div>
                      <div className="text-xl font-bold text-purple-600">
                        {selectedSchoolDetail.raw_data?.learning_objects_count || 0}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        {/* Desempenho dos Alunos - Com restrições de acesso */}
        {canViewStudentData && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg flex items-center gap-2">
                <Users className="h-5 w-5 text-green-600" />
                Desempenho dos Alunos
                {isProfessor && !selectedClass && (
                  <span className="text-xs font-normal text-amber-600 ml-2">(Selecione uma turma)</span>
                )}
              </CardTitle>
              {/* Indicador de restrição por perfil */}
              <div className="mt-1 text-xs text-gray-500">
                {isProfessor && (
                  <span className="flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3 text-amber-500" />
                    Visualização restrita às suas turmas e componentes curriculares
                  </span>
                )}
                {isSchoolStaff && (
                  <span className="flex items-center gap-1">
                    <Info className="h-3 w-3 text-blue-500" />
                    Visualização restrita à sua escola
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {/* Mensagem quando professor não selecionou turma */}
              {isProfessor && !selectedClass ? (
                <div className="text-center py-8 text-gray-500">
                  <Users className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                  <p className="font-medium">Selecione uma turma para visualizar o desempenho dos alunos</p>
                  <p className="text-sm mt-1">Como professor, você tem acesso apenas aos dados das suas turmas.</p>
                </div>
              ) : performanceRestricted ? (
                <div className="text-center py-8 text-amber-600">
                  <AlertTriangle className="h-12 w-12 mx-auto mb-3 text-amber-400" />
                  <p className="font-medium">Acesso Restrito</p>
                  <p className="text-sm mt-1 text-gray-500">Você não tem permissão para visualizar estes dados.</p>
                </div>
              ) : studentsPerformance.length > 0 ? (
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
              ) : (
                <div className="text-center py-8 text-gray-500">
                  <Users className="h-12 w-12 mx-auto mb-3 text-gray-300" />
                  <p>Nenhum dado de desempenho disponível para os filtros selecionados.</p>
                </div>
              )}
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
      
      {/* Modal Termo de Responsabilidade - SEMED */}
      {showSemedTerms && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="bg-gradient-to-r from-amber-500 to-orange-500 text-white p-6 rounded-t-xl">
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-8 w-8" />
                <div>
                  <h2 className="text-xl font-bold">Termo de Responsabilidade</h2>
                  <p className="text-amber-100 text-sm">Acesso a Dados Sensíveis - SEMED</p>
                </div>
              </div>
            </div>
            
            <div className="p-6 space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <h3 className="font-semibold text-amber-800 mb-2">Atenção:</h3>
                <p className="text-amber-700 text-sm">
                  Você está prestes a acessar dados sensíveis e confidenciais do sistema educacional municipal.
                </p>
              </div>
              
              <div className="space-y-3 text-sm text-gray-700">
                <p><strong>Ao aceitar este termo, você declara que:</strong></p>
                <ul className="list-disc pl-5 space-y-2">
                  <li>Compreende que os dados apresentados são <strong>confidenciais</strong> e protegidos pela LGPD (Lei Geral de Proteção de Dados);</li>
                  <li>Utilizará as informações <strong>exclusivamente para fins de gestão educacional</strong> no âmbito de suas atribuições;</li>
                  <li><strong>Não compartilhará, divulgará ou publicará</strong> dados individuais de alunos ou rankings comparativos de escolas em meios não autorizados;</li>
                  <li>Reconhece que o <strong>uso indevido</strong> dos dados pode resultar em responsabilização administrativa, civil e penal;</li>
                  <li>Compromete-se a <strong>reportar imediatamente</strong> qualquer incidente de segurança ou uso inadequado das informações.</li>
                </ul>
              </div>
              
              <div className="bg-gray-100 rounded-lg p-4 text-xs text-gray-600">
                <p><strong>Dados acessíveis após aceite:</strong></p>
                <ul className="mt-2 space-y-1">
                  <li>• Ranking de Escolas (Score V2.1)</li>
                  <li>• Desempenho individual de alunos (notas e frequência)</li>
                  <li>• Indicadores de distorção idade-série</li>
                  <li>• Taxas de evasão e aprovação por escola</li>
                </ul>
                <p className="mt-2 text-gray-500">Este aceite é válido por 30 dias.</p>
              </div>
              
              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => {
                    setShowSemedTerms(false);
                    // Redireciona para dashboard se não aceitar
                  }}
                  className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Recusar e Voltar
                </button>
                <button
                  onClick={handleAcceptSemedTerms}
                  className="flex-1 px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors font-medium"
                  data-testid="accept-semed-terms-btn"
                >
                  Li e Aceito o Termo
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}

export default AnalyticsDashboard;
