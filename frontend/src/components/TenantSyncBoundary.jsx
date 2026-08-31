/**
 * TenantSyncBoundary — remonta o subtree quando o tenant ativo muda e, na MT-1,
 * bloqueia páginas operacionais do super_admin enquanto não houver mantenedora
 * selecionada.
 *
 * CONTROL PLANE explícito continua acessível sem tenant operacional:
 * - /admin/mantenedoras
 * - /admin/tenant
 */
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Building2, ShieldAlert } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { getActiveTenantId } from '@/services/api';

const CONTROL_PLANE_PATHS = ['/admin/mantenedoras', '/admin/tenant'];

const isControlPlanePath = (pathname) => (
  CONTROL_PLANE_PATHS.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  )
);

export const TenantSyncBoundary = ({ children }) => {
  const { user } = useAuth();
  const location = useLocation();
  const [version, setVersion] = useState(0);
  const [activeTenantId, setActiveTenantId] = useState(getActiveTenantId() || '');

  useEffect(() => {
    const syncTenant = () => {
      setActiveTenantId(getActiveTenantId() || '');
      setVersion((v) => v + 1);
    };
    const syncStorage = (event) => {
      if (!event.key || event.key === 'activeMantenedoraId') {
        syncTenant();
      }
    };

    window.addEventListener('tenant-changed', syncTenant);
    window.addEventListener('storage', syncStorage);
    return () => {
      window.removeEventListener('tenant-changed', syncTenant);
      window.removeEventListener('storage', syncStorage);
    };
  }, []);

  const needsTenantSelection = (
    user?.role === 'super_admin'
    && !activeTenantId
    && !isControlPlanePath(location.pathname)
  );

  if (needsTenantSelection) {
    return (
      <div
        className="max-w-2xl mx-auto mt-10 bg-amber-50 border border-amber-200 rounded-xl p-6 text-amber-900"
        data-testid="tenant-selection-required"
      >
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-white border border-amber-200">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <h2 className="font-semibold text-lg">Selecione uma mantenedora</h2>
            <p className="text-sm mt-1 leading-relaxed">
              O Super Administrador pode acessar qualquer mantenedora, mas os
              módulos institucionais operam uma mantenedora por vez. Use o
              seletor acima para definir o contexto operacional.
            </p>
            <p className="text-xs mt-3 flex items-center gap-1.5 text-amber-700">
              <Building2 className="w-3.5 h-3.5" />
              Nenhuma consulta institucional foi iniciada sem tenant ativo.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // key força React a desmontar/remontar toda a árvore quando o tenant muda.
  return (
    <div key={`${version}:${activeTenantId}`} data-testid="tenant-sync-boundary">
      {children}
    </div>
  );
};

export default TenantSyncBoundary;
