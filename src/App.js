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

// ======================= INÍCIO DA CORREÇÃO =======================
// 1. IMPORTA A NOVA PÁGINA UNIFICADA E REMOVE AS ANTIGAS
import FrequenciaPage from './pages/frequenciaPage';
// import Frequencia2Page from './pages/frequencia2Page'; // REMOVIDO
// import Frequencia3Page from './pages/frequencia3Page'; // REMOVIDO
// import Frequencia4Page from './pages/frequencia4Page'; // REMOVIDO
import Conteudos1Page from './pages/conteudos1Page';
import Conteudos2Page from './pages/conteudos2Page';
import Conteudos3Page from './pages/conteudos3Page';
import Conteudos4Page from './pages/conteudos4Page';
import Notas1Page from './pages/notas1Page';
import Notas2Page from './pages/notas2Page';
import NotasR1Page from './pages/notasr1Page';
import NotasGeral1Page from './pages/notasgeral1Page';
import Notas3Page from './pages/notas3Page';
import Notas4Page from './pages/notas4Page';
import NotasR2Page from './pages/notasr2Page';
import NotasGeral2Page from './pages/notasgeral2Page';
import NotasFinalPage from './pages/notasfinalPage';
// ======================== FIM DA CORREÇÃO =========================

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

            {/* ======================= INÍCIO DA CORREÇÃO ======================= */}
            {/* 2. ATUALIZA AS ROTAS DE FREQUÊNCIA */}
            <Route path="diario/frequencia" element={<FrequenciaPage />} /> 
            {/* <Route path="diario/frequencia2" element={<Frequencia2Page />} /> // REMOVIDO */}
            {/* <Route path="diario/frequencia3" element={<Frequencia3Page />} /> // REMOVIDO */}
            {/* <Route path="diario/frequencia4" element={<Frequencia4Page />} /> // REMOVIDO */}
            <Route path="diario/conteudos1" element={<Conteudos1Page />} />
            <Route path="diario/conteudos2" element={<Conteudos2Page />} />
            <Route path="diario/conteudos3" element={<Conteudos3Page />} />
            <Route path="diario/conteudos4" element={<Conteudos4Page />} />
            <Route path="diario/notas1" element={<Notas1Page />} />
            <Route path="diario/notas2" element={<Notas2Page />} />
            <Route path="diario/notasr1" element={<NotasR1Page />} />
            <Route path="diario/notasgeral1" element={<NotasGeral1Page />} />
            <Route path="diario/notas3" element={<Notas3Page />} />
            <Route path="diario/notas4" element={<Notas4Page />} />
            <Route path="diario/notasr2" element={<NotasR2Page />} />
            <Route path="diario/notasgeral2" element={<NotasGeral2Page />} />
            <Route path="diario/notasfinal" element={<NotasFinalPage />} />
            {/* ======================== FIM DA CORREÇÃO ========================= */}

          </Route>
        </Routes>
      </UserProvider>
    </Router>
  );
}

export default App;