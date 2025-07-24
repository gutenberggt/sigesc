import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import RecuperarSenhaPage from './pages/RecuperarSenhaPage';
import DashboardPage from './pages/DashboardPage';
import UserManagementPage from './pages/UserManagementPage';
import ProfilePage from './pages/ProfilePage';
import WelcomePage from './pages/WelcomePage';
import SchoolManagementPage from './pages/SchoolManagementPage';
import NiveisDeEnsinoPage from './pages/NiveisDeEnsinoPage';
import SeriesAnosEtapasPage from './pages/SeriesAnosEtapasPage';
import ComponentesCurricularesPage from './pages/ComponentesCurricularesPage';
import StudentManagementPage from './pages/StudentManagementPage';
import TurmasPage from './pages/TurmasPage'; // Adicionei esta importação
import { UserProvider } from './context/UserContext';

function App() {
  return (
    <Router>
      <UserProvider>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/cadastro" element={<RegisterPage />} />
          <Route path="/recuperar-senha" element={<RecuperarSenhaPage />} />

          {/* Rota Pai para o DashboardPage como layout */}
          {/* Todas as rotas aninhadas devem estar DENTRO DESTA TAG <Route> */}
          <Route path="/dashboard" element={<DashboardPage />}>
            {/* Rota aninhada padrão para /dashboard (mostra a WelcomePage) */}
            <Route index element={<WelcomePage />} />
            {/* Rotas aninhadas para outras páginas que usarão o layout do Dashboard */}
            <Route path="gerenciar-usuarios" element={<UserManagementPage />} />
            <Route path="meu-perfil" element={<ProfilePage />} />
            <Route path="cadastro-interno" element={<RegisterPage />} />

            {/* Rotas aninhadas para os submenus da Escola */}
            <Route path="escola/escola" element={<SchoolManagementPage />} />
            <Route path="escola/cursos" element={<NiveisDeEnsinoPage />} />
            <Route path="escola/series" element={<SeriesAnosEtapasPage />} />
            <Route path="escola/componentes-curriculares" element={<ComponentesCurricularesPage />} />
            <Route path="escola/alunos" element={<StudentManagementPage />} />
            <Route path="escola/turmas" element={<div>Página de Turmas</div>} /> {/* Esta linha estava duplicada/genérica, mantendo para referência do problema se não foi removida antes */}

            {/* NOVA ROTA PARA GERENCIAR TURMAS COM PARAMETRO SCHOOL_ID */}
            {/* Esta é a rota que adicionamos e precisa estar corretamente aninhada */}
            <Route path="escola/turmas/:schoolId" element={<TurmasPage />} />

          </Route> {/* Esta é a tag de fechamento para a Rota Pai /dashboard */}

        </Routes>
      </UserProvider>
    </Router>
  );
}

export default App;