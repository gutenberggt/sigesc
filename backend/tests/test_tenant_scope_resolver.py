"""
Testes — `tenant_scope.resolve_active_mantenedora` (Fev/2026).

Fonte ÚNICA de resolução da mantenedora ativa. Cobre:
- Resolução por `user.mantenedora_id`.
- Resolução via header `X-Mantenedora-Id` (super_admin).
- Fallback para primeira mantenedora cadastrada.
- `fallback_to_first=False` → retorna None se não há scope direto.
- Projeção exclui `_id`.
"""
from __future__ import annotations

import os
import uuid
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tenant_scope import resolve_active_mantenedora  # noqa: E402


class _FakeRequest:
    def __init__(self, headers=None, query=None):
        self.headers = headers or {}
        self.query_params = query or {}


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    yield db
    client.close()


@pytest_asyncio.fixture
async def seeded(db):
    suf = uuid.uuid4().hex[:8]
    a_id = f"mant_a_{suf}"
    b_id = f"mant_b_{suf}"
    await db.mantenedoras.insert_many([
        {"id": a_id, "nome": "Mantenedora A", "aprovacao_com_dependencia": True},
        {"id": b_id, "nome": "Mantenedora B", "aprovacao_com_dependencia": False},
    ])
    yield {"a": a_id, "b": b_id}
    await db.mantenedoras.delete_many({"id": {"$in": [a_id, b_id]}})


@pytest.mark.asyncio
async def test_resolves_by_user_mantenedora_id(db, seeded):
    user = {"role": "admin", "mantenedora_id": seeded["a"]}
    doc = await resolve_active_mantenedora(db, user, None)
    assert doc is not None
    assert doc["id"] == seeded["a"]
    assert doc["aprovacao_com_dependencia"] is True
    assert "_id" not in doc


@pytest.mark.asyncio
async def test_super_admin_with_header_resolves_to_scoped_tenant(db, seeded):
    user = {"role": "super_admin"}
    req = _FakeRequest(headers={"X-Mantenedora-Id": seeded["b"]})
    doc = await resolve_active_mantenedora(db, user, req)
    assert doc is not None
    assert doc["id"] == seeded["b"]


@pytest.mark.asyncio
async def test_super_admin_without_scope_falls_back_to_first(db, seeded):
    user = {"role": "super_admin"}
    doc = await resolve_active_mantenedora(db, user, None, fallback_to_first=True)
    # Em ambiente com outras mantenedoras, retorna a primeira do banco —
    # contrato é "alguma mantenedora válida com fallback".
    assert doc is not None
    assert doc.get("id")


@pytest.mark.asyncio
async def test_super_admin_without_scope_no_fallback_returns_none(db, seeded):
    user = {"role": "super_admin"}
    doc = await resolve_active_mantenedora(db, user, None, fallback_to_first=False)
    assert doc is None


@pytest.mark.asyncio
async def test_user_with_invalid_mantenedora_id_falls_back_to_first(db, seeded):
    """Cenário do bug original: user.mantenedora_id aponta para tenant inexistente."""
    user = {"role": "admin", "mantenedora_id": "tenant_inexistente_xxx"}
    doc = await resolve_active_mantenedora(db, user, None, fallback_to_first=True)
    assert doc is not None
    assert doc.get("id")
