"""
Regressão — Papéis globais da SEMED têm visão total de escolas (Fev/2026).

Bug original: usuários `semed1` (Tutor) e `semed2` (Analista) com `school_ids=[]`
recebiam lista vazia em `GET /api/schools` porque NÃO estavam em `wide_roles`
de `routers/schools.py`. O frontend (`Users.js`) já declara `schools: 'view'`
para ambos; o backend precisava alinhar.

Cobre:
- check_school_access: semed1, semed2, semed3, ass_social, ass_social_2, agente_vacinas
  sempre retornam True (papéis globais da mantenedora).
- list_schools: semed1 e semed2 sem school_ids veem todas as escolas do tenant.
- coordenador (papel de escola) sem school_ids continua sem ver nada.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

from auth_middleware import AuthMiddleware

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break


@pytest.mark.parametrize("role", [
    "super_admin", "admin", "admin_teste", "gerente",
    "semed", "semed1", "semed2", "semed3",
    "ass_social", "ass_social_2", "agente_vacinas",
])
def test_check_school_access_global_tenant_roles_pass(role):
    user = {"role": role, "school_ids": []}
    assert AuthMiddleware.check_school_access(user, "any_school_id") is True


@pytest.mark.parametrize("role", [
    "coordenador", "secretario", "professor", "diretor", "aluno",
])
def test_check_school_access_school_scoped_roles_need_link(role):
    user = {"role": role, "school_ids": ["allowed_school"]}
    assert AuthMiddleware.check_school_access(user, "allowed_school") is True
    assert AuthMiddleware.check_school_access(user, "denied_school") is False


# ============================================================================
# E2E: list_schools com semed2 (Analista) sem school_ids vê todas
# ============================================================================
TENANT = "semed_schools_test_mant"


@pytest.fixture
def seeded_world():
    """Cria tenant + 2 escolas + usuário semed2 (Analista) global."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    suf = uuid.uuid4().hex[:8]
    user_id = f"semed2_{suf}"
    email = f"analista_{suf}@sigesctest.com"
    password = "Analista@2026"
    schools = [
        {"id": f"sch_a_{suf}", "name": f"Escola A {suf}", "mantenedora_id": TENANT},
        {"id": f"sch_b_{suf}", "name": f"Escola B {suf}", "mantenedora_id": TENANT},
    ]
    user_doc = {
        "id": user_id,
        "email": email,
        "password_hash": pwd_ctx.hash(password),
        "full_name": "ANALISTA TESTE",
        "role": "semed2",
        "school_ids": [],  # global da mantenedora
        "mantenedora_id": TENANT,
        "is_active": True,
    }

    async def _seed():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.users.insert_one(user_doc)
        await db.schools.insert_many(schools)
        await db.mantenedoras.update_one(
            {"id": TENANT},
            {"$setOnInsert": {"id": TENANT, "name": "TENANT TESTE SCHOOLS"}},
            upsert=True,
        )
        client.close()
        # Invalida cache de schools (chaveado por role+school_ids+tenant) — entre runs
        # pode haver colisão com mesmo tenant.
        try:
            from utils.cache import cache
            cache.invalidate('schools')
        except Exception:
            pass

    async def _cleanup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.users.delete_many({"id": user_id})
        await db.schools.delete_many({"id": {"$in": [s["id"] for s in schools]}})
        await db.mantenedoras.delete_many({"id": TENANT})
        client.close()

    asyncio.run(_seed())
    yield {"email": email, "password": password, "schools": schools, "tenant": TENANT}
    asyncio.run(_cleanup())


def test_e2e_analista_lists_all_schools_in_tenant(seeded_world):
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": seeded_world["email"], "password": seeded_world["password"]},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("access_token") or data.get("token")
    csrf = data.get("csrf_token") or r.headers.get("X-CSRF-Token")
    headers = {
        "Authorization": f"Bearer {token}" if token else "",
        "X-Mantenedora-Id": seeded_world["tenant"],
        "X-CSRF-Token": csrf or "",
    }
    r2 = s.get(f"{BASE_URL}/api/schools", headers=headers, timeout=30)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    ids = {s["id"] for s in body}
    expected_ids = {s["id"] for s in seeded_world["schools"]}
    assert expected_ids.issubset(ids), (
        f"Analista deveria ver {expected_ids}, mas veio {ids}"
    )
