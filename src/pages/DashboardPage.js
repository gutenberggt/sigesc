import React, { useState, useRef, useEffect } from "react";
import { signOut } from "firebase/auth";
import { auth } from "../firebase/config";
import { Link, useNavigate, Outlet } from "react-router-dom";
import Footer from "../components/Footer";
import { FaUserCircle, FaBars, FaSun, FaMoon } from "react-icons/fa";
import { useTheme } from "../context/ThemeContext";

// ✅ novos hooks
import { useClock } from "../hooks/useClock";
import { useOutsideClick } from "../hooks/useOutsideClick";
import { useAuthGuard } from "../hooks/useAuthGuard";
import { useToast } from "../hooks/useToast";

// ✅ Sidebar modular
import Sidebar from "../components/Sidebar/Sidebar";

function DashboardPage() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const navigate = useNavigate();
  const menuRef = useRef(null);

  const { userData, loading } = useAuthGuard("/");
  const { theme, toggleTheme } = useTheme();
  const { formattedDate, formattedTime } = useClock();
  const { toastError } = useToast();

  const handleLogout = async () => {
    try {
      await signOut(auth);
      navigate("/");
    } catch (error) {
      toastError("Erro ao sair. Tente novamente.");
    }
  };

  const toggleMenu = () => setIsMenuOpen((prev) => !prev);
  const toggleSidebar = () => setSidebarOpen((prev) => !prev);
  const toggleSubmenu = (menuName) =>
    setOpenSubmenu((prev) => (prev === menuName ? null : menuName));

  // ✅ fecha menu clicando fora
  useOutsideClick(menuRef, () => setIsMenuOpen(false));

  // ✅ fecha sidebar ao trocar de rota
  useEffect(() => {
    setSidebarOpen(false);
  }, [navigate]);

  if (loading) {
    return <div className="text-center p-6">Carregando painel...</div>;
  }
  if (!userData) {
    return <div className="text-center p-6 text-red-600">Acesso Negado.</div>;
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-blue-600 dark:bg-gray-800 text-white p-4 shadow-md z-40">
        <div className="container mx-auto flex justify-between items-center relative">
          <div className="flex items-center gap-3">
            <button
              onClick={toggleSidebar}
              aria-label="Abrir menu lateral"
              className="focus:outline-none md:hidden mr-3"
            >
              <FaBars size={24} />
            </button>
            <img src="/sigesc_log.png" alt="Logo SIGESC" className="h-8" />
            <div>
              <h1 className="text-xl font-semibold">SIGESC</h1>
              <p className="text-xs text-blue-200 dark:text-gray-400">
                Sistema Integrado de Gestão Escolar
              </p>
            </div>
            <div className="ml-6 hidden md:flex items-center border-l border-blue-500 dark:border-gray-600 pl-6">
              <span className="text-2xl font-bold mr-3">{formattedTime}</span>
              <div className="flex flex-col leading-tight">
                <span className="text-xs font-bold uppercase">
                  AVISO: Estamos em fases de teste.
                </span>
                <span className="text-xs text-blue-200 dark:text-gray-400">
                  Hoje é {formattedDate}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={toggleTheme}
              aria-label="Alternar tema"
              className="p-2 rounded-full hover:bg-blue-500 dark:hover:bg-gray-700 transition"
            >
              {theme === "light" ? <FaMoon size={18} /> : <FaSun size={18} />}
            </button>
            <div className="text-right hidden md:block">
              <p className="text-sm font-medium">
                {userData.funcao ? userData.funcao.toUpperCase() : "N/A"}
              </p>
              <p className="text-xs text-blue-200 dark:text-gray-400">
                {userData.nomeCompleto || "Usuário"}
              </p>
            </div>
            <button
              onClick={toggleMenu}
              aria-label="Abrir menu do usuário"
              className="focus:outline-none ml-auto"
            >
              {userData.photoURL ? (
                <img
                  src={userData.photoURL}
                  alt="Foto do usuário"
                  className="w-8 h-8 rounded-full object-cover border-2 border-white"
                />
              ) : (
                <FaUserCircle size={24} />
              )}
            </button>
            {isMenuOpen && (
              <div
                ref={menuRef}
                className="absolute top-full right-0 mt-2 w-48 bg-white dark:bg-gray-700 rounded-md shadow-lg py-1 z-50"
              >
                <Link
                  to="/dashboard/meu-perfil"
                  className="block px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600"
                  onClick={() => setIsMenuOpen(false)}
                >
                  Meu Perfil
                </Link>
                <button
                  onClick={handleLogout}
                  className="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600"
                >
                  Sair
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* ✅ Sidebar modular */}
        <Sidebar
          userRole={userData.funcao}
          openSubmenu={openSubmenu}
          toggleSubmenu={toggleSubmenu}
          sidebarOpen={sidebarOpen}
        />

        {/* Conteúdo principal */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <main className="flex-1 overflow-x-hidden overflow-y-auto bg-gray-100 dark:bg-gray-800 p-6">
            <Outlet />
          </main>
          <Footer />
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;
