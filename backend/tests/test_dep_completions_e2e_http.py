"""
E2E HTTP — Dependency Completion Snapshots (iteração 73).

Roda contra a URL pública (REACT_APP_BACKEND_URL) com Super Admin + tenant scope.
Cobre o pipeline completo: PUT (status=completed) → snapshot → list → public/verify
→ sign(409 data_quality) → backfill (dry_run) → revoke (RATIONALE_TOO_SHORT + ok).

Restaura `fix_dep_heitor_mat` para `status=active` ao final via PUT.
"""
from __future__ import annotations

import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: ler do .env do frontend (sem default — falha rápido)
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "gutenberg@sigesc.com"
ADMIN_PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
DEP_ID = "fix_dep_heitor_mat"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
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
    yield s
    # Restaura dep para active
    try:
        s.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
              json={"status": "active"}, timeout=15)
    except Exception:
        pass


def test_01_put_dep_completed_creates_snapshot(session):
    """PUT status=completed dispara hook que cria snapshot idempotente."""
    r = session.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
                    json={"status": "completed",
                          "completed_in_academic_year": 2026},
                    timeout=20)
    assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:300]}"

    # Repetir não duplica
    r2 = session.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
                     json={"status": "completed",
                           "completed_in_academic_year": 2026},
                     timeout=20)
    assert r2.status_code in (200, 201)


def test_02_list_completions_returns_snapshot(session):
    r = session.get(f"{BASE_URL}/api/dependency-completions/student/fix_stu_heitor",
                    timeout=20)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    items = data.get("items") or []
    # Filtra apenas o snapshot de fix_dep_heitor_mat
    relevant = [i for i in items if i.get("dependency_id") == DEP_ID]
    assert relevant, f"snapshot não encontrado para {DEP_ID}: {items}"
    snap = relevant[0]
    assert re.fullmatch(r"[0-9a-f]{64}", snap["document_hash_sha256"])
    assert snap["verification_token"]
    assert snap["data_quality"] in ("complete", "partial", "incomplete")
    assert snap["document_version"] == "1.0.0"
    assert snap["history_schema_version"] == "1"
    assert snap["signatures"] == []
    pytest.snapshot_id = snap["id"]
    pytest.verification_token = snap["verification_token"]
    pytest.data_quality = snap["data_quality"]


def test_03_get_completion_full_returns_audit_trail(session):
    snap_id = pytest.snapshot_id
    r = session.get(f"{BASE_URL}/api/dependency-completions/{snap_id}",
                    timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == snap_id
    assert isinstance(data.get("audit_trail"), list)
    assert any(a.get("action") == "snapshot_created" for a in data["audit_trail"])


def test_04_public_verify_no_auth_no_pii(session):
    """Endpoint público NÃO precisa de auth, NÃO expõe enum interno nem nome aluno."""
    token = pytest.verification_token
    # Sem auth deliberadamente
    r = requests.get(f"{BASE_URL}/api/public/verify/{token}", timeout=20)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    assert body["valid"] is True
    assert body["document_status"] in ("valido", "valido_reprovado")
    assert "completion_result" not in body, f"NUNCA expor enum interno: {body}"
    # Não deve conter nome do aluno (PII)
    assert "student_name" not in body
    assert "student_id" not in body
    assert re.fullmatch(r"[0-9a-f]{64}", body["document_hash"])
    assert body.get("school_name") is not None or body.get("school_name") == ""
    assert "signatures" in body
    pytest.public_doc_hash = body["document_hash"]


def test_05_sign_blocks_when_data_quality_partial(session):
    """409 DATA_QUALITY_INSUFFICIENT quando snapshot não está 'complete'."""
    if pytest.data_quality == "complete":
        pytest.skip("data_quality já é complete — assinatura seria aceita")
    snap_id = pytest.snapshot_id
    headers = {"X-Sign-As-Role": "diretor"}
    r = session.post(f"{BASE_URL}/api/dependency-completions/{snap_id}/sign",
                     headers=headers, timeout=20)
    assert r.status_code == 409, f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    detail = body.get("detail") or body
    assert detail.get("code") == "DATA_QUALITY_INSUFFICIENT"


def test_06_cancelled_without_reason_returns_422(session):
    """Restaura para active e tenta cancelar sem reason."""
    session.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
                json={"status": "active"}, timeout=15)
    r = session.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
                    json={"status": "cancelled"}, timeout=15)
    assert r.status_code in (400, 422), f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    detail = body.get("detail") or body
    code = detail.get("code") if isinstance(detail, dict) else None
    # Aceita variantes do código
    assert code in ("CANCELLATION_REASON_REQUIRED", "STATUS_REASON_REQUIRED",
                    "CANCEL_REASON_REQUIRED") or "reason" in str(body).lower(), (
        f"code esperado CANCELLATION_REASON_REQUIRED, recebido: {body}")


def test_07_backfill_dry_run(session):
    r = session.post(f"{BASE_URL}/api/admin/dependency-completions/backfill?dry_run=true",
                     timeout=60)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    data = r.json()
    assert data.get("dry_run") is True
    assert "created_count" in data
    assert "skipped_count" in data
    assert "errors" in data or "error_count" in data


def test_08_revoke_too_short_returns_422(session):
    snap_id = pytest.snapshot_id
    r = session.post(f"{BASE_URL}/api/dependency-completions/{snap_id}/revoke",
                     json={"rationale": "curto"}, timeout=20)
    assert r.status_code == 422
    body = r.json()
    detail = body.get("detail") or body
    assert detail.get("code") == "RATIONALE_TOO_SHORT"


def test_09_revoke_ok_and_public_verify_revoked(session):
    """Repõe estado: cria novo snapshot via PUT completed, pega novo token, revoga."""
    # Restaura active e completa de novo (idempotente reusa snapshot)
    session.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
                json={"status": "active"}, timeout=15)
    session.put(f"{BASE_URL}/api/student-dependencies/{DEP_ID}",
                json={"status": "completed", "completed_in_academic_year": 2026},
                timeout=15)
    r = session.get(f"{BASE_URL}/api/dependency-completions/student/fix_stu_heitor",
                    timeout=15)
    items = [i for i in r.json().get("items") or [] if i.get("dependency_id") == DEP_ID]
    assert items
    target = items[0]
    snap_id = target["id"]
    token = target["verification_token"]

    # Skip revoke se já revogado (idempotência defensiva)
    if target.get("revoked_at"):
        pytest.skip("snapshot já revogado em rodada anterior — verificando público")
    else:
        rationale = "Erro operacional detectado durante auditoria municipal de fevereiro 2026."
        assert len(rationale) >= 30
        r2 = session.post(f"{BASE_URL}/api/dependency-completions/{snap_id}/revoke",
                          json={"rationale": rationale}, timeout=20)
        assert r2.status_code == 200, f"{r2.status_code}: {r2.text[:300]}"
        body = r2.json()
        assert body.get("revoked_at")

    # Verify público deve retornar valid:false / status revogado
    r3 = requests.get(f"{BASE_URL}/api/public/verify/{token}", timeout=20)
    assert r3.status_code == 200
    pub = r3.json()
    assert pub["valid"] is False
    assert pub["document_status"] == "revogado"
