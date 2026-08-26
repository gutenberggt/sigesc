import { AuthProvider, useAuth } from './AuthContextLegacy';

// Sessões de impersonação são deliberadamente online-only e temporárias.
// O AuthContext legado mantém cache offline por até 30 dias; este guard impede
// que o usuário testado seja persistido nesse cache sem reescrever o motor de
// autenticação/offline já homologado.
const USER_DATA_KEY = 'userData';
const LAST_LOGIN_KEY = 'lastLoginTime';
const GUARD_MARKER = '__SIGESC_IMPERSONATION_STORAGE_GUARD__';
const BLOCK_MARKER = '__SIGESC_IMPERSONATION_OFFLINE_BLOCKED__';

const installImpersonationOfflineStorageGuard = () => {
  if (typeof window === 'undefined' || typeof Storage === 'undefined') return;
  if (window[GUARD_MARKER]) return;

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

  window[GUARD_MARKER] = true;
};

installImpersonationOfflineStorageGuard();

export { AuthProvider, useAuth };
