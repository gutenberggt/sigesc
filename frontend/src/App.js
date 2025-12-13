import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Login } from '@/pages/Login';
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
import '@/App.css';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Rota pública */}
          <Route path="/login" element={<Login />} />
          
          {/* Rotas protegidas */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          
          {/* Rotas de administração */}
          <Route
            path="/admin/schools"
            element={
              <ProtectedRoute allowedRoles={['admin', 'semed']}>
                <Schools />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed']}>
                <Users />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/classes"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'semed']}>
                <Classes />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/courses"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'semed']}>
                <Courses />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/students"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'semed']}>
                <Students />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/grades"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'semed']}>
                <Grades />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/calendar"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'diretor', 'coordenador', 'professor', 'semed']}>
                <Calendar />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/events"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'semed']}>
                <Events />
              </ProtectedRoute>
            }
          />
          
          <Route
            path="/admin/attendance"
            element={
              <ProtectedRoute allowedRoles={['admin', 'secretario', 'professor', 'diretor', 'coordenador', 'semed']}>
                <Attendance />
              </ProtectedRoute>
            }
          />
          
          {/* Redireciona raiz para dashboard ou login */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          
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
    </AuthProvider>
  );
}

export default App;
