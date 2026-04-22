/**
 * TenantSwitcher — Seletor visual de Mantenedora para super_admin.
 *
 * Mostra um dropdown compacto no header (somente quando user.role === 'super_admin')
 * permitindo alternar o contexto de tenant ativo. A seleção é persistida em
 * localStorage como `activeMantenedoraId` e enviada automaticamente via
 * header `X-Mantenedora-Id` pelo interceptor do axios (services/api.js).
 *
 * "Todas" (sem seleção) faz o super_admin operar cross-tenant (None no backend).
 */
import { useEffect, useState } from 'react';
import axios from 'axios';
import { ChevronDown, Building2, Check } from 'lucide-react';
import { getActiveTenantId } from '@/services/api';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const TenantSwitcher = () => {
  const [open, setOpen] = useState(false);
  const [mantenedoras, setMantenedoras] = useState([]);
  const [activeId, setActiveId] = useState(getActiveTenantId() || '');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const { data } = await axios.get(`${API}/mantenedoras`);
        setMantenedoras(Array.isArray(data) ? data : []);
      } catch (_e) {
        setMantenedoras([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const selectTenant = (id) => {
    if (id) {
      localStorage.setItem('activeMantenedoraId', id);
    } else {
      localStorage.removeItem('activeMantenedoraId');
    }
    setActiveId(id || '');
    setOpen(false);
    // Recarrega a página para que todos os dados sejam re-buscados sob o novo contexto
    window.location.reload();
  };

  const active = mantenedoras.find((m) => m.id === activeId);
  const label = active ? active.nome : 'Todas as mantenedoras';

  return (
    <div className="relative" data-testid="tenant-switcher">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 transition-colors text-xs font-medium max-w-[240px]"
        title="Alternar mantenedora ativa (super_admin)"
        data-testid="tenant-switcher-button"
      >
        <Building2 size={14} />
        <span className="truncate">{label}</span>
        <ChevronDown size={14} />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-72 bg-white border border-gray-200 rounded-md shadow-lg z-50 max-h-96 overflow-y-auto" data-testid="tenant-switcher-menu">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-gray-500 border-b border-gray-100">
            Contexto Multi-Tenant
          </div>
          <button
            onClick={() => selectTenant('')}
            className={`w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center justify-between text-sm ${!activeId ? 'bg-indigo-50 text-indigo-700 font-medium' : ''}`}
            data-testid="tenant-option-all"
          >
            <span>Todas (cross-tenant)</span>
            {!activeId && <Check size={14} />}
          </button>
          {loading && (
            <div className="px-3 py-2 text-xs text-gray-500">Carregando...</div>
          )}
          {!loading && mantenedoras.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-500">Nenhuma mantenedora cadastrada.</div>
          )}
          {mantenedoras.map((m) => (
            <button
              key={m.id}
              onClick={() => selectTenant(m.id)}
              className={`w-full text-left px-3 py-2 hover:bg-gray-50 flex items-center justify-between text-sm ${activeId === m.id ? 'bg-indigo-50 text-indigo-700 font-medium' : ''}`}
              data-testid={`tenant-option-${m.id}`}
            >
              <span className="truncate">{m.nome}</span>
              {activeId === m.id && <Check size={14} className="shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default TenantSwitcher;
