import React, { useState, useEffect } from 'react';
import { signOut } from 'firebase/auth';
import { auth } from '../firebase/config';
import { useUser } from '../context/UserContext';
import { Link, useNavigate, Outlet } from 'react-router-dom';
import Footer from '../components/Footer'; // NOVO: Importe o componente Footer

function DashboardPage() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [openSubmenu, setOpenSubmenu] = useState(null);
  const { userData, loading } = useUser(); 
  const navigate = useNavigate();

  console.log('Loading state in Dashboard:', loading);
  console.log('User Data in Dashboard:', userData);

  const handleLogout = async () => {
    await signOut(auth);
    navigate("/");
  };

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
  };

  const toggleSubmenu = (menuName) => {
    setOpenSubmenu(openSubmenu === menuName ? null : menuName);
  };

  useEffect(() => {
    if (!loading && !userData) {
      navigate("/");
    }
  }, [loading, userData, navigate]);


  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-gray-700">Carregando painel...</p>
      </div>
    );
  }

  if (!userData) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-red-100 text-red-700">
          <p>Erro: Dados do usuário não disponíveis. Redirecionando...</p>
        </div>
      );
  }

  const userRoleDisplay = userData && userData.funcao ? userData.funcao.toUpperCase() : 'N/A';

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header (mantido o mesmo) */}
      <header className="bg-blue-600 text-white p-4 shadow">
        <div className="container mx-auto flex justify-between items-center relative">
          <div className="flex items-center gap-3">
            <img src="/sigesc_log.png" alt="Logo SIGESC" className="h-8" />
            <div>
              <h1 className="text-xl font-semibold">SIGESC</h1>
              <p className="text-xs text-blue-200">Sistema Integrado de Gestão Escolar</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium">{userRoleDisplay}</span>
            <button onClick={toggleMenu} className="focus:outline-none">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="w-6 h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
                />
              </svg>
            </button>

            {isMenuOpen && (
              <div className="absolute top-full right-0 mt-2 w-48 bg-white rounded-md shadow-lg py-1 z-10">
                <a
                  href="/meu-perfil"
                  className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  Meu Perfil
                </a>
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

      {/* Conteúdo principal com barra lateral */}
      <div className="flex flex-grow">
        {/* Barra Lateral (mantida a mesma) */}
        <aside className="w-64 bg-blue-700 text-white flex-shrink-0 p-4">
          <nav>
            <ul>
              {/* Início */}
              <li className="mb-2">
                <Link to="/dashboard" className="flex items-center p-2 rounded hover:bg-blue-600 font-semibold">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12m-4.5 9V17.25a2.25 2.25 0 0 0-2.25-2.25H9.75a2.25 2.25 0 0 0-2.25 2.25V21mwa-4.5-9v-3.375c0-.621.504-1.125 1.125-1.125h1.5c.621 0 1.125.504 1.125 1.125V21" />
                  </svg>
                  Início
                </Link>
              </li>

              {/* Gerenciar Usuários */}
              <li className="mb-2">
                <Link to="/dashboard/gerenciar-usuarios" className="flex items-center p-2 rounded hover:bg-blue-600 font-semibold">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
                  </svg>
                  Gerenciar Usuários
                </Link>
              </li>
              
              {/* Escola e submenus (mantidos os mesmos) */}
              <li className="mb-2">
                <button
                  onClick={() => toggleSubmenu('escola')}
                  className="w-full text-left p-2 rounded hover:bg-blue-600 font-semibold flex justify-between items-center"
                >
                  <div className="flex items-center">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5 mr-2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15C20.221 3 21 3.779 21 4.5v15c0 .721-.779 1.5-1.5 1.5h-15C3.779 21 3 20.221 3 19.5v-15C3 3.779 3.779 3 4.5 3Z" />
                    </svg>
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
                      <Link to="escola/escola" className="flex items-center p-2 rounded hover:bg-blue-600 text-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15C20.221 3 21 3.779 21 4.5v15c0 .721-.779 1.5-1.5 1.5h-15C3.779 21 3 20.221 3 19.5v-15C3 3.779 3.779 3 4.5 3Z" />
                        </svg>
                        Escola
                      </Link>
                    </li>
                    <li>
                      <Link to="escola/cursos" className="flex items-center p-2 rounded hover:bg-blue-600 text-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.098 1.52A1.5 1.5 0 0 1 5.602 0h12.796c.732 0 1.29.624 1.503 1.25L23 10c.345 1.056-.47 2-1.5 2H2.5c-1.03 0-1.845-.944-1.5-2L4.098 1.52ZM14.25 5a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5a.75.75 0 0 1 .75-.75Zm-3.5 0a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5a.75.75 0 0 1 .75-.75Zm-3.5 0a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5a.75.75 0 0 1 .75-.75Z" />
                        </svg>
                        Cursos
                      </Link>
                    </li>
                    <li>
                      <Link to="escola/series" className="flex items-center p-2 rounded hover:bg-blue-600 text-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6.429 9.75 2.25 12l4.179 2.25m0-4.5 4.5 2.25L6.429 16.5m0-4.5H19.5" />
                        </svg>
                        Séries
                      </Link>
                    </li>
                    <li>
                      <Link to="escola/componentes-curriculares" className="flex items-center p-2 rounded hover:bg-blue-600 text-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.079 0-2.157.068-3.224.262.3.097.6.197.9.297V21.41l5.97-5.97a.75.75 0 0 1 .53-.22h.001c.026 0 .052-.002.079-.002a.75.75 0 0 1 .53.22L18 21.41V4.77c-.9-.18-1.8-.27-2.7-.27-.901 0-1.802.09-2.703.27-1.079-.194-2.157-.262-3.224-.262Z" />
                        </svg>
                        Componentes Curriculares
                      </Link>
                    </li>
                    <li>
                      <Link to="escola/turmas" className="flex items-center p-2 rounded hover:bg-blue-600 text-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.75V6.75A2.25 2.25 0 0 0 15.75 4.5H12a2.25 2.25 0 0 0-2.25 2.25v12A2.25 2.25 0 0 0 12 21.75h3.75m-3.75-9h6.375M12 10.5h.375M12 16.5h.375M2.25 10.5h8.572c.305 0 .572.235.572.534v8.075c0 .299-.267.534-.572.534H2.25A.263.263 0 0 1 2 19.075V10.704c0-.299.267-.534.572-.534Z" />
                        </svg>
                        Turmas
                      </Link>
                    </li>
                    <li>
                      <Link to="escola/alunos" className="flex items-center p-2 rounded hover:bg-blue-600 text-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 mr-2">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.75V6.75A2.25 2.25 0 0 0 15.75 4.5H12a2.25 2.25 0 0 0-2.25 2.25v12A2.25 2.25 0 0 0 12 21.75h3.75m-3.75-9h6.375M12 10.5h.375M12 16.5h.375M2.25 10.5h8.572c.305 0 .572.235.572.534v8.075c0 .299-.267.534-.572.534H2.25A.263.263 0 0 1 2 19.075V10.704c0-.299.267-.534.572-.534Z" />
                        </svg>
                        Alunos
                      </Link>
                    </li>
                  </ul>
                )}
              </li>
              {/* Adicione outros menus principais aqui, se houver */}
            </ul>
          </nav>
        </aside>

        {/* Conteúdo principal da página */}
        <main className="flex-grow container mx-auto p-6 flex flex-col min-h-screen"> {/* Adicionado flex flex-col min-h-screen para o rodapé */}
          <Outlet /> {/* ESTE É ONDE AS ROTAS ANINHADAS SERÃO RENDERIZADAS */}
          <div className="flex-grow"></div> {/* Empurra o rodapé para baixo */}
          <Footer /> {/* NOVO: Insere o rodapé aqui */}
        </main>
      </div>
    </div>
  );
}

export default DashboardPage;