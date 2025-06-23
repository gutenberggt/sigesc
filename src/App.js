import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import RecuperarSenhaPage from './pages/RecuperarSenhaPage';
import DashboardPage from './pages/DashboardPage';
// Adicione aqui os demais imports...

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/cadastro" element={<RegisterPage />} />
        <Route path="/dashboard" element={<div>Página protegida</div>} />
		<Route path="/recuperar-senha" element={<RecuperarSenhaPage />} />
		<Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </Router>
  );
}

export default App;
