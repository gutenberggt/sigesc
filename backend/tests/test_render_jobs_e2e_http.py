"""
E2E HTTP — Render Jobs (Passo 4 — Fev/2026).

Cobre os endpoints expostos por routers/render_jobs.py:
01. POST /api/render-jobs cria job pending (idempotent_hit=False).
02. POST idempotente (mesmo source+type+template+engine) retorna mesmo id (idempotent_hit=True).
03. POST com force_reissue=true cria NOVO job e marca o anterior superseded (se ainda pending).
04. GET /api/render-jobs/{id} retorna status atual.
05. GET /api/render-jobs?source_snapshot_id=... lista jobs com paginação.
06. POST /api/render-jobs/{id}/retry exige role admin+ — força retry de job failed.
07. POST com document_type inválido → 422 INVALID_DOCUMENT_TYPE.
"""
from __future__ import annotations

import asyncio
import os

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

SNAPSHOT_ID = "snap_e2e_rj_v1"
DOC_TYPE = "dependency_completion"
TEMPLATE = "e2e_test_v1.0.0"
ENGINE = "e2e-stub-1.0"


@pytest.fixture(scope="module")
def session():
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
    yield s


@pytest.fixture(scope="module", autouse=True)
def _cleanup_db():
    """Cleanup global da fila para o snapshot de teste antes/depois."""
    async def _do():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        await db.document_render_jobs.delete_many({"source_snapshot_id": SNAPSHOT_ID})
        client.close()
    asyncio.run(_do())
    yield
    asyncio.run(_do())


def _payload(*, force_reissue: bool = False, doc_type: str = DOC_TYPE,
             template: str = TEMPLATE) -> dict:
    return {
        "document_type": doc_type,
        "source_snapshot_id": SNAPSHOT_ID,
        "source_collection": "dependency_completions",
        "template_version": template,
        "render_engine_version": ENGINE,
        "render_options": {"page_size": "A4", "include_qr": True},
        "force_reissue": force_reissue,
    }


# ===========================================================================
def test_01_create_job_pending(session):
    r = session.post(f"{BASE_URL}/api/render-jobs", json=_payload(), timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["idempotent_hit"] is False
    assert body["job"]["template_version"] == TEMPLATE
    assert body["job"]["mantenedora_id"] == TENANT
    pytest.shared_job_id = body["id"]


def test_02_create_idempotent_returns_existing(session):
    r = session.post(f"{BASE_URL}/api/render-jobs", json=_payload(), timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["idempotent_hit"] is True
    assert body["id"] == pytest.shared_job_id


def test_03_get_job_returns_status(session):
    r = session.get(f"{BASE_URL}/api/render-jobs/{pytest.shared_job_id}", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == pytest.shared_job_id
    assert body["status"] in ("pending", "processing", "completed", "failed")
    # Sem handler real registrado, esperamos failed (NO_HANDLER_REGISTERED) — worker corre em loop.


def test_04_list_jobs_by_snapshot(session):
    r = session.get(
        f"{BASE_URL}/api/render-jobs",
        params={"source_snapshot_id": SNAPSHOT_ID},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == pytest.shared_job_id for it in body["items"])


def test_05_invalid_document_type_returns_422(session):
    r = session.post(
        f"{BASE_URL}/api/render-jobs",
        json=_payload(doc_type="not_a_real_type"),
        timeout=30,
    )
    assert r.status_code == 422
    detail = r.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "INVALID_DOCUMENT_TYPE"


def test_06_force_reissue_creates_new_job(session):
    # Aguarda worker eventualmente terminar o anterior (failed por NO_HANDLER) — até 8s
    for _ in range(16):
        r = session.get(f"{BASE_URL}/api/render-jobs/{pytest.shared_job_id}", timeout=30)
        if r.status_code == 200 and r.json().get("status") in ("completed", "failed"):
            break
        import time as _t
        _t.sleep(0.5)

    r = session.post(
        f"{BASE_URL}/api/render-jobs",
        json=_payload(force_reissue=True),
        timeout=30,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["idempotent_hit"] is False
    assert body["id"] != pytest.shared_job_id
    pytest.reissued_job_id = body["id"]


def test_07_retry_failed_job(session):
    # Aguarda o reissued chegar em failed (NO_HANDLER → falha imediata permanente)
    for _ in range(16):
        r = session.get(f"{BASE_URL}/api/render-jobs/{pytest.reissued_job_id}", timeout=30)
        if r.status_code == 200 and r.json().get("status") == "failed":
            break
        import time as _t
        _t.sleep(0.5)

    final = session.get(f"{BASE_URL}/api/render-jobs/{pytest.reissued_job_id}", timeout=30).json()
    assert final["status"] == "failed", f"esperava failed, veio {final.get('status')}"

    # Force retry como super_admin → volta a pending
    r = session.post(
        f"{BASE_URL}/api/render-jobs/{pytest.reissued_job_id}/retry",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"


def test_08_404_unknown_job(session):
    r = session.get(f"{BASE_URL}/api/render-jobs/never_existed_xxx", timeout=30)
    assert r.status_code == 404


def test_09_unauthenticated_401_or_403():
    r = requests.post(f"{BASE_URL}/api/render-jobs", json=_payload(), timeout=30)
    assert r.status_code in (401, 403)
