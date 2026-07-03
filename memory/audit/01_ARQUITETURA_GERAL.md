# ENTREGA 01 — Arquitetura Geral

> Auditoria READ-ONLY · Jun/2026 · classificação: 🟢🟡🔴⚫

## 1. Visão geral da aplicação
O **SIGESC IA** é um **Sistema Integrado de Gestão Escolar multi-tenant (SaaS)**
para prefeituras/secretarias municipais de educação, com **isolamento de dados
por mantenedora** (Row-Level Security), operação **offline-first (PWA)** para
escolas rurais e uma camada crescente de **inteligência (risco pedagógico,
alertas, IA generativa)**.

Arquitetura de alto nível (monólito modular em 3 camadas):

```
┌──────────────────────── Navegador (PWA) ────────────────────────┐
│  React 19 SPA  ·  Service Worker (cache app-shell + chunks)      │
│  IndexedDB (Dexie) p/ rascunhos e filas offline                  │
└───────────────▲──────────────────────────────────────────────────┘
                │ HTTPS (JWT em cookie HttpOnly / Bearer / ?token)
                │ prefixo /api  →  Traefik/ingress
┌───────────────┴──────────────── Backend ─────────────────────────┐
│  FastAPI (uvicorn :8001)  ·  89 routers  ·  574 endpoints         │
│  Middlewares: CORS · rate-limit (slowapi) · tenant scope ·        │
│               active-session tracking · auth (JWT)                │
│  Services de domínio (~44)  ·  Motores de risco/alertas/IA        │
│  APScheduler (jobs: relatórios mensais, PMPI cron)                │
└───────────────▲──────────────────────────────────────────────────┘
                │ Motor async (Motor 3.3.1)
┌───────────────┴──────────────── Dados ───────────────────────────┐
│  MongoDB 7  ·  102 coleções  ·  ~190 índices                      │
└───────────────────────────────────────────────────────────────────┘
        ┌──────────────── Integrações externas ────────────────┐
        │ Emergent LLM / Anthropic Claude (texto) · Resend      │
        │ (e-mail) · FTP (armazenamento de arquivos/PDFs)       │
        └────────────────────────────────────────────────────────┘
```

## 2. Tecnologias utilizadas
### Backend 🟢
- **Python 3.11**, **FastAPI 0.110.1**, **uvicorn 0.25**.
- **MongoDB** via **Motor 3.3.1** (async) + **pymongo 4.5**.
- **Pydantic v2** (validação/serialização; padrão `field_validator`/`model_validator`).
- Auth: **PyJWT** + **bcrypt/passlib** + **python-jose**.
- PDFs: **reportlab**, **PyPDF2**, **pdfplumber** (extração/testes).
- Jobs: **APScheduler**. Rate limit: **slowapi**. HTTP client: **httpx**.
- E-mail: **resend**. QR/verificação: **qrcode**, **segno**.
- IA: **emergentintegrations** (Universal Key) / SDK **anthropic** direto.
- Dados/analytics: **pandas**, **numpy**.
- Qualidade: **pytest** (173 arquivos de teste), black, isort, flake8, mypy, ruff.

### Frontend 🟢
- **React 19**, **react-router-dom 7**, **react-scripts 5 (CRA)**.
- UI: **Radix UI** + **shadcn/ui** (46 componentes), **tailwindcss** (+ animate),
  **lucide-react** (ícones), **sonner** (toasts).
- Estado/dados: Context API (9 providers) + **axios**.
- Offline: **Dexie 4** (IndexedDB) + **dexie-react-hooks** + Service Worker.
- Gráficos: **recharts 3**. Formulários: **react-hook-form** + **zod**.
- Documentos client-side: **jspdf/jspdf-autotable**, **xlsx**, **file-saver**, **html2canvas**.

## 3. Estrutura de diretórios (resumo)
```
/app
├── backend/
│   ├── server.py            # bootstrap FastAPI, middlewares, registro de 89 routers
│   ├── models.py            # ~3000 linhas — modelos Pydantic (entidades do domínio)
│   ├── routers/             # 89 arquivos — endpoints por domínio
│   ├── services/            # ~44 — regras de negócio, motores de risco/IA, renderers
│   ├── lib/                 # utilitários internos (ex.: critical_mutation)
│   ├── core/                # infra compartilhada
│   ├── startup/             # indexes.py, multi_tenant.py, seeds.py
│   ├── pdf/                 # builders de PDF (notas, frequência, objetos, recibo...)
│   ├── scripts/             # migrações, backfills, harness de homologação
│   ├── seeds/               # dados iniciais
│   ├── tenant_scope.py      # Row-Level Security (apply_tenant_filter)
│   ├── tenant_audit.py      # eventos de segurança tenant
│   ├── auth_middleware.py   # AuthMiddleware (get_current_user, require_roles/permission)
│   └── tests/               # 173 arquivos de teste
├── frontend/
│   └── src/
│       ├── App.js           # 86 rotas (public/auth/admin/professor/aluno/verify)
│       ├── pages/           # 77 páginas
│       ├── components/      # 105 (ui/ = 46 shadcn) + session/, grades/, etc.
│       ├── hooks/           # 17 hooks (offline, permissões, sessão, formulários)
│       ├── contexts/        # 9 providers
│       ├── services/api.js  # 38 clients de API (axios)
│       ├── db/              # database.js (Dexie)
│       ├── features/        # feature-slices (ex.: dependency)
│       └── public/sw.js     # Service Worker (PWA)
├── docker-compose.coolify.yml   # stack de produção (Coolify v4 + Traefik)
├── docker-compose.yml           # stack local
├── Makefile                     # migrações + GATE de regressão
└── memory/                      # PRD, changelog, credenciais, ESTA auditoria
```

## 4. Fluxo de autenticação 🟢
1. `POST /api/auth/login` (e-mail+senha) → valida bcrypt → emite **access token**
   (JWT curto, claims: `sub`, `role`, `school_ids`, `mantenedora_id`, `csrf`,
   `iat`, `exp`, `type=access`) + **refresh token** (rotativo).
2. Access token entregue em **cookie HttpOnly `sigesc_access`** (padrão seguro G2)
   e também aceito via `Authorization: Bearer` (retrocompat) e `?token=` (para abrir PDFs).
3. `AuthMiddleware.get_current_user` lê o token (cookie → header → query), decodifica,
   valida `type=access`, checa **blacklist** (revogação por `jti` ou janela `revoke_all`),
   e devolve o contexto do usuário.
4. **Refresh** (`POST /api/auth/refresh`) preserva `mantenedora_id`/`role`/`school_ids`
   (correção P0 crítica de isolamento). Rotação de refresh token com revogação do jti antigo.
5. **Offline:** a sessão é preservada em `localStorage` (`userData`/`lastLoginTime`,
   TTL 30 dias). Falhas de rede/401 por expiração **não** apagam a sessão offline;
   somente logout MANUAL faz wipe (`clearApplicationState`).

## 5. Fluxo de autorização 🟢🟡
Camadas complementares (defense-in-depth):
- **RBAC** — `AuthMiddleware.require_roles([...])` por endpoint e `allowedRoles` por rota no frontend.
- **Matriz de permissões dinâmica** — `require_permission(db, menu_key, default_roles)`
  consulta `permission_overrides` (override por role/menu). Sem override → cai no RBAC padrão.
- **Row-Level Security multi-tenant** — `tenant_scope.apply_tenant_filter` injeta
  `mantenedora_id` em toda query; **fail-closed** (sem tenant → filtro `__INVALID_TENANT__`
  = zero dados). super_admin faz bypass controlado.
- **Escopo por escola** — `check_school_access`/`verify_school_access` limitam staff à(s)
  `school_ids`. Coordenador tem semântica de **somente leitura** em áreas configuradas.
- **Role efetivo por lotação** — `school_assignments` pode dar a um usuário um papel
  efetivo diferente do papel base (ex.: professor lotado como secretário).
- **Auditoria de segurança** — `tenant_audit`/`tenant_security_events` registram
  `missing_tenant`, `tenant_mismatch`, `cross_tenant_attempt`, `invalid_token`.

Detalhe completo em [12 — Permissões](12_PERMISSOES.md).

## 6. Fluxo de build 🟢
- **Frontend** (`frontend/Dockerfile`): multi-stage — `node:20-alpine` → `yarn install
  --frozen-lockfile` → `yarn build` (com `GENERATE_SOURCEMAP=false` e
  `NODE_OPTIONS=--max-old-space-size=2048` p/ evitar OOM) → serve estático via **nginx:alpine**.
  `REACT_APP_BACKEND_URL` injetado como build-arg (baked no bundle).
- **Backend** (`backend/Dockerfile`): `python:3.11-slim` → `pip install` (com extra-index
  do Emergent p/ `emergentintegrations`) → `uvicorn server:app :8001`.

## 7. Fluxo de deploy 🟢🟡
- Deploy via **"Save to Github" → Coolify** (pull do repositório).
- **Coolify v4 + Traefik** (`docker-compose.coolify.yml`): 3 serviços — `mongo:7`
  (volume persistente), `backend` (Traefik host `api.sigesc.aprenderdigital.top`,
  porta 8001, TLS Let's Encrypt), `frontend` (host `sigesc.aprenderdigital.top`,
  nginx :80). Rede `external` = `${COOLIFY_RESOURCE_UUID}` (mesma rede do proxy).
- **Env de produção** injeta: `MONGO_URL`, `DB_NAME`, `JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`,
  `SNAPSHOT_HMAC_SECRET`, `EMERGENT_LLM_KEY`, `CORS_ORIGINS`, cookies (`COOKIE_SECURE/SAMESITE`),
  `FTP_*`, `RESEND_*`, `APP_FRONTEND_URL`.
- **CORS:** o backend deriva o domínio do frontend a partir de `api.<dominio>` → `<dominio>`
  (fix de preflight de produção).
- **Gate de regressão** (`.github/workflows/transfer-regression.yml` + `make regression`):
  bloqueia merge/deploy em PR/push→main (smoke E2E + 27 testes de transferência, fail-fast).
  ⚠️ Precisa estar marcado como *Required status check* para ser efetivo.
- **Ambiente preview (Emergent)** difere do de produção: roda em modo dev (sem asset-manifest
  hasheado; CORS `*` via ingress) — por isso alguns comportamentos de PWA/CORS só se validam em produção.

## 8. Estrutura Docker / Coolify
Ver seção 6/7. Resumo: 2 Dockerfiles (multi-stage no front), 2 composes
(local vs Coolify), MongoDB como container com volume nomeado
`sigesc-mongo-data`, healthchecks em todos os serviços.

## 9. Dependências entre módulos (macro)
```
auth/tenant  ──►  (base de TODOS os módulos: contexto + RLS)
schools ──► classes ──► enrollments ◄── students ──► guardians
classes ──► teacher_class_assignments ──► grades / attendance / diary / content
courses/curriculum ──► classes (grade horária) ──► diary_snapshots ──► documents/PDF
attendance ──► bolsa_familia (frequência) · risk engines
grades + attendance + content ──► diary_dashboard · pme_anos_finais · monthly_reports
risk engines (academic/attendance/overall) ──► alerts ──► interventions ──► pmpi_engine ──► pmpi_ai (IA)
school_transfer / history_reconstruction ──► classes/students/enrollments/grades/attendance/content (motor canônico + rollback)
verifiable_docs/public_verify ◄── documents (QR/verificação pública)
```
**Acoplamento central:** `students`, `classes`, `enrollments`, `attendance`, `grades`
são o núcleo do qual quase tudo depende — mudanças nessas coleções têm alto raio de impacto.
