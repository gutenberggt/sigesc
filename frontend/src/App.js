import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/contexts/AuthContext';
import { MantenedoraProvider } from '@/contexts/MantenedoraContext';
import { OfflineProvider } from '@/contexts/OfflineContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Login } from '@/pages/Login';
import LandingPage from '@/pages/LandingPage';
import TutorialsPage from '@/pages/TutorialsPage';
import TutorialAcesso from '@/pages/tutorials/TutorialAcesso';
import PreMatricula from '@/pages/PreMatricula';
import PreMatriculaManagement from '@/pages/PreMatriculaManagement';
import { Dashboard } from '@/pages/Dashboard';
import { SchoolsComplete as Schools } from '@/pages/SchoolsComplete';
import { Users } from '@/pages/Users';
import { Classes } from '@/pages/Classes';
import { Courses } from '@/pages/CoursesNew';
import { StudentsComplete as Students } from '@/pages/StudentsComplete';
import { Grades } from '@/pages/Grades';
import { Calendar } from '@/pages/Calendar';
import { Events } from '@/pages/Events';
import { Attendance } from '@/pages/Attendance';
import Staff from '@/pages/Staff';
import { LearningObjects } from '@/pages/LearningObjects';
import { UserProfile } from '@/pages/UserProfile';
import ProfessorDashboard from '@/pages/ProfessorDashboard';
import MessageLogs from '@/pages/MessageLogs';
import Announcements from '@/pages/Announcements';
import Mantenedora from '@/pages/Mantenedora';
import AuditLogs from '@/pages/AuditLogs';
import AdminTools from '@/pages/AdminTools';
import Promotion from '@/pages/Promotion';
import { AnalyticsDashboard } from '@/pages/AnalyticsDashboard';
import DiaryDashboard from '@/pages/DiaryDashboard';
import DiarioAEE from '@/pages/DiarioAEE';
import AssocialDashboard from '@/pages/AssocialDashboard';
import '@/App.css';

// Roles SEMED (todos os níveis)
const SEMED_ROLES = ['semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3'];
// Roles que podem ver o dashboard de diários
const DIARY_DASHBOARD_ROLES = ['admin', 'admin_teste', 'diretor', 'coordenador', 'secretario', 'auxiliar_secretaria', 'semed_nivel_2', 'semed_nivel_3'];

function App() {
  return (
    <AuthProvider>
      <OfflineProvider>
      <MantenedoraProvider>
      <BrowserRouter>
        <Routes>
          {/* Página inicial = Login */}
          <Route path="/" element={<Login />} />
          
          {/* Página Sobre (antiga landing page) */}
          <Route path="/sobre" element={<LandingPage />} />
          
          {/* Tutoriais */}
          <Route path="/tutoriais" element={<TutorialsPage />} />
          <Route path="/tutoriais/secretarios/acesso" element={<TutorialAcesso />} />
          
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
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'diretor', 'coordenador', 'secretario', 'auxiliar_secretaria']}>
                <AnalyticsDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Dashboard de Acompanhamento de Diários */}
          <Route
            path="/admin/diary-dashboard"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'diretor', 'coordenador', 'secretario', 'auxiliar_secretaria', 'semed_nivel_2', 'semed_nivel_3']}>
                <DiaryDashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Diário AEE (Atendimento Educacional Especializado) */}
          <Route
            path="/admin/diario-aee"
            element={
              <ProtectedRoute allowedRoles={['admin', 'admin_teste', 'coordenador', 'professor']}>
                <DiarioAEE />
              </ProtectedRoute>
            }
          />
          
          {/* Rotas de administração */}
          <Route
            path="/admin/schools"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
                <Schools />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Users />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/classes"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
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
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
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
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'coordenador', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
                <Grades />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/calendar"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
                <Calendar />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/events"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3']}>
                <Events />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/attendance"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'diretor', 'coordenador', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
                <Attendance />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/learning-objects"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'diretor', 'coordenador', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'auxiliar_secretaria']}>
                <LearningObjects />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/staff"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed', 'semed_nivel_1', 'semed_nivel_2', 'semed_nivel_3', 'diretor']}>
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
          
          {/* Avisos - todos os usuários autenticados */}
          <Route
            path="/avisos"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'aluno', 'responsavel', 'semed']}>
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
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'semed']}>
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
      </BrowserRouter>
      </MantenedoraProvider>
      </OfflineProvider>
    </AuthProvider>
  );
}

export default App;
