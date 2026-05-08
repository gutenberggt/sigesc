"""
Render Worker — single-process, in-asyncio, mínimo viável.

[Fev/2026] Passo 4. Owner explicitou: "worker simples já resolve;
overengineering proibido nesta fase".

Loop:
  while True:
    1. busca 1 job pending OU failed-com-retry-elegível (next_retry_at <= now)
    2. marca processing (compare-and-set por idempotency_key)
    3. invoca handler registrado para document_type
    4. sucesso → completed; exception → retry (se sobra) ou failed permanente
    5. sleep POLL_INTERVAL_SECONDS

Sem fila externa. Sem worker pool. Sem broker.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from utils.render_jobs import (
    MAX_RETRIES,
    compute_next_retry_at,
    get_render_handler,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _claim_next_job(db) -> dict | None:
    """Atomicamente reivindica o próximo job processável.

    Critério: status pending E (next_retry_at == null OR next_retry_at <= now).
    Marca como processing. Retorna o job ou None.
    """
    now = _now_iso()
    job = await db.document_render_jobs.find_one_and_update(
        {
            "status": "pending",
            "$or": [
                {"next_retry_at": None},
                {"next_retry_at": {"$lte": now}},
            ],
        },
        {
            "$set": {
                "status": "processing",
                "started_at": now,
            },
            "$push": {
                "audit_trail": {
                    "action": "processing",
                    "at": now,
                },
            },
        },
        sort=[("requested_at", 1)],
        return_document=True,
        projection={"_id": 0},
    )
    return job


async def _mark_completed(db, *, job_id: str, result: dict, started_at: str | None) -> None:
    duration_ms = None
    if started_at:
        try:
            t0 = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        except (ValueError, TypeError):
            duration_ms = None

    now = _now_iso()
    await db.document_render_jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "status": "completed",
                "completed_at": now,
                "generated_at": now,
                "generated_file_id": result.get("generated_file_id"),
                "generated_file_size_bytes": result.get("generated_file_size_bytes"),
                "pdf_hash_sha256": result.get("pdf_hash_sha256"),
                "error_message": None,
            },
            "$push": {
                "audit_trail": {
                    "action": "completed",
                    "at": now,
                    "duration_ms": duration_ms,
                    "file_id": result.get("generated_file_id"),
                },
            },
        },
    )


async def _mark_failed_or_retry(
    db, *, job_id: str, retry_count: int, error_message: str
) -> None:
    """Decide entre retry agendado ou falha permanente."""
    now = _now_iso()
    new_retry_count = retry_count + 1

    if new_retry_count >= MAX_RETRIES:
        # Falha permanente.
        await db.document_render_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "retry_count": new_retry_count,
                    "next_retry_at": None,
                    "failed_at": now,
                    "error_message": error_message[:1024],
                },
                "$push": {
                    "audit_trail": {
                        "action": "failed_permanent",
                        "at": now,
                        "error": error_message[:512],
                    },
                },
            },
        )
        return

    # Retry agendado.
    next_retry = compute_next_retry_at(new_retry_count)
    await db.document_render_jobs.update_one(
        {"id": job_id},
        {
            "$set": {
                "status": "pending",
                "retry_count": new_retry_count,
                "next_retry_at": next_retry,
                "error_message": error_message[:1024],
            },
            "$push": {
                "audit_trail": {
                    "action": "retry_scheduled",
                    "at": now,
                    "retry_count": new_retry_count,
                    "next_retry_at": next_retry,
                    "error": error_message[:512],
                },
            },
        },
    )


async def process_one_job(db) -> bool:
    """Processa UM job. Retorna True se algo foi feito; False se fila vazia."""
    job = await _claim_next_job(db)
    if not job:
        return False

    job_id = job["id"]
    document_type = job["document_type"]
    handler = get_render_handler(document_type)

    if handler is None:
        # Sem handler: erro NÃO recuperável → failed permanente sem retry.
        now = _now_iso()
        await db.document_render_jobs.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "next_retry_at": None,
                    "failed_at": now,
                    "error_message": f"NO_HANDLER_REGISTERED for document_type={document_type}",
                },
                "$push": {
                    "audit_trail": {
                        "action": "failed_no_handler",
                        "at": now,
                    },
                },
            },
        )
        logger.error("[render_worker] no handler for document_type=%s job=%s", document_type, job_id)
        return True

    try:
        result = await handler(job) or {}
        if not isinstance(result, dict):
            result = {}
        await _mark_completed(db, job_id=job_id, result=result, started_at=job.get("started_at"))
        logger.info("[render_worker] job %s completed (type=%s)", job_id, document_type)
    except Exception as e:  # noqa: BLE001 — handler pode lançar qualquer coisa
        logger.exception("[render_worker] job %s failed: %s", job_id, e)
        await _mark_failed_or_retry(
            db,
            job_id=job_id,
            retry_count=job.get("retry_count", 0),
            error_message=str(e) or e.__class__.__name__,
        )

    return True


async def run_worker_loop(db, *, stop_event: asyncio.Event | None = None) -> None:
    """Loop principal — chamado uma vez no startup como background task.

    `stop_event` permite shutdown limpo (set durante app shutdown).
    """
    logger.info("[render_worker] started, poll=%ss", POLL_INTERVAL_SECONDS)
    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("[render_worker] stop_event set, exiting")
            break
        try:
            did_work = await process_one_job(db)
        except Exception as e:  # noqa: BLE001 — defesa para não derrubar o loop
            logger.exception("[render_worker] loop iteration crashed: %s", e)
            did_work = False

        # Se trabalhamos, tenta de novo imediatamente; senão, dorme.
        if not did_work:
            try:
                if stop_event is not None:
                    await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL_SECONDS)
                else:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
