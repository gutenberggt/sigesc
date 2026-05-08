"""Fev 2026 — Sprint G1.6: Portal Público + Verifiable Documents genéricos."""
import asyncio
import os
import time
from datetime import datetime, timezone

import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")

BACKEND = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://adoring-ganguly-10.preview.emergentagent.com",
).rstrip("/")
SUPER_ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}
SCHOOL_ID = "school_g16_test"


@pytest.fixture(scope="module")
def token():
    time.sleep(1.2)
    r = httpx.post(f"{BACKEND}/api/auth/login", json=SUPER_ADMIN, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _db():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


@pytest.fixture(scope="module", autouse=True)
def seed():
    async def setup():
        db = _db()
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.verifiable_documents.delete_many({"entity_id": SCHOOL_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": SCHOOL_ID})
        await db.schools.insert_one({"id": SCHOOL_ID, "name": "Escola G16"})
        from services.verifiable_docs_service import ensure_indexes
        await ensure_indexes(db)

    async def teardown():
        db = _db()
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.verifiable_documents.delete_many({"entity_id": SCHOOL_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": SCHOOL_ID})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


# ---------- Formato de código ----------

def test_generate_code_formato_valido():
    from services.verifiable_docs_service import generate_code
    import re
    for _ in range(50):
        code = generate_code()
        assert re.match(r"^SIGESC-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$", code), code


def test_generate_code_unico_em_lote():
    from services.verifiable_docs_service import generate_code
    codes = {generate_code() for _ in range(200)}
    assert len(codes) == 200


# ---------- Normalização ----------

@pytest.mark.parametrize("inp,expected", [
    ("SIGESC-ABCD-2345", "SIGESC-ABCD-2345"),
    ("sigesc-abcd-2345", "SIGESC-ABCD-2345"),
    ("sigescabcd2345", "SIGESC-ABCD-2345"),
    ("abcd2345", "SIGESC-ABCD-2345"),
    ("abcd-2345", "SIGESC-ABCD-2345"),
    ("ABCD 2345", "SIGESC-ABCD-2345"),
    ("  abcd2345  ", "SIGESC-ABCD-2345"),
])
def test_normalize_aceita_variacoes(inp, expected):
    from services.verifiable_docs_service import normalize_code
    assert normalize_code(inp) == expected


@pytest.mark.parametrize("invalid", [
    "", None, "abc", "abcdefghi",
    "abcdefg1",   # '1' não está no alfabeto seguro
    "abcdefgO",   # 'O' é confuso
    "sigesc-abc-2345",
])
def test_normalize_rejeita_invalidos(invalid):
    from services.verifiable_docs_service import normalize_code
    assert normalize_code(invalid) is None


# ---------- Create / Resolve / Revoke ----------

def test_create_e_resolve():
    from services.verifiable_docs_service import (
        create_verifiable_document, resolve_code,
    )

    async def run():
        db = _db()
        doc = await create_verifiable_document(
            db, type="plano_acao",
            public_hash="sha256:test_abc",
            server_signature="hmac-sha256:sig",
            mantenedora_id=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            issued_by={"user_id": "u1", "email": "t@s", "role": "super_admin"},
            scope_label="Escola G16",
        )
        mixed = doc["code"].lower().replace("-", "").replace("sigesc", "")
        resolved = await resolve_code(db, mixed)
        await db.verifiable_documents.delete_one({"code": doc["code"]})
        return doc, resolved

    created, resolved = asyncio.run(run())
    assert resolved is not None
    assert resolved["code"] == created["code"]
    assert created["public_metadata"]["tipo_label"] == "Plano de Ação Automático"


def test_revoke_documento():
    from services.verifiable_docs_service import (
        create_verifiable_document, revoke_document,
    )

    async def run():
        db = _db()
        doc = await create_verifiable_document(
            db, type="plano_acao",
            public_hash="sha256:x", server_signature=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            issued_by={}, scope_label="x",
        )
        r = await revoke_document(
            db, code=doc["code"], reason="Teste revogação",
            user={"id": "u_admin", "email": "a@s.c", "role": "super_admin"},
        )
        await db.verifiable_documents.delete_one({"code": doc["code"]})
        return r

    r = asyncio.run(run())
    assert r["revoked"] is True
    assert r["revoked_reason"] == "Teste revogação"


# ---------- LGPD: portal não expõe payload ----------

def test_portal_response_nao_expoe_dados_sensiveis():
    from services.verifiable_docs_service import build_portal_response
    doc = {
        "code": "SIGESC-ABCD-2345",
        "type": "plano_acao",
        "public_hash": "sha256:x",
        "server_signature": None,
        "revoked": False,
        "snapshot_id": None,
        "public_metadata": {
            "tipo": "plano_acao",
            "tipo_label": "Plano de Ação Automático",
            "emitido_em": "2026-02-03",
            "emitido_por": "SIGESC",
            "escopo": "Escola X",
        },
        "ai_output": {"analise_executiva": "DADO_OPERACIONAL_SENSIVEL"},
        "payload_snapshot": {"alunos": [{"nome": "DADO_PESSOAL_SENSIVEL"}]},
    }
    resp = build_portal_response(doc)
    resp_str = str(resp)
    assert "DADO_OPERACIONAL_SENSIVEL" not in resp_str
    assert "DADO_PESSOAL_SENSIVEL" not in resp_str
    assert "payload_snapshot" not in resp_str


def test_portal_response_tres_estados():
    from services.verifiable_docs_service import build_portal_response
    assert build_portal_response(None)["status"] == "invalido"
    doc_rev = {
        "code": "SIGESC-ABCD-2345", "revoked": True,
        "revoked_at": "2026-02-03T12:00:00+00:00",
        "public_hash": "h", "server_signature": None,
        "public_metadata": {"tipo": "x", "tipo_label": "X",
                            "emitido_em": "2026-02-01",
                            "emitido_por": "S", "escopo": "e"},
    }
    assert build_portal_response(doc_rev)["status"] == "revogado"


# ---------- E2E: Portal público ----------

def test_portal_publico_sem_auth():
    from services.verifiable_docs_service import create_verifiable_document

    async def setup():
        db = _db()
        return (await create_verifiable_document(
            db, type="plano_acao",
            public_hash="sha256:pub_e2e", server_signature=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            issued_by={}, scope_label="Escola G16",
        ))["code"]

    code = asyncio.run(setup())
    r = httpx.get(f"{BACKEND}/api/public/verify/{code}", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("status", "codigo", "mensagem"):
        assert k in data
    for forbidden in ("ai_output", "payload_snapshot", "public_hash", "server_signature"):
        assert forbidden not in data
    assert data["codigo"] == code

    async def cleanup():
        db = _db()
        await db.verifiable_documents.delete_one({"code": code})
    asyncio.run(cleanup())


def test_portal_publico_codigo_nao_existente():
    r = httpx.get(f"{BACKEND}/api/public/verify/SIGESC-ZZZZ-ZZZZ", timeout=15)
    assert r.status_code == 200
    assert r.json()["status"] == "invalido"


def test_portal_publico_normaliza_input():
    from services.verifiable_docs_service import create_verifiable_document

    async def setup():
        db = _db()
        return (await create_verifiable_document(
            db, type="plano_acao",
            public_hash="sha256:norm", server_signature=None,
            entity_type="escola", entity_id=SCHOOL_ID, issued_by={},
        ))["code"]

    code = asyncio.run(setup())
    short = code.replace("SIGESC-", "").replace("-", "").lower()
    r = httpx.get(f"{BACKEND}/api/public/verify/{short}", timeout=15)
    assert r.status_code == 200
    assert r.json()["codigo"] == code

    async def cleanup():
        db = _db()
        await db.verifiable_documents.delete_one({"code": code})
    asyncio.run(cleanup())


# ---------- Admin endpoints ----------

def test_admin_lista(token):
    r = httpx.get(
        f"{BACKEND}/api/documents?entity_id={SCHOOL_ID}",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200
    assert "items" in r.json()


def test_admin_revoga_e_portal_retorna_revogado(token):
    from services.verifiable_docs_service import create_verifiable_document

    async def setup():
        db = _db()
        return (await create_verifiable_document(
            db, type="plano_acao",
            public_hash="sha256:rev_e2e", server_signature=None,
            entity_type="escola", entity_id=SCHOOL_ID, issued_by={},
        ))["code"]

    code = asyncio.run(setup())
    r = httpx.post(
        f"{BACKEND}/api/documents/{code}/revoke",
        headers=_h(token), json={"reason": "Erro de emissão"},
        timeout=20,
    )
    assert r.status_code == 200
    assert r.json()["revoked"] is True
    pr = httpx.get(f"{BACKEND}/api/public/verify/{code}", timeout=15)
    assert pr.json()["status"] == "revogado"

    async def cleanup():
        db = _db()
        await db.verifiable_documents.delete_one({"code": code})
    asyncio.run(cleanup())


# ---------- Integração ----------

def test_snapshot_gera_verification_code_automatico():
    from services.snapshot_service import create_snapshot

    async def run():
        db = _db()
        snap = await create_snapshot(
            db, mantenedora_id=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            analysis_type="plano_acao",
            payload_snapshot={"x": 1},
            ai_output={"analise_executiva": "t"},
            model="t",
            user={"id": "u", "email": "u@s", "role": "super_admin"},
        )
        vdoc = await db.verifiable_documents.find_one(
            {"snapshot_id": snap["id"]}, {"_id": 0}
        )
        await db.verifiable_documents.delete_many({"snapshot_id": snap["id"]})
        await db.ai_analysis_snapshots.delete_many({"id": snap["id"]})
        return snap, vdoc

    snap, vdoc = asyncio.run(run())
    assert snap.get("verification_code") is not None
    assert vdoc is not None
    assert vdoc["code"] == snap["verification_code"]


def test_ensure_for_snapshot_retroativo(token):
    async def setup_sem_code():
        db = _db()
        import uuid
        sid = str(uuid.uuid4())
        await db.ai_analysis_snapshots.insert_one({
            "id": sid, "version": 1,
            "mantenedora_id": None, "entity_type": "escola",
            "entity_id": SCHOOL_ID, "analysis_type": "plano_acao",
            "payload_snapshot": {"x": 1}, "ai_output": {"a": "b"},
            "model": "anthropic/claude-legacy",
            "public_hash": "sha256:legacy",
            "server_signature": "hmac-sha256:legacy",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": {"user_id": "u", "email": "u@s", "role": "super_admin"},
        })
        return sid

    sid = asyncio.run(setup_sem_code())
    r = httpx.post(
        f"{BACKEND}/api/documents/ensure-for-snapshot/{sid}",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["created"] is True
    assert data["document"]["code"].startswith("SIGESC-")
    # Idempotente
    r2 = httpx.post(
        f"{BACKEND}/api/documents/ensure-for-snapshot/{sid}",
        headers=_h(token), timeout=20,
    )
    assert r2.json()["created"] is False

    async def cleanup():
        db = _db()
        await db.verifiable_documents.delete_many({"snapshot_id": sid})
        await db.ai_analysis_snapshots.delete_many({"id": sid})
    asyncio.run(cleanup())
