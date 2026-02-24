import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { LogOut, Menu, X, HelpCircle } from 'lucide-react';
import { useState } from 'react';
import { NotificationBell, MessagesBadge } from '@/components/notifications';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { ConnectionStatusBadge, OfflineBanner, FloatingStatusIndicator } from '@/components/OfflineStatus';

export const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const { mantenedora } = useMantenedora();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const roleLabels = {
    admin: 'Administrador',
    admin_teste: 'Administrador',
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    professor: 'Professor(a)',
    aluno: 'Aluno(a)',
    responsavel: 'Responsável(is)',
    semed: 'SEMED'
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo e Mantenedora */}
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 rounded-md text-gray-600 hover:bg-gray-100"
                data-testid="menu-toggle-button"
              >
                {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
              </button>
              
              {/* Logo SIGESC */}
              <img
                src="https://aprenderdigital.top/imagens/logotipo/logosigesc.png"
                alt="SIGESC Logo"
                className="h-10"
                data-testid="sigesc-logo"
              />
              <div className="hidden sm:block border-r border-gray-200 pr-4">
                <h1 className="text-xl font-bold text-blue-600 leading-tight">SIGESC</h1>
                <p className="text-[10px] text-gray-500 leading-tight">SISTEMA INTEGRADO DE GESTÃO ESCOLAR</p>
              </div>
              
              {/* Brasão da Mantenedora */}
              {(mantenedora?.brasao_url || mantenedora?.logotipo_url) && (
                <img
                  src={mantenedora?.brasao_url || mantenedora?.logotipo_url}
                  alt="Brasão"
                  className="h-10 w-auto object-contain"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              )}
              
              {/* Nome da Mantenedora */}
              <div className="hidden md:block">
                <p className="text-xs font-medium text-gray-700 leading-tight">
                  {mantenedora?.nome || 'Prefeitura Municipal'}
                </p>
              </div>
            </div>

            {/* Notifications & User Info */}
            <div className="flex items-center space-x-2">
              {/* Status de Conexão Offline */}
              <ConnectionStatusBadge showDetails={false} />
              
              {/* Ícones de Notificação */}
              <MessagesBadge />
              <NotificationBell />
              
              {/* Ícone de Ajuda */}
              <a
                href="/tutoriais"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-md text-gray-600 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                title="Central de Ajuda - Tutoriais do SIGESC"
                data-testid="help-button"
              >
                <HelpCircle size={20} />
              </a>
              
              {/* Separador */}
              <div className="hidden sm:block h-8 w-px bg-gray-200 mx-2" />
              
              {/* User Info */}
              <div className="hidden sm:block text-right">
                <p className="text-sm font-medium text-gray-900" data-testid="user-name">{user?.full_name}</p>
                <p className="text-xs text-gray-500" data-testid="user-role">{roleLabels[user?.role]}</p>
              </div>
              <button
                onClick={handleLogout}
                className="p-2 rounded-md text-gray-600 hover:bg-red-50 hover:text-red-600 transition-colors"
                title="Sair"
                data-testid="logout-button"
              >
                <LogOut size={20} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Banner de Offline */}
      <OfflineBanner />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-grow">
        {children}
      </main>
      
      {/* Footer com Copyright */}
      <footer className="mt-auto py-4 text-center text-gray-500 text-sm border-t border-gray-200 bg-white">
        © 2026 Desenvolvido por{' '}
        <a 
          href="https://www.facebook.com/prof.gutenbergbarroso" 
          target="_blank" 
          rel="noopener noreferrer"
          className="text-blue-500 hover:text-blue-700 hover:underline"
        >
          Gutenberg Barroso
        </a>
      </footer>
      
      {/* Indicador flutuante de status */}
      <FloatingStatusIndicator />
    </div>
  );
};
