"""Fase 5 (Mai/2026) — Tests do snapshot imutável do Diário Escolar.

Cobertura crítica:
  1. Hash determinístico (mesmo payload → mesmo hash).
  2. Hash imutável após signatures (diretriz 3 + 7).
  3. Idempotência draft (mesmo período → mesmo snapshot).
  4. Publish gera token + hash + enfileira render_job.
  5. Hash preservado após revoke (diretriz 9 — revoke ≠ delete).
  6. Rationale curto bloqueado (revoke/supersede ≥ 30 chars).
  7. Sign duplicado por (role, user) → 409.
  8. Renders[] array (diretriz 6) — não singular.
  9. semantic_rules_version + branding congelados (diretriz 5 + 10).
 10. Snapshot NÃO muda quando attendance é alterado após publicação.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://sla-trio-weighted.preview.emergentagent.com"
).rstrip("/")
ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

# Turma seedada com assignments — usar uma fora das outras suites para isolar.
CLASS_ID = "73844918-60b1-4c62-b6cb-a21a35cc49c1"

PERIOD_FROM = "2027-04-01"
PERIOD_TO = "2027-04-30"


@pytest.fixture(scope="module", autouse=True)
def _clean():
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    db.diary_snapshots.delete_many({"class_id": CLASS_ID})
    db.document_render_jobs.delete_many({"source_snapshot_id": {"$regex": "."}, "document_type": "diary_period"})
    yield
    db.diary_snapshots.delete_many({"class_id": CLASS_ID})


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    d = r.json()
    s.headers.update({
        "Authorization": f"Bearer {d.get('access_token') or d.get('token')}",
        "X-CSRF-Token": d.get("csrf_token") or "",
        "Content-Type": "application/json",
    })
    return s


def _create(session, **over):
    body = {
        "class_id": CLASS_ID,
        "period_type": "month",
        "period_from": PERIOD_FROM,
        "period_to": PERIOD_TO,
        "period_label": "Abril 2027 (test)",
    }
    body.update(over)
    return session.post(f"{BASE_URL}/api/diary/snapshots", json=body, timeout=20)


_PERIOD_COUNTER = [0]


def _unique_period():
    """Cada chamada usa dia diferente — counter monotônico evita colisão.

    Range: 2028-07-XX (mês fora de qualquer outra suite de testes).
    """
    _PERIOD_COUNTER[0] += 1
    n = _PERIOD_COUNTER[0] % 27 + 1
    return f"2028-07-{n:02d}", f"2028-07-{n:02d}"


def _create_unique(session, **over):
    pf, pt = _unique_period()
    body = {
        "class_id": CLASS_ID,
        "period_type": "custom",
        "period_from": pf,
        "period_to": pt,
        "period_label": f"test-{pf}",
    }
    body.update(over)
    r = session.post(f"{BASE_URL}/api/diary/snapshots", json=body, timeout=20)
    if r.status_code != 200:
        raise AssertionError(f"_create_unique failed: {r.status_code} {r.text[:400]}")
    return r


# ============================================================================
# 1. Hash determinístico (puramente unitário, sem HTTP)
# ============================================================================
def test_hash_deterministic():
    from utils.document_hash import compute_document_hash
    payload = {"a": 1, "b": [3, 2, 1], "c": {"x": "ç", "y": True}}
    h1 = compute_document_hash(payload)
    h2 = compute_document_hash({"c": {"y": True, "x": "ç"}, "b": [3, 2, 1], "a": 1})
    assert h1 == h2 and len(h1) == 64


# ============================================================================
# 2. Idempotência draft
# ============================================================================
def test_idempotent_draft_returns_same(session):
    r1 = _create(session)
    assert r1.status_code == 200, r1.text[:400]
    d1 = r1.json()
    snap_id = d1["snapshot"]["id"]
    assert d1["snapshot"]["status"] == "draft"
    # Idempotency_hit=False na primeira; campo `_idempotent_hit` só é setado quando retorna existente
    r2 = _create(session)
    d2 = r2.json()
    assert d2["snapshot"]["id"] == snap_id
    assert d2["idempotent_hit"] is True


# ============================================================================
# 3. Publish → hash + token + render_job + status=published
# ============================================================================
def test_publish_creates_hash_token_render_job(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    r = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    snap = d["snapshot"]
    assert snap["status"] == "published"
    assert len(snap["payload_hash_sha256"]) == 64
    assert len(snap["verification_token"]) == 32
    assert snap["issued_at"] is not None
    rj = d["render_job"]
    assert rj["document_type"] == "diary_period"
    assert rj["source_snapshot_id"] == snap_id
    assert rj["status"] in ("pending", "processing", "completed")


# ============================================================================
# 4. Hash imutável após signature (diretriz 3 + 7)
# ============================================================================
def test_hash_immutable_after_signature(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    snap_before = session.get(f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20).json()
    hash_before = snap_before["payload_hash_sha256"]

    r = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "diretor", "full_name": "Dir. Teste"}, timeout=20,
    )
    assert r.status_code == 200
    snap_after = r.json()
    assert snap_after["payload_hash_sha256"] == hash_before  # NÃO mudou
    assert len(snap_after["signatures"]) == 1
    sig = snap_after["signatures"][0]
    assert sig["signed_document_hash"] == hash_before
    assert sig["status"] == "active"  # nova arquitetura: status em vez de campo único
    assert sig["signature_type"] == "manual"  # default


# ============================================================================
# 5. Sign duplicado por (role, user) → 409
# ============================================================================
def test_sign_duplicate_rejected(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    body = {"role": "secretario", "full_name": "Sec. Teste"}
    r1 = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign", json=body, timeout=20)
    assert r1.status_code == 200
    r2 = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign", json=body, timeout=20)
    assert r2.status_code == 409


# ============================================================================
# 6. Revoke preserva hash (diretriz 9 — revoke ≠ supersede)
# ============================================================================
def test_revoke_preserves_hash(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    pub = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20).json()
    hash_orig = pub["snapshot"]["payload_hash_sha256"]
    r = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/revoke",
        json={"rationale": "Erro de emissão detectado — documento será reemitido com correções (test)"},
        timeout=20,
    )
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "revoked"
    assert d["payload_hash_sha256"] == hash_orig
    assert d["revoked_at"] is not None


# ============================================================================
# 7. Rationale curto → 422
# ============================================================================
def test_revoke_rationale_too_short_blocks(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    r = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/revoke",
        json={"rationale": "curto"}, timeout=20,
    )
    assert r.status_code == 422


# ============================================================================
# 8. Schema reservas obrigatórias (diretrizes 5 + 6 + 10)
# ============================================================================
def test_schema_reserved_fields(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    snap = session.get(f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20).json()
    # diretriz 5 — branding congelado
    assert "branding" in snap
    for k in ("mantenedora_name", "school_name", "logo_file_id",
              "primary_color", "secondary_color", "document_footer", "signature_layout"):
        assert k in snap["branding"], f"branding.{k} ausente"
    # diretriz 6 — renders[] array
    assert isinstance(snap["renders"], list)
    # diretriz 10 — semantic_rules_version
    assert snap["semantic_rules_version"] == "1"
    assert snap["schema_version"] == "1"
    assert snap["template_version"] == "diary-v1"
    assert snap["render_engine_version"] == "1"


# ============================================================================
# 9. Snapshot NÃO muda quando attendance é alterado após publicação
# ============================================================================
def test_snapshot_immutable_against_live_db(session):
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    snap_id = _create_unique(session).json()["snapshot"]["id"]
    session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    snap_v1 = session.get(f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20).json()
    hash_v1 = snap_v1["payload_hash_sha256"]
    summary_v1 = snap_v1["payload"]["summary"]["day_status_counts"]

    # Insere attendance "depois" da publicação — para um dia útil dentro do range.
    db.attendance.insert_one({
        "id": str(uuid.uuid4()),
        "class_id": CLASS_ID,
        "date": "2027-04-15",
        "academic_year": 2027,
        "attendance_type": "daily",
        "records": [{"student_id": "x", "status": "P"}],
        "validated_by": None,
        "created_by": "tester",
    })
    try:
        snap_v2 = session.get(f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20).json()
        assert snap_v2["payload_hash_sha256"] == hash_v1
        assert snap_v2["payload"]["summary"]["day_status_counts"] == summary_v1
    finally:
        db.attendance.delete_one({"date": "2027-04-15", "class_id": CLASS_ID})


# ============================================================================
# 10. Render job idempotente: mesmo snapshot publicado 2x → 1 render_job só.
# ============================================================================
def test_render_job_idempotent_on_republish(session):
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    snap_id = _create_unique(session).json()["snapshot"]["id"]
    p1 = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20).json()
    rj1_id = p1["render_job"]["id"]

    # Segunda chamada ao publish — esperado: 409 (já published) E o render_job
    # já criado não duplica (mesmo `idempotency_key`).
    p2 = session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    assert p2.status_code == 409
    # Mas se simularmos um snapshot novo com MESMO idem_key (mesmo source+template+engine),
    # find_existing_job retornaria o mesmo job. Validamos a 1:1 do snapshot:
    jobs = list(db.document_render_jobs.find(
        {"source_snapshot_id": snap_id, "document_type": "diary_period"},
        {"_id": 0, "id": 1, "idempotency_key": 1},
    ))
    assert len(jobs) == 1
    assert jobs[0]["id"] == rj1_id


# ============================================================================
# 11. Worker eventualmente gera renders[] (diretriz 6 — array, não singular)
# ============================================================================
def test_renders_array_populated_after_worker(session):
    snap_id = _create_unique(session).json()["snapshot"]["id"]
    session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    # poll até 15s
    snap = None
    for _ in range(15):
        snap = session.get(f"{BASE_URL}/api/diary/snapshots/{snap_id}", timeout=20).json()
        if snap.get("renders"):
            break
        time.sleep(1)
    assert snap is not None
    assert isinstance(snap["renders"], list)
    assert len(snap["renders"]) >= 1
    r0 = snap["renders"][0]
    assert r0["template_version"] == "diary-v1"
    assert r0["render_engine_version"] == "1"
    assert r0["generated_file_id"]
    assert len(r0["checksum_sha256"]) == 64
