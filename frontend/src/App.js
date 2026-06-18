import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { lazy as reactLazy, Suspense } from 'react';
import { Toaster as SonnerToaster } from 'sonner';
import { AuthProvider } from '@/contexts/AuthContext';
import { BrandingProvider } from '@/contexts/BrandingContext';
import { MantenedoraProvider } from '@/contexts/MantenedoraContext';
import { OfflineProvider } from '@/contexts/OfflineContext';
import { MessagingProvider } from '@/contexts/MessagingContext';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';
import { ProgressProvider } from '@/contexts/ProgressContext';
import ProgressModal from '@/components/ProgressModal';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Login } from '@/pages/Login';
import { Skeleton } from '@/components/ui/skeleton';
import '@/App.css';

// P0 (Jun/2026) — Recuperação automática de ChunkLoadError com proteção anti-loop.
// Em deploys, os chunks antigos (hash diferente) deixam de existir; ao navegar para
// uma rota lazy cujo chunk sumiu, o import dinâmico falha com "Loading chunk X failed".
// Aqui envolvemos TODOS os `lazy()` num retry que, ao detectar esse erro, recarrega a
// página UMA vez (puxando o index.html/manifest novos) — com guard de 10s em
// sessionStorage para nunca entrar em loop de reload caso o chunk realmente não exista
// (ex.: offline sem pré-cache). Com o pré-cache de chunks no sw.js, o caso offline já
// não ocorre para rotas do build; este retry cobre o cenário de deploy/hash antigo.
const CHUNK_RELOAD_KEY = 'sigesc_chunk_reload_ts';
function isChunkLoadError(err) {
  const msg = (err && err.message) || '';
  return (
    (err && err.name === 'ChunkLoadError') ||
    /Loading chunk [\w-]+ failed/i.test(msg) ||
    /Failed to fetch dynamically imported module/i.test(msg) ||
    /error loading dynamically imported module/i.test(msg)
  );
}
function lazy(factory) {
  return reactLazy(async () => {
    try {
      return await factory();
    } catch (err) {
      if (isChunkLoadError(err)) {
        try {
          const last = parseInt(window.sessionStorage.getItem(CHUNK_RELOAD_KEY) || '0', 10);
          // Loop guard: só recarrega se o último reload por chunk foi há mais de 10s.
          if (Date.now() - last > 10000) {
            window.sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()));
            window.location.reload();
            // Segura o render (nunca resolve) até o reload assumir.
            return new Promise(() => {});
          }
        } catch (e) {
          /* sessionStorage indisponível — cai no throw abaixo */
        }
      }
      throw err;
    }
  });
}

// Lazy-loaded pages
const LandingPage = lazy(() => import('@/pages/LandingPage'));
const TutorialsPage = lazy(() => import('@/pages/TutorialsPage'));
const TutorialAcesso = lazy(() => import('@/pages/tutorials/TutorialAcesso'));
const TutorialDiarioAEE = lazy(() => import('@/pages/tutorials/TutorialDiarioAEE'));
const TutorialTransferencia = lazy(() => import('@/pages/tutorials/TutorialTransferencia'));
const PreMatricula = lazy(() => import('@/pages/PreMatricula'));
const PreMatriculaManagement = lazy(() => import('@/pages/PreMatriculaManagement'));
const VerifyPublic = lazy(() => import('@/pages/VerifyPublic'));
const ConfirmEmailChange = lazy(() => import('@/pages/ConfirmEmailChange'));
const PermissionMatrix = lazy(() => import('@/pages/PermissionMatrix'));
const CurriculumImport = lazy(() => import('@/pages/CurriculumImport'));
const CurriculumAdaptations = lazy(() => import('@/pages/CurriculumAdaptations'));
const CurriculumCoverage = lazy(() => import('@/pages/CurriculumCoverage'));
const Interventions = lazy(() => import('@/pages/Interventions'));
const RankingGestores = lazy(() => import('@/pages/RankingGestores'));
const PlanoAcao = lazy(() => import('@/pages/PlanoAcao'));
const DocumentValidator = lazy(() => import('@/pages/DocumentValidator'));
const ContentReview = lazy(() => import('@/pages/ContentReview'));
const TextImprovement = lazy(() => import('@/pages/TextImprovement'));
const SchoolDocuments = lazy(() => import('@/pages/SchoolDocuments'));
const BulletinViewer = lazy(() => import('@/pages/BulletinViewer'));
const VerifyBulletin = lazy(() => import('@/pages/VerifyBulletin'));
const VerifyHistory = lazy(() => import('@/pages/VerifyHistory'));
const MonthlyReports = lazy(() => import('@/pages/MonthlyReports'));
const TenantAdmin = lazy(() => import('@/pages/TenantAdmin'));
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Schools = lazy(() => import('@/pages/SchoolsComplete').then(m => ({ default: m.SchoolsComplete })));
const Users = lazy(() => import('@/pages/Users').then(m => ({ default: m.Users })));
const Classes = lazy(() => import('@/pages/Classes').then(m => ({ default: m.Classes })));
const Courses = lazy(() => import('@/pages/CoursesNew').then(m => ({ default: m.Courses })));
const Students = lazy(() => import('@/pages/StudentsComplete').then(m => ({ default: m.StudentsComplete })));
const Grades = lazy(() => import('@/pages/Grades').then(m => ({ default: m.Grades })));
const Calendar = lazy(() => import('@/pages/Calendar').then(m => ({ default: m.Calendar })));
const Events = lazy(() => import('@/pages/Events').then(m => ({ default: m.Events })));
const Attendance = lazy(() => import('@/pages/Attendance').then(m => ({ default: m.Attendance })));
const Staff = lazy(() => import('@/pages/Staff'));
const StudentHistory = lazy(() => import('@/pages/StudentHistory'));
const LearningObjects = lazy(() => import('@/pages/LearningObjects').then(m => ({ default: m.LearningObjects })));
const UserProfile = lazy(() => import('@/pages/UserProfile').then(m => ({ default: m.UserProfile })));
const ProfessorDashboard = lazy(() => import('@/pages/ProfessorDashboard'));
const MessageLogs = lazy(() => import('@/pages/MessageLogs'));
const Announcements = lazy(() => import('@/pages/Announcements'));
const Mantenedora = lazy(() => import('@/pages/Mantenedora'));
const AuditLogs = lazy(() => import('@/pages/AuditLogs'));
const EnrollmentAudit = lazy(() => import('@/pages/EnrollmentAudit').then(m => ({ default: m.EnrollmentAudit })));
const AdminTools = lazy(() => import('@/pages/AdminTools'));
const Mantenedoras = lazy(() => import('@/pages/Mantenedoras'));
const SemedPanel = lazy(() => import('@/pages/SemedPanel'));
const ActionPlans = lazy(() => import('@/pages/ActionPlans'));
const PmpiEngine = lazy(() => import('@/pages/PmpiEngine'));
const BoletimAluno = lazy(() => import('@/pages/BoletimAluno'));
const AlunoDashboard = lazy(() => import('@/pages/AlunoDashboard'));
const Promotion = lazy(() => import('@/pages/Promotion'));
const AnalyticsDashboard = lazy(() => import('@/pages/AnalyticsDashboard').then(m => ({ default: m.AnalyticsDashboard })));
const DiaryDashboard = lazy(() => import('@/pages/DiaryDashboard'));
const DiaryCalendar = lazy(() => import('@/pages/DiaryCalendar'));
const GradeIntegrity = lazy(() => import('@/pages/GradeIntegrity'));
const VerifyDiarySnapshot = lazy(() => import('@/pages/VerifyDiarySnapshot'));
const DiarioAEE = lazy(() => import('@/pages/DiarioAEE'));
const AssocialDashboard = lazy(() => import('@/pages/AssocialDashboard'));
const VaccineDashboard = lazy(() => import('@/pages/VaccineDashboard'));
const OnlineUsers = lazy(() => import('@/pages/OnlineUsers'));
const HRPayroll = lazy(() => import('@/pages/HRPayroll'));
const MECIntegration = lazy(() => import('@/pages/MECIntegration'));
const BolsaFamilia = lazy(() => import('@/pages/BolsaFamilia'));
const BuscaAtivaDashboard = lazy(() => import('@/pages/BuscaAtivaDashboard'));

// Loading fallback
function PageLoader() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="w-full max-w-md space-y-4 p-8">
        <Skeleton className="h-8 w-48 mx-auto" />
        <Skeleton className="h-4 w-64 mx-auto" />
        <div className="space-y-3 mt-8">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-3/4" />
        </div>
      </div>
    </div>
  );
}

// Roles SEMED (todos os níveis)
const SEMED_ROLES = ['semed', 'semed1', 'semed2', 'semed3'];
// Roles que podem ver o dashboard de diários
const DIARY_DASHBOARD_ROLES = ['admin', 'admin_teste', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3'];

function App() {
  return (
    <ErrorBoundary>
    <BrandingProvider>
    <AuthProvider>
      <OfflineProvider>
      <MessagingProvider>
      <MantenedoraProvider>
      <BrowserRouter>
        <UnsavedChangesProvider>
        <ProgressProvider>
        <ProgressModal />
        <SonnerToaster
          position="top-right"
          richColors
          closeButton
          toastOptions={{ duration: 5000 }}
        />
        <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Página inicial = Login */}
          <Route path="/" element={<Login />} />
          
          {/* Página Sobre (antiga landing page) */}
          <Route path="/sobre" element={<LandingPage />} />
          
          {/* Tutoriais */}
          <Route path="/tutoriais" element={<TutorialsPage />} />
          <Route path="/tutoriais/secretarios/acesso" element={<TutorialAcesso />} />
          <Route path="/tutoriais/professor-aee/diario-aee" element={<TutorialDiarioAEE />} />
          <Route path="/tutoriais/secretarios/transferencia" element={<TutorialTransferencia />} />
          
          {/* Rotas públicas */}
          <Route path="/login" element={<Login />} />
          <Route path="/confirm-email-change" element={<ConfirmEmailChange />} />
          <Route path="/pre-matricula" element={<PreMatricula />} />
          {/* G1.6 — Portal público de verificação (sem auth) */}
          <Route path="/verificar" element={<VerifyPublic />} />
          <Route path="/verificar/:code" element={<VerifyPublic />} />
          {/* Fase 5b (Mai/2026) — Verificação pública de snapshot do Diário (QR) */}
          <Route path="/verify/diary/:token" element={<VerifyDiarySnapshot />} />
          {/* Verifiable Documents MVP: URL curta /v/{token} (carregada no QR) */}
          <Route path="/v/:token" element={<VerifyPublic />} />
          {/* Boletim Oficial — verificação pública (Fase A / Iter 76) */}
          <Route path="/verify/boletim/:token" element={<VerifyBulletin />} />
          {/* Histórico Escolar Consolidado — verificação pública (Fase B / Iter 76) */}
          <Route path="/verify/historico/:token" element={<VerifyHistory />} />
          
          {/* Rotas protegidas */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard Analítico */}
          <Route
            path="/admin/analytics"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'semed3', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'secretario']}>
                <AnalyticsDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard de Acompanhamento de Diários */}
          <Route
            path="/admin/diary-dashboard"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <DiaryDashboard />
              </ProtectedRoute>
            }
          />

          {/* Calendário Operacional do Diário (Fase 5 — Mai/2026) */}
          <Route
            path="/admin/diary-calendar"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3']}>
                <DiaryCalendar />
              </ProtectedRoute>
            }
          />

          {/* Integridade da Grade Horária (Fase 6b — Mai/2026) */}
          <Route
            path="/admin/grade-integrity"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'super_admin', 'gerente', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'semed3']}>
                <GradeIntegrity />
              </ProtectedRoute>
            }
          />
          
          {/* Diário AEE (Atendimento Educacional Especializado) */}
          <Route
            path="/admin/diario-aee"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'gerente', 'admin', 'admin_teste', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'professor', 'secretario', 'diretor', 'semed1', 'semed2', 'semed3']}>
                <DiarioAEE />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard Assistente Social */}
          <Route
            path="/ass-social"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'ass_social', 'ass_social_2']}>
                <AssocialDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard Agente de Vacinas */}
          <Route
            path="/vacinas"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'agente_vacinas']}>
                <VaccineDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Rotas de administração */}
          <Route
            path="/admin/mantenedoras"
            element={
              <ProtectedRoute allowedRoles={['super_admin']}>
                <Mantenedoras />
              </ProtectedRoute>
            }
          />

          {/* PMPI-GE — Painel do Secretário */}
          <Route
            path="/semed/panel"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'secretario', 'diretor']}>
                <SemedPanel />
              </ProtectedRoute>
            }
          />

          {/* PMPI-GE — Planos de Ação */}
          <Route
            path="/action-plans"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'secretario', 'diretor', 'coordenador']}>
                <ActionPlans />
              </ProtectedRoute>
            }
          />

          {/* PMPI-GE — Motor (Alertas, Regras, Metas) - Onda 2 */}
          <Route
            path="/pmpi/engine"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3']}>
                <PmpiEngine />
              </ProtectedRoute>
            }
          />

          {/* Portal do Aluno — Dashboard + Boletim virtual */}
          <Route
            path="/aluno"
            element={
              <ProtectedRoute allowedRoles={['aluno', 'student', 'super_admin', 'admin', 'admin_teste']}>
                <AlunoDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/aluno/boletim"
            element={
              <ProtectedRoute allowedRoles={['aluno', 'student', 'super_admin', 'admin', 'admin_teste']}>
                <BoletimAluno />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin/schools"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3', 'auxiliar_secretaria']}>
                <Schools />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Users />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/classes"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Classes />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/courses"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste']}>
                <Courses />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/students"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Students />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/students/:studentId/historico"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'auxiliar_secretaria']}>
                <StudentHistory />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/pre-matriculas"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'semed3']}>
                <PreMatriculaManagement />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/grades"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Grades />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/calendar"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Calendar />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/events"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Events />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/attendance"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'secretario', 'professor', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Attendance />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/learning-objects"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <LearningObjects />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/staff"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed1', 'semed2', 'semed3', 'diretor']}>
                <Staff />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/mantenedora"
            element={
              <ProtectedRoute allowedRoles={['admin', 'semed']}>
                <Mantenedora />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/logs"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente']}>
                <MessageLogs />
              </ProtectedRoute>
            }
          />
          
          {/* Usuários Online - apenas admin */}
          <Route
            path="/admin/online-users"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'semed3']}>
                <OnlineUsers />
              </ProtectedRoute>
            }
          />
          
          {/* Avisos - todos os usuários autenticados */}
          <Route
            path="/avisos"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'professor', 'aluno', 'responsavel', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Announcements />
              </ProtectedRoute>
            }
          />
          
          {/* Rotas do Professor */}
          <Route
            path="/professor"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <ProfessorDashboard />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/turma/:classId/diario"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <ProfessorDashboard />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/turma/:classId/alunos"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <ProfessorDashboard />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/notas"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <Grades />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/frequencia"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <Attendance />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/objetos-conhecimento"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <LearningObjects />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/calendario"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <Calendar />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/professor/perfil"
            element={
              <ProtectedRoute allowedRoles={['professor']}>
                <UserProfile />
              </ProtectedRoute>
            }
          />
          
          {/* Perfil do Usuário - Rotas para todos */}
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <UserProfile />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/profile/:userId"
            element={
              <ProtectedRoute>
                <UserProfile />
              </ProtectedRoute>
            }
          />
          
          {/* Redireciona raiz para dashboard ou login */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          
          {/* Auditoria - Apenas admin, secretario, semed */}
          <Route
            path="/admin/audit-logs"
            element={
              <ProtectedRoute allowedRoles={['admin', 'semed3']}>
                <AuditLogs />
              </ProtectedRoute>
            }
          />

          {/* Auditoria de Matrículas (read-only) */}
          <Route
            path="/admin/auditoria-matriculas"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'semed', 'semed1', 'semed2', 'semed3', 'secretario']}>
                <EnrollmentAudit />
              </ProtectedRoute>
            }
          />

          {/* Matriz de Permissões — apenas Super Administrador */}
          <Route
            path="/admin/permission-matrix"
            element={
              <ProtectedRoute allowedRoles={['super_admin']}>
                <PermissionMatrix />
              </ProtectedRoute>
            }
          />

          {/* Importador de Currículo (BNCC/DCM) — apenas Super Administrador */}
          <Route
            path="/admin/curriculo/importar"
            element={
              <ProtectedRoute allowedRoles={['super_admin']}>
                <CurriculumImport />
              </ProtectedRoute>
            }
          />

          {/* CRUD de Adaptações Curriculares (v2) — Super Admin / Coordenação */}
          <Route
            path="/admin/curriculo/adaptacoes"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'coordenador', 'apoio_pedagogico']}>
                <CurriculumAdaptations />
              </ProtectedRoute>
            }
          />

          {/* Widget de Cobertura Curricular — Coordenação / Direção / Secretaria */}
          <Route
            path="/admin/curriculo/cobertura"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'coordenador', 'apoio_pedagogico', 'diretor', 'secretario', 'admin']}>
                <CurriculumCoverage />
              </ProtectedRoute>
            }
          />

          {/* Feed de Intervenções Necessárias — gestão ativa */}
          <Route
            path="/admin/intervencoes"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'coordenador', 'apoio_pedagogico', 'diretor', 'secretario']}>
                <Interventions />
              </ProtectedRoute>
            }
          />

          {/* Ranking de Gestão Curricular — accountability real */}
          <Route
            path="/admin/ranking-gestores"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'secretario', 'diretor', 'coordenador']}>
                <RankingGestores />
              </ProtectedRoute>
            }
          />

          {/* Plano de Ação Automático — direção operacional */}
          <Route
            path="/admin/plano-acao"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'secretario', 'diretor', 'coordenador']}>
                <PlanoAcao />
              </ProtectedRoute>
            }
          />

          {/* G1.7 — Declarações Escolares Verificáveis */}
          <Route
            path="/admin/declaracoes"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'secretario', 'auxiliar_secretaria', 'diretor']}>
                <SchoolDocuments />
              </ProtectedRoute>
            }
          />

          {/* G3 — Relatório Executivo Mensal */}
          <Route
            path="/admin/relatorios-mensais"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'secretario']}>
                <MonthlyReports />
              </ProtectedRoute>
            }
          />

          {/* Multi-Tenant Admin — auditoria + onboarding */}
          <Route
            path="/admin/tenant"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin']}>
                <TenantAdmin />
              </ProtectedRoute>
            }
          />

          {/* Validação de Documentos — apoio interno (Mai/2026) */}
          <Route
            path="/admin/document-validator"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'secretario', 'auxiliar_secretaria', 'diretor', 'coordenador']}>
                <DocumentValidator />
              </ProtectedRoute>
            }
          />

          {/* Boletim Online MVP — Passo 5 Fev/2026 (read-only puro) */}
          <Route
            path="/admin/bulletins"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'gerente', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'professor', 'semed', 'semed1', 'semed2', 'semed3']}>
                <BulletinViewer />
              </ProtectedRoute>
            }
          />

          {/* Fila de Revisão de Conteúdo — Mai/2026 */}
          <Route
            path="/admin/content-review"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste']}>
                <ContentReview />
              </ProtectedRoute>
            }
          />

          {/* Apoio à Escrita — Fev/2026: agora também acessível por professores
              (com escopo restrito aos próprios registros, enforced no backend). */}
          <Route
            path="/admin/text-improvement"
            element={
              <ProtectedRoute allowedRoles={['super_admin', 'admin', 'admin_teste', 'professor']}>
                <TextImprovement />
              </ProtectedRoute>
            }
          />

          {/* Ferramentas de Admin */}
          <Route
            path="/admin/tools"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste']}>
                <AdminTools />
              </ProtectedRoute>
            }
          />
          
          {/* Livro de Promoção - admin, secretario, diretor, coordenador, semed */}
          <Route
            path="/admin/promotion"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed1', 'semed2', 'semed3']}>
                <Promotion />
              </ProtectedRoute>
            }
          />
          
          {/* RH / Folha - admin, semed2, semed3, diretor, secretario */}
          <Route
            path="/admin/hr"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'semed2', 'semed3', 'diretor', 'secretario']}>
                <HRPayroll />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/mec"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste']}>
                <MECIntegration />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/bolsa-familia"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'secretario', 'diretor', 'semed3', 'ass_social_2']}>
                <BolsaFamilia />
              </ProtectedRoute>
            }
          />

          <Route
            path="/admin/bolsa-familia/busca-ativa"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'secretario', 'diretor', 'semed3', 'ass_social_2', 'gerente']}>
                <BuscaAtivaDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* 404 - Rota não encontrada */}
          <Route
            path="*"
            element={
              <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-center">
                  <h1 className="text-6xl font-bold text-gray-900 mb-4">404</h1>
                  <p className="text-xl text-gray-600 mb-6">Página não encontrada</p>
                  <a
                    href="/dashboard"
                    className="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Voltar ao Dashboard
                  </a>
                </div>
              </div>
            }
          />
        </Routes>
        </Suspense>
        </ProgressProvider>
        </UnsavedChangesProvider>
      </BrowserRouter>
      </MantenedoraProvider>
      </MessagingProvider>
      </OfflineProvider>
    </AuthProvider>
    </BrandingProvider>
    </ErrorBoundary>
  );
}

export default App;
