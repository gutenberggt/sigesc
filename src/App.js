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
// Removido StudentManagementPage e adicionado PessoaManagementPage
import PessoaManagementPage from './pages/PessoaManagementPage';
import TurmasPage from './pages/TurmasPage';
import MatriculaAlunoPage from './pages/MatriculaAlunoPage';
import BuscaAlunoPage from './pages/BuscaAlunoPage'; // NOVO: Importar a página de Busca de Aluno

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
          <Route path="/dashboard" element={<DashboardPage />}>
            <Route index element={<WelcomePage />} /> 
            <Route path="gerenciar-usuarios" element={<UserManagementPage />} />
            <Route path="meu-perfil" element={<ProfilePage />} />
            <Route path="cadastro-interno" element={<RegisterPage />} /> 
            
            {/* Rotas para os submenus da Escola */}
            <Route path="escola/escola" element={<SchoolManagementPage />} /> 
			<Route path="escola/matriculas" element={<MatriculaAlunoPage />} /> {/* Nova rota */}
			<Route path="escola/busca-aluno" element={<BuscaAlunoPage />} /> {/* NOVA ROTA PARA BUSCA DE ALUNO */}
			<Route path="escola/cursos" element={<NiveisDeEnsinoPage />} />
			<Route path="escola/series" element={<SeriesAnosEtapasPage />} />
			<Route path="escola/componentes-curriculares" element={<ComponentesCurricularesPage />} />
			<Route path="escola/pessoas" element={<PessoaManagementPage />} /> {/* Rota para Gerenciar Pessoas */}
            <Route path="escola/turmas/:schoolId" element={<TurmasPage />} /> {/* Rota para Gerenciar Turmas */}

          </Route>
                    
        </Routes>
      </UserProvider>
    </Router>
  );
}

export default App;