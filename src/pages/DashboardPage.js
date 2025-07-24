import React, { useState, useEffect, useRef } from 'react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase/config';
import { useUser } from '../context/UserContext';
import { Link, useNavigate, Outlet, useLocation } from 'react-router-dom'; // Adicionado useLocation
import Footer from '../components/Footer';
import { FaHome, FaUsers, FaUserCircle, FaSignOutAlt, FaBars, FaTimes, FaSchool, FaBookOpen, FaGraduationCap, FaChalkboardTeacher } from 'react-icons/fa'; // Importado ícones

function DashboardPage() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const menuRef = useRef(null); // Ref para o menu dropdown do usuário
  const location = useLocation(); // Hook para obter a rota atual para destaque de menu

  // Estado para controlar a abertura/fechamento da sidebar em telas menores
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    await signOut(auth);
    navigate("/");
  };

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  const toggleSidebar = () => { // Função para o botão de menu mobile que abre a sidebar
    setSidebarOpen(!sidebarOpen);
  };

  const toggleSubmenu = (menuName) => {
    setOpenSubmenu(openSubmenu === menuName ? null : menuName);
  };

  // Fecha o menu dropdown do usuário se clicar fora
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsMenuOpen(false);
      }
    }
    // Adicionado um pequeno atraso para evitar que o clique no botão de toggle do menu
    // feche o menu imediatamente (devido à propagação do evento)
    const timer = setTimeout(() => {
        if (isMenuOpen) { // Só adiciona o listener se o menu estiver aberto
            document.addEventListener("mousedown", handleClickOutside);
        }
    }, 100); // Pequeno atraso

    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen, menuRef]); // Depende do estado do menu e da ref


  useEffect(() => {
    if (!loading && !userData) {
      navigate("/");
    }
  }, [loading, userData, navigate]);

  // Função para determinar o título da página baseado na rota atual
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
    if (path === '/dashboard/escola/pessoas') return 'Gerenciar Pessoas'; // Adicionado
    return 'Dashboard';
  };


  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-gray-700">Carregando painel...</p>
      </div>
    );
  }

  // Redirecionamento se userData for nulo após o carregamento
  if (!userData) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-red-100 text-red-700">
          <p>Acesso Negado: Dados do usuário não disponíveis. Redirecionando...</p>
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
            {/* Botão para abrir sidebar em mobile */}
            <button onClick={toggleSidebar} className="focus:outline-none md:hidden mr-3">
              {sidebarOpen ? <FaTimes size={24} /> : <FaBars size={24} />}
            </button>
            <img src="/sigesc_log.png" alt="Logo SIGESC" className="h-8" />
            <div>
              <h1 className="text-xl font-semibold">SIGESC</h1>
              <p className="text-xs text-blue-200">Sistema Integrado de Gestão Escolar</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium hidden md:block">{userRoleDisplay}</span>
            {/* Título da página atual para mobile/telas pequenas */}
            <h2 className="text-lg font-bold md:hidden">{getPageTitle()}</h2>
            
            {/* Menu dropdown do usuário (Meu Perfil, Sair) */}
            <button onClick={toggleMenu} className="focus:outline-none ml-auto"> {/* ml-auto para empurrar para a direita */}
              <FaUserCircle size={24} />
            </button>
            {isMenuOpen && (
              <div className="absolute top-full right-0 mt-2 w-48 bg-white rounded-md shadow-lg py-1 z-50" ref={menuRef}>
                <Link
                  to="/dashboard/meu-perfil"
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  onClick={() => setIsMenuOpen(false)}
                >
                  Meu Perfil
                </Link>
                <button
                  onClick={handleLogout}
                  className="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Sair
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Conteúdo principal com barra lateral - Adicionado pt-16 para o header fixo */}
      {/* Adicionado md:pl-64 para o padding da sidebar fixa */}
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

              {/* Gerenciar Usuários - Visível apenas para Administrador/Secretário */}
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                 <li className="mb-2">
                   <Link to="/dashboard/gerenciar-usuarios" className={`flex items-center p-2 rounded hover:bg-blue-600 font-semibold ${location.pathname === '/dashboard/gerenciar-usuarios' ? 'bg-blue-600' : ''}`}>
                     <FaUsers className="w-5 h-5 mr-2" />
                     <span>Gerenciar Usuários</span>
                   </Link>
                 </li>
              )}
              
              {/* Gerenciar Pessoas - Visível apenas para Administrador/Secretário */}
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                <li className="mb-2">
                  <Link to="/dashboard/escola/pessoas" className={`flex items-center p-2 rounded hover:bg-blue-600 font-semibold ${location.pathname === '/dashboard/escola/pessoas' ? 'bg-blue-600' : ''}`}>
                    <FaUsers className="w-5 h-5 mr-2" /> {/* Reusando ícone, ou use FaUserCircle */}
                    <span>Gerenciar Pessoas</span>
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
                    {/* Item de Gerenciar Escolas - Visível apenas para Admin/Secretário */}
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                        <li>
                          <Link to="/dashboard/escola/escola" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/escola' ? 'bg-blue-600' : ''}`}>
                            <FaSchool className="w-4 h-4 mr-2" />
                            <span>Escola</span>
                          </Link>
                        </li>
                    )}
                    {/* Itens de Níveis, Séries, Componentes - Visível para Admin, Secretário, Diretor, Coordenador, Professor */}
                    {(userData.funcao && (userData.funcao.toLowerCase() !== 'aluno')) && ( // Quase todos, exceto aluno
                        <>
                            <li>
                              <Link to="/dashboard/escola/cursos" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/cursos' ? 'bg-blue-600' : ''}`}>
                                <FaGraduationCap className="w-4 h-4 mr-2" />
                                <span>Níveis de Ensino</span>
                              </Link>
                            </li>
                            <li>
                              <Link to="/dashboard/escola/series" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/series' ? 'bg-blue-600' : ''}`}>
                                <FaChalkboardTeacher className="w-4 h-4 mr-2" />
                                <span>Séries / Anos / Etapas</span>
                              </Link>
                            </li>
                            <li>
                              <Link to="/dashboard/escola/componentes-curriculares" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/componentes-curriculares' ? 'bg-blue-600' : ''}`}>
                                <FaBookOpen className="w-4 h-4 mr-2" />
                                <span>Componentes Curriculares</span>
                              </Link>
                            </li>
                            {/* O link para Turmas terá um :schoolId, então ele não pode ser um link direto estático aqui.
                            Será acessado de SchoolManagementPage ou de uma lista de turmas global */}
                            {/* <li>
                              <Link to="/dashboard/escola/turmas" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/turmas' ? 'bg-blue-600' : ''}`}>
                                <FaUsers className="w-4 h-4 mr-2" />
                                <span>Turmas</span>
                              </Link>
                            </li> */}
                        </>
                    )}
                  </ul>
                )}
              </li>
              {/* Adicione outros menus principais aqui, se houver */}
            </ul>
          </nav>
        </aside>

        {/* Overlay para fechar sidebar em mobile */}
        {sidebarOpen && (
          <div onClick={toggleSidebar} className="fixed inset-0 bg-black opacity-50 z-20 md:hidden"></div>
        )}

        {/* Conteúdo principal da página - ONDE AS ROTAS ANINHADAS SERÃO RENDERIZADAS */}
        {/* Adicionado padding-left em telas maiores para evitar sobreposição da sidebar */}
        <main className="flex-grow overflow-x-hidden overflow-y-auto bg-gray-100 p-6">
          <Outlet /> {/* ESTE É ONDE AS ROTAS ANINHADAS SERÃO RENDERIZADAS */}
        </main>
      </div>

      {/* Footer GLOBAL - fora do main, no nível do div principal (irmão do header e do container flex-grow) */}
      <Footer />
    </div>
  );
}

export default DashboardPage;