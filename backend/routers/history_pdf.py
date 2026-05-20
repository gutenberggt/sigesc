"""Endpoints do Histórico Escolar Consolidado (PDF assíncrono).

  POST /api/students/{id}/historico-consolidado/render-pdf  → enfileira
  GET  /api/verify/historico/{token}  (sem auth, sem CSRF)  → verificação pública

O download e o GET do job reusam endpoints de `/api/render-jobs/*`.
"""
from __future__ import annotations

import hashlib
import uuid
from fastapi import APIRouter, HTTPException, Request

from auth_middleware import AuthMiddleware
from tenant_scope import get_mantenedora_scope
from utils.render_jobs import compute_idempotency_key, find_existing_job, now_iso

HISTORY_TEMPLATE_VERSION = "historico_v1.0.0"
HISTORY_RENDER_ENGINE_VERSION = "reportlab+qrcode-v1"


def setup_history_pdf_router(db, audit_service=None):
    router = APIRouter(tags=["Histórico Escolar Consolidado"])

    @router.post("/students/{student_id}/historico-consolidado/render-pdf")
    async def request_history_pdf(student_id: str, request: Request):
        """Enfileira a geração do Histórico Escolar Consolidado.

        O Histórico é consolidado por aluno (sem `academic_year` específico —
        consolida TODOS os anos disponíveis no SIGESC).
        """
        user = await AuthMiddleware.get_current_user(request)
        allowed = {
            "super_admin", "admin", "admin_teste", "gerente", "secretario",
            "diretor", "coordenador",
            "semed", "semed1", "semed2", "semed3", "apoio_pedagogico",
        }
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Sem permissão.")

        student = await db.students.find_one({"id": student_id}, {"_id": 0})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        if user.get("role") in {"diretor", "coordenador", "secretario"}:
            if user.get("school_id") and student.get("school_id") != user.get("school_id"):
                raise HTTPException(status_code=403, detail="Aluno fora da sua escola")

        source_snapshot_id = f"history:{student_id}"
        idem_key = compute_idempotency_key(
            source_snapshot_id=source_snapshot_id,
            document_type="history",
            template_version=HISTORY_TEMPLATE_VERSION,
            render_engine_version=HISTORY_RENDER_ENGINE_VERSION,
        )
        existing = await find_existing_job(db, idempotency_key=idem_key)
        if existing and existing.get("status") in ("pending", "processing", "completed"):
            return {"id": existing["id"], "status": existing["status"], "idempotent_hit": True}

        now_s = now_iso()
        tenant = get_mantenedora_scope(user, request)
        job = {
            "id": str(uuid.uuid4()),
            "idempotency_key": idem_key,
            "document_type": "history",
            "source_snapshot_id": source_snapshot_id,
            "source_collection": "students",
            "template_version": HISTORY_TEMPLATE_VERSION,
            "render_engine_version": HISTORY_RENDER_ENGINE_VERSION,
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
            "audit_trail": [{"action": "queued", "at": now_s, "by_user_id": user.get("id")}],
        }
        await db.document_render_jobs.insert_one(job)
        return {"id": job["id"], "status": "pending", "idempotent_hit": False}

    @router.get("/verify/historico/{token}")
    async def verify_history(token: str):
        """Endpoint público de verificação (sem auth, sem CSRF)."""
        if not token or len(token) < 12:
            raise HTTPException(status_code=400, detail="Token inválido")
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        v = await db.history_verifications.find_one({"token_hash": token_hash}, {"_id": 0})
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
            "document_type": "Histórico Escolar Consolidado",
            "student_name": v.get("student_name"),
            "school_name": v.get("school_name"),
            "years_covered": v.get("years_covered") or [],
            "records_count": v.get("records_count"),
            "issued_at": v.get("created_at"),
            "pdf_sha256": v.get("pdf_hash_sha256"),
            "verification_id": v.get("id"),
            "note": (
                "Este Histórico Escolar foi consolidado automaticamente pelo SIGESC a "
                "partir dos registros internos (matrículas, notas, frequência) ao "
                "longo dos anos cursados. Compare o hash SHA-256 acima com o do PDF "
                "que você recebeu para confirmar a autenticidade. Em caso de "
                "divergência, o documento é inválido."
            ),
        }

    return router
