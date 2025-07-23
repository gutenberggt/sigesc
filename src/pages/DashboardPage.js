import React, { useState, useEffect } from 'react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase/config';
import { useUser } from '../context/UserContext';
import { Link, useNavigate, Outlet, useLocation } from 'react-router-dom';
import Footer from '../components/Footer'; 
import { FaHome, FaUsers, FaUserCircle, FaSignOutAlt, FaBars, FaTimes, FaSchool, FaBookOpen, FaGraduationCap, FaChalkboardTeacher } from 'react-icons/fa'; 

function DashboardPage() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const { userData, loading } = useUser(); 
  const navigate = useNavigate();
  const location = useLocation(); 

  const [sidebarOpen, setSidebarOpen] = useState(false); 

  console.log('Loading state in Dashboard:', loading);
  console.log('User Data in Dashboard:', userData);

  const handleLogout = async () => {
    await signOut(auth);
    navigate("/");
  };

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  const toggleSubmenu = (menuName) => {
    setOpenSubmenu(openSubmenu === menuName ? null : menuName);
  };

  useEffect(() => {
    if (!loading && !userData) {
      navigate("/");
    }
  }, [loading, userData, navigate]);

  const getPageTitle = () => {
    const path = location.pathname;
    if (path === '/dashboard') return 'Visão Geral';
    if (path === '/dashboard/meu-perfil') return 'Meu Perfil';
    if (path === '/dashboard/gerenciar-usuarios') return 'Gerenciar Usuários';
    if (path === '/dashboard/escola/escola') return 'Gerenciar Escolas';
    if (path === '/dashboard/escola/cursos') return 'Níveis de Ensino';
    if (path === '/dashboard/escola/series') return 'Séries / Anos / Etapas';
    if (path === '/dashboard/escola/componentes-curriculares') return 'Componentes Curriculares';
    if (path === '/dashboard/escola/turmas') return 'Gerenciar Turmas';
    if (path === '/dashboard/escola/alunos') return 'Gerenciar Alunos';
    return 'Dashboard';
  };


  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-gray-700">Carregando painel...</p>
      </div>
    );
  }

  if (!userData) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-red-100 font-bold">
          <p>Acesso Negado: Você não tem permissão para acessar esta página.</p>
        </div>
      );
  }

  const userRoleDisplay = userData && userData.funcao ? userData.funcao.toUpperCase() : 'N/A';

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header Fixo */}
      <header className="bg-blue-600 text-white p-4 shadow-md fixed top-0 left-0 right-0 z-40"> 
        <div className="container mx-auto flex justify-between items-center relative">
          <div className="flex items-center gap-3">
            <img src="/sigesc_log.png" alt="Logo SIGESC" className="h-8" />
            <div>
              <h1 className="text-xl font-semibold">SIGESC</h1>
              <p className="text-xs text-blue-200">Sistema Integrado de Gestão Escolar</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium hidden md:block">{userRoleDisplay}</span> 
            {/* Botão de menu para mobile */}
            <button onClick={toggleMenu} className="focus:outline-none md:hidden"> 
              {isMenuOpen ? <FaTimes size={24} /> : <FaBars size={24} />}
            </button>
            {/* Menu dropdown para desktop (e mobile quando aberto) */}
            <div className={`absolute top-full right-0 mt-2 w-48 bg-white rounded-md shadow-lg py-1 z-50 ${isMenuOpen ? 'block' : 'hidden'} md:static md:block md:w-auto md:bg-transparent md:shadow-none md:p-0 md:flex md:items-center md:gap-x-4`}> {/* MUDANÇA AQUI: Adicionado md:flex md:items-center md:gap-x-4 */}
              <Link
                to="/dashboard/meu-perfil"
                className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 md:text-white md:hover:bg-blue-700 md:inline-block" // MUDANÇA AQUI: md:inline-block
                onClick={() => setIsMenuOpen(false)}
              >
                Meu Perfil
              </Link>
              <button
                onClick={handleLogout}
                className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 md:text-white md:hover:bg-blue-700 md:inline-block md:w-auto" // MUDANÇA AQUI: md:inline-block md:w-auto
              >
                Sair
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Conteúdo principal com barra lateral */}
      <div className="flex flex-grow pt-16 md:pl-64"> 
        {/* Sidebar fixa */}
        <aside className={`w-64 bg-blue-700 text-white flex-shrink-0 p-4 fixed inset-y-0 left-0 transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0 transition-transform duration-200 ease-in-out z-30 pt-16`}> 
          {/* Botão para fechar sidebar em mobile */}
          <button onClick={toggleSidebar} className="md:hidden absolute top-4 right-4 text-gray-400 hover:text-white focus:outline-none">
            <FaTimes size={20} />
          </button>
          <nav className="mt-4"> 
            <ul>
              {/* Início */}
              <li className="mb-2">
                <Link to="/dashboard" className={`flex items-center p-2 rounded hover:bg-blue-600 font-semibold ${location.pathname === '/dashboard' ? 'bg-blue-600' : ''}`}>
                  <FaHome className="w-5 h-5 mr-2" />
                  <span>Início</span>
                </Link>
              </li>

              {/* Gerenciar Usuários */}
              {userData && userData.funcao && userData.funcao.toLowerCase() === 'administrador' && (
                <li className="mb-2">
                  <Link to="/dashboard/gerenciar-usuarios" className={`flex items-center p-2 rounded hover:bg-blue-600 font-semibold ${location.pathname === '/dashboard/gerenciar-usuarios' ? 'bg-blue-600' : ''}`}>
                    <FaUsers className="w-5 h-5 mr-2" />
                    <span>Gerenciar Usuários</span>
                  </Link>
                </li>
              )}
              
              {/* Escola e submenus */}
              <li className="mb-2">
                <button
                  onClick={() => toggleSubmenu('escola')}
                  className={`w-full text-left p-2 rounded hover:bg-blue-600 font-semibold flex justify-between items-center ${openSubmenu === 'escola' || location.pathname.startsWith('/dashboard/escola') ? 'bg-blue-600' : ''}`}
                >
                  <div className="flex items-center">
                    <FaSchool className="w-5 h-5 mr-2" />
                    <span>Escola</span>
                  </div>
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    className={`w-4 h-4 transform transition-transform ${openSubmenu === 'escola' ? 'rotate-90' : ''}`}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                  </svg>
                </button>
                {openSubmenu === 'escola' && (
                  <ul className="ml-4 mt-1">
                    <li>
                      <Link to="/dashboard/escola/escola" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/escola' ? 'bg-blue-600' : ''}`}>
                        <FaSchool className="w-4 h-4 mr-2" />
                        Escola
                      </Link>
                    </li>
                    <li>
                      <Link to="/dashboard/escola/cursos" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/cursos' ? 'bg-blue-600' : ''}`}>
                        <FaGraduationCap className="w-4 h-4 mr-2" /> 
                        Níveis de Ensino
                      </Link>
                    </li>
                    <li>
                      <Link to="/dashboard/escola/series" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/series' ? 'bg-blue-600' : ''}`}>
                        <FaChalkboardTeacher className="w-4 h-4 mr-2" /> 
                        Séries / Anos / Etapas
                      </Link>
                    </li>
                    <li>
                      <Link to="/dashboard/escola/componentes-curriculares" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/componentes-curriculares' ? 'bg-blue-600' : ''}`}>
                        <FaBookOpen className="w-4 h-4 mr-2" /> 
                        Componentes Curriculares
                      </Link>
                    </li>
                    <li>
                      <Link to="/dashboard/escola/turmas" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/turmas' ? 'bg-blue-600' : ''}`}>
                        <FaUsers className="w-4 h-4 mr-2" /> 
                        Turmas
                      </Link>
                    </li>
                    <li>
                      <Link to="/dashboard/escola/alunos" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/alunos' ? 'bg-blue-600' : ''}`}>
                        <FaUserCircle className="w-4 h-4 mr-2" /> 
                        Gerenciar Alunos
                      </Link>
                    </li>
                  </ul>
                )}
              </li>
            </ul>
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-gray-100 p-6"> 
          <Outlet />
          <Footer />
        </main>
      </div>
    </div>
  );
}

export default DashboardPage;