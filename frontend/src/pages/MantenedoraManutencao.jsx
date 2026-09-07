import { useState } from 'react';
import { Building2, LogOut, RefreshCw, ShieldCheck, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';

export default function MantenedoraManutencao({ accessStatus, onRetry }) {
  const { logout } = useAuth();
  const [checking, setChecking] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const mantenedora = accessStatus?.mantenedora || {};
  const institutionName = mantenedora.nome || 'Sua rede de ensino';
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
      <main className="w-full max-w-2xl" data-testid="mantenedora-maintenance-page">
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
          <div className="h-2 bg-amber-500" />
          <div className="px-6 py-10 text-center sm:px-10 sm:py-12">
            <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl border border-amber-100 bg-amber-50">
              {logo ? (
                <img
                  src={logo}
                  alt="Brasão da mantenedora"
                  className="h-14 w-14 object-contain"
                  onError={(event) => { event.currentTarget.style.display = 'none'; }}
                />
              ) : (
                <Building2 className="h-10 w-10 text-amber-700" aria-hidden="true" />
              )}
            </div>

            <p className="text-sm font-semibold uppercase tracking-wide text-amber-700">
              SIGESC
            </p>
            <h1 className="mt-2 text-2xl font-bold text-slate-900 sm:text-3xl">
              Sistema em manutenção
            </h1>
            <p className="mt-3 text-base font-medium text-slate-700">
              {institutionName}
            </p>

            <div className="mx-auto mt-7 max-w-xl rounded-2xl border border-slate-200 bg-slate-50 px-5 py-5 text-left">
              <div className="flex items-start gap-3">
                <Wrench className="mt-1 h-5 w-5 flex-none text-amber-700" aria-hidden="true" />
                <div>
                  <p className="leading-7 text-slate-700">
                    Estamos realizando uma manutenção temporária no SIGESC desta rede de ensino.
                    Durante esse período, o acesso operacional fica reservado à equipe responsável
                    pela manutenção.
                  </p>
                  <p className="mt-3 leading-7 text-slate-700">
                    Assim que o serviço for concluído, o acesso normal será restabelecido. Você
                    poderá continuar de onde parou.
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-6 flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-left">
              <ShieldCheck className="mt-0.5 h-5 w-5 flex-none text-emerald-700" aria-hidden="true" />
              <p className="text-sm text-emerald-900">
                Seus dados permanecem preservados. Não é necessário refazer cadastro, lançamentos
                ou criar outra conta.
              </p>
            </div>

            <div className="mt-8 flex flex-col-reverse gap-3 sm:flex-row sm:justify-center">
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
          Esta página é exibida automaticamente enquanto a mantenedora estiver em manutenção.
        </p>
      </main>
    </div>
  );
}
