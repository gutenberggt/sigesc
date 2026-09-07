import { useState } from 'react';
import { Building2, LogOut, RefreshCw, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';

export default function MantenedoraDesativada({ accessStatus, onRetry }) {
  const { logout } = useAuth();
  const [checking, setChecking] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const mantenedora = accessStatus?.mantenedora || {};
  const institutionName = mantenedora.nome || 'Sua unidade de ensino';
  const logo = mantenedora.brasao_url || '';

  const handleRetry = async () => {
    if (!onRetry) return;
    try {
      setChecking(true);
      await onRetry();
    } finally {
      setChecking(false);
    }
  };

  const handleLogout = async () => {
    try {
      setLeaving(true);
      await logout();
    } finally {
      setLeaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4 py-10">
      <main className="w-full max-w-2xl">
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="h-2 bg-indigo-600" />
          <div className="px-6 py-10 sm:px-10 sm:py-12 text-center">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-indigo-50 border border-indigo-100">
              {logo ? (
                <img
                  src={logo}
                  alt="Brasão da mantenedora"
                  className="h-14 w-14 object-contain"
                  onError={(event) => { event.currentTarget.style.display = 'none'; }}
                />
              ) : (
                <Building2 className="h-10 w-10 text-indigo-600" aria-hidden="true" />
              )}
            </div>

            <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
              SIGESC
            </p>
            <h1 className="mt-2 text-2xl sm:text-3xl font-bold text-slate-900">
              Acesso temporariamente indisponível
            </h1>
            <p className="mt-3 text-base font-medium text-slate-700">
              {institutionName}
            </p>

            <div className="mx-auto mt-7 max-w-xl rounded-2xl bg-slate-50 border border-slate-200 px-5 py-5 text-left">
              <p className="text-slate-700 leading-7">
                Neste momento, o acesso da sua rede de ensino ao SIGESC está temporariamente suspenso.
                Seus dados permanecem preservados no sistema.
              </p>
              <p className="mt-3 text-slate-700 leading-7">
                Para mais informações ou orientação sobre a liberação do acesso, procure a
                <strong> direção da sua escola</strong>.
              </p>
            </div>

            <div className="mt-6 flex items-start gap-3 rounded-xl bg-emerald-50 border border-emerald-100 px-4 py-3 text-left">
              <ShieldCheck className="mt-0.5 h-5 w-5 flex-none text-emerald-700" aria-hidden="true" />
              <p className="text-sm text-emerald-900">
                Não é necessário criar outra conta ou refazer seu cadastro. Quando o acesso for
                restabelecido, você poderá continuar usando o SIGESC normalmente.
              </p>
            </div>

            <div className="mt-8 flex flex-col-reverse sm:flex-row sm:justify-center gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={handleLogout}
                disabled={leaving || checking}
                className="sm:min-w-36"
              >
                <LogOut className="mr-2 h-4 w-4" />
                {leaving ? 'Saindo...' : 'Sair'}
              </Button>
              <Button
                type="button"
                onClick={handleRetry}
                disabled={checking || leaving}
                className="sm:min-w-48"
              >
                <RefreshCw className={`mr-2 h-4 w-4 ${checking ? 'animate-spin' : ''}`} />
                {checking ? 'Verificando...' : 'Verificar novamente'}
              </Button>
            </div>
          </div>
        </div>

        <p className="mt-5 text-center text-xs text-slate-500">
          Esta mensagem é exibida automaticamente enquanto a mantenedora estiver com o acesso suspenso.
        </p>
      </main>
    </div>
  );
}
