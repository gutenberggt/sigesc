# SIGESC — Sistema Integrado de Gestão Escolar

Plataforma SaaS multi-tenant para Secretarias Municipais de Educação (SEMED) e
mantenedoras escolares. Engloba gestão de alunos, professores, AEE, currículo
multi-camadas, folha de pagamento docente, declarações oficiais (matrícula,
transferência, frequência, histórico), filas de revisão de conteúdo e relatórios.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│  React 19 (frontend)                                    │
│  ├─ shadcn/ui + lucide-react                            │
│  ├─ Vite/CRA, REACT_APP_BACKEND_URL                     │
│  └─ Roteamento por roles (super_admin, semed,           │
│     diretor, secretario, professor, etc.)               │
└──────────────────────┬──────────────────────────────────┘
                       │ /api/*
┌──────────────────────▼──────────────────────────────────┐
│  FastAPI (backend, porta 8001)                          │
│  ├─ routers/* (staff, hr, students, documents,         │
│  │   assignments, content_review, text_improvement,    │
│  │   schools, courses, classes, mantenedoras, ...)     │
│  ├─ utils/  (calculadores, normalizadores, locks)      │
│  ├─ pdf/    (geradores ReportLab)                      │
│  └─ scripts/ (CLI: migrações, auditorias, backfills)   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  MongoDB (motor async)                                  │
│  ├─ Tenant scope: mantenedora_id em todos os docs       │
│  ├─ Coleções principais: staff, students, enrollments,  │
│  │   teacher_assignments, school_assignments, classes,  │
│  │   courses, schools, mantenedoras, ...                │
│  └─ Coleções de fila: content_review_queue,             │
│      text_improvement_queue, enrollment_counters        │
└─────────────────────────────────────────────────────────┘
```

## Variáveis de ambiente

`/app/backend/.env`:

| Variável | Descrição | Exemplo |
|---|---|---|
| `MONGO_URL` | URI MongoDB | `mongodb://localhost:27017` |
| `DB_NAME` | Nome do banco | `sigesc` |
| `CORS_ORIGINS` | Whitelist de origens (vírgula) | `https://app.com,http://localhost:3000` |
| `JWT_SECRET_KEY` | Chave HMAC do JWT | random ≥ 32 chars |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | TTL do access token | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | TTL do refresh token | `7` |
| `EMERGENT_LLM_KEY` | Chave universal Emergent (Claude/Gemini/GPT) | `sk-emergent-...` |
| `RESEND_API_KEY` | API key Resend (e-mails) | `re_...` |
| `FTP_*` | Storage de imagens (legado) | — |

`/app/frontend/.env`:

| Variável | Descrição |
|---|---|
| `REACT_APP_BACKEND_URL` | URL pública do backend |

> Nunca commit valores reais. **CORS_ORIGINS=`*` é proibido** (incompatível com `allow_credentials=True`).

## Setup local

```bash
# Backend
cd backend
pip install -r requirements.txt
sudo supervisorctl restart backend

# Frontend
cd frontend
yarn install
sudo supervisorctl restart frontend
```

Hot-reload está habilitado pelo supervisor — restart só é necessário ao mudar
`.env` ou instalar dependências.

## Scripts CLI úteis

Executar de `/app/backend/`:

```bash
# Auditoria: comparar carga horária manual vs calculada
python scripts/audit_carga_horaria.py --save

# Normalização retroativa de nomes (CAPS → Sentence Case)
python scripts/normalize_names_back.py

# Higienização textual (formatação + ortografia conservadora)
python scripts/normalize_content.py
python scripts/text_improvement.py

# Tudo via Makefile (compatível com Coolify)
make audit-ch
make normalize-content
```

## Convenções

- **Rotas backend**: sempre prefixadas com `/api`.
- **Tenant scope**: toda query/insert deve usar `apply_tenant_filter` ou `resolve_tenant_id_for_create` de `tenant_scope.py`.
- **MongoDB**: jamais retorne `_id` em respostas — projete `{"_id": 0}`.
- **Carga horária**: derivada via `utils/carga_horaria_calculator.py` (fonte única). Não duplicar lógica.
- **Datas**: `datetime.now(timezone.utc)` (nunca `utcnow()`).
- **Emojis**: evitar em código/PDFs; usar `lucide-react` no frontend.

## Testes

```bash
cd /app/backend
python -m pytest tests/ -q --asyncio-mode=auto
```

Cobre: cálculos de CH, carga horária por lotação, normalizações textuais,
auth/permissions, geração de relatórios HR, multi-tenant scope.

## Documentação Técnica

- [`/app/memory/PRD.md`](memory/PRD.md) — Requisitos do produto e changelog
- [`/app/memory/test_credentials.md`](memory/test_credentials.md) — Credenciais de teste
- [`/app/docs/pdf-performance.md`](docs/pdf-performance.md) — Otimizações de PDFs

## Deploy

Produção: **Coolify** (containers). `Makefile` em `/app/backend/Makefile` orquestra
migrações via `make` no `WORKDIR=/app`.

## Licença

Proprietário — © Aprender Digital. Uso interno autorizado pelas mantenedoras
contratantes.
