import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Mail, Lock, AlertCircle, UserPlus, WifiOff, Info, Smartphone, Download, X } from 'lucide-react';
import { mantenedoraAPI } from '@/services/api';
import useTenantBranding from '@/hooks/useTenantBranding';

export const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [exibirPreMatricula, setExibirPreMatricula] = useState(true);
  const [storagePersisted, setStoragePersisted] = useState(null);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [appInstalled, setAppInstalled] = useState(false);
  const [installDismissed, setInstallDismissed] = useState(() => sessionStorage.getItem('sigesc_install_dismissed') === '1');
  const { login } = useAuth();
  const navigate = useNavigate();
  const { branding } = useTenantBranding();

  // P0 (Jun/2026) — Diagnóstico VISÍVEL da sessão offline (sem precisar de console).
  // Lê o localStorage e mostra na tela quando offline, para identificar rapidamente
  // se a sessão salva existe, sua idade e o e-mail gravado. Também exibe a versão
  // do build para confirmar que o código novo está em execução.
  const offlineDiag = (() => {
    try {
      const ud = localStorage.getItem('userData');
      const ll = localStorage.getItem('lastLoginTime');
      if (!ud) return { has: false, hasLastLogin: !!ll };
      let savedEmail = '?';
      try { savedEmail = JSON.parse(ud).email || '(sem email no userData)'; } catch { savedEmail = '(json inválido)'; }
      const dias = ll ? ((Date.now() - Number(ll)) / 86400000).toFixed(1) : null;
      return { has: true, hasLastLogin: !!ll, savedEmail, dias };
    } catch (e) {
      return { has: false, hasLastLogin: false, err: e.message };
    }
  })();

  // P0 (Jun/2026) — Verifica/solicita armazenamento PERSISTENTE. Sem isso, o
  // navegador pode apagar localStorage/IndexedDB ao fechar (eviction "best-effort"),
  // o que destrói a sessão offline. Mostramos o status no painel de diagnóstico.
  useEffect(() => {
    if (navigator.storage && navigator.storage.persisted) {
      navigator.storage.persisted()
        .then((p) => {
          setStoragePersisted(p);
          if (!p && navigator.storage.persist) {
            navigator.storage.persist().then((granted) => setStoragePersisted(granted)).catch(() => {});
          }
        })
        .catch(() => setStoragePersisted(null));
    }
  }, []);

  // P0 (Jun/2026) — Banner de instalação do PWA. Quando o app NÃO está instalado e
  // o armazenamento não é persistente, o navegador pode apagar a sessão offline ao
  // fechar. Instalar como app garante persistência. Captura o evento nativo
  // `beforeinstallprompt` para oferecer instalação em 1 clique.
  useEffect(() => {
    const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    setIsStandalone(standalone);

    const onBeforeInstallPrompt = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    const onAppInstalled = () => {
      setAppInstalled(true);
      setDeferredPrompt(null);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    window.addEventListener('appinstalled', onAppInstalled);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
      window.removeEventListener('appinstalled', onAppInstalled);
    };
  }, []);

  const handleInstallApp = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    try { await deferredPrompt.userChoice; } catch (e) { /* ignore */ }
    setDeferredPrompt(null);
  };

  const dismissInstallBanner = () => {
    setInstallDismissed(true);
    try { sessionStorage.setItem('sigesc_install_dismissed', '1'); } catch (e) { /* ignore */ }
  };

  // Mostra o banner quando NÃO está instalado, não foi dispensado e a persistência
  // ainda não está garantida (storagePersisted !== true).
  const showInstallBanner = !isStandalone && !appInstalled && !installDismissed && storagePersisted !== true;

  // Monitora status de conexão
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Busca configuração da mantenedora
  useEffect(() => {
    const fetchMantenedora = async () => {
      try {
        const data = await mantenedoraAPI.get();
        setExibirPreMatricula(data.exibir_pre_matricula !== false);
      } catch (error) {
        console.error('Erro ao buscar configuração:', error);
        // Em caso de erro, mantém o padrão (exibir)
      }
    };
    
    if (isOnline) {
      fetchMantenedora();
    }
  }, [isOnline]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setInfo('');
    setLoading(true);

    const result = await login(email, password);

    if (result.success) {
      const userRole = result.user?.role;
      const targetPath = userRole === 'aluno' ? '/aluno' : '/dashboard';
      // Mostra mensagem se for login offline
      if (result.offline) {
        setInfo(result.message);
        setTimeout(() => {
          navigate(targetPath);
        }, 1500);
      } else {
        navigate(targetPath);
      }
    } else {
      setError(result.error);
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-gray-100 flex items-center justify-center px-4">
      <div className="max-w-md w-full">
        {/* Logo */}
        <div className="text-center mb-8">
          <img
            src={branding.logo_url || "https://aprenderdigital.top/imagens/logotipo/logosigesc.png"}
            alt={branding.name || "SIGESC"}
            className="h-24 mx-auto mb-4 object-contain"
            data-testid="login-logo"
            onError={(e) => { e.target.src = "https://aprenderdigital.top/imagens/logotipo/logosigesc.png"; }}
          />
          <h1
            className="sr-only"
            data-testid="login-tenant-name"
          >
            {branding.name || 'SIGESC'}
          </h1>
          {branding.secretaria && (
            <p className="text-xs text-gray-500 mt-1">{branding.secretaria}</p>
          )}
        </div>

        {/* Card de Login */}
        <div className="bg-white rounded-lg shadow-xl p-8">
          <div className="mb-6 text-center">
            <h2 className="text-2xl font-bold text-gray-900">Olá! Que bom ter você aqui!</h2>
            <p className="text-base text-gray-700 mt-1">Acesse sua conta</p>
          </div>

          {/* Banner: instalar como app (PWA) para garantir acesso offline */}
          {showInstallBanner && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg" data-testid="install-pwa-banner">
              <div className="flex items-start">
                <Smartphone className="text-blue-600 mr-3 flex-shrink-0 mt-0.5" size={22} />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-blue-900">📲 Instale o SIGESC como aplicativo</p>
                  <p className="text-xs text-blue-700 mt-1">
                    Garante o <b>acesso offline confiável</b> — a sessão não é apagada quando você fecha o navegador.
                  </p>
                  <div className="mt-3 flex items-center gap-3 flex-wrap">
                    {deferredPrompt ? (
                      <button
                        type="button"
                        onClick={handleInstallApp}
                        data-testid="install-pwa-button"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg transition-colors"
                      >
                        <Download size={16} /> Instalar app
                      </button>
                    ) : (
                      <p className="text-xs text-blue-600">
                        No menu do navegador (⋯) escolha <b>“Instalar este site como um aplicativo”</b>.
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={dismissInstallBanner}
                      data-testid="install-pwa-dismiss"
                      className="text-xs text-blue-500 hover:text-blue-700 underline"
                    >
                      Agora não
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={dismissInstallBanner}
                  aria-label="Fechar"
                  className="text-blue-400 hover:text-blue-600 ml-2 flex-shrink-0"
                >
                  <X size={18} />
                </button>
              </div>
            </div>
          )}
          {/* Aviso de Offline */}
          {!isOnline && (
            <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start" data-testid="offline-warning">
              <WifiOff className="text-amber-600 mr-2 flex-shrink-0 mt-0.5" size={20} />
              <div>
                <p className="text-sm font-medium text-amber-800">Você está offline</p>
                <p className="text-xs text-amber-600 mt-1">
                  Se você já fez login antes neste dispositivo, pode acessar com o mesmo e-mail.
                </p>
              </div>
            </div>
          )}

          {/* Diagnóstico de sessão offline ocultado a pedido (UI mais limpa) */}

          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start" data-testid="login-error">
              <AlertCircle className="text-red-600 mr-2 flex-shrink-0 mt-0.5" size={20} />
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {info && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-start" data-testid="login-info">
              <Info className="text-blue-600 mr-2 flex-shrink-0 mt-0.5" size={20} />
              <p className="text-sm text-blue-600">{info}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                E-mail
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="text-gray-400" size={20} />
                </div>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                  placeholder="seu@email.com"
                  data-testid="login-email-input"
                />
              </div>
            </div>

            {/* Senha */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                Senha
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="text-gray-400" size={20} />
                </div>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                  placeholder="••••••••"
                  data-testid="login-password-input"
                />
              </div>
            </div>

            {/* Botão de Login */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 focus:ring-4 focus:ring-blue-300 transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed"
              data-testid="login-submit-button"
            >
              {loading ? 'Entrando...' : (isOnline ? 'Entrar' : 'Entrar (Offline)')}
            </button>
          </form>
          
          {/* Divisor e Botão de Pré-Matrícula - apenas se habilitado */}
          {exibirPreMatricula && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-200"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white text-gray-500">ou</span>
                </div>
              </div>
              
              {/* Botão de Pré-Matrícula */}
              <Link
                to="/pre-matricula"
                className={`w-full flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-colors ${
                  isOnline 
                    ? 'bg-green-600 text-white hover:bg-green-700 focus:ring-4 focus:ring-green-300'
                    : 'bg-gray-300 text-gray-500 cursor-not-allowed pointer-events-none'
                }`}
                data-testid="pre-matricula-button"
                onClick={(e) => !isOnline && e.preventDefault()}
              >
                <UserPlus size={20} />
                Pré-Matrícula
              </Link>
              {!isOnline && (
                <p className="text-xs text-gray-500 text-center mt-2">
                  Pré-matrícula requer conexão com internet
                </p>
              )}
            </>
          )}

        </div>
        
        {/* Link para a página de apresentação */}
        <div className="text-center mt-6">
          <Link
            to="/sobre"
            className="text-sm text-blue-600 hover:text-blue-800 hover:underline transition-colors"
            data-testid="landing-page-link"
          >
            ← Conheça mais sobre o SIGESC
          </Link>
        </div>
        
        {/* Rodapé com créditos */}
        <div className="text-center mt-4">
          <p className="text-xs text-gray-400">
            Desenvolvido por{' '}
            <a 
              href="https://www.facebook.com/prof.gutenbergbarroso" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-500 hover:text-blue-700 hover:underline"
            >
              Gutenberg Barroso
            </a>
          </p>
        </div>
      </div>
    </div>
  );
};
