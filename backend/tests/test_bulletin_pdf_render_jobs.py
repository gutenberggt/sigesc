"""
E2E test — Boletim Oficial PDF via render_jobs + QR Code (Fase A, Iter 76).

Cobre o fluxo completo:
  1. POST /api/bulletins/{student_id}/render-pdf → enfileira job
  2. Polling /api/render-jobs/{job_id} → completed
  3. GET /api/render-jobs/{job_id}/file → PDF com QR Code
  4. GET /api/verify/boletim/{token} (sem auth) → JSON LGPD-safe
  5. Idempotência: chamadas subsequentes retornam o mesmo job
  6. Revogação: marcar revoked_at em bulletin_verifications → endpoint retorna valid=false
  7. Token inválido → 404
"""
from __future__ import annotations

import asyncio
import os
import re
import time

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "https://school-integrity-fix.preview.emergentagent.com")
    .rstrip("/")
)
EMAIL = "gutenberg@sigesc.com"
PASSWORD = "@Celta2007"
TENANT = "fix_mant_v1"
STU_FELIPE = "fix_stu_felipe"
YEAR = 2026


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
            {"source_snapshot_id": f"boletim:{STU_FELIPE}:{YEAR}"}
        ))
        loop.run_until_complete(db.bulletin_verifications.delete_many(
            {"student_id": STU_FELIPE, "academic_year": YEAR}
        ))
        loop.run_until_complete(db.document_files.delete_many(
            {"student_id": STU_FELIPE, "document_type": "bulletin"}
        ))
    finally:
        loop.close()


def _wait_completion(auth, job_id: str, timeout_s: float = 20.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = auth.get(f"{BASE_URL}/api/render-jobs/{job_id}", timeout=10)
        assert r.status_code == 200, r.text[:200]
        job = r.json().get("job") or r.json()
        if job.get("status") in ("completed", "failed", "superseded"):
            return job
        time.sleep(1)
    pytest.fail(f"Job {job_id} não finalizou em {timeout_s}s")


def test_full_flow_request_poll_download_verify(auth, db):
    """E2E completo da Fase A."""
    _cleanup(db)
    # 1) Enfileira
    r = auth.post(f"{BASE_URL}/api/bulletins/{STU_FELIPE}/render-pdf",
                  params={"academic_year": YEAR}, timeout=15)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    job_id = body["id"]
    assert body.get("idempotent_hit") is False

    # 2) Polling
    job = _wait_completion(auth, job_id, timeout_s=20)
    assert job.get("status") == "completed", f"status={job.get('status')} err={job.get('error_message')}"
    assert job.get("generated_file_id")
    assert job.get("pdf_hash_sha256")
    pdf_hash = job["pdf_hash_sha256"]

    # 3) Download
    rd = auth.get(f"{BASE_URL}/api/render-jobs/{job_id}/file", timeout=30)
    assert rd.status_code == 200, rd.text[:200]
    assert rd.headers.get("content-type", "").startswith("application/pdf")
    assert rd.headers.get("content-disposition", "").startswith("attachment;")
    assert rd.headers.get("x-pdf-sha256") == pdf_hash
    assert rd.content.startswith(b"%PDF-")
    # Hash do conteúdo bate
    import hashlib
    assert hashlib.sha256(rd.content).hexdigest() == pdf_hash

    # 4) Verificação pública — extrai token do PDF
    try:
        import pdfplumber
        from io import BytesIO
        with pdfplumber.open(BytesIO(rd.content)) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
        m = re.search(r"/verify/boletim/([A-Za-z0-9_-]+)", txt)
        assert m, f"URL do QR não encontrada no PDF. texto[:500]={txt[:500]}"
        token = m.group(1)
    except ImportError:
        pytest.skip("pdfplumber indisponível para extrair token do PDF.")

    # GET PÚBLICO (sem auth!)
    rv = requests.get(f"{BASE_URL}/api/verify/boletim/{token}", timeout=10)
    assert rv.status_code == 200, rv.text[:200]
    vd = rv.json()
    assert vd.get("valid") is True
    assert vd.get("document_type") == "Boletim Escolar Oficial"
    assert vd.get("academic_year") == YEAR
    assert vd.get("pdf_sha256") == pdf_hash
    assert vd.get("student_name")  # nome do aluno
    assert vd.get("school_name")
    # LGPD: NÃO deve expor notas detalhadas
    assert "grades" not in vd
    assert "scores" not in vd


def test_idempotency_returns_same_job(auth, db):
    """Segunda chamada com mesmos parâmetros retorna mesmo job_id."""
    r1 = auth.post(f"{BASE_URL}/api/bulletins/{STU_FELIPE}/render-pdf",
                   params={"academic_year": YEAR}, timeout=15)
    assert r1.status_code == 200
    id1 = r1.json()["id"]

    r2 = auth.post(f"{BASE_URL}/api/bulletins/{STU_FELIPE}/render-pdf",
                   params={"academic_year": YEAR}, timeout=15)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["id"] == id1
    assert body2.get("idempotent_hit") is True


def test_verify_invalid_token_returns_404(auth):
    r = requests.get(f"{BASE_URL}/api/verify/boletim/invalid_xxxxxxx", timeout=10)
    assert r.status_code == 404


def test_verify_short_token_returns_400(auth):
    r = requests.get(f"{BASE_URL}/api/verify/boletim/abc", timeout=10)
    assert r.status_code == 400


def test_verify_revoked_returns_invalid(auth, db):
    """Marca documento como revogado → endpoint público retorna valid=false."""
    # Garante que existe um documento (pode reusar do test_full_flow)
    r = auth.post(f"{BASE_URL}/api/bulletins/{STU_FELIPE}/render-pdf",
                  params={"academic_year": YEAR}, timeout=15)
    job_id = r.json()["id"]
    _wait_completion(auth, job_id, timeout_s=20)

    # Baixa PDF para extrair token
    rd = auth.get(f"{BASE_URL}/api/render-jobs/{job_id}/file", timeout=30)
    try:
        import pdfplumber
        from io import BytesIO
        with pdfplumber.open(BytesIO(rd.content)) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
        m = re.search(r"/verify/boletim/([A-Za-z0-9_-]+)", txt)
    except ImportError:
        pytest.skip("pdfplumber indisponível.")
    assert m
    token = m.group(1)

    # Marca como revogado direto no DB
    import hashlib
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(db.bulletin_verifications.update_one(
            {"token_hash": token_hash},
            {"$set": {"revoked_at": "2026-12-31T00:00:00+00:00", "revoked_by": "test"}}
        ))
    finally:
        loop.close()

    rv = requests.get(f"{BASE_URL}/api/verify/boletim/{token}", timeout=10)
    assert rv.status_code == 200
    vd = rv.json()
    assert vd.get("valid") is False
    assert vd.get("revoked") is True


def test_unauthorized_request_pdf_returns_403_or_401(auth):
    """Endpoint de enfileiramento exige auth."""
    r = requests.post(
        f"{BASE_URL}/api/bulletins/{STU_FELIPE}/render-pdf",
        params={"academic_year": YEAR}, timeout=10,
    )
    assert r.status_code in (401, 403)
