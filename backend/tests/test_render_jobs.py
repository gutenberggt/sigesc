"""
Testes — Render Jobs (Passo 4 — Fev/2026).

Escopo MÍNIMO autorizado pelo owner:
- Idempotência por (snapshot, type, template_v, engine_v).
- Status pending → processing → completed.
- Retry exponencial básico (3 tentativas).
- Falha permanente após max_retries.
- force_reissue cria novo job.
- NO_HANDLER_REGISTERED → failed sem retry.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.render_worker import process_one_job  # noqa: E402
from utils.render_jobs import (  # noqa: E402
    MAX_RETRIES,
    RETRY_BACKOFF_SECONDS,
    compute_idempotency_key,
    compute_next_retry_at,
    ensure_indexes,
    register_render_handler,
)


SNAPSHOT_ID = "snap_rj_test_v1"
DOC_TYPE = "dependency_completion"
TEMPLATE = "test_v1.0.0"
ENGINE = "stub-1.0"
MANT = "rj_mant_v1"


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    await ensure_indexes(db)
    yield db
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup(db):
    await db.document_render_jobs.delete_many({"source_snapshot_id": SNAPSHOT_ID})
    yield
    await db.document_render_jobs.delete_many({"source_snapshot_id": SNAPSHOT_ID})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _seed_pending_job(db, *, idempotency_key: str | None = None, retry_count: int = 0,
                             next_retry_at: str | None = None, doc_type: str = DOC_TYPE) -> str:
    import uuid
    job_id = str(uuid.uuid4())
    key = idempotency_key or compute_idempotency_key(
        source_snapshot_id=SNAPSHOT_ID, document_type=doc_type,
        template_version=TEMPLATE, render_engine_version=ENGINE,
    )
    await db.document_render_jobs.insert_one({
        "id": job_id,
        "idempotency_key": key,
        "document_type": doc_type,
        "source_snapshot_id": SNAPSHOT_ID,
        "source_collection": "dependency_completions",
        "template_version": TEMPLATE,
        "render_engine_version": ENGINE,
        "render_options": {},
        "payload_hash": "h",
        "status": "pending",
        "retry_count": retry_count,
        "max_retries": MAX_RETRIES,
        "next_retry_at": next_retry_at,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "generated_file_id": None,
        "generated_file_size_bytes": None,
        "generated_at": None,
        "pdf_hash_sha256": None,
        "error_message": None,
        "requested_by_user_id": "u",
        "requested_at": _now_iso(),
        "request_ip": None,
        "request_user_agent": "",
        "mantenedora_id": MANT,
        "school_id": None,
        "audit_trail": [],
    })
    return job_id


# ===========================================================================
# Pure logic
# ===========================================================================
def test_idempotency_key_is_deterministic():
    k1 = compute_idempotency_key(
        source_snapshot_id="s1", document_type="bulletin",
        template_version="v1", render_engine_version="e1",
    )
    k2 = compute_idempotency_key(
        source_snapshot_id="s1", document_type="bulletin",
        template_version="v1", render_engine_version="e1",
    )
    assert k1 == k2 and len(k1) == 64

    k3 = compute_idempotency_key(
        source_snapshot_id="s1", document_type="bulletin",
        template_version="v2", render_engine_version="e1",
    )
    assert k1 != k3


def test_retry_backoff_progression():
    assert compute_next_retry_at(MAX_RETRIES) is None
    assert compute_next_retry_at(MAX_RETRIES + 1) is None

    nxt = compute_next_retry_at(0)
    assert nxt is not None
    delta = datetime.fromisoformat(nxt.replace("Z", "+00:00")) - datetime.now(timezone.utc)
    # ~30s ± tolerance
    assert 25 <= delta.total_seconds() <= 35

    nxt2 = compute_next_retry_at(1)
    delta2 = datetime.fromisoformat(nxt2.replace("Z", "+00:00")) - datetime.now(timezone.utc)
    # ~120s
    assert 115 <= delta2.total_seconds() <= 125


def test_retry_backoff_table_matches_contract():
    assert RETRY_BACKOFF_SECONDS == (30, 120, 600)


# ===========================================================================
# Worker behavior
# ===========================================================================
@pytest.mark.asyncio
async def test_worker_completes_successful_job(db):
    async def ok_handler(job: dict) -> dict:
        return {
            "generated_file_id": "f_test_001",
            "generated_file_size_bytes": 12345,
            "pdf_hash_sha256": "abc" * 21 + "x",
        }
    register_render_handler(DOC_TYPE, ok_handler)

    job_id = await _seed_pending_job(db)
    did = await process_one_job(db)
    assert did is True

    job = await db.document_render_jobs.find_one({"id": job_id}, {"_id": 0})
    assert job["status"] == "completed"
    assert job["generated_file_id"] == "f_test_001"
    assert job["generated_file_size_bytes"] == 12345
    assert job["completed_at"] is not None
    actions = [a["action"] for a in job["audit_trail"]]
    assert "processing" in actions and "completed" in actions


@pytest.mark.asyncio
async def test_worker_retries_on_failure_then_succeeds(db):
    attempts = {"n": 0}

    async def flaky_handler(job: dict) -> dict:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError(f"transient error #{attempts['n']}")
        return {"generated_file_id": "ok"}

    register_render_handler(DOC_TYPE, flaky_handler)

    job_id = await _seed_pending_job(db)
    # 1ª iteração: falha → retry agendado (status volta a pending com next_retry_at no futuro).
    await process_one_job(db)
    job = await db.document_render_jobs.find_one({"id": job_id}, {"_id": 0})
    assert job["status"] == "pending"
    assert job["retry_count"] == 1
    assert job["next_retry_at"] is not None

    # Sem mexer em next_retry_at, worker NÃO deve pegar o job (porque está no futuro).
    did = await process_one_job(db)
    assert did is False

    # Forçar next_retry_at para o passado (simula passagem de tempo).
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    await db.document_render_jobs.update_one({"id": job_id}, {"$set": {"next_retry_at": past}})

    # 2ª iteração: sucesso.
    await process_one_job(db)
    job = await db.document_render_jobs.find_one({"id": job_id}, {"_id": 0})
    assert job["status"] == "completed"
    assert job["retry_count"] == 1


@pytest.mark.asyncio
async def test_worker_marks_failed_after_max_retries(db):
    async def always_fails(job: dict) -> dict:
        raise RuntimeError("boom")
    register_render_handler(DOC_TYPE, always_fails)

    job_id = await _seed_pending_job(db)

    # Roda MAX_RETRIES iterações forçando next_retry_at para passado entre elas.
    for _ in range(MAX_RETRIES):
        await process_one_job(db)
        # adianta o relógio se ainda não esgotou
        await db.document_render_jobs.update_one(
            {"id": job_id, "status": "pending"},
            {"$set": {"next_retry_at": (datetime.now(timezone.utc) - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")}},
        )

    job = await db.document_render_jobs.find_one({"id": job_id}, {"_id": 0})
    assert job["status"] == "failed"
    assert job["retry_count"] == MAX_RETRIES
    assert job["next_retry_at"] is None
    assert "boom" in (job.get("error_message") or "")


@pytest.mark.asyncio
async def test_worker_no_handler_fails_permanent(db):
    # Usa um document_type sem handler registrado.
    # Limpa a registry para garantir
    from utils.render_jobs import _HANDLERS
    _HANDLERS.pop("history", None)

    job_id = await _seed_pending_job(db, doc_type="history")
    await process_one_job(db)
    job = await db.document_render_jobs.find_one({"id": job_id}, {"_id": 0})
    assert job["status"] == "failed"
    assert "NO_HANDLER_REGISTERED" in (job.get("error_message") or "")
    # Sem retry agendado.
    assert job["next_retry_at"] is None
    assert job["retry_count"] == 0


@pytest.mark.asyncio
async def test_worker_returns_false_when_queue_empty(db):
    did = await process_one_job(db)
    assert did is False


@pytest.mark.asyncio
async def test_worker_skips_jobs_with_future_retry(db):
    async def ok(_):
        return {}
    register_render_handler(DOC_TYPE, ok)

    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    await _seed_pending_job(db, retry_count=1, next_retry_at=future)
    did = await process_one_job(db)
    assert did is False


@pytest.mark.asyncio
async def test_worker_picks_oldest_first(db):
    async def ok(_):
        return {"generated_file_id": "f"}
    register_render_handler(DOC_TYPE, ok)

    # Cria 2 jobs com idempotency keys distintas
    j1 = await _seed_pending_job(db, idempotency_key="key_old")
    await asyncio.sleep(0.05)
    j2 = await _seed_pending_job(db, idempotency_key="key_new")

    # Fixa requested_at distintos
    await db.document_render_jobs.update_one({"id": j1}, {"$set": {"requested_at": "2026-01-01T00:00:00Z"}})
    await db.document_render_jobs.update_one({"id": j2}, {"$set": {"requested_at": "2026-02-01T00:00:00Z"}})

    await process_one_job(db)
    j1_doc = await db.document_render_jobs.find_one({"id": j1})
    j2_doc = await db.document_render_jobs.find_one({"id": j2})
    assert j1_doc["status"] == "completed"
    assert j2_doc["status"] == "pending"
