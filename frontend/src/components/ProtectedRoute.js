import { cloneElement, isValidElement, useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useMantenedora } from '@/contexts/MantenedoraContext';
import MantenedoraDesativada from '@/pages/MantenedoraDesativada';
import MantenedoraManutencao from '@/pages/MantenedoraManutencao';

const SUPER_ADMIN_INACTIVE_CONTROL_PATHS = new Set([
  '/admin/mantenedoras',
  '/admin/mantenedora',
]);

export const ProtectedRoute = ({ children, allowedRoles = [] }) => {
  const { user, loading } = useAuth();
  const { accessStatus, accessLoading, refreshAccessStatus } = useMantenedora();
  const location = useLocation();
  const [tenantRevision, setTenantRevision] = useState(0);

  useEffect(() => {
    const handleTenantChange = () => {
      setTenantRevision((revision) => revision + 1);
    };

    window.addEventListener('tenant-changed', handleTenantChange);
    return () => window.removeEventListener('tenant-changed', handleTenantChange);
  }, []);

  if (loading || (user && accessLoading)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Carregando...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const isSuperAdmin = user.role === 'super_admin' || (user.roles || []).includes('super_admin');
  const isInactiveTenant = (
    accessStatus?.access_allowed === false
    && accessStatus?.reason === 'TENANT_INACTIVE'
  );
  const isMaintenanceTenant = (
    accessStatus?.access_allowed === false
    && accessStatus?.reason === 'TENANT_MAINTENANCE'
  );
  const isSuperAdminControlPage = (
    isSuperAdmin
    && SUPER_ADMIN_INACTIVE_CONTROL_PATHS.has(location.pathname)
  );

  // Precedência: a suspensão institucional continua sendo a trava mais forte.
  // O super_admin só atravessa tenant DESATIVADO nas páginas administrativas
  // explicitamente allowlisted, conforme o backend/control plane.
  if (isInactiveTenant && !isSuperAdminControlPage) {
    return (
      <MantenedoraDesativada
        accessStatus={accessStatus}
        onRetry={refreshAccessStatus}
      />
    );
  }

  // Manutenção é diferente de inatividade: enquanto a mantenedora está ativa em
  // manutenção, usuários comuns veem a página própria; o super_admin permanece
  // com acesso operacional completo para executar a manutenção.
  if (isMaintenanceTenant && !isSuperAdmin) {
    return (
      <MantenedoraManutencao
        accessStatus={accessStatus}
        onRetry={refreshAccessStatus}
      />
    );
  }

  // super_admin tem TODOS os poderes de admin; admin_teste idem
  // gerente tem poderes de admin dentro da própria mantenedora
  let effectiveRole = user.role;
  if (effectiveRole === 'admin_teste') effectiveRole = 'admin';
  if (effectiveRole === 'super_admin' && !allowedRoles.includes('super_admin')) effectiveRole = 'admin';
  if (effectiveRole === 'gerente' && !allowedRoles.includes('gerente')) effectiveRole = 'admin';

  if (allowedRoles.length > 0 && !allowedRoles.includes(effectiveRole)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-red-600 mb-4">Acesso Negado</h1>
          <p className="text-gray-600">Você não tem permissão para acessar esta página.</p>
        </div>
      </div>
    );
  }

  if (isValidElement(children)) {
    return cloneElement(children, { key: `tenant-${tenantRevision}` });
  }

  return children;
};
