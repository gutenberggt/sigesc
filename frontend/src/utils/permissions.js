/**
 * Helpers centralizados de permissão por role.
 *
 * Regra do produto: `super_admin` tem acesso total a todas as funcionalidades.
 * Qualquer checagem AFIRMATIVA ("o usuário pode X?") deve usar estes helpers
 * para evitar regressões onde super_admin é esquecido da lista.
 *
 * NÃO use estes helpers para checagens NEGATIVAS do tipo
 * "esconder para semed" (`!SEMED_ROLES.includes(role)`). Nesse caso, mantenha
 * a checagem negativa original — super_admin já não está na lista negada.
 */

const SUPER_ADMIN = 'super_admin';

/**
 * Retorna true se o usuário tem qualquer um dos roles informados,
 * OU se é super_admin (acesso universal).
 *
 * @example
 *   if (hasRole(user, ['admin', 'secretario'])) { ... }
 *   const canEdit = hasRole(user, 'admin');  // string também aceita
 */
export function hasRole(user, roles) {
  const role = user?.role;
  if (!role) return false;
  if (role === SUPER_ADMIN) return true;
  const list = Array.isArray(roles) ? roles : [roles];
  return list.includes(role);
}

/** Alias expressivo — semanticamente idêntico a hasRole. */
export const hasAnyRole = hasRole;

/**
 * Retorna true se o usuário é super_admin. Útil para atalhos bem específicos.
 */
export function isSuperAdmin(user) {
  return user?.role === SUPER_ADMIN;
}
