# AUDITORIA — Login Offline / Bootstrap Offline (read-only, sem correções)

> Escopo: fluxo de autenticação offline do SIGESC. Sintoma relatado: SW ativo,
> App Shell servido do cache, app entra na tela offline, mas a **sessão não é
> reconhecida**; logs mostram `/api/auth/refresh → 401`.
> **Nenhuma correção aplicada** — apenas mapeamento e classificação.

---

## 0. Fluxo completo de autenticação offline (mapa)

```
LOGIN ONLINE  (AuthContext.login → POST /api/auth/login)
   └─ sucesso → clearApplicationState() → grava no localStorage:
        accessToken, refreshToken, userData(JSON), lastLoginTime, sigesc_csrf_token
        ↓
PERSISTÊNCIA LOCAL  (localStorage; NÃO usa Dexie/IndexedDB/Cache API p/ sessão)
        ↓
DESCONEXÃO / REABERTURA DO APP
        ↓
BOOTSTRAP  (AuthContext.loadUser, roda no mount)
   ├─ se accessToken existe E navigator.onLine===true  → GET /api/auth/me
   │     ├─ 200 → setUser + regrava userData              ✅
   │     └─ ERRO (401 ou rede) → interceptor tenta refresh
   │            └─ POST /api/auth/refresh
   │                  ├─ 200 → segue
   │                  └─ 401/rede → null → reject → catch → logout()
   │                                                   └─ clearApplicationState()
   │                                                      → localStorage.clear()  ⛔ APAGA SESSÃO OFFLINE
   └─ se accessToken existe E navigator.onLine===false → getLocalUserData()
         ├─ válido → restaura sessão offline                ✅
         └─ null   → logout()
        ↓
VALIDAÇÃO DA SESSÃO OFFLINE (login() branch offline)
   └─ getLocalUserData() null (porque foi apagada acima)
         → "Sem conexão com a internet. Faça login online primeiro..."  ⛔
```

---

## P0.1 — Persistência da sessão

| Item | Detalhe |
|---|---|
| **Arquivo** | `frontend/src/contexts/AuthContext.js` |
| **Função de gravação** | `saveUserDataLocally(userData)` (linhas 74–81) |
| **Storage usado** | **localStorage** (sessão NÃO usa IndexedDB/Dexie/Cache API) |
| **Gravação ocorre após login?** | **Sim** — chamada em `login()` linha 349 (logo após sucesso online), em `/auth/me` ok (linha 298) e em `refresh` ok (linha 141). |

**Chaves gravadas (todas em localStorage):**
- `accessToken` (token JWT de acesso)
- `refreshToken`
- `userData` → JSON do objeto `user` do backend **+ email** (inclui `id`, `role`, `roles[]`, `mantenedora`/tenant, `school_ids`, etc. — o que o `/auth/login` retornar)
- `lastLoginTime` (timestamp; base do TTL de 7 dias)
- `lastActivityTime`
- `sigesc_csrf_token` (gravado por `setCsrfToken` em `services/api.js` — desde Jun/2026 em localStorage, não sessionStorage)
- `activeMantenedoraId` (super_admin com tenant ativo)

**Observação:** permissões NÃO são persistidas separadamente — derivam do `role` em `userData` no frontend (Dashboard/ProtectedRoute). Não há cache de `/auth/permissions` para offline.

---

## P0.2 — Mensagem "Faça login online primeiro"

| Item | Detalhe |
|---|---|
| **Local exato** | `AuthContext.js` **linha 396**, dentro de `login()`, branch `else` de `isOnline()` |
| **Condição que dispara** | `navigator.onLine === false` **E** `getLocalUserData()` === `null` |
| **"Sessão offline válida" =** | ter `userData` **e** `lastLoginTime` no localStorage, com idade `< 7 dias` (`MAX_OFFLINE_SESSION`), **e** o email digitado bater com `cachedUser.email` (linha 373) |
| **Verificações que falham no cenário** | `getLocalUserData()` retorna null porque `userData`/`lastLoginTime` **foram apagados do localStorage** (ver P0.3). Não é o TTL de 7 dias nem mismatch de email — é wipe de storage. |

`getLocalUserData()` (linhas 84–103) retorna null quando: (1) falta `userData` ou `lastLoginTime`, ou (2) `Date.now() - lastLoginTime > 7 dias`.

---

## P0.3 — Refresh offline → 401  **(CAUSA RAIZ)**

**Cadeia de falha completa:**

1. `loadUser` (linhas 290–321) roda no mount. Se há `accessToken` e `navigator.onLine === true` → `GET /api/auth/me`.
2. **`navigator.onLine` é não-confiável**: retorna `true` em qualquer Wi-Fi/LAN mesmo SEM internet real (`isOnline()` linha 50).
3. `/auth/me` falha:
   - **401** (access token expirado, chega ao servidor) → interceptor de resposta (linhas 193–226) chama `refreshAccessToken()`.
   - **erro de rede** (offline real, mas onLine=true) → cai direto no catch da linha 300.
4. `refreshAccessToken` (linhas 106–163) faz `POST /api/auth/refresh`. Se o refresh token expirou → **401** (os logs do usuário). Retorna `null` (só faz logout se `detail` contém 'revogado'/'revoked').
5. Interceptor: `newToken` null → **rejeita** o erro original.
6. `loadUser` catch (linha 300) → chama **`logout()`**.
7. `logout()` (linha 458) → **`clearApplicationState()`** (`services/api.js` linhas 70–73) → **`localStorage.clear()` + `sessionStorage.clear()`**.
8. ⛔ Resultado: `userData`, `lastLoginTime`, `accessToken`, `refreshToken`, `sigesc_csrf_token` — **TODOS apagados**.
9. Usuário fica offline e tenta logar → `getLocalUserData()` = null → **"Faça login online primeiro"**.

**Respostas objetivas:**
- Existe logout automático? **SIM** (loadUser catch → logout).
- Limpa tokens? **SIM**.
- Limpa cache de autenticação? **SIM — apaga TODO o localStorage/sessionStorage** (não seletivo).
- A sessão offline é invalidada indevidamente? **SIM** — um único 401/erro de rede no bootstrap destrói a base offline inteira.

```
Offline (ou flaky, onLine=true)
   ↓ GET /auth/me → 401/erro
   ↓ POST /auth/refresh → 401
   ↓ refreshAccessToken() = null
   ↓ interceptor reject → loadUser catch
   ↓ logout() → clearApplicationState() → localStorage.clear()
   ↓ SESSÃO OFFLINE DESTRUÍDA
```

---

## P0.4 — Super Admin × Offline

| Item | Detalhe |
|---|---|
| **Whitelist/blacklist de cargos p/ offline?** | **NÃO existe.** O branch offline do `login()` (linhas 361–399) só compara `cachedUser.email === email`. |
| **Lógica diferenciada por perfil no login offline?** | **NÃO.** Nenhum gate por role. |
| **ProtectedRoute diferencia online/offline?** | **NÃO** (`components/ProtectedRoute.js`) — só checa `user` + `allowedRoles`; super_admin tem bypass de admin. |

**Permitido logar offline?**
- Professor → **SIM**
- Diretor → **SIM**
- Gerente → **SIM**
- Administrador → **SIM**
- Super Admin → **SIM**

**Ressalva (não é bloqueio de login):** telas de super_admin/gerente dependem de `activeMantenedoraId` (header `X-Mantenedora-Id`) e dados de rede; offline esses dados não existem e `activeMantenedoraId` também é apagado no wipe (P0.3). Mas o **login** em si não é bloqueado por perfil.

---

## P0.5 — Bootstrap offline do Dashboard

**Arquivo:** `pages/Dashboard.js`, `loadData` (linhas 165–230) + `permissionOverridesAPI` (linha 124).
Todas as chamadas usam `.catch(() => [])` / `.catch(() => null)` → **nenhuma bloqueia a renderização**. Offline, o Dashboard renderiza com stats zeradas/vazias.

| Endpoint | Cache Offline (SW) | Fallback no código | Bloqueia Tela |
|---|---|---|---|
| `/api/schools` | networkFirst (cacheável se já visitado online) | `.catch(()=>[])` | **Não** |
| `/api/users` | networkFirst | `.catch(()=>[])` | **Não** |
| `/api/users/count` | networkFirst | `.catch(()=>null)` | **Não** |
| `/api/classes` | **NEVER_CACHE** (sempre rede, 503 offline) | `.catch(()=>[])` | **Não** |
| `/api/students` | networkFirst (em CACHE_PATTERNS.api) | `.catch(()=>[])` | **Não** |
| `/api/staff` | networkFirst | `.catch(()=>[])` | **Não** |
| `/api/profiles/me` | networkFirst | `.catch(()=>null)` | **Não** |
| `/api/mantenedora` | networkFirst (cacheável) | `.catch(()=>null)` | **Não** |
| `/api/analytics/overview` | networkFirst | `.catch(()=>null)` | **Não** |
| `/api/permission-overrides` | networkFirst | `.catch` silencioso | **Não** |

**Conclusão P0.5:** o Dashboard **NÃO é o bloqueador** do acesso offline. Os dados de domínio não têm cache em Dexie (aparecem zerados offline — cosmético), mas a tela carrega. O bloqueador real é o **wipe de sessão (P0.3)**, que ocorre ANTES de chegar ao Dashboard (no bootstrap do AuthContext).

---

## Classificação dos problemas

### 🔴 P0 — impedem o acesso offline
- **P0-A (raiz):** `loadUser` chama `logout() → clearApplicationState()` ao falhar `/auth/me` ou `/auth/refresh` no bootstrap, **apagando todos os dados de sessão offline**. Causa direta de "sessão não reconhecida" + "Faça login online primeiro".
- **P0-B:** dependência de `navigator.onLine` (true em LAN sem internet) faz o bootstrap tentar rede e cair no fluxo de wipe, mesmo havendo sessão offline válida.
- **P0-C:** `clearApplicationState()` usa `localStorage.clear()`/`sessionStorage.clear()` indiscriminado — destrói a base offline em QUALQUER logout/erro de auth, sem preservar `userData`/`lastLoginTime`.

### 🟠 P1
- **P1-A:** interceptor de resposta dispara refresh em 401 mesmo sem conectividade real; refresh 401 não distingue "expirado" de "revogado" → tratamento único.
- **P1-B:** `refreshAccessToken` não separa erro de rede vs 401; bootstrap não usa o guard de idle/online que o refresh proativo usa.
- **P1-C:** wipe apaga também `sigesc_csrf_token` e `activeMantenedoraId` → super_admin/gerente offline perdem CSRF e contexto de tenant.

### 🟡 P2
- **P2-A:** Dashboard mostra zeros offline (sem cache de domínio em Dexie) — UX/cosmético.
- **P2-B:** mensagem de erro genérica; não informa que a sessão foi perdida nem orienta reconexão.

---

## Pontos exatos que impedem o acesso offline observado
1. `AuthContext.js:300-303` — catch do `loadUser` chama `logout()` em qualquer erro de `/auth/me`.
2. `AuthContext.js:149-162` — `refreshAccessToken` retorna null em 401 (esperado), mas o caller (interceptor) propaga reject → logout.
3. `AuthContext.js:458` + `services/api.js:70-73` — `logout()` → `clearApplicationState()` → `localStorage.clear()` apaga a sessão offline.
4. `AuthContext.js:50 / 293` — `navigator.onLine` decide tentar rede; falso-positivo de conectividade dispara toda a cadeia.
5. `AuthContext.js:392-399` — sem dados (já apagados), `login()` offline emite a mensagem.

**Próximo passo:** definir plano de correção a partir desta classificação (aguardando sua direção).

---

## ✅ CORREÇÃO P0 APLICADA E VALIDADA (Jun/2026)

**Decisão do usuário:** implementar a+b+c; nenhuma `localStorage.clear()` em falhas de
auth no bootstrap; somente logout MANUAL invalida a sessão local.

**Mudanças (frontend, `contexts/AuthContext.js`):**
1. **`loadUser` reescrito (P0-A/B/C):** ao falhar `/auth/me`/refresh no bootstrap,
   classifica o erro:
   - `401` com `detail` contendo `revog/revoked` → **logout real** (ação deliberada do servidor).
   - Qualquer outro caso (erro de rede, timeout, backend fora, 401 por expiração SEM
     revogação) → **mantém a sessão offline cacheada** (`setUser(cachedUser)` +
     `isOfflineSession=true`). NUNCA chama `logout()`/`localStorage.clear()`.
   - Offline sem cache → apenas `setUser(null)` (mostra login, sem wipe).
2. **Recuperação automática offline→online:** `refreshAccessToken` em sucesso agora faz
   `setIsOfflineSession(false)`; o refresh proativo voltou a rodar mesmo em modo offline
   por falha transitória (só age quando `isOnline()`), promovendo a sessão de volta a
   online quando a conectividade real retorna.

**Revisão de todos os logouts automáticos:**
- `Layout.js`, `VaccineDashboard.js`, `AssocialDashboard.js` → logout MANUAL (botão). Mantidos.
- `AuthContext.js:157` (refreshAccessToken, só em revogação explícita) → mantido (correto).
- `AuthContext.js` bootstrap (antigas linhas 303/313) → **removidos os logout() automáticos**.
- `services/api.js` → só tem request interceptor; nenhum logout automático.

**Validação (Playwright, preview):**
- Cenário 1 (bug real): login online → bloquear `**/api/**` (backend fora, `onLine=true`)
  → reload → **sessão preservada** (userData intacto, permaneceu em /dashboard). PASS.
- Cenário 2: login online → `set_offline(True)` → reload → **sessão offline restaurada**
  (banner "Você está offline", "Modo Offline"). PASS.

**Pendente:** retomar investigação dos chunks/lazy loading (P0 original) — decisão em aberto:
pré-cachear TODOS os chunks no install do `sw.js` vs apenas entrypoints.
