import React, { useState, useEffect, useRef } from 'react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase/config';
import { useUser } from '../context/UserContext';
import { Link, useNavigate, Outlet, useLocation } from 'react-router-dom';
import Footer from '../components/Footer';
// ADIÇÃO: Novo ícone importado
import { FaHome, FaUsers, FaUserCircle, FaSignOutAlt, FaBars, FaTimes, FaSchool, FaBookOpen, FaGraduationCap, FaChalkboardTeacher, FaUserGraduate, FaSearch, FaCogs } from 'react-icons/fa';

function DashboardPage() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const { userData, loading } = useUser();
  const navigate = useNavigate();
  const menuRef = useRef(null);
  const location = useLocation();

  const [sidebarOpen, setSidebarOpen] = useState(false);

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
    setOpenSubmenu(prev => {
        if (prev && prev.startsWith(menuName.split('/')[0])) {
            if (prev === menuName) return null;
            return menuName;
        }
        return menuName;
    });
  };

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsMenuOpen(false);
      }
    }
    const timer = setTimeout(() => {
        if (isMenuOpen) {
            document.addEventListener("mousedown", handleClickOutside);
        }
    }, 100);

    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen, menuRef]);


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
    if (path === '/dashboard/escola/matriculas') return 'Matrícula de Aluno';
    if (path === '/dashboard/escola/busca-aluno') return 'Busca de Aluno';
    if (path.startsWith('/dashboard/escola/aluno/ficha')) return 'Ficha do Aluno';
    if (path.startsWith('/dashboard/escola/aluno/editar')) return 'Editar Aluno';
    if (path.startsWith('/dashboard/escola/aluno/nova-matricula')) return 'Nova Matrícula';
    if (path === '/dashboard/escola/cursos') return 'Níveis de Ensino';
    if (path === '/dashboard/escola/series') return 'Séries / Anos / Etapas';
    if (path === '/dashboard/escola/componentes-curriculares') return 'Componentes Curriculares';
    if (path.startsWith('/dashboard/escola/turmas')) return 'Gerenciar Turmas';
    if (path === '/dashboard/escola/pessoas') return 'Gerenciar Pessoas';
    if (path.startsWith('/dashboard/escola/servidores/cadastro')) return 'Cadastrar Servidor';
    if (path.startsWith('/dashboard/escola/servidores/busca')) return 'Buscar Servidor';
    if (path.startsWith('/dashboard/escola/servidor/ficha')) return 'Ficha do Servidor';
    if (path.startsWith('/dashboard/diario/frequencia')) return 'Lançar Frequência';
    if (path.startsWith('/dashboard/diario/conteudos')) return 'Lançar Conteúdos';
    if (path.startsWith('/dashboard/diario/notas')) return 'Lançar Notas';
    return 'Dashboard';
  };


  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-gray-700">
        <p className="text-gray-700">Carregando painel...</p>
      </div>
    );
  }

  if (!userData) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-red-100 text-red-700">
          <p>Acesso Negado: Dados do usuário não disponíveis. Redirecionando...</p>
        </div>
      );
  }

  const userDisplay = userData 
    ? `${userData.nomeCompleto || 'Usuário'} - ${userData.funcao ? userData.funcao.toUpperCase() : 'N/A'}`
    : 'N/A';

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-blue-600 text-white p-4 shadow-md fixed top-0 left-0 right-0 z-40">
        <div className="container mx-auto flex justify-between items-center relative">
          <div className="flex items-center gap-3">
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
            <span className="text-sm font-medium hidden md:block">{userDisplay}</span>
            <h2 className="text-lg font-bold md:hidden">{getPageTitle()}</h2>
            
            <button onClick={toggleMenu} className="focus:outline-none ml-auto">
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

      <div className="flex pt-16 h-screen">
        <aside className={`w-64 bg-blue-700 text-white flex-shrink-0 p-4 fixed md:relative inset-y-0 left-0 transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0 transition-transform duration-200 ease-in-out z-30 pt-16 md:pt-4`}>
          <button onClick={toggleSidebar} className="md:hidden absolute top-4 right-4 text-gray-400 hover:text-white focus:outline-none">
            <FaTimes size={20} />
          </button>
          <nav className="mt-4">
            <ul>
              <li className="mb-2">
                <Link to="/dashboard" className={`flex items-center p-2 rounded hover:bg-blue-600 font-semibold ${location.pathname === '/dashboard' ? 'bg-blue-600' : ''}`}>
                  <FaHome className="w-5 h-5 mr-2" />
                  <span>Início</span>
                </Link>
              </li>

              {/* ======================= INÍCIO DA ALTERAÇÃO ======================= */}
              {/* NOVO MENU: ADMINISTRATIVO */}
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                <li className="mb-2">
                  <button
                    onClick={() => toggleSubmenu('administrativo')}
                    className={`w-full text-left p-2 rounded hover:bg-blue-600 font-semibold flex justify-between items-center ${openSubmenu === 'administrativo' ? 'bg-blue-600' : ''}`}
                  >
                    <div className="flex items-center">
                      <FaCogs className="w-5 h-5 mr-2" />
                      <span>Administrativo</span>
                    </div>
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu === 'administrativo' ? 'rotate-90' : ''}`}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                    </svg>
                  </button>
                  {openSubmenu === 'administrativo' && (
                    <ul className="ml-4 mt-1">
                      {/* Gerenciar Pessoas */}
                      <li>
                        <Link to="/dashboard/escola/pessoas" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/pessoas' ? 'bg-blue-600' : ''}`}>
                          <FaUserCircle className="w-4 h-4 mr-2" />
                          <span>Pessoas</span>
                        </Link>
                      </li>
                      {/* Gerenciar Servidores */}
                      <li>
                        <Link to="/dashboard/escola/servidores/busca" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname.startsWith('/dashboard/escola/servidor') ? 'bg-blue-600' : ''}`}>
                          <FaChalkboardTeacher className="w-4 h-4 mr-2" />
                          <span>Servidores</span>
                        </Link>
                      </li>
                      {/* Gerenciar Usuários */}
                      <li>
                        <Link to="/dashboard/gerenciar-usuarios" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/gerenciar-usuarios' ? 'bg-blue-600' : ''}`}>
                          <FaUsers className="w-4 h-4 mr-2" />
                          <span>Usuários</span>
                        </Link>
                      </li>
                    </ul>
                  )}
                </li>
              )}
              {/* ======================== FIM DA ALTERAÇÃO ========================= */}
              
              {/* Menus "Pessoas", "Servidores" e "Usuários" foram removidos daqui */}
              
              <li className="mb-2">
                <button
                  onClick={() => toggleSubmenu('escola')}
                  className={`w-full text-left p-2 rounded hover:bg-blue-600 font-semibold flex justify-between items-center ${openSubmenu === 'escola' || location.pathname.startsWith('/dashboard/escola') ? 'bg-blue-600' : ''}`}
                >
                  <div className="flex items-center">
                    <FaSchool className="w-5 h-5 mr-2" />
                    <span>Escola</span>
                  </div>
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu === 'escola' ? 'rotate-90' : ''}`}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                  </svg>
                </button>
                {openSubmenu === 'escola' && (
                  <ul className="ml-4 mt-1">
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                        <li>
                          <Link to="/dashboard/escola/escola" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/escola' ? 'bg-blue-600' : ''}`}>
                            <FaSchool className="w-4 h-4 mr-2" />
                            <span>Escola</span>
                          </Link>
                        </li>
                    )}
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario')) && (
                        <li>
                            <Link to="/dashboard/escola/matriculas" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/matriculas' ? 'bg-blue-600' : ''}`}>
                                <FaUserGraduate className="w-4 h-4 mr-2" />
                                <span>Matrícula de Aluno</span>
                            </Link>
                        </li>
                    )}
                    {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario' || userData.funcao.toLowerCase() === 'diretor' || userData.funcao.toLowerCase() === 'coordenador' || userData.funcao.toLowerCase() === 'professor')) && (
                        <li>
                            <Link to="/dashboard/escola/busca-aluno" className={`flex items-center p-2 rounded hover:bg-blue-600 text-sm ${location.pathname === '/dashboard/escola/busca-aluno' ? 'bg-blue-600' : ''}`}>
                                <FaSearch className="w-4 h-4 mr-2" />
                                <span>Busca de Aluno</span>
                            </Link>
                        </li>
                    )}
                    {(userData.funcao && (userData.funcao.toLowerCase() !== 'aluno')) && (
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
                        </>
                    )}
                  </ul>
                )}
              </li>
              
              {(userData.funcao && (userData.funcao.toLowerCase() === 'administrador' || userData.funcao.toLowerCase() === 'secretario' || userData.funcao.toLowerCase() === 'professor')) && (
              <li className="mb-2">
                  <button onClick={() => toggleSubmenu('diario')} className={`w-full text-left p-2 rounded hover:bg-blue-600 font-semibold flex justify-between items-center ${openSubmenu?.startsWith('diario') ? 'bg-blue-600' : ''}`}>
                      <div className="flex items-center"><FaBookOpen className="w-5 h-5 mr-2" /><span>Diário</span></div>
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className={`w-4 h-4 transform transition-transform ${openSubmenu?.startsWith('diario') ? 'rotate-90' : ''}`}><path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" /></svg>
                  </button>
                  {openSubmenu?.startsWith('diario') && (
                  <ul className="ml-4 mt-1 border-l-2 border-blue-500">
                      <li>
                          <Link to="/dashboard/diario/frequencia" className="w-full text-left p-2 rounded hover:bg-blue-600 text-sm font-semibold flex justify-between items-center">
                            Frequência
                          </Link>
                      </li>
                      <li>
                          <button onClick={() => toggleSubmenu('diario/conteudos')} className="w-full text-left p-2 rounded hover:bg-blue-600 text-sm font-semibold flex justify-between items-center">Conteúdos</button>
                          {openSubmenu === 'diario/conteudos' && (
                              <ul className="ml-4">
                                  <li><Link to="/dashboard/diario/conteudos1" className="block p-2 rounded hover:bg-blue-600 text-xs">1º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/conteudos2" className="block p-2 rounded hover:bg-blue-600 text-xs">2º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/conteudos3" className="block p-2 rounded hover:bg-blue-600 text-xs">3º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/conteudos4" className="block p-2 rounded hover:bg-blue-600 text-xs">4º Bimestre</Link></li>
                              </ul>
                          )}
                      </li>
                      <li>
                          <button onClick={() => toggleSubmenu('diario/notas')} className="w-full text-left p-2 rounded hover:bg-blue-600 text-sm font-semibold flex justify-between items-center">Notas</button>
                          {openSubmenu === 'diario/notas' && (
                              <ul className="ml-4">
                                  <li><Link to="/dashboard/diario/notas1" className="block p-2 rounded hover:bg-blue-600 text-xs">1º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/notas2" className="block p-2 rounded hover:bg-blue-600 text-xs">2º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/notasr1" className="block p-2 rounded hover:bg-blue-600 text-xs">Rec. 1</Link></li>
                                  <li><Link to="/dashboard/diario/notasgeral1" className="block p-2 rounded hover:bg-blue-600 text-xs">1º Semestre</Link></li>
                                  <li><Link to="/dashboard/diario/notas3" className="block p-2 rounded hover:bg-blue-600 text-xs">3º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/notas4" className="block p-2 rounded hover:bg-blue-600 text-xs">4º Bimestre</Link></li>
                                  <li><Link to="/dashboard/diario/notasr2" className="block p-2 rounded hover:bg-blue-600 text-xs">Rec. 2</Link></li>
                                  <li><Link to="/dashboard/diario/notasgeral2" className="block p-2 rounded hover:bg-blue-600 text-xs">2º Semestre</Link></li>
                                  <li><Link to="/dashboard/diario/notasfinal" className="block p-2 rounded hover:bg-blue-600 text-xs">Final</Link></li>
                              </ul>
                          )}
                      </li>
                  </ul>
                  )}
              </li>
              )}
            </ul>
          </nav>
        </aside>

        <div className="flex-1 flex flex-col overflow-hidden">
          <main className="flex-1 overflow-x-hidden overflow-y-auto bg-gray-100 p-6">
            <div className="pb-16">
              <Outlet />
            </div>
          </main>
          
          <div className="w-full">
             <Footer />
          </div>
        </div>
      </div>
    </div>
  );
}

export default DashboardPage;