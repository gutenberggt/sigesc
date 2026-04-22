/**
 * TenantSyncBoundary — envolve um subtree da aplicação e força
 * desmontagem/remontagem completa quando o tenant ativo muda.
 *
 * Funciona escutando o evento custom `tenant-changed` (disparado pelo
 * TenantSwitcher e pelo fluxo de editar mantenedora). Ao receber o evento,
 * incrementa um contador interno que serve de `key` para o children — o
 * React então desmonta e remonta tudo, refazendo todas as chamadas de API.
 *
 * Vantagem sobre `window.location.reload()`: mantém sessão do usuário,
 * posição no histórico de navegação e evita o flash branco do reload.
 */
import { useEffect, useState } from 'react';

export const TenantSyncBoundary = ({ children }) => {
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const bump = () => setVersion((v) => v + 1);
    window.addEventListener('tenant-changed', bump);
    return () => window.removeEventListener('tenant-changed', bump);
  }, []);

  // key força React a remontar toda a árvore de filhos quando version muda
  return (
    <div key={version} data-testid="tenant-sync-boundary">
      {children}
    </div>
  );
};

export default TenantSyncBoundary;
