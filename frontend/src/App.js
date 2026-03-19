import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AuthProvider } from '@/contexts/AuthContext';
import { MantenedoraProvider } from '@/contexts/MantenedoraContext';
import { OfflineProvider } from '@/contexts/OfflineContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Login } from '@/pages/Login';
import { Skeleton } from '@/components/ui/skeleton';
import '@/App.css';

// Lazy-loaded pages
const LandingPage = lazy(() => import('@/pages/LandingPage'));
const TutorialsPage = lazy(() => import('@/pages/TutorialsPage'));
const TutorialAcesso = lazy(() => import('@/pages/tutorials/TutorialAcesso'));
const TutorialDiarioAEE = lazy(() => import('@/pages/tutorials/TutorialDiarioAEE'));
const PreMatricula = lazy(() => import('@/pages/PreMatricula'));
const PreMatriculaManagement = lazy(() => import('@/pages/PreMatriculaManagement'));
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
const LearningObjects = lazy(() => import('@/pages/LearningObjects').then(m => ({ default: m.LearningObjects })));
const UserProfile = lazy(() => import('@/pages/UserProfile').then(m => ({ default: m.UserProfile })));
const ProfessorDashboard = lazy(() => import('@/pages/ProfessorDashboard'));
const MessageLogs = lazy(() => import('@/pages/MessageLogs'));
const Announcements = lazy(() => import('@/pages/Announcements'));
const Mantenedora = lazy(() => import('@/pages/Mantenedora'));
const AuditLogs = lazy(() => import('@/pages/AuditLogs'));
const AdminTools = lazy(() => import('@/pages/AdminTools'));
const Promotion = lazy(() => import('@/pages/Promotion'));
const AnalyticsDashboard = lazy(() => import('@/pages/AnalyticsDashboard').then(m => ({ default: m.AnalyticsDashboard })));
const DiaryDashboard = lazy(() => import('@/pages/DiaryDashboard'));
const DiarioAEE = lazy(() => import('@/pages/DiarioAEE'));
const AssocialDashboard = lazy(() => import('@/pages/AssocialDashboard'));
const OnlineUsers = lazy(() => import('@/pages/OnlineUsers'));

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
const SEMED_ROLES = ['semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3'];
// Roles que podem ver o dashboard de diários
const DIARY_DASHBOARD_ROLES = ['admin', 'admin_teste', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed3'];

function App() {
  return (
    <AuthProvider>
      <OfflineProvider>
      <MantenedoraProvider>
      <BrowserRouter>
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
          
          {/* Rotas públicas */}
          <Route path="/login" element={<Login />} />
          <Route path="/pre-matricula" element={<PreMatricula />} />
          
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
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'secretario']}>
                <AnalyticsDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard de Acompanhamento de Diários */}
          <Route
            path="/admin/diary-dashboard"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed3']}>
                <DiaryDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Diário AEE (Atendimento Educacional Especializado) */}
          <Route
            path="/admin/diario-aee"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'professor', 'semed3']}>
                <DiarioAEE />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard Assistente Social */}
          <Route
            path="/ass-social"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'ass_social']}>
                <AssocialDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Rotas de administração */}
          <Route
            path="/admin/schools"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
                <Schools />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Users />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/classes"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
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
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Students />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/pre-matriculas"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor']}>
                <PreMatriculaManagement />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/grades"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Grades />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/calendar"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'auxiliar_secretaria', 'professor', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Calendar />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/events"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Events />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/attendance"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Attendance />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/learning-objects"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <LearningObjects />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/staff"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed3', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'diretor']}>
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
              <ProtectedRoute allowedRoles={['admin']}>
                <MessageLogs />
              </ProtectedRoute>
            }
          />
          
          {/* Usuários Online - apenas admin */}
          <Route
            path="/admin/online-users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'semed3']}>
                <OnlineUsers />
              </ProtectedRoute>
            }
          />
          
          {/* Avisos - todos os usuários autenticados */}
          <Route
            path="/avisos"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'professor', 'aluno', 'responsavel', 'semed', 'semed3']}>
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
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed']}>
                <AuditLogs />
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
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'apoio_pedagogico', 'auxiliar_secretaria', 'semed', 'semed3']}>
                <Promotion />
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
      </BrowserRouter>
      </MantenedoraProvider>
      </OfflineProvider>
    </AuthProvider>
  );
}

export default App;
