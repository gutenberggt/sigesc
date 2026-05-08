"""Fev 2026 — Sprint G1.5: Snapshots imutáveis + integridade.

Cobre:
  1. Hash determinístico: mesmo input → mesmo hash.
  2. Qualquer alteração no payload muda o hash.
  3. HMAC verifica corretamente com o secret correto.
  4. verify_snapshot_integrity detecta tampering.
  5. create_snapshot persiste doc com TTL apropriado.
  6. get_scope_for_user bloqueia professor/aluno e escopa diretor.
  7. Política de retenção: custom abaixo do mínimo é rejeitada.
  8. Endpoint /snapshots lista com escopo (professor bloqueado).
  9. Endpoint /verify retorna schema rico (valid, hash_valid, signature_valid).
 10. Endpoint /pdf gera bytes válidos de PDF.
 11. enrich_plan_with_ai cria snapshot automaticamente quando user é passado.
"""
import asyncio
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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

SCHOOL_ID = "school_g15_test"
CLASS_ID = "cls_g15_test"


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
def seed_g15():
    async def setup():
        db = _db()
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.classes.delete_many({"school_id": SCHOOL_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": SCHOOL_ID})
        await db.schools.insert_one({"id": SCHOOL_ID, "name": "Escola G15"})
        await db.classes.insert_one({
            "id": CLASS_ID, "name": "Turma G15", "school_id": SCHOOL_ID,
            "academic_year": 9994,
        })

    async def teardown():
        db = _db()
        await db.schools.delete_many({"id": SCHOOL_ID})
        await db.classes.delete_many({"school_id": SCHOOL_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": SCHOOL_ID})

    asyncio.run(setup())
    yield
    asyncio.run(teardown())


# ---------- Hash & HMAC ----------

def test_hash_deterministico():
    from services.snapshot_service import compute_public_hash
    args = dict(
        entity_type="escola", entity_id="x1", analysis_type="plano_acao",
        payload_snapshot={"a": 1, "b": [1, 2, 3]},
        ai_output={"analise_executiva": "ok", "z": None},
        created_at_iso="2026-02-03T12:00:00+00:00",
        model="anthropic/claude",
    )
    h1 = compute_public_hash(**args)
    h2 = compute_public_hash(**args)
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == 7 + 64


def test_hash_muda_quando_payload_altera():
    from services.snapshot_service import compute_public_hash
    base = dict(
        entity_type="escola", entity_id="x1", analysis_type="plano_acao",
        payload_snapshot={"a": 1},
        ai_output={"t": "x"},
        created_at_iso="2026-02-03T12:00:00+00:00",
        model="m",
    )
    h_base = compute_public_hash(**base)
    # Altera payload
    b2 = {**base, "payload_snapshot": {"a": 2}}
    h2 = compute_public_hash(**b2)
    assert h2 != h_base
    # Altera output
    b3 = {**base, "ai_output": {"t": "y"}}
    h3 = compute_public_hash(**b3)
    assert h3 != h_base
    # Altera timestamp
    b4 = {**base, "created_at_iso": "2026-02-03T12:00:01+00:00"}
    h4 = compute_public_hash(**b4)
    assert h4 != h_base


def test_hmac_signature_valida_com_secret(monkeypatch):
    from services.snapshot_service import compute_signature
    monkeypatch.setenv("SNAPSHOT_HMAC_SECRET", "s1")
    sig = compute_signature("sha256:abc")
    assert sig.startswith("hmac-sha256:")
    # Recomputa manualmente
    expected = hmac.new(b"s1", b"sha256:abc", hashlib.sha256).hexdigest()
    assert sig == f"hmac-sha256:{expected}"
    # Secret diferente → sig diferente
    monkeypatch.setenv("SNAPSHOT_HMAC_SECRET", "s2")
    sig2 = compute_signature("sha256:abc")
    assert sig != sig2


def test_hmac_sem_secret_retorna_none(monkeypatch):
    from services.snapshot_service import compute_signature
    monkeypatch.delenv("SNAPSHOT_HMAC_SECRET", raising=False)
    assert compute_signature("x") is None


# ---------- Verify / Tampering ----------

def test_verify_detecta_tampering(monkeypatch):
    from services.snapshot_service import (
        compute_public_hash, compute_signature, verify_snapshot_integrity,
    )
    monkeypatch.setenv("SNAPSHOT_HMAC_SECRET", "test_secret_123")
    created = "2026-02-03T12:00:00+00:00"
    payload = {"x": 1}
    output = {"analise_executiva": "ok"}
    h = compute_public_hash(
        entity_type="escola", entity_id="s1", analysis_type="plano_acao",
        payload_snapshot=payload, ai_output=output,
        created_at_iso=created, model="m",
    )
    sig = compute_signature(h)
    doc = {
        "version": 1, "entity_type": "escola", "entity_id": "s1",
        "analysis_type": "plano_acao", "payload_snapshot": payload,
        "ai_output": output, "created_at": created, "model": "m",
        "public_hash": h, "server_signature": sig,
    }
    good = verify_snapshot_integrity(doc)
    assert good["valid"] is True
    assert good["hash_valid"] is True
    assert good["signature_valid"] is True

    # Tampering no payload
    tampered = {**doc, "payload_snapshot": {"x": 999}}
    bad = verify_snapshot_integrity(tampered)
    assert bad["valid"] is False
    assert bad["hash_valid"] is False

    # Signature inválida (gerada com outro secret)
    monkeypatch.setenv("SNAPSHOT_HMAC_SECRET", "other_secret")
    bad2 = verify_snapshot_integrity(doc)
    assert bad2["hash_valid"] is True
    assert bad2["signature_valid"] is False
    assert bad2["valid"] is False
    # monkeypatch restaura secret original ao sair do teste


# ---------- Persistência (create_snapshot) ----------

def test_create_snapshot_persiste_com_hash_e_ttl():
    from services.snapshot_service import create_snapshot

    async def run():
        db = _db()
        snap = await create_snapshot(
            db,
            mantenedora_id=None,
            entity_type="escola",
            entity_id=SCHOOL_ID,
            analysis_type="plano_acao",
            payload_snapshot={"x": 1},
            ai_output={"analise_executiva": "teste"},
            model="anthropic/test",
            user={"id": "u1", "email": "test@sigesc.com", "role": "super_admin"},
        )
        stored = await db.ai_analysis_snapshots.find_one({"id": snap["id"]}, {"_id": 0})
        await db.ai_analysis_snapshots.delete_one({"id": snap["id"]})
        return snap, stored

    snap, stored = asyncio.run(run())
    assert snap["public_hash"].startswith("sha256:")
    assert stored is not None
    assert stored["public_hash"] == snap["public_hash"]
    # TTL: default 5 anos → expires_at definido
    assert stored["expires_at"] is not None


# ---------- Scope (access control) ----------

def test_scope_professor_sem_acesso():
    from services.snapshot_service import get_scope_for_user
    assert get_scope_for_user({"role": "professor", "id": "p1"}) is None
    assert get_scope_for_user({"role": "aluno", "id": "a1"}) is None


def test_scope_diretor_escopo_escolas():
    from services.snapshot_service import get_scope_for_user
    scope = get_scope_for_user({
        "role": "diretor", "id": "d1",
        "school_ids": ["s1", "s2"], "mantenedora_id": "m1",
    })
    assert scope == {"entity_ids": ["s1", "s2"], "mantenedora_id": "m1"}


def test_scope_secretario_mantenedora():
    from services.snapshot_service import get_scope_for_user
    scope = get_scope_for_user({
        "role": "secretario", "id": "s1", "mantenedora_id": "m1",
    })
    assert scope == {"mantenedora_id": "m1"}


def test_scope_super_admin_global():
    from services.snapshot_service import get_scope_for_user
    scope = get_scope_for_user({"role": "super_admin", "id": "x"})
    assert scope == {}


# ---------- Retention policy ----------

def test_retention_custom_abaixo_do_minimo_rejeita():
    from services import snapshot_service as svc

    async def run():
        db = _db()
        with pytest.raises(ValueError):
            await svc.set_retention_policy(
                db, mantenedora_id="m_test_ret", mode="custom", days=30,
            )
        await db.snapshot_retention_policies.delete_many({"mantenedora_id": "m_test_ret"})

    asyncio.run(run())


def test_retention_forever_ok():
    from services import snapshot_service as svc

    async def run():
        db = _db()
        doc = await svc.set_retention_policy(
            db, mantenedora_id="m_test_forever", mode="forever",
        )
        await db.snapshot_retention_policies.delete_many({"mantenedora_id": "m_test_forever"})
        return doc

    doc = asyncio.run(run())
    assert doc["mode"] == "forever"
    assert doc["days"] is None


# ---------- Endpoint E2E ----------

def test_endpoint_list_super_admin_sem_escopo(token):
    async def setup_one():
        db = _db()
        from services.snapshot_service import create_snapshot
        snap = await create_snapshot(
            db, mantenedora_id=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            analysis_type="plano_acao",
            payload_snapshot={"x": 1},
            ai_output={"analise_executiva": "teste"},
            model="test",
            user={"id": "u1", "email": "t@s.c", "role": "super_admin"},
        )
        return snap["id"]

    snap_id = asyncio.run(setup_one())
    r = httpx.get(
        f"{BACKEND}/api/snapshots?entity_id={SCHOOL_ID}",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    ids = [i["id"] for i in data["items"]]
    assert snap_id in ids


def test_endpoint_verify_retorna_schema_rico(token):
    async def setup_one():
        db = _db()
        from services.snapshot_service import create_snapshot
        snap = await create_snapshot(
            db, mantenedora_id=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            analysis_type="plano_acao",
            payload_snapshot={"y": 2},
            ai_output={"analise_executiva": "v"},
            model="test",
            user={"id": "u2", "email": "t2@s.c", "role": "super_admin"},
        )
        return snap["id"]

    snap_id = asyncio.run(setup_one())
    r = httpx.get(
        f"{BACKEND}/api/snapshots/{snap_id}/verify",
        headers=_h(token), timeout=20,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("valid", "hash_valid", "signature_valid",
              "public_hash", "recomputed_hash", "server_signature",
              "snapshot_id", "entity_id"):
        assert k in data
    assert data["valid"] is True
    assert data["hash_valid"] is True
    assert data["signature_valid"] is True


def test_endpoint_pdf_retorna_bytes_validos(token):
    async def setup_one():
        db = _db()
        from services.snapshot_service import create_snapshot
        snap = await create_snapshot(
            db, mantenedora_id=None,
            entity_type="escola", entity_id=SCHOOL_ID,
            analysis_type="plano_acao",
            payload_snapshot={
                "school_name": "Escola G15",
                "period": "30d",
                "acoes": [
                    {"ordem": 1, "categoria": "cobertura", "titulo": "Ação teste",
                     "descricao": "Descrição teste", "prioridade": 1, "impacto": "alto",
                     "prazo_dias": 7, "responsavel": "coordenador",
                     "metrica_sucesso": "Meta"},
                ],
            },
            ai_output={
                "analise_executiva": "Análise teste 123",
                "analise_evidencias": [{"metrica": "X", "valor": "1", "fonte": "payload.x"}],
                "insight_historico": "Insight teste",
                "insight_evidencias": [],
                "recomendacoes_extra": [],
                "acoes_enriquecidas": {},
            },
            model="anthropic/claude-test",
            user={"id": "u3", "email": "t3@s.c", "role": "super_admin"},
        )
        return snap["id"]

    snap_id = asyncio.run(setup_one())
    # Modo executivo
    r = httpx.get(
        f"{BACKEND}/api/snapshots/{snap_id}/pdf?mode=executive",
        headers=_h(token), timeout=30,
    )
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000
    # Modo auditor
    r2 = httpx.get(
        f"{BACKEND}/api/snapshots/{snap_id}/pdf?mode=auditor",
        headers=_h(token), timeout=30,
    )
    assert r2.status_code == 200
    assert r2.content[:4] == b"%PDF"
    # Auditor deve ser maior (inclui anexo técnico)
    assert len(r2.content) > len(r.content)


def test_endpoint_bloqueia_nao_auditor():
    """Professor não consegue acessar /snapshots (403)."""
    # Precisa de um token de professor — usa user de teste se existir,
    # senão skip (ambiente não tem professor cadastrado)
    from models import UserInDB  # noqa
    import json as _json
    prof = httpx.post(
        f"{BACKEND}/api/auth/login",
        json={"email": "professor.teste@sigesc.com", "password": "Professor@2026"},
        timeout=20,
    )
    if prof.status_code != 200:
        pytest.skip("usuário professor de teste não disponível")
    tk = prof.json()["access_token"]
    r = httpx.get(f"{BACKEND}/api/snapshots", headers=_h(tk), timeout=15)
    assert r.status_code == 403, r.text


# ---------- Integração: enrich_plan_with_ai cria snapshot ----------

def test_enrich_cria_snapshot_automatico(monkeypatch):
    from services import plano_acao_ai as mod

    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-fake")
    fake = json.dumps({
        "analise_executiva": "A",
        "analise_evidencias": [{"metrica": "m", "valor": "1", "fonte": "contexto_atual.active"}],
        "insight_historico": "I",
        "insight_evidencias": [{"metrica": "r", "valor": "MA", "fonte": "gestor.most_neglected_component"}],
        "recomendacoes_extra": [],
        "acoes_enriquecidas": {"1": "ok"},
    })

    async def run():
        db = _db()
        # Limpa cache e snapshots antigos
        await db.ai_plans.delete_many({"school_id": SCHOOL_ID})
        await db.ai_analysis_snapshots.delete_many({"entity_id": SCHOOL_ID})
        with patch.object(mod, "LlmChat") as MockChat:
            inst = MockChat.return_value
            inst.with_model = lambda *a, **kw: inst
            inst.send_message = AsyncMock(return_value=fake)
            out = await mod.enrich_plan_with_ai(
                db,
                mantenedora_id=None,
                school_id=SCHOOL_ID,
                school_name="Escola G15",
                period="30d",
                contexto={"active": 1},
                acoes=[{"ordem": 1, "titulo": "T"}],
                force=True,
                user={"id": "u_auto", "email": "a@s.c", "role": "super_admin"},
            )
        snap_doc = await db.ai_analysis_snapshots.find_one(
            {"entity_id": SCHOOL_ID}, {"_id": 0}
        )
        return out, snap_doc

    out, snap = asyncio.run(run())
    assert out["snapshot_id"] is not None
    assert out["public_hash"].startswith("sha256:")
    assert out["server_signature"].startswith("hmac-sha256:")
    assert snap is not None
    assert snap["id"] == out["snapshot_id"]
    assert snap["public_hash"] == out["public_hash"]
