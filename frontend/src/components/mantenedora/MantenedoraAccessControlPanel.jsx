import { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  LockKeyhole,
  Power,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { apiFetch, getActiveTenantId } from '@/services/api';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ACCESS_CONTROL_API = `${API_BASE}/mantenedoras/access-control`;
const TENANTS_API = `${API_BASE}/mantenedoras`;

const roleLabel = (item) => item?.label || item?.value || '';

const detailMessage = (detail, fallback) => {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object' && detail.message) return detail.message;
  return fallback;
};

const blockerNames = (users = []) => (
  users.map((item) => item?.full_name || item?.email || 'Usuário').filter(Boolean)
);

const accessControlUrl = (tenantId) => (
  `${ACCESS_CONTROL_API}?mantenedora_id=${encodeURIComponent(tenantId)}`
);

const requestJson = async (url, options = {}) => {
  const response = await apiFetch(url, options);
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const error = new Error(detailMessage(data?.detail, `Falha HTTP ${response.status}`));
    error.status = response.status;
    error.detail = data?.detail;
    throw error;
  }
  return data;
};

export default function MantenedoraAccessControlPanel() {
  const { user } = useAuth();
  const { refreshAccessStatus, refreshMantenedora } = useMantenedora();
  const [tenants, setTenants] = useState([]);
  const [controls, setControls] = useState({});
  const [roleDrafts, setRoleDrafts] = useState({});
  const [controlErrors, setControlErrors] = useState({});
  const [messages, setMessages] = useState({});
  const [busyByTenant, setBusyByTenant] = useState({});
  const [loading, setLoading] = useState(true);
  const [globalError, setGlobalError] = useState(null);

  const isSuperAdmin = user?.role === 'super_admin' || (user?.roles || []).includes('super_admin');

  const loadAll = useCallback(async () => {
    if (!isSuperAdmin) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setGlobalError(null);
    try {
      const data = await requestJson(TENANTS_API);
      const items = Array.isArray(data) ? data : [];
      setTenants(items);

      const results = await Promise.all(items.map(async (tenant) => {
        try {
          const control = await requestJson(accessControlUrl(tenant.id));
          return { tenantId: tenant.id, control, error: null };
        } catch (error) {
          return {
            tenantId: tenant.id,
            control: null,
            error: detailMessage(
              error.detail,
              'Não foi possível carregar o controle de disponibilidade desta mantenedora.'
            ),
          };
        }
      }));

      const nextControls = {};
      const nextDrafts = {};
      const nextErrors = {};
      results.forEach(({ tenantId, control, error }) => {
        if (control) {
          nextControls[tenantId] = control;
          nextDrafts[tenantId] = control.allowed_roles || [];
        }
        if (error) nextErrors[tenantId] = error;
      });
      setControls(nextControls);
      setRoleDrafts(nextDrafts);
      setControlErrors(nextErrors);
    } catch (error) {
      setTenants([]);
      setControls({});
      setRoleDrafts({});
      setControlErrors({});
      setGlobalError(detailMessage(error.detail, 'Não foi possível carregar as mantenedoras.'));
    } finally {
      setLoading(false);
    }
  }, [isSuperAdmin]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  if (!isSuperAdmin) return null;

  const setBusy = (tenantId, value) => {
    setBusyByTenant((current) => ({ ...current, [tenantId]: value }));
  };

  const setTenantMessage = (tenantId, message) => {
    setMessages((current) => ({ ...current, [tenantId]: message }));
  };

  const refreshContextIfCurrent = async (tenantId) => {
    if (String(getActiveTenantId() || '') !== String(tenantId)) return;
    await Promise.allSettled([refreshAccessStatus(), refreshMantenedora()]);
  };

  const reloadTenant = async (tenantId) => {
    setBusy(tenantId, true);
    setTenantMessage(tenantId, null);
    try {
      const control = await requestJson(accessControlUrl(tenantId));
      setControls((current) => ({ ...current, [tenantId]: control }));
      setRoleDrafts((current) => ({ ...current, [tenantId]: control.allowed_roles || [] }));
      setControlErrors((current) => {
        const next = { ...current };
        delete next[tenantId];
        return next;
      });
    } catch (error) {
      setControlErrors((current) => ({
        ...current,
        [tenantId]: detailMessage(
          error.detail,
          'Não foi possível carregar o controle de disponibilidade desta mantenedora.'
        ),
      }));
    } finally {
      setBusy(tenantId, false);
    }
  };

  const toggleAvailability = async (tenantId) => {
    const control = controls[tenantId];
    if (!control) return;

    const targetActive = !control.active;
    setBusy(tenantId, true);
    setTenantMessage(tenantId, null);

    try {
      const data = await requestJson(accessControlUrl(tenantId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ativo: targetActive }),
      });
      setControls((current) => ({ ...current, [tenantId]: data }));
      setRoleDrafts((current) => ({ ...current, [tenantId]: data.allowed_roles || [] }));
      setControlErrors((current) => {
        const next = { ...current };
        delete next[tenantId];
        return next;
      });
      setTenantMessage(tenantId, {
        type: 'success',
        text: targetActive
          ? 'Mantenedora ativada. O acesso normal foi restabelecido.'
          : 'Mantenedora desativada. Configure abaixo, se necessário, os perfis com acesso excepcional.',
      });
      await refreshContextIfCurrent(tenantId);
    } catch (error) {
      const detail = error.detail;
      if (detail?.code === 'TENANT_HAS_ACTIVE_SESSIONS') {
        const names = blockerNames(detail.users || []);
        const count = detail.count || names.length;
        setControls((current) => ({
          ...current,
          [tenantId]: {
            ...current[tenantId],
            online_blockers: detail.users || [],
            online_blocker_count: count,
          },
        }));
        setTenantMessage(tenantId, {
          type: 'error',
          text: names.length
            ? `Não foi possível desativar: ${count} usuário(s) estão conectados — ${names.join(', ')}.`
            : `Não foi possível desativar: ${count} usuário(s) estão conectados.`,
        });
      } else {
        setTenantMessage(tenantId, {
          type: 'error',
          text: detailMessage(detail, 'Não foi possível alterar a disponibilidade da mantenedora.'),
        });
      }
    } finally {
      setBusy(tenantId, false);
    }
  };

  const toggleRole = (tenantId, role) => {
    setRoleDrafts((current) => {
      const roles = current[tenantId] || [];
      return {
        ...current,
        [tenantId]: roles.includes(role)
          ? roles.filter((item) => item !== role)
          : [...roles, role],
      };
    });
  };

  const saveRoles = async (tenantId) => {
    const control = controls[tenantId];
    if (!control || control.active) return;

    setBusy(tenantId, true);
    setTenantMessage(tenantId, null);
    try {
      const data = await requestJson(accessControlUrl(tenantId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ allowed_roles: roleDrafts[tenantId] || [] }),
      });
      setControls((current) => ({ ...current, [tenantId]: data }));
      setRoleDrafts((current) => ({ ...current, [tenantId]: data.allowed_roles || [] }));
      setTenantMessage(tenantId, {
        type: 'success',
        text: 'Acessos excepcionais salvos com sucesso.',
      });
      await refreshContextIfCurrent(tenantId);
    } catch (error) {
      setTenantMessage(tenantId, {
        type: 'error',
        text: detailMessage(error.detail, 'Não foi possível salvar os acessos excepcionais.'),
      });
    } finally {
      setBusy(tenantId, false);
    }
  };

  return (
    <section className="space-y-4" data-testid="mantenedora-access-control-panels">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <LockKeyhole className="h-5 w-5 text-indigo-600" />
          Disponibilidade e Controle de Acesso
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Ative ou desative cada mantenedora diretamente em seu painel. A desativação preserva todos os dados.
        </p>
      </div>

      {globalError && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {globalError}
        </div>
      )}

      {loading ? (
        <Card className="border-slate-200">
          <CardContent className="flex min-h-32 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Carregando mantenedoras...
          </CardContent>
        </Card>
      ) : tenants.length === 0 && !globalError ? (
        <Card className="border-slate-200">
          <CardContent className="py-8 text-center text-sm text-slate-500">
            Nenhuma mantenedora cadastrada.
          </CardContent>
        </Card>
      ) : (
        tenants.map((tenant) => {
          const tenantId = tenant.id;
          const control = controls[tenantId];
          const error = controlErrors[tenantId];
          const message = messages[tenantId];
          const busy = Boolean(busyByTenant[tenantId]);
          const active = Boolean(control?.active);
          const roles = roleDrafts[tenantId] || [];

          return (
            <Card
              key={tenantId}
              className="border-slate-200"
              data-testid={`mantenedora-access-card-${tenantId}`}
            >
              <CardHeader className="pb-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <CardTitle className="text-lg">
                      {tenant.nome || tenant.name || tenantId}
                    </CardTitle>
                    {tenant.cnpj && (
                      <p className="mt-1 text-sm text-slate-500">CNPJ: {tenant.cnpj}</p>
                    )}
                  </div>
                  {control && (
                    <span className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-1 text-sm font-semibold ${
                      active
                        ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                        : 'border-amber-200 bg-amber-50 text-amber-800'
                    }`}>
                      {active ? <CheckCircle2 className="h-4 w-4" /> : <Power className="h-4 w-4" />}
                      {active ? 'Mantenedora ativa' : 'Mantenedora desativada'}
                    </span>
                  )}
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                {error ? (
                  <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                    <div className="flex items-start gap-3">
                      <AlertTriangle className="mt-0.5 h-5 w-5 flex-none" />
                      <div className="flex-1">
                        <p>{error}</p>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="mt-3 bg-white"
                          onClick={() => reloadTenant(tenantId)}
                          disabled={busy}
                        >
                          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          Tentar novamente
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : !control ? (
                  <div className="flex min-h-24 items-center justify-center text-sm text-slate-500">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Carregando disponibilidade...
                  </div>
                ) : (
                  <>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5">
                      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <h3 className="font-semibold text-slate-900">Disponibilidade</h3>
                          <p className="mt-1 text-sm leading-6 text-slate-600">
                            {active
                              ? 'Acesso normal liberado para os usuários desta mantenedora.'
                              : 'A mantenedora está suspensa. Escolas, estudantes, diários e documentos permanecem preservados.'}
                          </p>
                        </div>

                        <div className="flex items-center gap-3">
                          {busy && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
                          <span className={`text-sm font-semibold ${active ? 'text-emerald-700' : 'text-slate-600'}`}>
                            {active ? 'Ativa' : 'Desativada'}
                          </span>
                          <button
                            type="button"
                            role="switch"
                            aria-checked={active}
                            aria-label={active ? 'Desativar mantenedora' : 'Ativar mantenedora'}
                            data-testid={`mantenedora-active-switch-${tenantId}`}
                            onClick={() => toggleAvailability(tenantId)}
                            disabled={busy}
                            className={`relative inline-flex h-7 w-12 flex-none items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 ${
                              active ? 'bg-emerald-600' : 'bg-slate-300'
                            }`}
                          >
                            <span
                              aria-hidden="true"
                              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                                active ? 'translate-x-6' : 'translate-x-1'
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                    </div>

                    {message && (
                      <div className={`rounded-xl border px-4 py-3 text-sm ${
                        message.type === 'success'
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                          : 'border-red-200 bg-red-50 text-red-800'
                      }`}>
                        {message.type === 'error' && (
                          <AlertTriangle className="mr-2 inline h-4 w-4 align-text-bottom" />
                        )}
                        {String(message.text)}
                      </div>
                    )}

                    {!active && (
                      <section
                        className="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-4 sm:p-5"
                        data-testid={`mantenedora-exceptional-access-${tenantId}`}
                      >
                        <div className="flex items-start gap-3">
                          <ShieldCheck className="mt-0.5 h-5 w-5 flex-none text-indigo-600" />
                          <div>
                            <h3 className="font-semibold text-slate-900">
                              Acesso excepcional enquanto desativada
                            </h3>
                            <p className="mt-1 text-sm leading-6 text-slate-600">
                              Assinale os tipos de usuário que poderão continuar entrando no SIGESC. Cada usuário
                              mantém somente as permissões normais do próprio perfil; esta seleção não amplia privilégios.
                            </p>
                          </div>
                        </div>

                        <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                          {(control.role_options || []).map((option) => {
                            const checked = roles.includes(option.value);
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
                                  onChange={() => toggleRole(tenantId, option.value)}
                                  disabled={busy}
                                  className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                                />
                                <span className="text-sm font-medium">{roleLabel(option)}</span>
                              </label>
                            );
                          })}
                        </div>

                        <div className="mt-4 rounded-xl border border-indigo-100 bg-white/70 px-4 py-3 text-sm text-indigo-900">
                          <strong>Super Administrador:</strong> o acesso administrativo ao control plane permanece
                          disponível para diagnóstico, ajuste desta lista e reativação da mantenedora.
                        </div>

                        <div className="mt-4 flex justify-end">
                          <Button type="button" onClick={() => saveRoles(tenantId)} disabled={busy}>
                            {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                            Salvar acessos excepcionais
                          </Button>
                        </div>
                      </section>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          );
        })
      )}
    </section>
  );
}
