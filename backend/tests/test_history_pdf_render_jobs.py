"""
E2E test — Histórico Escolar Consolidado via render_jobs + QR Code
(Fase B, Iter 76).

Cobre:
  1. POST /api/students/{id}/historico-consolidado/render-pdf → enfileira
  2. Polling /api/render-jobs/{job_id} → completed
  3. GET /api/render-jobs/{job_id}/file → PDF com QR Code (download)
  4. GET /api/verify/historico/{token} (sem auth) → JSON LGPD-safe
  5. Idempotência
  6. Revogação → endpoint público retorna valid=false
  7. Token inválido / curto
  8. Sem auth → 401/403
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from io import BytesIO

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://multi-tenant-fixed.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
STU_FELIPE = "fix_stu_felipe"


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    csrf = d.get("csrf_token") or ""
    s.headers.update({
        "Authorization": f"Bearer {tok}",
        "X-CSRF-Token": csrf,
        "X-Mantenedora-Id": TENANT,
        "Content-Type": "application/json",
    })
    if s.get(f"{BASE_URL}/api/students/{STU_FELIPE}", timeout=10).status_code == 404:
        pytest.skip("Fixture seed_dependency_diary_fixture ausente.")
    return s


@pytest.fixture
def db():
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        pytest.skip("MONGO_URL não disponível.")
    client = AsyncIOMotorClient(mongo_url)
    yield client[os.environ.get("DB_NAME", "sigesc")]
    client.close()


def _cleanup(db):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(db.document_render_jobs.delete_many(
            {"source_snapshot_id": f"history:{STU_FELIPE}"}
        ))
        loop.run_until_complete(db.history_verifications.delete_many(
            {"student_id": STU_FELIPE}
        ))
        loop.run_until_complete(db.document_files.delete_many(
            {"student_id": STU_FELIPE, "document_type": "history"}
        ))
    finally:
        loop.close()


def _wait(auth, job_id: str, timeout_s: float = 25.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = auth.get(f"{BASE_URL}/api/render-jobs/{job_id}", timeout=10)
        assert r.status_code == 200
        job = r.json().get("job") or r.json()
        if job.get("status") in ("completed", "failed", "superseded"):
            return job
        time.sleep(1)
    pytest.fail(f"Job {job_id} não finalizou em {timeout_s}s")


def test_full_flow_history_request_poll_download_verify(auth, db):
    _cleanup(db)
    # 1) Enfileira
    r = auth.post(f"{BASE_URL}/api/students/{STU_FELIPE}/historico-consolidado/render-pdf", timeout=15)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    job_id = body["id"]
    assert body.get("idempotent_hit") is False

    # 2) Polling
    job = _wait(auth, job_id)
    assert job.get("status") == "completed", f"status={job.get('status')} err={job.get('error_message')}"
    pdf_hash = job["pdf_hash_sha256"]
    assert pdf_hash

    # 3) Download (Content-Disposition: attachment + X-PDF-SHA256)
    rd = auth.get(f"{BASE_URL}/api/render-jobs/{job_id}/file", timeout=30)
    assert rd.status_code == 200
    assert rd.headers.get("content-type", "").startswith("application/pdf")
    assert rd.headers.get("content-disposition", "").startswith("attachment;")
    assert rd.headers.get("x-pdf-sha256") == pdf_hash
    assert rd.content.startswith(b"%PDF-")
    assert hashlib.sha256(rd.content).hexdigest() == pdf_hash

    # 4) Verificação pública
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(rd.content)) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
        m = re.search(r"/verify/historico/([A-Za-z0-9_-]+)", txt)
        assert m, "URL de verificação não encontrada no PDF"
        token = m.group(1)
    except ImportError:
        pytest.skip("pdfplumber indisponível.")

    rv = requests.get(f"{BASE_URL}/api/verify/historico/{token}", timeout=10)
    assert rv.status_code == 200
    vd = rv.json()
    assert vd.get("valid") is True
    assert vd.get("document_type") == "Histórico Escolar Consolidado"
    assert vd.get("pdf_sha256") == pdf_hash
    assert vd.get("student_name")
    assert isinstance(vd.get("years_covered"), list)
    assert isinstance(vd.get("records_count"), int)
    # LGPD: NÃO expõe notas detalhadas
    assert "grades" not in vd
    assert "scores" not in vd


def test_history_idempotency(auth):
    r1 = auth.post(f"{BASE_URL}/api/students/{STU_FELIPE}/historico-consolidado/render-pdf", timeout=15)
    r2 = auth.post(f"{BASE_URL}/api/students/{STU_FELIPE}/historico-consolidado/render-pdf", timeout=15)
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json().get("idempotent_hit") is True


def test_verify_history_invalid_token_returns_404():
    r = requests.get(f"{BASE_URL}/api/verify/historico/invalid_xxxxxxx", timeout=10)
    assert r.status_code == 404


def test_verify_history_short_token_returns_400():
    r = requests.get(f"{BASE_URL}/api/verify/historico/abc", timeout=10)
    assert r.status_code == 400


def test_verify_history_revoked(auth, db):
    """Marca como revogado e checa que endpoint público retorna valid=false."""
    r = auth.post(f"{BASE_URL}/api/students/{STU_FELIPE}/historico-consolidado/render-pdf", timeout=15)
    job_id = r.json()["id"]
    _wait(auth, job_id)
    rd = auth.get(f"{BASE_URL}/api/render-jobs/{job_id}/file", timeout=30)
    try:
        import pdfplumber
        with pdfplumber.open(BytesIO(rd.content)) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
        m = re.search(r"/verify/historico/([A-Za-z0-9_-]+)", txt)
    except ImportError:
        pytest.skip("pdfplumber indisponível.")
    assert m
    token = m.group(1)

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(db.history_verifications.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked_at": "2026-12-31T00:00:00+00:00", "revoked_by": "test"}}
        ))
    finally:
        loop.close()

    rv = requests.get(f"{BASE_URL}/api/verify/historico/{token}", timeout=10)
    assert rv.status_code == 200
    vd = rv.json()
    assert vd.get("valid") is False
    assert vd.get("revoked") is True


def test_history_render_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/students/{STU_FELIPE}/historico-consolidado/render-pdf",
        timeout=10,
    )
    assert r.status_code in (401, 403)
