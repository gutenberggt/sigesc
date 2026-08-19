"""Endpoints públicos e autenticados para o Boletim Oficial (PDF assíncrono).

PR #54 endurece o acesso do professor: solicitar ou baixar um boletim exige que
o estudante pertença ao roster avaliativo autorizado do Diário por Vínculo.
"""
from __future__ import annotations

import hashlib
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from io import BytesIO

from auth_middleware import AuthMiddleware
from services.document_files import fetch_pdf
from services.teacher_grade_access import (
    TeacherGradeAccessError,
    ensure_teacher_student_grade_access,
)
from tenant_scope import get_mantenedora_scope
from utils.render_jobs import compute_idempotency_key, find_existing_job, now_iso

BULLETIN_TEMPLATE_VERSION = "boletim_v1.0.0"
BULLETIN_RENDER_ENGINE_VERSION = "reportlab+qrcode-v1"


async def _ensure_professor_bulletin_scope(
    db,
    user,
    request: Request,
    *,
    student_id: str,
    academic_year: int,
) -> None:
    if user.get("role") != "professor":
        return
    try:
        await ensure_teacher_student_grade_access(
            db,
            user,
            student_id=student_id,
            academic_year=int(academic_year),
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
    except TeacherGradeAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


def _bulletin_job_subject(job: dict) -> tuple[str | None, int | None]:
    student_id = job.get("student_id")
    academic_year = job.get("academic_year")
    if student_id and academic_year:
        try:
            return str(student_id), int(academic_year)
        except (TypeError, ValueError):
            return None, None

    source = str(job.get("source_snapshot_id") or "")
    if not source.startswith("boletim:"):
        return None, None
    parts = source.split(":", 2)
    if len(parts) != 3:
        return None, None
    try:
        return parts[1], int(parts[2])
    except (TypeError, ValueError):
        return None, None


def setup_bulletin_pdf_router(db, audit_service=None):
    router = APIRouter(tags=["Boletim Oficial PDF"])

    @router.post("/bulletins/{student_id}/render-pdf")
    async def request_bulletin_pdf(
        student_id: str,
        academic_year: int,
        request: Request,
    ):
        """Enfileira um job de geração do Boletim Oficial."""
        user = await AuthMiddleware.get_current_user(request)
        allowed = {
            "super_admin", "admin", "admin_teste", "gerente", "secretario",
            "diretor", "coordenador", "professor",
            "semed", "semed1", "semed2", "semed3", "apoio_pedagogico",
        }
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Sem permissão.")

        await _ensure_professor_bulletin_scope(
            db,
            user,
            request,
            student_id=student_id,
            academic_year=academic_year,
        )

        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Estudante não encontrado")

        # Demais perfis escolares mantêm a regra preexistente de escola.
        if user.get("role") in {"diretor", "coordenador", "secretario"}:
            if user.get("school_id") and student.get("school_id") != user.get("school_id"):
                raise HTTPException(status_code=403, detail="Estudante fora da sua escola")

        source_snapshot_id = f"boletim:{student_id}:{int(academic_year)}"
        idem_key = compute_idempotency_key(
            source_snapshot_id=source_snapshot_id,
            document_type="bulletin",
            template_version=BULLETIN_TEMPLATE_VERSION,
            render_engine_version=BULLETIN_RENDER_ENGINE_VERSION,
        )

        existing = await find_existing_job(db, idempotency_key=idem_key)
        if existing and existing.get("status") in ("pending", "processing", "completed"):
            return {
                "id": existing["id"],
                "status": existing["status"],
                "idempotent_hit": True,
            }

        import uuid

        now_s = now_iso()
        tenant = get_mantenedora_scope(user, request)
        job = {
            "id": str(uuid.uuid4()),
            "idempotency_key": idem_key,
            "document_type": "bulletin",
            "source_snapshot_id": source_snapshot_id,
            "source_collection": "students",
            # Metadados explícitos facilitam ACL do download sem depender só de parsing.
            "student_id": student_id,
            "academic_year": int(academic_year),
            "template_version": BULLETIN_TEMPLATE_VERSION,
            "render_engine_version": BULLETIN_RENDER_ENGINE_VERSION,
            "render_options": {"page_size": "A4", "include_qr": True},
            "payload_hash": idem_key,
            "status": "pending",
            "generated_file_id": None,
            "generated_file_size_bytes": None,
            "generated_at": None,
            "pdf_hash_sha256": None,
            "error_message": None,
            "retry_count": 0,
            "max_retries": 3,
            "next_retry_at": None,
            "started_at": None,
            "completed_at": None,
            "failed_at": None,
            "requested_by_user_id": user.get("id"),
            "requested_at": now_s,
            "request_ip": request.client.host if request.client else None,
            "request_user_agent": request.headers.get("user-agent", "")[:512],
            "mantenedora_id": tenant,
            "school_id": student.get("school_id"),
            "audit_trail": [
                {"action": "queued", "at": now_s, "by_user_id": user.get("id")},
            ],
        }
        await db.document_render_jobs.insert_one(job)
        return {"id": job["id"], "status": "pending", "idempotent_hit": False}

    @router.get("/render-jobs/{job_id}/file")
    async def download_render_job_file(job_id: str, request: Request):
        """Baixa o PDF de um job completo, respeitando ACL do documento."""
        user = await AuthMiddleware.get_current_user(request)
        job = await db.document_render_jobs.find_one({"id": job_id}, {"_id": 0})
        if not job:
            raise HTTPException(status_code=404, detail="Job não encontrado")
        if job.get("status") != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Job ainda não concluído (status={job.get('status')})",
            )

        role = user.get("role")
        if role not in ("super_admin", "admin", "admin_teste", "gerente"):
            tenant = get_mantenedora_scope(user, request)
            if tenant and job.get("mantenedora_id") and job.get("mantenedora_id") != tenant:
                raise HTTPException(status_code=403, detail="Job de outra mantenedora")

        if role == "professor" and job.get("document_type") == "bulletin":
            student_id, academic_year = _bulletin_job_subject(job)
            if not student_id or not academic_year:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "BULLETIN_JOB_SCOPE_UNRESOLVED",
                        "message": "Não foi possível comprovar o estudante/ano deste boletim.",
                    },
                )
            await _ensure_professor_bulletin_scope(
                db,
                user,
                request,
                student_id=student_id,
                academic_year=academic_year,
            )

        file_id = job.get("generated_file_id")
        if not file_id:
            raise HTTPException(status_code=500, detail="Job sem arquivo associado")
        f = await fetch_pdf(db, file_id)
        if not f:
            raise HTTPException(status_code=404, detail="Arquivo expirado ou removido")

        return StreamingResponse(
            BytesIO(f["pdf_bytes"]),
            media_type=f["mime_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{f["filename"]}"',
                "X-PDF-SHA256": f["sha256"] or "",
            },
        )

    @router.get("/verify/boletim/{token}")
    async def verify_bulletin(token: str):
        """Verificação pública LGPD-safe do Boletim Oficial."""
        if not token or len(token) < 12:
            raise HTTPException(status_code=400, detail="Token inválido")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        v = await db.bulletin_verifications.find_one({"token_hash": token_hash}, {"_id": 0})
        if not v:
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        if v.get("revoked_at"):
            return {
                "valid": False,
                "revoked": True,
                "revoked_at": v.get("revoked_at"),
                "reason": "Documento revogado pela instituição emissora.",
            }
        if not v.get("pdf_hash_sha256"):
            return {"valid": False, "reason": "Documento em geração. Tente novamente em alguns segundos."}

        return {
            "valid": True,
            "document_type": "Boletim Escolar Oficial",
            "student_name": v.get("student_name"),
            "school_name": v.get("school_name"),
            "class_name": v.get("class_name"),
            "grade_level": v.get("grade_level"),
            "academic_year": v.get("academic_year"),
            "issued_at": v.get("created_at"),
            "pdf_sha256": v.get("pdf_hash_sha256"),
            "verification_id": v.get("id"),
            "note": (
                "Este documento foi emitido pelo SIGESC. Compare o hash SHA-256 "
                "acima com o do arquivo PDF que você recebeu para confirmar a "
                "autenticidade. Em caso de divergência, o documento é inválido."
            ),
        }

    return router
