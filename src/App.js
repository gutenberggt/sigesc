import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import RecuperarSenhaPage from "./pages/RecuperarSenhaPage";
import DashboardPage from "./pages/DashboardPage";
import UserManagementPage from "./pages/UserManagementPage";
import ProfilePage from "./pages/ProfilePage";
import WelcomePage from "./pages/WelcomePage";
import SchoolManagementPage from "./pages/SchoolManagementPage";
import NiveisDeEnsinoPage from "./pages/NiveisDeEnsinoPage";
import SeriesAnosEtapasPage from "./pages/SeriesAnosEtapasPage";
import ComponentesCurricularesPage from "./pages/ComponentesCurricularesPage";
import PessoaManagementPage from "./pages/PessoaManagementPage";
import TurmasPage from "./pages/TurmasPage";
import MatriculaAlunoPage from "./pages/MatriculaAlunoPage";
import BuscaAlunoPage from "./pages/BuscaAlunoPage";
import FichaAlunoPage from "./pages/FichaAlunoPage";
import EditarAlunoPage from "./pages/EditarAlunoPage";
import NovaMatriculaAlunoPage from "./pages/NovaMatriculaAlunoPage";
import CadastroServidorPage from "./pages/CadastroServidorPage";
import BuscaServidorPage from "./pages/BuscaServidorPage";
import FichaServidorPage from "./pages/FichaServidorPage";
import CalendarioPage from "./pages/calendarioPage";
import BimestresPage from "./pages/bimestresPage";
import EventosPage from "./pages/eventosPage";
import AdicionarEventosPage from "./pages/adicionarEventosPage";
import HorarioPage from "./pages/horarioPage";
import ListaHorarioPage from "./pages/listaHorarioPage";
import EditarServidorPage from "./pages/EditarServidorPage";
import FrequenciaPage from "./pages/frequenciaPage";
import RelatorioFrequenciaPage from "./pages/RelatorioFrequenciaPage";
import RelatoriosPage from "./pages/RelatoriosPage";
import RegistroConteudosPage from "./pages/RegistroConteudosPage";
import LancamentoNotasPage from "./pages/LancamentoNotasPage.jsx";

import { UserProvider } from "./context/UserContext";
import { ThemeProvider } from "./context/ThemeContext";

function App() {
  return (
    <Router>
      <ThemeProvider>
        <UserProvider>
          <Routes>
            <Route path="/" element={<LoginPage />} />
            <Route path="/cadastro" element={<RegisterPage />} />
            <Route path="/recuperar-senha" element={<RecuperarSenhaPage />} />

            <Route path="/dashboard" element={<DashboardPage />}>
              <Route index element={<WelcomePage />} />
              <Route
                path="gerenciar-usuarios"
                element={<UserManagementPage />}
              />
              <Route path="meu-perfil" element={<ProfilePage />} />
              <Route path="cadastro-interno" element={<RegisterPage />} />
              <Route path="escola/pessoas" element={<PessoaManagementPage />} />
              <Route path="escola/escola" element={<SchoolManagementPage />} />
              <Route
                path="escola/matriculas"
                element={<MatriculaAlunoPage />}
              />
              <Route path="escola/cursos" element={<NiveisDeEnsinoPage />} />
              <Route path="escola/series" element={<SeriesAnosEtapasPage />} />
              <Route
                path="escola/componentes-curriculares"
                element={<ComponentesCurricularesPage />}
              />
              <Route path="escola/turmas/:schoolId" element={<TurmasPage />} />
              <Route path="escola/busca-aluno" element={<BuscaAlunoPage />} />
              <Route
                path="escola/aluno/ficha/:alunoId"
                element={<FichaAlunoPage />}
              />
              <Route
                path="escola/aluno/nova-matricula/:alunoId"
                element={<NovaMatriculaAlunoPage />}
              />
              <Route
                path="escola/aluno/editar/:alunoId"
                element={<EditarAlunoPage />}
              />
              <Route
                path="escola/servidores/cadastro"
                element={<CadastroServidorPage />}
              />
              <Route
                path="escola/servidores/busca"
                element={<BuscaServidorPage />}
              />
              <Route
                path="escola/servidor/ficha/:servidorId"
                element={<FichaServidorPage />}
              />
              <Route
                path="escola/servidor/editar/:servidorId"
                element={<EditarServidorPage />}
              />

              <Route
                path="calendario/calendario"
                element={<CalendarioPage />}
              />
              <Route path="calendario/bimestres" element={<BimestresPage />} />
              <Route path="calendario/eventos" element={<EventosPage />} />
              <Route
                path="calendario/adicionar-evento"
                element={<AdicionarEventosPage />}
              />
              <Route
                path="calendario/editar-evento/:eventoId"
                element={<AdicionarEventosPage />}
              />
              <Route path="calendario/horario" element={<ListaHorarioPage />} />
              <Route
                path="calendario/horario/:turmaId"
                element={<HorarioPage />}
              />

              <Route path="diario/frequencia" element={<FrequenciaPage />} />
              <Route
                path="diario/conteudos"
                element={<RegistroConteudosPage />}
              />
              <Route path="diario/notas" element={<LancamentoNotasPage />} />

              <Route path="relatorios" element={<RelatoriosPage />} />
            </Route>

            <Route
              path="/relatorio/frequencia/:schoolId/:turmaId/:year/:period/:componente"
              element={<RelatorioFrequenciaPage />}
            />
          </Routes>
        </UserProvider>
      </ThemeProvider>
    </Router>
  );
}

export default App;
