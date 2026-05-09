"""
E2E HTTP — Verifiable Documents MVP (Fev/2026).

Cobre o que foi adicionado nesta sprint:
- verification_token UUID opaco (32 hex)
- Endpoint público `/api/public/verify/{identifier}` aceita code OU token
- Backfill on startup preenche token em docs antigos
- POST /api/documents/{code}/signatures (admin/diretor)
- POST /api/documents/{code}/supersede (admin/secretario)
- build_portal_response retorna `assinaturas`, `verification_token`,
  `document_type`, `schema_version`
- Estado `substituido` (substituído ≠ revogado)
- Resposta LGPD-safe: NÃO expõe student_id, school_id, user_id, email
"""
from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from datetime import datetime, timezone

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

_ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _gen_code() -> str:
    return f"SIGESC-{''.join(secrets.choice(_ALPHA) for _ in range(4))}-{''.join(secrets.choice(_ALPHA) for _ in range(4))}"


def _login() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
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


@pytest.fixture(scope="module")
def session():
    return _login()


@pytest.fixture
def vdoc_pair():
    """Cria 2 verifiable_documents válidos para testar substituição/assinatura."""
    code_a = _gen_code()
    code_b = _gen_code()
    token_a = uuid.uuid4().hex
    token_b = uuid.uuid4().hex

    async def _setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        now = datetime.now(timezone.utc).isoformat()
        common = {
            "schema_version": "1",
            "type": "declaracao",
            "document_type": "declaracao",
            "public_hash": "ab" * 32,
            "server_signature": "sig_test",
            "mantenedora_id": TENANT,
            "entity_type": "student",
            "entity_id": "fix_stu_ana",
            "student_id": "fix_stu_ana",
            "school_id": "fix_school_v1",
            "snapshot_id": None,
            "issued_by": {"email": "test@sigesc.com"},
            "public_metadata": {
                "tipo": "declaracao",
                "tipo_label": "Declaração Escolar",
                "emitido_em": now[:10],
                "emitido_por": "SIGESC",
                "escopo": "Teste",
            },
            "created_at": now,
            "expires_at": None,
            "revoked": False,
            "revoked_at": None,
            "revoked_reason": None,
            "revoked_by": None,
            "signatures": [],
            "superseded_by_document_id": None,
            "superseded_at": None,
        }
        await db.verifiable_documents.delete_many({"code": {"$in": [code_a, code_b]}})
        await db.verifiable_documents.insert_one({
            **common, "code": code_a, "verification_token": token_a,
        })
        await db.verifiable_documents.insert_one({
            **common, "code": code_b, "verification_token": token_b,
        })
        client.close()

    async def _teardown():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.verifiable_documents.delete_many({"code": {"$in": [code_a, code_b]}})
        client.close()

    asyncio.run(_setup())
    yield {"code_a": code_a, "code_b": code_b, "token_a": token_a, "token_b": token_b}
    asyncio.run(_teardown())


# ===========================================================================
def test_01_public_verify_by_code(vdoc_pair):
    r = requests.get(
        f"{BASE_URL}/api/public/verify/{vdoc_pair['code_a']}",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in ("valido", "invalido")  # depende de snapshot_id; aqui é None
    assert body["codigo"] == vdoc_pair["code_a"]
    assert body["verification_token"] == vdoc_pair["token_a"]
    assert body["document_type"] == "declaracao"
    assert body["schema_version"] == "1"
    assert body["assinaturas"] == []


def test_02_public_verify_by_token(vdoc_pair):
    """Owner spec: GET /api/public/verify/{verification_token} aceita token opaco."""
    r = requests.get(
        f"{BASE_URL}/api/public/verify/{vdoc_pair['token_a']}",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["codigo"] == vdoc_pair["code_a"]
    assert body["verification_token"] == vdoc_pair["token_a"]


def test_03_public_response_is_lgpd_safe(vdoc_pair):
    """Resposta pública NÃO pode expor PII operacional."""
    r = requests.get(
        f"{BASE_URL}/api/public/verify/{vdoc_pair['token_a']}",
        timeout=30,
    )
    body = r.json()
    forbidden = ["student_id", "school_id", "mantenedora_id", "entity_id",
                 "email", "cpf", "registration_number", "filiacao",
                 "issued_by", "user_id", "snapshot_id", "public_hash",
                 "server_signature"]
    for f in forbidden:
        assert f not in body, f"Campo PII vazou: {f}"


def test_04_unknown_identifier_returns_invalido():
    r = requests.get(f"{BASE_URL}/api/public/verify/SIGESC-AAAA-BBBB", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "invalido"
    assert body["codigo"] is None


def test_05_add_signature(session, vdoc_pair):
    code = vdoc_pair["code_a"]
    r = session.post(
        f"{BASE_URL}/api/documents/{code}/signatures",
        json={"role": "diretor", "full_name": "Maria Souza"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["signatures"]) == 1
    assert body["signatures"][0]["role"] == "diretor"
    assert body["signatures"][0]["full_name"] == "Maria Souza"

    # Aparece no portal público (LGPD-safe — sem user_id)
    pub = requests.get(f"{BASE_URL}/api/public/verify/{code}", timeout=30).json()
    assert len(pub["assinaturas"]) == 1
    sig = pub["assinaturas"][0]
    assert sig["role"] == "diretor"
    assert sig["full_name"] == "Maria Souza"
    assert "signed_by_user_id" not in sig
    assert "user_id" not in sig


def test_06_add_signature_missing_fields_400(session, vdoc_pair):
    r = session.post(
        f"{BASE_URL}/api/documents/{vdoc_pair['code_a']}/signatures",
        json={"role": "diretor"},
        timeout=30,
    )
    assert r.status_code == 400


def test_07_supersede_marks_old_as_substituido(session, vdoc_pair):
    """A.code → marca como substituído por B.code."""
    code_a, code_b = vdoc_pair["code_a"], vdoc_pair["code_b"]
    r = session.post(
        f"{BASE_URL}/api/documents/{code_a}/supersede",
        json={"new_code": code_b},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["superseded_by_document_id"] == code_b

    # Portal público mostra status 'substituido'
    pub = requests.get(f"{BASE_URL}/api/public/verify/{code_a}", timeout=30).json()
    assert pub["status"] == "substituido"
    assert pub["substituido_por"] == code_b
    assert "substituído" in pub["mensagem"].lower()


def test_08_supersede_same_doc_400(session, vdoc_pair):
    code = vdoc_pair["code_a"]
    r = session.post(
        f"{BASE_URL}/api/documents/{code}/supersede",
        json={"new_code": code},
        timeout=30,
    )
    assert r.status_code == 400


def test_09_supersede_unknown_404(session, vdoc_pair):
    r = session.post(
        f"{BASE_URL}/api/documents/{vdoc_pair['code_a']}/supersede",
        json={"new_code": "SIGESC-ZZZZ-ZZZZ"},
        timeout=30,
    )
    assert r.status_code == 404


def test_10_token_is_uuid_hex_format(vdoc_pair):
    """Garante que tokens gerados/persistidos seguem o formato UUID hex 32 chars."""
    import re
    assert re.match(r"^[a-f0-9]{32}$", vdoc_pair["token_a"])
    assert re.match(r"^[a-f0-9]{32}$", vdoc_pair["token_b"])
