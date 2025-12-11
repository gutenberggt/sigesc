import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { LogOut, Menu, X } from 'lucide-react';
import { useState } from 'react';

export const Layout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const roleLabels = {
    admin: 'Administrador',
    secretario: 'Secretário',
    diretor: 'Diretor',
    coordenador: 'Coordenador',
    professor: 'Professor',
    aluno: 'Aluno',
    responsavel: 'Responsável',
    semed: 'SEMED'
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 rounded-md text-gray-600 hover:bg-gray-100"
                data-testid="menu-toggle-button"
              >
                {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
              </button>
              <img
                src="https://aprenderdigital.top/imagens/logotipo/logosigesc.png"
                alt="SIGESC Logo"
                className="h-10"
                data-testid="sigesc-logo"
              />
              <h1 className="text-xl font-bold text-blue-600 hidden sm:block">SIGESC</h1>
            </div>

            {/* User Info */}
            <div className="flex items-center space-x-4">
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

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
    </div>
  );
};
