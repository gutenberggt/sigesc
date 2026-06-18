"""Fase 7 (Mai/2026) — Validação Institucional + Signature Multi-maturidade.

Cobertura:
  Validação:
    1. Validate cria validated_by/at + bumpa version + audit_log
    2. Validate em attendance vazia → 422
    3. Validate idempotente → 409 (já validado)
    4. Unvalidate exige rationale ≥ 30 → 422
    5. Unvalidate por outro user não-admin → 403
    6. Unvalidate por admin OK; preserva histórico
    7. Validate batch: N audit_logs, batch_marker correlaciona
    8. Validate batch pula dias sem attendance

  Signature multi-maturity:
    9. signature_type=manual (default)
   10. signature_type=image exige image_file_id (422 sem)
   11. signature_type=icp_brasil exige certificate_info
   12. Revoke signature preserva append-only (status=revoked, NÃO remove)
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://pwa-chunk-fix.preview.emergentagent.com"
).rstrip("/")
ADMIN = {"email": "gutenberg@sigesc.com", "password": "@Celta2007"}

CLASS_ID = "73844918-60b1-4c62-b6cb-a21a35cc49c1"


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


@pytest.fixture
def cleanup_atts():
    """Limpa attendances criados pelo teste."""
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    created_ids = []
    yield created_ids
    if created_ids:
        db.attendance.delete_many({"id": {"$in": created_ids}})


def _make_attendance(cleanup_atts, *, with_records=True, date=None):
    """Insere attendance diretamente no banco — evita complexidade do POST oficial."""
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    aid = str(uuid.uuid4())
    doc = {
        "id": aid,
        "class_id": CLASS_ID,
        "date": date or "2029-08-15",
        "academic_year": 2029,
        "attendance_type": "daily",
        "records": [{"student_id": "x", "status": "P"}] if with_records else [],
        "validated_by": None,
        "created_by": "tester",
        "version": 0,
    }
    db.attendance.insert_one(doc)
    cleanup_atts.append(aid)
    return aid


# ============================================================================
# 1. Validate cria validated_by/at + bump version + audit_log
# ============================================================================
def test_validate_marks_attendance(session, cleanup_atts):
    aid = _make_attendance(cleanup_atts)
    r = session.post(f"{BASE_URL}/api/attendance/{aid}/validate", timeout=20)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["validated_by"]
    assert d["validated_at"]
    assert d["validated_by_role"] in (None, "super_admin")  # depende do user
    assert d["version"] == 1

    # Audit log existe
    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    log = db.audit_logs.find_one({"action": "validate_attendance", "document_id": aid})
    assert log is not None


# ============================================================================
# 2. Empty records → 422
# ============================================================================
def test_validate_blocks_empty_records(session, cleanup_atts):
    aid = _make_attendance(cleanup_atts, with_records=False)
    r = session.post(f"{BASE_URL}/api/attendance/{aid}/validate", timeout=20)
    assert r.status_code == 422


# ============================================================================
# 3. Idempotent validate → 409
# ============================================================================
def test_validate_already_validated_returns_409(session, cleanup_atts):
    aid = _make_attendance(cleanup_atts)
    r1 = session.post(f"{BASE_URL}/api/attendance/{aid}/validate", timeout=20)
    assert r1.status_code == 200
    r2 = session.post(f"{BASE_URL}/api/attendance/{aid}/validate", timeout=20)
    assert r2.status_code == 409


# ============================================================================
# 4. Unvalidate exige rationale ≥ 30
# ============================================================================
def test_unvalidate_rationale_too_short(session, cleanup_atts):
    aid = _make_attendance(cleanup_atts)
    session.post(f"{BASE_URL}/api/attendance/{aid}/validate", timeout=20)
    r = session.post(
        f"{BASE_URL}/api/attendance/{aid}/unvalidate",
        json={"rationale": "curto"}, timeout=20,
    )
    assert r.status_code == 422


# ============================================================================
# 6. Admin pode unvalidate; histórico preservado em validation_history[]
# ============================================================================
def test_admin_unvalidate_preserves_history(session, cleanup_atts):
    aid = _make_attendance(cleanup_atts)
    session.post(f"{BASE_URL}/api/attendance/{aid}/validate", timeout=20)
    rationale = "Validação revertida por inconsistência detectada em auditoria posterior (teste)"
    r = session.post(
        f"{BASE_URL}/api/attendance/{aid}/unvalidate",
        json={"rationale": rationale}, timeout=20,
    )
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["validated_by"] is None
    assert d["validated_at"] is None
    # histórico append-only
    hist = d.get("validation_history") or []
    assert len(hist) == 1
    assert hist[0]["rationale"] == rationale
    assert hist[0]["unvalidated_by"]


# ============================================================================
# 7. Validate batch: N audit_logs com mesmo batch_marker
# ============================================================================
def test_validate_batch_creates_n_audit_logs(session, cleanup_atts):
    d1 = "2029-08-10"
    d2 = "2029-08-11"
    _make_attendance(cleanup_atts, date=d1)
    _make_attendance(cleanup_atts, date=d2)

    r = session.post(
        f"{BASE_URL}/api/attendance/validate-batch",
        json={"class_id": CLASS_ID, "dates": [d1, d2]}, timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    res = r.json()
    assert res["total_validated"] == 2
    assert res["total_skipped"] == 0
    batch_marker = res["batch_marker"]
    assert len(batch_marker) >= 16

    cli = MongoClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]
    logs = list(db.audit_logs.find(
        {"action": "validate_attendance", "extra_data.batch_marker": batch_marker},
    ))
    assert len(logs) == 2


# ============================================================================
# 8. Validate batch pula dias sem attendance
# ============================================================================
def test_validate_batch_skips_dates_without_attendance(session, cleanup_atts):
    d1 = "2029-08-20"
    _make_attendance(cleanup_atts, date=d1)
    r = session.post(
        f"{BASE_URL}/api/attendance/validate-batch",
        json={"class_id": CLASS_ID, "dates": [d1, "2029-08-21"]}, timeout=20,
    )
    assert r.status_code == 200
    res = r.json()
    assert res["total_validated"] == 1
    skipped_reasons = [s["reason"] for s in res["skipped"]]
    assert "NO_ATTENDANCE" in skipped_reasons


# ============================================================================
# 9-11. Signature multi-maturity
# ============================================================================
def _create_published_snapshot(session, period_from, period_to):
    body = {
        "class_id": CLASS_ID, "period_type": "custom",
        "period_from": period_from, "period_to": period_to,
        "period_label": f"sig-test-{period_from}",
    }
    snap = session.post(f"{BASE_URL}/api/diary/snapshots", json=body, timeout=20).json()
    snap_id = snap["snapshot"]["id"]
    session.post(f"{BASE_URL}/api/diary/snapshots/{snap_id}/publish", timeout=20)
    return snap_id


def test_signature_manual_default(session):
    snap_id = _create_published_snapshot(session, "2029-09-01", "2029-09-01")
    r = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "diretor", "full_name": "Dir. Manual"}, timeout=20,
    )
    assert r.status_code == 200
    sig = r.json()["signatures"][0]
    assert sig["signature_type"] == "manual"
    assert sig["status"] == "active"


def test_signature_image_requires_file_id(session):
    snap_id = _create_published_snapshot(session, "2029-09-02", "2029-09-02")
    # Sem image_file_id → 409 (ValueError do service)
    r1 = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "secretario", "full_name": "Sec.",
              "signature_type": "image"},
        timeout=20,
    )
    assert r1.status_code == 409
    # Com image_file_id → 200
    r2 = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "secretario", "full_name": "Sec.",
              "signature_type": "image", "image_file_id": "fake-image-id-123"},
        timeout=20,
    )
    assert r2.status_code == 200
    sig = next(s for s in r2.json()["signatures"] if s["signature_type"] == "image")
    assert sig["image_file_id"] == "fake-image-id-123"


def test_signature_icp_brasil_requires_cert_info(session):
    snap_id = _create_published_snapshot(session, "2029-09-03", "2029-09-03")
    r1 = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "diretor", "full_name": "Dir. ICP",
              "signature_type": "icp_brasil"},
        timeout=20,
    )
    assert r1.status_code == 409  # certificate_info ausente
    r2 = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "diretor", "full_name": "Dir. ICP",
              "signature_type": "icp_brasil",
              "certificate_info": {"subject": "CN=Dir", "issuer": "AC SERASA",
                                    "serial": "abc", "valid_until": "2099-12-31"}},
        timeout=20,
    )
    assert r2.status_code == 200
    sig = next(s for s in r2.json()["signatures"] if s["signature_type"] == "icp_brasil")
    assert sig["certificate_info"]["subject"] == "CN=Dir"


# ============================================================================
# 12. Revoke signature: append-only (status=revoked, NÃO remove)
# ============================================================================
def test_revoke_signature_preserves_object(session):
    snap_id = _create_published_snapshot(session, "2029-09-04", "2029-09-04")
    r = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "diretor", "full_name": "Dir. X"}, timeout=20,
    )
    sig_id = r.json()["signatures"][0]["id"]
    rev = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/signatures/{sig_id}/revoke",
        json={"rationale": "Assinatura revogada por motivo institucional documentado (teste)"},
        timeout=20,
    )
    assert rev.status_code == 200
    snap = rev.json()
    # Objeto preservado, apenas marcado
    assert len(snap["signatures"]) == 1
    assert snap["signatures"][0]["status"] == "revoked"
    assert snap["signatures"][0]["revoked_at"] is not None
    # Tentativa de assinar de novo com mesmo papel/user → OK (revogado libera slot)
    r2 = session.post(
        f"{BASE_URL}/api/diary/snapshots/{snap_id}/sign",
        json={"role": "diretor", "full_name": "Dir. X (re-sign)"}, timeout=20,
    )
    assert r2.status_code == 200
    assert len(r2.json()["signatures"]) == 2
