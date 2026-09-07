import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  LockKeyhole,
  Power,
  RefreshCw,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';

const API = `${process.env.REACT_APP_BACKEND_URL}/api/mantenedoras/access-control`;

const roleLabel = (item) => item?.label || item?.value || '';

export default function MantenedoraAccessControlPanel() {
  const { user } = useAuth();
  const { refreshAccessStatus, refreshMantenedora } = useMantenedora();
  const [state, setState] = useState(null);
  const [selectedRoles, setSelectedRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [message, setMessage] = useState(null);

  const isSuperAdmin = user?.role === 'super_admin' || (user?.roles || []).includes('super_admin');

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!isSuperAdmin) {
      setLoading(false);
      return null;
    }
    try {
      if (!quiet) setLoading(true);
      const response = await axios.get(API);
      setState(response.data);
      setSelectedRoles(response.data.allowed_roles || []);
      return response.data;
    } catch (error) {
      setMessage({
        type: 'error',
        text: error.response?.data?.detail || 'Não foi possível carregar o controle de acesso da mantenedora.',
      });
      return null;
    } finally {
      setLoading(false);
    }
  }, [isSuperAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const handleTenantChange = () => {
      setState(null);
      setSelectedRoles([]);
      setConfirmDeactivate(false);
      setMessage(null);
      load();
    };
    window.addEventListener('tenant-changed', handleTenantChange);
    return () => window.removeEventListener('tenant-changed', handleTenantChange);
  }, [load]);

  const blockerNames = useMemo(
    () => (state?.online_blockers || []).map((item) => item.full_name || item.email || 'Usuário').filter(Boolean),
    [state]
  );

  if (!isSuperAdmin) return null;

  const toggleRole = (role) => {
    setSelectedRoles((current) => (
      current.includes(role)
        ? current.filter((item) => item !== role)
        : [...current, role]
    ));
  };

  const saveRoles = async () => {
    try {
      setBusy(true);
      setMessage(null);
      const response = await axios.put(API, { allowed_roles: selectedRoles });
      setState((current) => ({ ...current, ...response.data }));
      setSelectedRoles(response.data.allowed_roles || []);
      await refreshAccessStatus();
      setMessage({ type: 'success', text: 'Permissões excepcionais salvas com sucesso.' });
    } catch (error) {
      const detail = error.response?.data?.detail;
      setMessage({
        type: 'error',
        text: typeof detail === 'string' ? detail : detail?.message || 'Não foi possível salvar as permissões.',
      });
    } finally {
      setBusy(false);
    }
  };

  const setActive = async (active) => {
    if (!active && (state?.online_blocker_count || 0) > 0) {
      setMessage({
        type: 'error',
        text: 'A desativação não pode ser realizada enquanto houver usuários conectados.',
      });
      return;
    }

    try {
      setBusy(true);
      setMessage(null);
      const response = await axios.put(API, {
        ativo: active,
        allowed_roles: selectedRoles,
      });
      setState((current) => ({ ...current, ...response.data }));
      setSelectedRoles(response.data.allowed_roles || []);
      setConfirmDeactivate(false);
      await Promise.all([refreshAccessStatus(), refreshMantenedora()]);
      setMessage({
        type: 'success',
        text: active
          ? 'Mantenedora ativada. O acesso normal foi restabelecido.'
          : 'Mantenedora desativada. Somente os perfis assinalados poderão acessar.',
      });
      await load({ quiet: true });
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (detail?.code === 'TENANT_HAS_ACTIVE_SESSIONS') {
        setState((current) => ({
          ...current,
          online_blockers: detail.users || [],
          online_blocker_count: detail.count || 0,
        }));
        setConfirmDeactivate(false);
        setMessage({
          type: 'error',
          text: 'A desativação foi bloqueada porque existem usuários conectados. Aguarde a saída deles e verifique novamente.',
        });
      } else {
        setMessage({
          type: 'error',
          text: typeof detail === 'string' ? detail : detail?.message || 'Não foi possível alterar o estado da mantenedora.',
        });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-slate-200">
      <CardHeader className="pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <LockKeyhole className="h-5 w-5 text-indigo-600" />
              Disponibilidade e Controle de Acesso
            </CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              Controle global da mantenedora e dos perfis que podem acessar durante uma suspensão.
            </p>
          </div>
          {state && (
            <span className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${
              state.active
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-amber-50 text-amber-800 border border-amber-200'
            }`}>
              {state.active ? <CheckCircle2 className="h-4 w-4" /> : <Power className="h-4 w-4" />}
              {state.active ? 'Mantenedora ativa' : 'Mantenedora desativada'}
            </span>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {loading ? (
          <div className="flex min-h-32 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Carregando controle de acesso...
          </div>
        ) : !state ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            Selecione uma mantenedora para gerenciar sua disponibilidade.
          </div>
        ) : (
          <>
            {message && (
              <div className={`rounded-xl border px-4 py-3 text-sm ${
                message.type === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : 'border-red-200 bg-red-50 text-red-800'
              }`}>
                {String(message.text)}
              </div>
            )}

            <section className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="max-w-2xl">
                  <h3 className="font-semibold text-slate-900">Ativar ou desativar a mantenedora</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    Desativar não apaga escolas, estudantes, diários ou documentos. O sistema bloqueia
                    operacionalmente tudo que pertence à mantenedora, preservando os dados para reativação.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => load({ quiet: true })}
                  disabled={busy}
                >
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Verificar conexões
                </Button>
              </div>

              <div className={`mt-4 rounded-xl border p-4 ${
                state.online_blocker_count > 0
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-emerald-200 bg-emerald-50'
              }`}>
                <div className="flex items-start gap-3">
                  <Users className={`mt-0.5 h-5 w-5 flex-none ${
                    state.online_blocker_count > 0 ? 'text-amber-700' : 'text-emerald-700'
                  }`} />
                  <div className="min-w-0">
                    <p className={`font-medium ${
                      state.online_blocker_count > 0 ? 'text-amber-900' : 'text-emerald-900'
                    }`}>
                      {state.online_blocker_count > 0
                        ? `${state.online_blocker_count} usuário(s) conectado(s)`
                        : 'Nenhum usuário conectado à mantenedora'}
                    </p>
                    {state.online_blocker_count > 0 && (
                      <p className="mt-1 text-sm text-amber-800 break-words">
                        {blockerNames.join(', ')}
                      </p>
                    )}
                    <p className={`mt-1 text-xs ${
                      state.online_blocker_count > 0 ? 'text-amber-700' : 'text-emerald-700'
                    }`}>
                      {state.online_blocker_count > 0
                        ? 'Por segurança, a desativação permanece indisponível enquanto qualquer desses usuários estiver conectado.'
                        : 'A condição de presença permite uma eventual desativação neste momento.'}
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                {state.active ? (
                  !confirmDeactivate ? (
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={() => setConfirmDeactivate(true)}
                      disabled={busy || state.online_blocker_count > 0}
                    >
                      <Power className="mr-2 h-4 w-4" />
                      Desativar mantenedora
                    </Button>
                  ) : (
                    <div className="w-full rounded-xl border border-red-200 bg-red-50 p-4">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="mt-0.5 h-5 w-5 flex-none text-red-700" />
                        <div>
                          <p className="font-semibold text-red-900">Confirmar desativação?</p>
                          <p className="mt-1 text-sm text-red-800">
                            Os usuários não liberados serão direcionados ao aviso de acesso temporariamente indisponível após o login.
                          </p>
                        </div>
                      </div>
                      <div className="mt-4 flex flex-wrap gap-2">
                        <Button type="button" variant="destructive" onClick={() => setActive(false)} disabled={busy}>
                          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          Sim, desativar
                        </Button>
                        <Button type="button" variant="outline" onClick={() => setConfirmDeactivate(false)} disabled={busy}>
                          Cancelar
                        </Button>
                      </div>
                    </div>
                  )
                ) : (
                  <Button type="button" onClick={() => setActive(true)} disabled={busy}>
                    {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Power className="mr-2 h-4 w-4" />}
                    Ativar mantenedora
                  </Button>
                )}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 p-4 sm:p-5">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 h-5 w-5 flex-none text-indigo-600" />
                <div>
                  <h3 className="font-semibold text-slate-900">Acesso excepcional enquanto desativada</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-600">
                    Assinale os tipos de usuário que continuarão entrando no SIGESC. Eles manterão exatamente
                    as permissões normais do próprio perfil; esta seleção não amplia nenhum privilégio.
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {(state.role_options || []).map((option) => {
                  const checked = selectedRoles.includes(option.value);
                  return (
                    <label
                      key={option.value}
                      className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-3 transition-colors ${
                        checked
                          ? 'border-indigo-300 bg-indigo-50 text-indigo-900'
                          : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleRole(option.value)}
                        disabled={busy}
                        className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm font-medium">{roleLabel(option)}</span>
                    </label>
                  );
                })}
              </div>

              <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-900">
                <strong>Super Administrador:</strong> acesso administrativo permanece disponível mesmo com a
                mantenedora desativada, exclusivamente para permitir diagnóstico, ajuste desta lista e reativação.
              </div>

              <div className="mt-4 flex justify-end">
                <Button type="button" onClick={saveRoles} disabled={busy}>
                  {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Salvar acessos excepcionais
                </Button>
              </div>
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}
