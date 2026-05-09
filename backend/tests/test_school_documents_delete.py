"""
E2E HTTP — DELETE /api/school-documents/{code} (Fev/2026).

Cobre:
- super_admin consegue excluir declaração existente.
- usuário não-super-admin recebe 403.
- código inexistente → 404.
- sem auth → 401/403.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password},
               timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    csrf = data.get("csrf_token") or r.headers.get("X-CSRF-Token")
    token = data.get("access_token") or data.get("token")
    s.headers.update({
        "X-Mantenedora-Id": TENANT,
        "X-CSRF-Token": csrf or "",
        "Content-Type": "application/json",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture
def super_admin_session():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def fixture_doc():
    """Cria diretamente no Mongo um school_documents_log + verifiable_documents
    com código previsível para o teste, e remove ao final."""
    # alfabeto seguro do verifiable_docs_service (sem 0/O/1/I/L)
    import secrets as _secrets
    _ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    code = f"SIGESC-{''.join(_secrets.choice(_ALPHA) for _ in range(4))}-{''.join(_secrets.choice(_ALPHA) for _ in range(4))}"
    import asyncio

    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        now = datetime.now(timezone.utc).isoformat()
        valid_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        await db.school_documents_log.insert_one({
            "id": str(uuid.uuid4()),
            "code": code,
            "doc_type": "matricula",
            "student_id": "fix_stu_ana",
            "student_name": "Aluno Teste DEL",
            "purpose": "TESTE",
            "school_id": "any",
            "mantenedora_id": TENANT,
            "emitted_at": now,
            "valid_until": valid_until,
        })
        await db.verifiable_documents.insert_one({
            "id": str(uuid.uuid4()),
            "code": code,
            "snapshot_id": "snap_del_test",
            "doc_type": "matricula",
            "mantenedora_id": TENANT,
            "entity_type": "student",
            "entity_id": "fix_stu_ana",
            "issued_at": now,
            "expires_at": valid_until,
        })
        client.close()

    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.school_documents_log.delete_many({"code": code})
        await db.verifiable_documents.delete_many({"code": code})
        client.close()

    asyncio.run(_setup())
    yield code
    asyncio.run(_teardown())


def test_super_admin_can_delete(super_admin_session, fixture_doc):
    code = fixture_doc
    r = super_admin_session.delete(
        f"{BASE_URL}/api/school-documents/{code}",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["log_deleted"] == 1
    assert body["verifiable_deleted"] == 1


def test_delete_missing_returns_404(super_admin_session):
    r = super_admin_session.delete(
        f"{BASE_URL}/api/school-documents/SIGESC-XXXX-XXXX",
        timeout=30,
    )
    assert r.status_code == 404


def test_unauthenticated_blocked():
    r = requests.delete(
        f"{BASE_URL}/api/school-documents/SIGESC-AAAA-BBBB",
        timeout=30,
    )
    assert r.status_code in (401, 403)


def test_non_super_admin_blocked(super_admin_session, fixture_doc):
    """Tenta deletar com user secretario — deve retornar 403."""
    # tenta logar como secretario; se conta não existir pula
    try:
        sec = _login("secretario@sigesc.com", "secretario123")
    except AssertionError:
        pytest.skip("conta secretario indisponível neste ambiente")
        return
    r = sec.delete(
        f"{BASE_URL}/api/school-documents/{fixture_doc}",
        timeout=30,
    )
    assert r.status_code == 403
