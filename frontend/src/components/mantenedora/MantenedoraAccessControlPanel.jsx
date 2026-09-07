import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Loader2,
  LockKeyhole,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import { apiFetch, getActiveTenantId } from '@/services/api';

const API_BASE = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ACCESS_CONTROL_API = `${API_BASE}/mantenedora/access-control`;
const MAINTENANCE_CONTROL_API = `${API_BASE}/mantenedora/maintenance-control`;

const ROLE_PRIORITY = new Map([
  ['diretor', 0],
  ['secretario', 1],
  ['professor', 2],
  ['coordenador', 3],
]);

const PREFERRED_ROLE_LABELS = {
  diretor: 'Diretor',
  secretario: 'Secretário Escolar',
  professor: 'Professor',
  coordenador: 'Coordenador',
};

const roleLabel = (item) => (
  PREFERRED_ROLE_LABELS[item?.value] || item?.label || item?.value || ''
);

const detailMessage = (detail, fallback) => {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object' && detail.message) return detail.message;
  return fallback;
};

const blockerNames = (users = []) => (
  users.map((item) => item?.full_name || item?.email || 'Usuário').filter(Boolean)
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

const assertCurrentTenantResponse = (data, tenantId) => {
  if (!data?.id || String(data.id) !== String(tenantId)) {
    const error = new Error('O servidor retornou um contexto de mantenedora divergente.');
    error.detail = {
      code: 'TENANT_CONTEXT_MISMATCH',
      message: 'O controle administrativo foi bloqueado por divergência de mantenedora.',
    };
    throw error;
  }
  return data;
};

export default function MantenedoraAccessControlPanel() {
  const { user } = useAuth();
  const { mantenedora, refreshAccessStatus, refreshMantenedora } = useMantenedora();
  const [control, setControl] = useState(null);
  const [maintenance, setMaintenance] = useState(null);
  const [roleDrafts, setRoleDrafts] = useState([]);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [maintenanceBusy, setMaintenanceBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const isSuperAdmin = user?.role === 'super_admin' || (user?.roles || []).includes('super_admin');
  const tenantId = getActiveTenantId();

  const loadControl = useCallback(async () => {
    if (!isSuperAdmin) {
      setLoading(false);
      return;
    }

    setControl(null);
    setMaintenance(null);
    setRoleDrafts([]);
    setMessage(null);

    if (!tenantId) {
      setError('Selecione uma mantenedora para visualizar e alterar somente a condição dela.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [accessData, maintenanceData] = await Promise.all([
        requestJson(ACCESS_CONTROL_API),
        requestJson(MAINTENANCE_CONTROL_API),
      ]);
      const access = assertCurrentTenantResponse(accessData, tenantId);
      const maintenanceControl = assertCurrentTenantResponse(maintenanceData, tenantId);
      setControl(access);
      setMaintenance(maintenanceControl);
      setRoleDrafts(access.allowed_roles || []);
    } catch (requestError) {
      setControl(null);
      setMaintenance(null);
      setRoleDrafts([]);
      setError(detailMessage(
        requestError.detail,
        'Não foi possível carregar os controles desta mantenedora.',
      ));
    } finally {
      setLoading(false);
    }
  }, [isSuperAdmin, tenantId]);

  useEffect(() => {
    loadControl();
  }, [loadControl]);

  const refreshContext = async () => {
    await Promise.allSettled([refreshAccessStatus(), refreshMantenedora()]);
  };

  const toggleAvailability = async () => {
    if (!control || !tenantId) return;

    const targetActive = !control.active;
    setBusy(true);
    setMessage(null);

    try {
      const data = assertCurrentTenantResponse(
        await requestJson(ACCESS_CONTROL_API, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ativo: targetActive }),
        }),
        tenantId,
      );
      setControl(data);
      setRoleDrafts(data.allowed_roles || []);
      setError(null);
      setMessage({
        type: 'success',
        text: targetActive
          ? 'Mantenedora ativada. A disponibilidade institucional foi restabelecida.'
          : 'Mantenedora desativada. Defina abaixo, se necessário, os acessos excepcionais.',
      });
      await refreshContext();
    } catch (requestError) {
      const detail = requestError.detail;
      if (detail?.code === 'TENANT_HAS_ACTIVE_SESSIONS') {
        const names = blockerNames(detail.users || []);
        const count = detail.count || names.length;
        setControl((current) => current ? ({
          ...current,
          online_blockers: detail.users || [],
          online_blocker_count: count,
        }) : current);
        setMessage({
          type: 'error',
          text: names.length
            ? `Não foi possível desativar: ${count} usuário(s) estão conectados — ${names.join(', ')}.`
            : `Não foi possível desativar: ${count} usuário(s) estão conectados.`,
        });
      } else {
        setMessage({
          type: 'error',
          text: detailMessage(detail, 'Não foi possível alterar a disponibilidade da mantenedora.'),
        });
      }
    } finally {
      setBusy(false);
    }
  };

  const toggleMaintenance = async () => {
    if (!maintenance || !tenantId) return;

    const targetMode = !maintenance.maintenance_mode;
    const connectedCount = maintenance.online_user_count || 0;

    if (targetMode && connectedCount > 0) {
      const confirmed = window.confirm(
        `Há ${connectedCount} usuário(s) conectado(s) nesta mantenedora. `
        + 'Ao ativar a manutenção, eles terão o acesso operacional interrompido e serão direcionados para a página de manutenção. Deseja continuar?'
      );
      if (!confirmed) return;
    }

    setMaintenanceBusy(true);
    setMessage(null);
    try {
      const data = assertCurrentTenantResponse(
        await requestJson(MAINTENANCE_CONTROL_API, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ maintenance_mode: targetMode }),
        }),
        tenantId,
      );
      setMaintenance(data);
      setError(null);
      setMessage({
        type: 'success',
        text: targetMode
          ? 'Modo de manutenção ativado. O Super Administrador permanece com acesso operacional completo.'
          : 'Modo de manutenção encerrado. O acesso normal foi restabelecido.',
      });
      await refreshContext();
    } catch (requestError) {
      setMessage({
        type: 'error',
        text: detailMessage(requestError.detail, 'Não foi possível alterar o modo de manutenção.'),
      });
    } finally {
      setMaintenanceBusy(false);
    }
  };

  const toggleRole = (role) => {
    setRoleDrafts((current) => (
      current.includes(role)
        ? current.filter((item) => item !== role)
        : [...current, role]
    ));
  };

  const saveRoles = async () => {
    if (!control || control.active || !tenantId) return;

    setBusy(true);
    setMessage(null);
    try {
      const data = assertCurrentTenantResponse(
        await requestJson(ACCESS_CONTROL_API, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ allowed_roles: roleDrafts }),
        }),
        tenantId,
      );
      setControl(data);
      setRoleDrafts(data.allowed_roles || []);
      setMessage({
        type: 'success',
        text: 'Acessos excepcionais salvos com sucesso.',
      });
      await refreshContext();
    } catch (requestError) {
      setMessage({
        type: 'error',
        text: detailMessage(requestError.detail, 'Não foi possível salvar os acessos excepcionais.'),
      });
    } finally {
      setBusy(false);
    }
  };

  const roleOptions = useMemo(() => (
    [...(control?.role_options || [])].sort((a, b) => {
      const aPriority = ROLE_PRIORITY.has(a?.value) ? ROLE_PRIORITY.get(a.value) : 100;
      const bPriority = ROLE_PRIORITY.has(b?.value) ? ROLE_PRIORITY.get(b.value) : 100;
      if (aPriority !== bPriority) return aPriority - bPriority;
      return roleLabel(a).localeCompare(roleLabel(b), 'pt-BR');
    })
  ), [control?.role_options]);

  if (!isSuperAdmin) return null;

  const active = Boolean(control?.active);
  const maintenanceMode = Boolean(maintenance?.maintenance_mode);
  const tenantName = control?.nome || mantenedora?.nome || mantenedora?.name || 'Mantenedora selecionada';
  const maintenanceDisabled = maintenanceBusy || busy || (!active && !maintenanceMode);

  return (
    <section className="space-y-4" data-testid="mantenedora-access-control-panel">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <LockKeyhole className="h-5 w-5 text-indigo-600" />
          Disponibilidade e Controle de Acesso
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Este painel mostra exclusivamente a mantenedora selecionada no contexto atual.
        </p>
      </div>

      {loading ? (
        <Card className="border-slate-200">
          <CardContent className="flex min-h-32 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Carregando controles...
          </CardContent>
        </Card>
      ) : error ? (
        <Card className="border-red-200">
          <CardContent className="p-4 text-sm text-red-800">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-none" />
              <div className="flex-1">
                <p>{error}</p>
                {tenantId && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-3 bg-white"
                    onClick={loadControl}
                    disabled={busy || maintenanceBusy}
                  >
                    Tentar novamente
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ) : control && maintenance ? (
        <Card className="border-slate-200" data-testid="mantenedora-access-card-current">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg">{tenantName}</CardTitle>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2" data-testid="mantenedora-control-cards-grid">
              <section className="flex min-h-32 flex-col justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                <div>
                  <h3 className="font-semibold text-slate-900">Disponibilidade</h3>
                  <p className="mt-1 text-sm text-slate-600">
                    {active
                      ? 'Acesso normal liberado para esta mantenedora.'
                      : 'Mantenedora desativada; os dados permanecem preservados.'}
                  </p>
                </div>

                <div className="flex items-center justify-end gap-3">
                  {busy && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
                  <span className={`text-sm font-semibold ${active ? 'text-emerald-700' : 'text-slate-700'}`}>
                    {active ? 'Ativa' : 'Desativada'}
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={active}
                    aria-label={active ? 'Desativar mantenedora' : 'Ativar mantenedora'}
                    data-testid="mantenedora-active-switch"
                    onClick={toggleAvailability}
                    disabled={busy || maintenanceBusy}
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
              </section>

              <section
                className={`flex min-h-32 flex-col justify-between gap-4 rounded-2xl border p-4 ${
                  maintenanceMode
                    ? 'border-amber-200 bg-amber-50/70'
                    : 'border-slate-200 bg-slate-50/60'
                }`}
                data-testid="mantenedora-maintenance-card"
              >
                <div>
                  <h3 className="flex items-center gap-2 font-semibold text-slate-900">
                    <Wrench className={`h-4 w-4 ${maintenanceMode ? 'text-amber-700' : 'text-slate-500'}`} />
                    Manutenção
                  </h3>
                  <p className="mt-1 text-sm text-slate-600">
                    {!active && !maintenanceMode
                      ? 'Ative a mantenedora antes de iniciar uma manutenção.'
                      : maintenanceMode
                      ? 'Acesso operacional restrito. O Super Administrador permanece com acesso completo.'
                      : 'Sistema operando normalmente para os usuários desta mantenedora.'}
                  </p>
                </div>

                <div className="flex items-center justify-end gap-3">
                  {maintenanceBusy && <Loader2 className="h-4 w-4 animate-spin text-slate-500" />}
                  <span className={`text-sm font-semibold ${maintenanceMode ? 'text-amber-800' : 'text-slate-700'}`}>
                    {maintenanceMode ? 'Em manutenção' : 'Operação normal'}
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={maintenanceMode}
                    aria-label={maintenanceMode ? 'Encerrar manutenção' : 'Ativar manutenção'}
                    data-testid="mantenedora-maintenance-switch"
                    onClick={toggleMaintenance}
                    disabled={maintenanceDisabled}
                    className={`relative inline-flex h-7 w-12 flex-none items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
                      maintenanceMode ? 'bg-amber-600' : 'bg-slate-300'
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                        maintenanceMode ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </section>
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
                data-testid="mantenedora-exceptional-access"
              >
                <div className="flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-5 w-5 flex-none text-indigo-600" />
                  <div>
                    <h3 className="font-semibold text-slate-900">
                      Acesso excepcional enquanto desativada
                    </h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      Assinale os perfis que poderão continuar entrando. A seleção não amplia as permissões normais do perfil.
                    </p>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {roleOptions.map((option) => {
                    const checked = roleDrafts.includes(option.value);
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
                          disabled={busy || maintenanceBusy}
                          className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="text-sm font-medium">{roleLabel(option)}</span>
                      </label>
                    );
                  })}
                </div>

                <div className="mt-4 flex justify-end">
                  <Button type="button" onClick={saveRoles} disabled={busy || maintenanceBusy}>
                    {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Salvar acessos excepcionais
                  </Button>
                </div>
              </section>
            )}
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}
