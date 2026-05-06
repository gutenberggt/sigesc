# SIGESC Backend — FastAPI

API multi-tenant para a plataforma SIGESC. Veja o [README raiz](../README.md)
para visão geral.

## Estrutura

```
backend/
├── server.py             # Entrypoint FastAPI: lifespan, CORS, registro de routers
├── models.py             # Pydantic models (refatoração para pacote em curso)
├── auth_middleware.py    # JWT + roles + brute-force lock
├── tenant_scope.py       # Multi-tenant filtering helpers
├── csrf_middleware.py    # CSRF guard nos POST/PUT/DELETE
├── routers/              # Rotas por domínio (/api/*)
├── utils/                # Calculadores, normalizadores, locks
│   └── carga_horaria_calculator.py   # Fonte única de CH derivada
├── pdf/                  # Geradores ReportLab (declarações, históricos, etc.)
├── scripts/              # CLI assíncronos (auditoria, migrações, backfills)
├── tests/                # pytest suite (modo asyncio=auto)
└── Makefile              # Orquestra scripts em produção (Coolify)
```

## Endpoints principais

| Domínio | Prefixo | Notas |
|---|---|---|
| Autenticação | `/api/auth/*` | login, refresh, logout, recover password |
| Servidores | `/api/staff/*` | inclui `GET /staff/{id}/carga-horaria` (CH derivada) |
| Lotações | `/api/school-assignments/*` | `carga_horaria_calculada` exposta |
| Alocações de docentes | `/api/teacher-assignments/*` | regulares + substituições |
| Folha de pagamento | `/api/hr/*` | usa `calcular_carga_por_lotacao` (modo `atual`) |
| Estudantes | `/api/students/*` | enrollment, transferências, AEE |
| Documentos | `/api/documents/*` | declarações + histórico (com backfill de matrícula) |
| Currículo | `/api/curriculum/*` | multi-camadas (nacional → mantenedora → escola) |
| Filas de revisão | `/api/admin/content-review/*`, `/api/admin/text-improvement/*` | normalização textual |

## Regras críticas

1. **Nunca** importe modelos com `*` para arquivos novos — a longo prazo isto
   está sendo migrado para `from models.staff import Staff`, `from models.students import Student`, etc.
2. **Nunca** retorne `_id` do MongoDB. Sempre projete `{"_id": 0, ...}`.
3. **Nunca** confie em CH manual — use `utils/carga_horaria_calculator.py`.
4. **Nunca** insira/atualize sem chamar `assert_same_tenant` (multi-tenant).
5. **Datetimes**: `datetime.now(timezone.utc)` (não `utcnow()`).

## Como rodar testes

```bash
cd /app/backend
python -m pytest tests/ -q --asyncio-mode=auto
# Ou um arquivo específico:
python -m pytest tests/test_carga_horaria_calculator.py -v --asyncio-mode=auto
```

## Como adicionar um router

```python
# routers/meu_dominio.py
from fastapi import APIRouter, Request
from auth_middleware import AuthMiddleware

def get_router():
    router = APIRouter(prefix="/meu-dominio", tags=["meu-dominio"])

    @router.get("")
    async def listar(request: Request):
        user = await AuthMiddleware.require_roles(['admin'])(request)
        return {"ok": True}

    return router
```

Em `server.py`:

```python
from routers.meu_dominio import get_router as get_meu_dominio_router
api_router.include_router(get_meu_dominio_router())
```

## Performance

Veja [`docs/pdf-performance.md`](../docs/pdf-performance.md). Resumo:
- Sem `find_one()` em loops — use `$in`.
- Queries independentes em `asyncio.gather`.
- Cache global para mantenedora/escola (`_doc_cache`).
- Notas em lote.

## Segurança

- **CORS**: whitelist explícita via `CORS_ORIGINS` (vírgula) e/ou regex via `CORS_ORIGIN_REGEX` (ex.: `https://.*\.aprenderdigital\.top`). Sem `*`. Origin `'*'` com `allow_credentials=True` é rejeitado pela RFC.
  - **Variáveis aceitas em produção (Coolify/.env)**:
    - `CORS_ORIGINS=https://sigesc.aprenderdigital.top` (uma ou mais, separadas por vírgula)
    - `CORS_ORIGIN_REGEX=https://.*\.aprenderdigital\.top` (opcional, p/ múltiplos subdomínios)
    - `APP_FRONTEND_URL=https://sigesc.aprenderdigital.top` (incluído automaticamente)
- **CSRF**: `CSRFMiddleware` ativa em mutações de cookie.
- **JWT**: HMAC HS256, segredo em `JWT_SECRET_KEY`.
- **Brute-force lock**: bloqueio de 15 min após 5 falhas (`brute_force_lock`).
- **Tenant scope**: enforcement em todas as rotas (`tenant_scope.py`).
