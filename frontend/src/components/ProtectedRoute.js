import { cloneElement, isValidElement, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

export const ProtectedRoute = ({ children, allowedRoles = [] }) => {
  const { user, loading } = useAuth();
  const [tenantRevision, setTenantRevision] = useState(0);

  // MT-1: a troca de mantenedora precisa remontar a PÁGINA protegida inteira.
  // O TenantSyncBoundary vive dentro de Layout e, sozinho, remonta apenas o
  // subtree visual recebido por Layout. Estados/effects pertencentes à página
  // (ex.: os cards do Dashboard) ficam acima desse boundary e não eram refeitos,
  // preservando resultados vazios obtidos antes da seleção do tenant.
  useEffect(() => {
    const handleTenantChange = () => {
      setTenantRevision((revision) => revision + 1);
    };

    window.addEventListener('tenant-changed', handleTenantChange);
    return () => window.removeEventListener('tenant-changed', handleTenantChange);
  }, []);

  if (loading) {
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

  // Trocar a key desmonta/remonta o elemento de página sem hard reload do browser.
  // Assim todos os useEffect([]) da rota executam novamente já com
  // X-Mantenedora-Id atualizado pelo TenantSwitcher.
  if (isValidElement(children)) {
    return cloneElement(children, { key: `tenant-${tenantRevision}` });
  }

  return children;
};
