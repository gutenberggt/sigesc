import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { LogOut, Menu, X, HelpCircle, Shield, ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { NotificationBell, MessagesBadge } from '@/components/notifications';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { useBranding } from '@/contexts/BrandingContext';
import { OfflineBanner } from '@/components/OfflineStatus';
import { StatusIndicator } from '@/components/session/StatusIndicator';
import { useMessaging } from '@/contexts/MessagingContext';
import { ChatBox } from '@/components/messaging';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { TenantSwitcher } from '@/components/TenantSwitcher';
import { SilentModeToggle } from '@/components/SilentModeToggle';
import { TenantSyncBoundary } from '@/components/TenantSyncBoundary';

export const Layout = ({ children }) => {
  const { user, logout, switchRole, getAvailableRoles } = useAuth();
  const { mantenedora } = useMantenedora();
  const { branding } = useBranding();
  const { activeChat, closeChat } = useMessaging();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showRoleSelector, setShowRoleSelector] = useState(false);
  const [switchingRole, setSwitchingRole] = useState(false);
  const { getUnsavedState } = useUnsavedChangesContext();

  const handleLogout = () => {
    const { hasChanges, message } = getUnsavedState();
    if (hasChanges) {
      const leave = window.confirm(message || 'Você tem alterações não salvas. Deseja sair sem salvar?');
      if (!leave) return;
    }
    logout();
    navigate('/login');
  };

  const roleLabels = {
    super_admin: 'Super Administrador',
    gerente: 'Gerente',
    admin: 'Administrador',
    admin_teste: 'Administrador',
    secretario: 'Secretário(a)',
    diretor: 'Diretor(a)',
    coordenador: 'Coordenador(a)',
    apoio_pedagogico: 'Apoio Pedagógico',
    auxiliar_secretaria: 'Auxiliar de Secretaria',
    professor: 'Professor(a)',
    aluno: 'Estudante',
    responsavel: 'Responsável(is)',
    ass_social: 'Ass. Social',
    ass_social_2: 'Ass. Social',
    agente_vacinas: 'Agente de Vacinas',
    semed: 'SEMED',
    semed1: 'Tutor',
    semed2: 'Analista',
    semed3: 'Administração'
  };

  // P0 multipapel (Ago/2026): o seletor precisa viver no Layout, não apenas no
  // Dashboard administrativo. Professores são redirecionados para /professor antes
  // de o Dashboard renderizar seu seletor local, portanto ficavam sem caminho para
  // ativar um papel adicional mesmo tendo uma sessão multipapel válida.
  const availableRoles = Array.from(new Set(
    getAvailableRoles ? getAvailableRoles().filter(Boolean) : [user?.role].filter(Boolean)
  ));
  const hasMultipleRoles = availableRoles.length > 1;

  const handleSwitchRole = async (newRole) => {
    if (!newRole || newRole === user?.role) {
      setShowRoleSelector(false);
      return;
    }

    const { hasChanges, message } = getUnsavedState();
    if (hasChanges) {
      const leave = window.confirm(
        message || 'Você tem alterações não salvas. Deseja trocar de papel sem salvar?'
      );
      if (!leave) return;
    }

    setSwitchingRole(true);
    try {
      const result = await switchRole(newRole);
      if (!result?.success) {
        window.alert(result?.error || 'Erro ao trocar papel');
        return;
      }

      setShowRoleSelector(false);
      // A sessão já foi integralmente rotacionada pelo AuthContext. Recarregar pelo
      // /dashboard força todos os contexts/permissões a nascerem do novo JWT; o
      // Dashboard redireciona automaticamente papéis com home própria (ex.: professor).
      window.location.assign('/dashboard');
    } catch (error) {
      console.error('Erro ao trocar papel:', error);
      window.alert('Erro ao trocar papel');
    } finally {
      setSwitchingRole(false);
    }
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
              
              {/* Logo do Tenant (G4 — fallback ao SIGESC se default) */}
              <img
                src={branding?.logo_url || "https://aprenderdigital.top/imagens/logotipo/logosigesc.png"}
                alt={branding?.name ? `Logo ${branding.name}` : "SIGESC Logo"}
                className="h-10 w-auto object-contain"
                onError={(e) => { e.target.src = "https://aprenderdigital.top/imagens/logotipo/logosigesc.png"; }}
                data-testid="brand-logo"
              />
              <div className="hidden sm:block border-r border-gray-200 pr-4">
                <h1
                  className="text-xl font-bold leading-tight"
                  style={{ color: branding?.primary_color || '#2563eb' }}
                  data-testid="brand-name"
                >
                  {branding?.name || 'SIGESC'}
                </h1>
                <p className="text-[10px] text-gray-500 leading-tight uppercase tracking-wide">
                  {branding?.slogan || 'Sistema Integrado de Gestão Escolar'}
                </p>
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
              
              {/* Nome da Mantenedora + Secretaria */}
              <div className="hidden md:block">
                <p className="text-xs font-medium text-gray-700 leading-tight">
                  {mantenedora?.nome || 'Prefeitura Municipal'}
                </p>
                {mantenedora?.secretaria && (
                  <p className="text-[10px] text-gray-500 leading-tight mt-0.5" data-testid="mantenedora-secretaria">
                    {mantenedora.secretaria}
                  </p>
                )}
              </div>
            </div>

            {/* Notifications & User Info */}
            <div className="flex items-center space-x-2">
              {/* Status permanente do sistema (conexão + sync + sessão) — P2 */}
              <StatusIndicator />
              
              {/* Modo Silencioso */}
              <SilentModeToggle />
              
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

              {/* Seletor global de papel — visível em qualquer dashboard/página */}
              {hasMultipleRoles && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowRoleSelector((current) => !current)}
                    disabled={switchingRole}
                    className="flex items-center gap-1.5 px-2.5 py-2 rounded-md text-gray-600 hover:bg-blue-50 hover:text-blue-700 transition-colors disabled:opacity-50"
                    title="Trocar papel ativo"
                    data-testid="global-role-switcher-button"
                  >
                    <Shield size={18} />
                    <span className="hidden xl:inline text-xs font-medium">Trocar Papel</span>
                    <ChevronDown
                      size={14}
                      className={`transition-transform ${showRoleSelector ? 'rotate-180' : ''}`}
                    />
                  </button>

                  {showRoleSelector && (
                    <div
                      className="absolute right-0 top-full mt-2 w-56 bg-white rounded-lg shadow-xl border border-gray-200 py-2 z-50"
                      data-testid="global-role-switcher-menu"
                    >
                      <div className="px-3 py-2 border-b border-gray-100">
                        <p className="text-xs text-gray-500 font-medium">Papel ativo da sessão</p>
                      </div>
                      {availableRoles.map((role) => (
                        <button
                          type="button"
                          key={role}
                          onClick={() => handleSwitchRole(role)}
                          disabled={switchingRole}
                          className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 flex items-center justify-between disabled:opacity-50 ${
                            role === user?.role ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700'
                          }`}
                          data-testid={`global-role-option-${role}`}
                        >
                          <span>{roleLabels[role] || role}</span>
                          {role === user?.role && (
                            <span className="text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded">Atual</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              
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
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-grow pb-16">
        {/* Seletor de Mantenedora (somente super_admin) - topo direito da área de conteúdo */}
        {user?.role === 'super_admin' && (
          <div className="flex justify-end -mt-6 mb-1" data-testid="tenant-switcher-wrapper">
            <TenantSwitcher />
          </div>
        )}
        <TenantSyncBoundary>
          {children}
        </TenantSyncBoundary>
      </main>
      
      {/* Footer com Copyright - Fixo na parte inferior */}
      <footer className="fixed bottom-0 left-0 right-0 py-3 px-4 text-center text-gray-500 text-sm border-t border-gray-200 bg-white z-30">
        <span>
          © 2026 Desenvolvido por{' '}
          <a 
            href="https://www.facebook.com/prof.gutenbergbarroso" 
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 hover:text-blue-700 hover:underline"
          >
            Gutenberg Barroso
          </a>
        </span>
        <a
          href="https://aprenderdigital.top"
          target="_blank"
          rel="noopener noreferrer"
          className="fixed bottom-3 right-4 flex items-center gap-2 text-gray-700 hover:text-blue-600 transition-colors no-underline z-30"
          data-testid="aprender-digital-link"
        >
          <img src="https://aprenderdigital.top/imagens/favicom.png" alt="Aprender Digital" className="w-5 h-5" />
          <span className="text-xs font-medium">Aprender Digital</span>
        </a>
      </footer>
      
      {/* Chat Box Global */}
      {activeChat && (
        <ChatBox
          connection={activeChat}
          onClose={closeChat}
        />
      )}
    </div>
  );
};
