# 🔎 Auditoria do Modo Offline — SIGESC (Jun/2026)

Auditoria baseada em **leitura de código** (evidências com arquivo:linha). Cobre Service Worker,
IndexedDB (Dexie), caches, fila de sincronização, endpoints de sync e o critério de aceite do professor.

---

## Etapa 1 — Inventário Offline (mapa real)

| Funcionalidade | Offline? | Evidência |
|---|---|---|
| Login (UI) | 🟡 Parcial | App shell cacheado (`sw.js` precacheAppShell); sessão restaurada de cache (`AuthContext.js:305-314`). Autenticação nova exige rede salvo credencial em cache. |
| Sessão (reabrir offline) | 🟢 Sim | `AuthContext.js:290-321` restaura usuário do localStorage offline. |
| Frequência (Anos Iniciais/diário) | 🟡 Parcial | Salva local + fila (`Attendance.js:683-707`). Mas sync grava cru (ver P0-2). |
| Frequência (Anos Finais / multi-aula) | 🔴 **Não** | `Attendance.js:604-634` — só salva `if (isOnline)`. Sem caminho offline. |
| Notas (Grades) | 🟡 Parcial | Salva local + fila (`Grades.js:557-585`). Sync grava cru (P2-8). |
| Conteúdo / Diário | 🔴 **Não** | Nenhuma página de conteúdo toca IndexedDB (grep: só Attendance/Grades/StudentsComplete). |
| Observações | 🔴 Não | Idem (parte do conteúdo/diário). |
| AEE / Bolsa Família / PMPI | 🔴 Não | Sem hooks/IndexedDB. |
| Relatórios / PDFs | 🔴 Não | Geração server-side (reportlab). |
| Dashboard / Calendário / Horário | 🔴 Não | Network-first (cache de leitura via SW só se já visitado). |
| Matrículas | 🔴 Não | `students` CRUD offline existe no schema, mas sem fluxo de UI conectado. |
| Dados de referência (alunos/turmas/componentes) | 🟡 Parcial | `useOfflineSync.syncAll` existe, **mas só dispara por clique manual** (P1-5). |

---

## Etapa 2 — Service Worker  (`frontend/public/sw.js`, v2.11.0)

- ✅ Registrado: `OfflineContext.jsx:236` `navigator.serviceWorker.register('/sw.js')`.
- ✅ `install` pré-cacheia app shell + assets; `activate` limpa caches antigos e faz `clients.claim()`.
- ✅ Auto-reload em `controllerchange` (`OfflineContext.jsx:229-234`) evita bundle velho pós-deploy.
- ✅ Background Sync com CSRF derivado do JWT (`sw.js:448-501`) — corrige 403 silencioso.
- ⚠️ Background Sync (`sync` event) só existe em Chromium. No iOS Safari não dispara; recai no
  handler `online` (`OfflineContext.jsx:183-199` → `triggerSync`). Funciona em foreground.

## Etapa 3 — Caches

`CACHE_NAME = 'sigesc-cache-v13'`. Estratégias (`sw.js:248-271`):
- Navegação HTML → **Network-first** + fallback app shell (login offline). ✅
- `/api/(schools|classes|courses|students|mantenedora)` → **Network-first** (cacheável).
- `/api/(attendance|grades|classes/{id}/details|cancelled-enrollments)` → **Network-only** (`NEVER_CACHE_API`) → 503 JSON offline (correto: evita roster fantasma).
- `*.js|*.css` → Network-first (código fresco). Imagens/fontes → Cache-first.

## Etapa 4 — IndexedDB  (`frontend/src/db/database.js`, Dexie v3, `SigescOfflineDB`)

Stores: `grades, attendance, students, classes, courses, schools, syncQueue, syncMeta`.
- ✅ Reset automático em `VersionError` (`database.js:62-84`).
- Salvo localmente: notas, frequência, alunos (CRUD), referência (turmas/componentes/escolas), fila e metadados.

## Etapa 5 — Sincronização

- Fila: `syncQueue` (Dexie). Criada por `addToSyncQueue` (`database.js:124-145`) que também registra Background Sync.
- Consumida por: (a) `syncService.processQueue` (foreground, `online` event) e (b) SW `syncAllPendingData` (background) → ambos `POST /api/sync/push`.
- Apagada: item removido em sucesso; em falha vira `pending` (retry) e após 3 tentativas → `failed`.
- ⚠️ `syncService.pullData` (`/api/sync/pull`) **nunca é chamado** no app → arquitetura de delta-pull é **código morto** (P1-6).

---

## Etapas 6-9 — Achados classificados (com evidência)

### 🔴 P0 — Perda / corrupção de dados

**P0-1 · Anos Finais não grava frequência offline.**
`Attendance.js:604-634`: no ramo `isMultiAula`, `attendanceAPI.save(payload)` só executa dentro de
`if (isOnline)`. Offline → `savedCount` fica 0 → mensagem "Registre a frequência de pelo menos um aluno".
→ Professor de Anos Finais/EJA Final **não consegue** lançar frequência offline. Dado perdido.

**P0-2 · Sync de frequência grava documento CRU → duplicatas e dado inconsistente.**
`sync.py:321-359` (`process_sync_operation`, create) faz `db.attendance.insert_one(clean_data)` direto,
**sem** passar pelo endpoint canônico `POST /api/attendance` (`attendance.py:455-715`). Consequências:
- Não faz upsert por `{class_id, date, course_id, aula_numero}` → **cria duplicata** se já existir registro.
- Não define `version`, `attendance_type`, `aula_numero` corretos; ignora Academic Event Lock, dependency e optimistic locking.
- O diário/relatórios podem mostrar frequência duplicada/divergente após a sincronização.

**P0-3 · UPDATE offline de frequência existente falha ao sincronizar.**
`Attendance.js:699`: `recordId = existingLocal.id || \`temp_${Date.now()}\``. O doc cacheado vem da *view*
`attendanceAPI.getByClass` (não o doc cru), podendo não ter `id` → vira `temp_...`. No servidor, update por
`{id: temp_...}` → `matched_count==0` → "Registro não encontrado" → marcado `failed`. Edição offline de
frequência já existente pode **nunca** sincronizar.

### 🟠 P1 — Impossível trabalhar offline

**P1-4 · Conteúdo/Diário/Observações sem suporte offline.** Critério de aceite exige "Registrar conteúdo"
offline; nenhuma página de conteúdo usa IndexedDB.

**P1-5 · Sem pré-cache automático de alunos/turmas.** `syncAll`/`syncClass` (`OfflineManagementPanel.jsx:70,80`)
só por clique manual. Abrir turma/data nova offline sem ter sincronizado antes → `db.students` vazio →
"Nenhum dado disponível offline" (`Attendance.js:490-492`). Quebra o passo "abrir turma offline".

**P1-6 · `/api/sync/pull` é código morto** (`syncService.js:159` nunca chamado).

### 🟡 P2 — UX / robustez

- **P2-7** Grades: mesmo padrão de `recordId` frágil (`Grades.js:578`) → update vira temp → risco de falha silenciosa.
- **P2-8** Sync de notas grava doc cru em `db.grades` (`sync.py`), divergindo da lógica canônica de notas.
- **P2-9** Itens `failed` (após 3 retries) ficam no painel sem alerta proeminente; risco de o professor não perceber.

---

## Critério de Aceite (professor) — status atual

1. Entrar online ✅ · 2. Abrir turma ✅ (online) · 3. Ficar sem internet ✅ ·
4. Registrar frequência 🟡 (Anos Iniciais ok / **Anos Finais ❌ P0-1**) · 5. Registrar conteúdo ❌ (P1-4) ·
6. Fechar navegador ✅ · 7. Reabrir sem internet ✅ (sessão) / 🟡 (dados só se pré-cacheados, P1-5) ·
8. Continuar trabalhando 🟡 · 9. Reconectar ✅ · 10. Sincronizar sem perder dados ❌ (**P0-2/P0-3**).

**Veredito:** o modo offline **NÃO pode ser considerado concluído** — bloqueado por P0-1, P0-2, P0-3 e P1-4/P1-5.

---

## ✅ Pontos saudáveis
- SW robusto (login offline via shell, anti-bundle-velho, CSRF no background sync).
- Isolamento multi-tenant aplicado no `/api/sync/push|pull` (`sync.py`) e filtragem de campos sensíveis no pull.
- Restauração de sessão offline funcional.
- `attendance/grades` corretamente em Network-only no SW (sem roster fantasma).
