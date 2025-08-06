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
import PessoaManagementPage from './pages/PessoaManagementPage';
import TurmasPage from './pages/TurmasPage';
import MatriculaAlunoPage from './pages/MatriculaAlunoPage';
import BuscaAlunoPage from './pages/BuscaAlunoPage';
import FichaAlunoPage from './pages/FichaAlunoPage';
import EditarAlunoPage from './pages/EditarAlunoPage';
import NovaMatriculaAlunoPage from './pages/NovaMatriculaAlunoPage';
import CadastroServidorPage from "./pages/CadastroServidorPage";
import BuscaServidorPage from "./pages/BuscaServidorPage";
import FichaServidorPage from "./pages/FichaServidorPage";
import CalendarioPage from "./pages/calendarioPage";
import BimestresPage from "./pages/bimestresPage";
import EventosPage from "./pages/eventosPage";
import AdicionarEventosPage from './pages/adicionarEventosPage';
import HorarioPage from "./pages/horarioPage";
import ListaHorarioPage from "./pages/listaHorarioPage";
import EditarServidorPage from "./pages/EditarServidorPage";

import { UserProvider } from './context/UserContext';

function App() {
  return (
    <Router>
      <UserProvider>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/cadastro" element={<RegisterPage />} /> 
          <Route path="/recuperar-senha" element={<RecuperarSenhaPage />} />
          
          <Route path="/dashboard" element={<DashboardPage />}>
            <Route index element={<WelcomePage />} /> 
            <Route path="gerenciar-usuarios" element={<UserManagementPage />} />
            <Route path="meu-perfil" element={<ProfilePage />} />
            <Route path="cadastro-interno" element={<RegisterPage />} /> 
            
            {/* Rotas de Gestão */}
            <Route path="escola/escola" element={<SchoolManagementPage />} /> 
			      <Route path="escola/matriculas" element={<MatriculaAlunoPage />} />
			      <Route path="escola/busca-aluno" element={<BuscaAlunoPage />} />
			      <Route path="escola/cursos" element={<NiveisDeEnsinoPage />} />
			      <Route path="escola/series" element={<SeriesAnosEtapasPage />} />
			      <Route path="escola/componentes-curriculares" element={<ComponentesCurricularesPage />} />
			      <Route path="escola/pessoas" element={<PessoaManagementPage />} />
            <Route path="escola/turmas/:schoolId" element={<TurmasPage />} />
            <Route path="escola/aluno/ficha/:alunoId" element={<FichaAlunoPage />} />
            <Route path="escola/aluno/editar/:alunoId" element={<EditarAlunoPage />} />
            <Route path="escola/aluno/nova-matricula/:alunoId" element={<NovaMatriculaAlunoPage />} />
            <Route path="escola/servidores/cadastro" element={<CadastroServidorPage />} />
            <Route path="escola/servidores/busca" element={<BuscaServidorPage />} />
            <Route path="escola/servidor/ficha/:servidorId" element={<FichaServidorPage />} />
            
            {/* ======================= INÍCIO DA ADIÇÃO ======================= */}
            <Route path="escola/servidor/editar/:servidorId" element={<EditarServidorPage />} />
            {/* ======================== FIM DA ADIÇÃO ========================= */}

            {/* Rotas do Calendário */}
            <Route path="calendario/calendario" element={<CalendarioPage />} />
            <Route path="calendario/bimestres" element={<BimestresPage />} />
            <Route path="calendario/eventos" element={<EventosPage />} /> 
			      <Route path="calendario/adicionar-evento" element={<AdicionarEventosPage />} />
            <Route path="calendario/editar-evento/:eventoId" element={<AdicionarEventosPage />} />
            <Route path="calendario/horario" element={<ListaHorarioPage />} />
            <Route path="calendario/horario/:turmaId" element={<HorarioPage />} />
            
          </Route>
        </Routes>
      </UserProvider>
    </Router>
  );
}

export default App;