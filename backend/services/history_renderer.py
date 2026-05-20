"""Handler de render para document_type='history' — Histórico Escolar Consolidado.

Mesmo padrão de `bulletin_renderer`:
  1. Decodifica `source_snapshot_id = "history:{student_id}"`.
  2. Coleta dados via `services.history_consolidator.build_consolidated_history`.
  3. Cria pre-registro em `history_verifications` (token público + token_hash).
  4. Gera PDF via `pdf.historico_escolar.generate_historico_escolar_pdf`.
  5. Overlay com QR Code apontando para `/verify/historico/{token}`.
  6. Persiste arquivo + atualiza `history_verifications.pdf_hash_sha256`.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from services.bulletin_renderer import _stamp_qr_overlay  # reusa overlay QR
from services.document_files import store_pdf
from services.history_consolidator import build_consolidated_history

logger = logging.getLogger(__name__)


def _parse_source_id(source: str) -> str:
    parts = (source or "").split(":")
    if len(parts) != 2 or parts[0] != "history":
        raise ValueError(
            f"source_snapshot_id inválido para document_type=history: "
            f"esperado 'history:STU', got '{source}'"
        )
    return parts[1]


def _generate_token() -> str:
    return secrets.token_urlsafe(16)


def _verify_url(base: str, token: str) -> str:
    return f"{(base or '').rstrip('/')}/verify/historico/{token}"


async def render_history_handler(job: dict, *, db, public_base_url: str) -> dict:
    student_id = _parse_source_id(job.get("source_snapshot_id") or "")

    student = await db.students.find_one({"id": student_id}, {"_id": 0})
    if not student:
        raise ValueError(f"Aluno não encontrado: {student_id}")

    # Consolida histórico
    history = await build_consolidated_history(db, student_id=student_id)

    # Escola e mantenedora (usa a mais recente do aluno se disponível)
    school = None
    if student.get("school_id"):
        school = await db.schools.find_one({"id": student["school_id"]}, {"_id": 0})
    if not school and history["records"]:
        sid = history["records"][0].get("_school_id")
        if sid:
            school = await db.schools.find_one({"id": sid}, {"_id": 0})
    school = school or {"name": "Escola Municipal", "city": "", "state": ""}
    mantenedora = await db.mantenedoras.find_one({}, {"_id": 0}) or {}

    # Pre-registra verification
    token = _generate_token()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    verification_id = str(uuid.uuid4())
    url = _verify_url(public_base_url, token)
    now = datetime.now(timezone.utc).isoformat()

    summary = {
        "id": verification_id,
        "token_hash": token_hash,
        "document_type": "history",
        "job_id": job.get("id"),
        "student_id": student_id,
        "student_name": student.get("full_name"),
        "school_id": school.get("id"),
        "school_name": school.get("name"),
        "mantenedora_id": mantenedora.get("id"),
        "years_covered": history["consolidated_meta"]["years_covered"],
        "records_count": len(history.get("records") or []),
        "verify_url": url,
        "pdf_hash_sha256": None,
        "file_id": None,
        "created_at": now,
        "revoked_at": None,
        "revoked_by": None,
        "issued_by_user_id": job.get("requested_by_user_id"),
    }
    await db.history_verifications.insert_one(summary)

    # PDF base
    from pdf.historico_escolar import generate_historico_escolar_pdf
    try:
        from routers.documents import resolve_anexa_name
        await resolve_anexa_name(db, school)
    except Exception:  # noqa: BLE001
        pass

    buf = generate_historico_escolar_pdf(
        student=student,
        school=school,
        mantenedora=mantenedora,
        history=history,
        verification_code=verification_id[:8].upper(),
        valid_until=None,
    )
    buf.seek(0)
    pdf_bytes = buf.read()

    # Overlay QR
    final_pdf = _stamp_qr_overlay(pdf_bytes, url, doc_id=verification_id)
    pdf_hash = hashlib.sha256(final_pdf).hexdigest()

    safe = (student.get("full_name") or "aluno").replace(" ", "_")
    filename = f"historico_oficial_{safe}.pdf"
    stored = await store_pdf(
        db,
        pdf_bytes=final_pdf,
        filename=filename,
        document_type="history",
        mantenedora_id=mantenedora.get("id"),
        school_id=school.get("id"),
        student_id=student_id,
    )

    await db.history_verifications.update_one(
        {"id": verification_id},
        {"$set": {"pdf_hash_sha256": pdf_hash, "file_id": stored["file_id"]}}
    )

    logger.info(
        "[history_renderer] job=%s student=%s file_id=%s years=%s sha=%s",
        job.get("id"), student_id, stored["file_id"],
        history["consolidated_meta"]["years_covered"], pdf_hash[:12]
    )

    return {
        "generated_file_id": stored["file_id"],
        "generated_file_size_bytes": stored["size_bytes"],
        "pdf_hash_sha256": pdf_hash,
        "verification_id": verification_id,
        "verify_url": url,
    }
