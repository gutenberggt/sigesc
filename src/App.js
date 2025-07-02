import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import RecuperarSenhaPage from './pages/RecuperarSenhaPage';
import DashboardPage from './pages/DashboardPage'; // Componente de Layout para rotas aninhadas
import UserManagementPage from './pages/UserManagementPage';
import ProfilePage from './pages/ProfilePage';
import WelcomePage from './pages/WelcomePage';
import SchoolManagementPage from './pages/SchoolManagementPage'; // MODIFICAÇÃO: Importe a nova página SchoolManagementPage
import { UserProvider } from './context/UserContext';

function App() {
  return (
    <Router>
      <UserProvider>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/cadastro" element={<RegisterPage />} /> {/* Manter /cadastro externo por enquanto */}
          <Route path="/recuperar-senha" element={<RecuperarSenhaPage />} />
          
          {/* Rota Pai para o DashboardPage como layout */}
          <Route path="/dashboard" element={<DashboardPage />}>
            {/* Rota aninhada padrão para /dashboard (mostra a WelcomePage) */}
            <Route index element={<WelcomePage />} /> 
            {/* Rotas aninhadas para outras páginas que usarão o layout do Dashboard */}
            <Route path="gerenciar-usuarios" element={<UserManagementPage />} />
            <Route path="meu-perfil" element={<ProfilePage />} />
            <Route path="cadastro-interno" element={<RegisterPage />} /> {/* Adicione esta rota aninhada para o RegisterPage dentro do Dashboard */}
            
            {/* Adicionar rotas para os submenus da Escola aqui, ex: */}
            <Route path="escola/escola" element={<SchoolManagementPage />} /> {/* MODIFICAÇÃO: Use SchoolManagementPage aqui */}
            <Route path="escola/cursos" element={<div>Página de Cursos</div>} />
            <Route path="escola/series" element={<div>Página de Séries</div>} />
            <Route path="escola/componentes-curriculares" element={<div>Página de Componentes Curriculares</div>} />
            <Route path="escola/turmas" element={<div>Página de Turmas</div>} />
            <Route path="escola/alunos" element={<div>Página de Alunos</div>} />

          </Route>
          
          {/* Se você quiser manter o /cadastro original como uma página independente, mantenha a linha abaixo */}
          {/* <Route path="/cadastro" element={<RegisterPage />} /> */}
        </Routes>
      </UserProvider>
    </Router>
  );
}

export default App;