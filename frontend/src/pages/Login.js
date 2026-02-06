import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Mail, Lock, AlertCircle, UserPlus, WifiOff, Info } from 'lucide-react';
import { mantenedoraAPI } from '@/services/api';

export const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [exibirPreMatricula, setExibirPreMatricula] = useState(true);
  const { login } = useAuth();
  const navigate = useNavigate();

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
      // Mostra mensagem se for login offline
      if (result.offline) {
        setInfo(result.message);
        setTimeout(() => {
          navigate('/dashboard');
        }, 1500);
      } else {
        navigate('/dashboard');
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
            src="https://aprenderdigital.top/imagens/logotipo/logosigesc.png"
            alt="SIGESC Logo"
            className="h-24 mx-auto mb-4"
            data-testid="login-logo"
          />
          <h1 className="text-3xl font-bold text-gray-900">SIGESC</h1>
          <p className="text-gray-600 mt-2">Sistema Integrado de Gestão Escolar</p>
        </div>

        {/* Card de Login */}
        <div className="bg-white rounded-lg shadow-xl p-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-6 text-center">Entrar no Sistema</h2>

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
              <p className="text-xs text-gray-500 text-center mt-2">
                {isOnline ? 'Realize a pré-matrícula de novos alunos' : 'Pré-matrícula requer conexão com internet'}
              </p>
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
              href="https://aprenderdigital.top" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-500 hover:text-blue-700 hover:underline"
            >
              Aprender Digital
            </a>
          </p>
        </div>
      </div>
    </div>
  );
};
