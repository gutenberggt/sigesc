import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { LogOut, Menu, X, AlertTriangle } from 'lucide-react';
import { useState } from 'react';
import { NotificationBell, MessagesBadge } from '@/components/notifications';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { ConnectionStatusBadge, OfflineBanner, FloatingStatusIndicator } from '@/components/OfflineStatus';

export const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const { mantenedora } = useMantenedora();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Verifica se está em modo teste (sandbox)
  const isSandboxMode = user?.role === 'admin_teste';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const roleLabels = {
    admin: 'Administrador',
    admin_teste: 'Admin (Teste)',
    secretario: 'Secretário',
    diretor: 'Diretor',
    coordenador: 'Coordenador',
    professor: 'Professor',
    aluno: 'Aluno',
    responsavel: 'Responsável',
    semed: 'SEMED'
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Barra de aviso do Modo Teste */}
      {isSandboxMode && (
        <div className="bg-amber-500 text-white px-4 py-2 text-center text-sm font-medium flex items-center justify-center gap-2 sticky top-0 z-50">
          <AlertTriangle size={18} />
          <span>⚠️ MODO TESTE — Alterações não serão salvas no sistema real. Reset automático à meia-noite.</span>
          <AlertTriangle size={18} />
        </div>
      )}
      
      {/* Header */}
      <header className={`bg-white shadow-sm border-b border-gray-200 sticky ${isSandboxMode ? 'top-10' : 'top-0'} z-40`}>
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
              {mantenedora?.logotipo_url && (
                <img
                  src={mantenedora.logotipo_url}
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
        © 2026 Aprender Digital — Gutenberg Barroso
      </footer>
      
      {/* Indicador flutuante de status */}
      <FloatingStatusIndicator />
    </div>
  );
};
