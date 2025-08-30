import React, { useState, useEffect, useRef } from 'react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase/config';
import { useUser } from '../context/UserContext';
import { Link, useNavigate, Outlet, useLocation } from 'react-router-dom';
import Footer from '../components/Footer';
import { FaHome, FaUserCircle, FaBars, FaSchool, FaBookOpen, FaChartBar, FaCalendarAlt, FaCogs, FaSun, FaMoon } from 'react-icons/fa';
import { useTheme } from '../context/ThemeContext'; // Importar o hook do tema

function DashboardPage() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const menuRef = useRef(null);
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());
  const { theme, toggleTheme } = useTheme(); // Usar o hook para obter o tema e a função de troca

  const handleLogout = async () => {
    await signOut(auth);
    navigate("/");
  };

  const toggleMenu = () => setIsMenuOpen(!isMenuOpen);
  const toggleSidebar = () => setSidebarOpen(!sidebarOpen);
  const toggleSubmenu = (menuName) => setOpenSubmenu(prev => (prev === menuName ? null : menuName));

  useEffect(() => {
    const timerId = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timerId);
  }, []);

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuRef]);

  useEffect(() => {
    if (!loading && !userData) {
      navigate("/");
    }
  }, [loading, userData, navigate]);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  if (loading) {
    return <div className="text-center p-6">Carregando painel...</div>;
  }
  if (!userData) {
    return <div className="text-center p-6 text-red-600">Acesso Negado.</div>;
  }

  const formattedDate = currentTime.toLocaleDateString('pt-BR', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric'
  });
  const formattedTime = currentTime.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="flex flex-col h-screen bg-gray-50 dark:bg-gray-900">
      <header className="bg-blue-600 dark:bg-gray-800 text-white p-4 shadow-md z-40">
        <div className="container mx-auto flex justify-between items-center relative">
          <div className="flex items-center gap-3">
            <button onClick={toggleSidebar} className="focus:outline-none md:hidden mr-3">
              <FaBars size={24} />
            </button>
            <img src="/sigesc_log.png" alt="Logo SIGESC" className="h-8" />
            <div>
              <h1 className="text-xl font-semibold">SIGESC</h1>
              <p className="text-xs text-blue-200 dark:text-gray-400">Sistema Integrado de Gestão Escolar</p>
            </div>
            <div className="ml-6 hidden md:flex items-center border-l border-blue-500 dark:border-gray-600 pl-6">
              <span className="text-2xl font-bold mr-3">{formattedTime}</span>
              <div className="flex flex-col leading-tight">
                <span className="text-xs font-bold uppercase">AVISO: Estamos em fases de teste.</span>
                <span className="text-xs text-blue-200 dark:text-gray-400">Hoje é {formattedDate}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <button onClick={toggleTheme} className="p-2 rounded-full hover:bg-blue-500 dark:hover:bg-gray-700 transition">
              {theme === 'light' ? <FaMoon size={18} /> : <FaSun size={18} />}
            </button>
            <div className="text-right hidden md:block">
              <p className="text-sm font-medium">{userData.funcao ? userData.funcao.toUpperCase() : 'N/A'}</p>
              <p className="text-xs text-blue-200 dark:text-gray-400">{userData.nomeCompleto || 'Usuário'}</p>
            </div>
            <button onClick={toggleMenu} className="focus:outline-none ml-auto">
              {userData.photoURL ? (
                <img src={userData.photoURL} alt="Foto do usuário" className="w-8 h-8 rounded-full object-cover border-2 border-white" />
              ) : (
                <FaUserCircle size={24} />
              )}
            </button>
            {isMenuOpen && (
              <div className="absolute top-full right-0 mt-2 w-48 bg-white dark:bg-gray-700 rounded-md shadow-lg py-1 z-50" ref={menuRef}>
                <Link to="/dashboard/meu-perfil" className="block px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600" onClick={() => setIsMenuOpen(false)}>Meu Perfil</Link>
                <button onClick={handleLogout} className="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">Sair</button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className={`w-64 bg-blue-700 dark:bg-gray-800 text-white flex-shrink-0 p-4 fixed md:relative inset-y-0 left-0 transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0 transition-transform duration-200 ease-in-out z-30 pt-16 md:pt-4`}>
          <nav className="mt-4">
            <ul>
              <li className="mb-2">
                <Link to="/dashboard" className="flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold">
                  <FaHome className="w-5 h-5 mr-2" /><span>Início</span>
                </Link>
              </li>
              <li className="mb-2">
                <button onClick={() => toggleSubmenu('administrativo')} className={`w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold flex justify-between items-center ${openSubmenu === 'administrativo' ? 'bg-blue-600 dark:bg-gray-700' : ''}`}>
                  <div className="flex items-center"><FaCogs className="w-5 h-5 mr-2" /><span>Administrativo</span></div>
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu === 'administrativo' ? 'rotate-90' : ''}`}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </button>
                {openSubmenu === 'administrativo' && (
                  <ul className="ml-4 mt-1 border-l-2 border-blue-500 dark:border-blue-400">
                    <li><Link to="/dashboard/escola/pessoas" className="w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm font-semibold flex justify-between items-center">Pessoas</Link></li>
                    <li><Link to="/dashboard/escola/servidores/busca" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname.startsWith('/dashboard/escola/servidor') ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Servidores</Link></li>
                    <li><Link to="/dashboard/gerenciar-usuarios" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/gerenciar-usuarios' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Usuários</Link></li>
                  </ul>
                )}
              </li>
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                <li className="mb-2">
                  <button onClick={() => toggleSubmenu('calendario')} className={`w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold flex justify-between items-center ${openSubmenu === 'calendario' ? 'bg-blue-600 dark:bg-gray-700' : ''}`}>
                    <div className="flex items-center"><FaCalendarAlt className="w-5 h-5 mr-2" /><span>Calendário</span></div>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu === 'calendario' ? 'rotate-90' : ''}`}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                  </button>
                  {openSubmenu === 'calendario' && (
                    <ul className="ml-4 mt-1 border-l-2 border-blue-500 dark:border-blue-400">
                      <li><Link to="/dashboard/calendario/calendario" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname.includes('/calendario/calendario') ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Calendário Letivo</Link></li>
                      <li><Link to="/dashboard/calendario/bimestres" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname.includes('/calendario/bimestres') ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Bimestres</Link></li>
                      <li><Link to="/dashboard/calendario/eventos" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname.includes('/calendario/eventos') ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Eventos</Link></li>
                      <li><Link to="/dashboard/calendario/horario" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname.includes('/calendario/horario') ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Horário de Aulas</Link></li>
                    </ul>
                  )}
                </li>
              )}
              <li className="mb-2">
                <button onClick={() => toggleSubmenu('escola')} className={`w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold flex justify-between items-center ${openSubmenu === 'escola' || location.pathname.startsWith('/dashboard/escola') ? 'bg-blue-600 dark:bg-gray-700' : ''}`}>
                  <div className="flex items-center"><FaSchool className="w-5 h-5 mr-2" /><span>Escola</span></div>
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu === 'escola' ? 'rotate-90' : ''}`}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                </button>
                {openSubmenu === 'escola' && (
                  <ul className="ml-4 mt-1 border-l-2 border-blue-500 dark:border-blue-400">
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && ( <li><Link to="/dashboard/escola/escola" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/escola/escola' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Escola</Link></li> )}
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && ( <li><Link to="/dashboard/escola/matriculas" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/escola/matriculas' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Matrícula de Aluno</Link></li> )}
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario' || userData.funcao.toLowerCase() === 'diretor' || userData.funcao.toLowerCase() === 'coordenador' || userData.funcao.toLowerCase() === 'professor')) && ( <li><Link to="/dashboard/escola/busca-aluno" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/escola/busca-aluno' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Busca de Aluno</Link></li> )}
                    {(userData.funcao && (userData.funcao.toLowerCase() !== 'aluno')) && ( <><li><Link to="/dashboard/escola/cursos" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/escola/cursos' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Níveis de Ensino</Link></li><li><Link to="/dashboard/escola/series" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/escola/series' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Séries/Anos/Etapas</Link></li><li><Link to="/dashboard/escola/componentes-curriculares" className={`flex items-center p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm ${location.pathname === '/dashboard/escola/componentes-curriculares' ? 'bg-blue-600 dark:bg-gray-600' : ''}`}>Componentes Curriculares</Link></li></> )}
                  </ul>
                )}
              </li>
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario' || userData.funcao.toLowerCase() === 'professor')) && (
                <li className="mb-2">
                  <button onClick={() => toggleSubmenu('diario')} className={`w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold flex justify-between items-center ${openSubmenu?.startsWith('diario') ? 'bg-blue-600 dark:bg-gray-700' : ''}`}>
                    <div className="flex items-center"><FaBookOpen className="w-5 h-5 mr-2" /><span>Diário</span></div>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu?.startsWith('diario') ? 'rotate-90' : ''}`}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                  </button>
                  {openSubmenu?.startsWith('diario') && (
                    <ul className="ml-4 mt-1 border-l-2 border-blue-500 dark:border-blue-400">
                      <li><Link to="/dashboard/diario/frequencia" className="w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm font-semibold flex justify-between items-center">Frequência</Link></li>
                      <li><Link to="/dashboard/diario/conteudos" className="w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm font-semibold flex justify-between items-center">Conteúdos</Link></li>
                      <li><Link to="/dashboard/diario/notas" className="w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm font-semibold flex justify-between items-center">Notas</Link></li>
                    </ul>
                  )}
                </li>
              )}
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                <li className="mb-2">
                  <button onClick={() => toggleSubmenu('relatorios')} className={`w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-700 font-semibold flex justify-between items-center ${openSubmenu === 'relatorios' ? 'bg-blue-600 dark:bg-gray-700' : ''}`}>
                    <div className="flex items-center"><FaChartBar className="w-5 h-5 mr-2" /><span>Relatórios e Declarações</span></div>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu === 'relatorios' ? 'rotate-90' : ''}`}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                  </button>
                  {openSubmenu === 'relatorios' && (
                    <ul className="ml-4 mt-1 border-l-2 border-blue-500 dark:border-blue-400">
                      <li><Link to="/dashboard/relatorios" className="w-full text-left p-2 rounded hover:bg-blue-600 dark:hover:bg-gray-600 text-sm font-semibold flex items-center">Gerar Relatório</Link></li>
                    </ul>
                  )}
                </li>
              )}
            </ul>
          </nav>
        </aside>

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