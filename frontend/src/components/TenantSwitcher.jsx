/**
 * TenantSwitcher — seletor operacional de Mantenedora para super_admin.
 *
 * MT-1: o Super Administrador pode enxergar qualquer mantenedora, mas opera
 * exatamente uma por vez. Não existe mais a opção "Todas (cross-tenant)" no
 * plano operacional.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ChevronDown, Building2, Check, Settings, ShieldAlert } from 'lucide-react';
import { getActiveTenantId } from '@/services/api';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const isTenantActive = (tenant) => {
  if (!tenant) return false;
  if (tenant.ativo === false || tenant.ativa === false) return false;
  const status = String(tenant.status || '').trim().toLowerCase();
  return !['inactive', 'inativo', 'disabled', 'desativado', 'desativada'].includes(status);
};

export const TenantSwitcher = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [mantenedoras, setMantenedoras] = useState([]);
  const [activeId, setActiveId] = useState(getActiveTenantId() || '');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        // /api/mantenedoras é CONTROL PLANE explícito: super_admin pode listar
        // tenants mesmo antes de selecionar o contexto operacional.
        const { data } = await axios.get(`${API}/mantenedoras`);
        const items = Array.isArray(data) ? data : [];
        setMantenedoras(items);

        const stored = getActiveTenantId();
        if (stored) {
          const selected = items.find((m) => m.id === stored);
          if (!selected || !isTenantActive(selected)) {
            localStorage.removeItem('activeMantenedoraId');
            setActiveId('');
            window.dispatchEvent(new Event('tenant-changed'));
          }
        }
      } catch (_e) {
        setMantenedoras([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const selectTenant = (tenant) => {
    if (!tenant?.id || !isTenantActive(tenant)) return;
    localStorage.setItem('activeMantenedoraId', tenant.id);
    setActiveId(tenant.id);
    setOpen(false);
    // Componentes sob TenantSyncBoundary são remontados/refazem suas consultas.
    window.dispatchEvent(new Event('tenant-changed'));
  };

  const active = mantenedoras.find((m) => m.id === activeId && isTenantActive(m));
  const label = active ? active.nome : 'Selecione a mantenedora';

  return (
    <div className="relative" data-testid="tenant-switcher">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md border transition-colors text-xs font-medium max-w-[260px] ${
          active
            ? 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100'
            : 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100'
        }`}
        title="Selecionar mantenedora operacional"
        data-testid="tenant-switcher-button"
      >
        {active ? <Building2 size={14} /> : <ShieldAlert size={14} />}
        <span className="truncate">{label}</span>
        <ChevronDown size={14} />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded-md shadow-lg z-50 max-h-96 overflow-y-auto" data-testid="tenant-switcher-menu">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-gray-500 border-b border-gray-100">
            Contexto Operacional Multi-Tenant
          </div>
          {!activeId && (
            <div className="px-3 py-2 text-xs text-amber-700 bg-amber-50 border-b border-amber-100">
              Selecione uma mantenedora para acessar os módulos institucionais.
            </div>
          )}
          {loading && (
            <div className="px-3 py-2 text-xs text-gray-500">Carregando...</div>
          )}
          {!loading && mantenedoras.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-500">Nenhuma mantenedora cadastrada.</div>
          )}
          {mantenedoras.map((m) => {
            const enabled = isTenantActive(m);
            return (
              <button
                key={m.id}
                onClick={() => selectTenant(m)}
                disabled={!enabled}
                className={`w-full text-left px-3 py-2 flex items-center justify-between text-sm ${
                  !enabled
                    ? 'text-gray-400 cursor-not-allowed bg-gray-50'
                    : activeId === m.id
                      ? 'bg-indigo-50 text-indigo-700 font-medium hover:bg-indigo-100'
                      : 'hover:bg-gray-50'
                }`}
                data-testid={`tenant-option-${m.id}`}
              >
                <span className="truncate">
                  {m.nome}
                  {!enabled && <span className="ml-2 text-[10px] uppercase">(inativa)</span>}
                </span>
                {activeId === m.id && enabled && <Check size={14} className="shrink-0" />}
              </button>
            );
          })}

          {/* CONTROL PLANE: gestão global de mantenedoras continua permitida. */}
          <div className="border-t border-gray-100 mt-1">
            <button
              onClick={() => { setOpen(false); navigate('/admin/mantenedoras'); }}
              className="w-full text-left px-3 py-2 hover:bg-indigo-50 text-indigo-700 flex items-center gap-2 text-sm font-medium"
              data-testid="tenant-switcher-manage"
            >
              <Settings size={14} />
              <span>Gerenciar mantenedoras</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantSwitcher;
