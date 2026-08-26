// Sessões de impersonação são deliberadamente online-only e temporárias.
// O AuthContext canônico mantém cache offline por até 30 dias; este guard é
// instalado no bootstrap, antes do App, e impede que o usuário testado seja
// persistido em userData/lastLoginTime sem alterar o motor de autenticação.

const USER_DATA_KEY = 'userData';
const LAST_LOGIN_KEY = 'lastLoginTime';
const INSTALL_MARKER = '__SIGESC_IMPERSONATION_OFFLINE_GUARD__';
const BLOCK_MARKER = '__SIGESC_IMPERSONATION_OFFLINE_BLOCKED__';

export const installImpersonationOfflineGuard = () => {
  if (typeof window === 'undefined' || typeof Storage === 'undefined') return;
  if (window[INSTALL_MARKER]) return;

  const originalSetItem = Storage.prototype.setItem;
  const originalRemoveItem = Storage.prototype.removeItem;

  Storage.prototype.setItem = function guardedSetItem(key, value) {
    if (this === window.localStorage && key === USER_DATA_KEY) {
      let isImpersonation = false;
      try {
        const parsed = JSON.parse(value);
        isImpersonation = Boolean(parsed?.impersonation?.active);
      } catch (_) {
        isImpersonation = false;
      }

      window[BLOCK_MARKER] = isImpersonation;
      if (isImpersonation) {
        originalRemoveItem.call(this, USER_DATA_KEY);
        originalRemoveItem.call(this, LAST_LOGIN_KEY);
        return;
      }
    }

    if (
      this === window.localStorage
      && key === LAST_LOGIN_KEY
      && window[BLOCK_MARKER]
    ) {
      return;
    }

    return originalSetItem.call(this, key, value);
  };

  window[INSTALL_MARKER] = true;
};
