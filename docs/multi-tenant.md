# 🏢 Multi-Tenancy (Mantenedoras) — Guia para Agentes

> **Atualizado: 2026-02.** Este documento descreve o escopo multi-tenant do SIGESC e os
> padrões que **todo novo código** deve seguir.

## Modelo

Cada **Mantenedora** é um tenant isolado:
- Uma coleção `mantenedoras` com `id`, `nome`, `cnpj`, `municipio`, `estado`, `logotipo_url`, `ativo`.
- Todos os documentos de domínio carregam `mantenedora_id`.
- Migração inicial automática (ver `server.py` startup) cria a **Mantenedora Principal** e
  marca todos os documentos legados com seu `id`.

## Papéis

| Papel | Escopo |
|-------|--------|
| `super_admin` | Enxerga e administra **tudo**. Pode criar mantenedoras, designar gerentes, alternar de contexto. |
| `gerente` | Admin **restrito** à sua mantenedora. |
| `admin`, `secretario`, `diretor`, etc. | Restritos à mantenedora do próprio `user.mantenedora_id`. |

Token JWT agora carrega `mantenedora_id` — basta usar `auth_middleware.get_current_user()`.

## Helpers (backend/tenant_scope.py)

```python
from tenant_scope import (
    is_super_admin,          # bool
    get_mantenedora_scope,   # mantenedora_id ativa (None = cross-tenant)
    apply_tenant_filter,     # injeta filtro no query
    assert_same_tenant,      # 403 se doc de outro tenant
)
```

### Padrão obrigatório em novos endpoints

```python
@router.get("/items")
async def list_items(request: Request):
    user = await AuthMiddleware.get_current_user(request)
    q = apply_tenant_filter({"status": "active"}, user, request)
    return await db.items.find(q, {"_id": 0}).to_list(500)

@router.post("/items")
async def create_item(body: ItemCreate, request: Request):
    user = await AuthMiddleware.get_current_user(request)
    payload = body.model_dump()
    # **persiste** o tenant no próprio documento
    mid = get_mantenedora_scope(user, request) or get_user_mantenedora_id(user)
    payload["mantenedora_id"] = mid
    await db.items.insert_one(payload)

@router.put("/items/{item_id}")
async def update_item(item_id: str, body: ItemUpdate, request: Request):
    user = await AuthMiddleware.get_current_user(request)
    doc = await db.items.find_one({"id": item_id})
    assert_same_tenant(doc, user, request)   # 403 se for de outra mantenedora
    ...
```

## Cross-tenant para super_admin

- Pode atuar como uma mantenedora específica enviando header `X-Mantenedora-Id: <uuid>`
  ou query string `?mantenedora_id=<uuid>`.
- Sem esses parâmetros, enxerga tudo (nenhum filtro).

## Índices

`server.py::create_indexes()` já criou o índice `mantenedora_id` nas principais coleções.
Ao criar nova coleção com tenant, **adicione também o índice lá**.

## Frontend

- Página `pages/Mantenedoras.jsx` — CRUD + designação de gerente. Rota `/admin/mantenedoras`.
- Protegida por `ProtectedRoute allowedRoles={['super_admin']}`.
- Futuro: seletor de mantenedora no topo para super_admin alternar contexto (incluir o
  header `X-Mantenedora-Id` nas requests do axios).

## Status da implementação

- [x] Modelo + coleção `mantenedoras`
- [x] Migração automática dos dados legados
- [x] Papel `super_admin` + promoção automática do primeiro admin
- [x] Papel `gerente` + endpoint de designação
- [x] CRUD frontend
- [x] JWT carrega `mantenedora_id`
- [x] Helper `tenant_scope.py`
- [ ] **Aplicar scoping em cada router de domínio** (schools, staff, students, classes,
      courses, enrollments, grades, learning_objects, etc.) — **pendente**.
- [ ] Seletor de contexto de mantenedora no header do frontend.
- [ ] Cache de PDFs por tenant (hoje `pdf_cache.py` é global).

Atenção: sem o scoping nos routers de domínio, **dados ainda não estão isolados entre
tenants**. A criação da 2ª mantenedora é possível mas ela compartilha dados com a 1ª
enquanto o scoping não for aplicado. Próxima sessão deve focar em aplicar
`apply_tenant_filter` em cada router.
