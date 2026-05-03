"""Router: Emissão de Declarações Escolares (G1.7 — Fev/2026).

Endpoints:
  POST /api/school-documents/issue         — emite declaração + baixa PDF
  GET  /api/school-documents               — lista emissões (com escopo)
  GET  /api/school-documents/{code}/pdf    — baixa PDF de uma emissão existente
  POST /api/school-documents/{code}/revoke — revoga (reusa verifiable_docs_service)

Permissões (opção 2a):
  super_admin, admin, admin_teste, gerente, secretario, auxiliar_secretaria, diretor
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from services import school_docs_service as svc
from services import verifiable_docs_service as vsvc
from services import snapshot_service as snap_svc

logger = logging.getLogger(__name__)

_SCHOOL_DOC_ROLES = (
    "super_admin", "admin", "admin_teste", "gerente",
    "secretario", "auxiliar_secretaria", "diretor",
)


class IssueRequest(BaseModel):
    student_id: str = Field(..., description="ID do aluno (students.id)")
    doc_type: str = Field(..., description="matricula | frequencia | escolaridade")
    purpose: str = Field("", description="Finalidade (banco, benefício, etc.)")
    class_id: Optional[str] = None
    validity_days: Optional[int] = None
    # Campos específicos
    frequencia_pct: Optional[float] = None
    bimestre: Optional[str] = None
    serie_concluida: Optional[str] = None


def setup_router(db):
    router = APIRouter(prefix="/school-documents", tags=["Declarações Escolares"])

    async def _require(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in _SCHOOL_DOC_ROLES:
            raise HTTPException(403, "Sem permissão para emitir declarações")
        return user

    @router.post("/issue")
    async def issue(payload: IssueRequest, request: Request):
        user = await _require(request)
        ip = (request.client.host if request.client else None)
        extra = {}
        if payload.frequencia_pct is not None:
            extra["frequencia_pct"] = payload.frequencia_pct
        if payload.bimestre:
            extra["bimestre"] = payload.bimestre
        if payload.serie_concluida:
            extra["serie_concluida"] = payload.serie_concluida

        result = await svc.issue_school_document(
            db,
            student_id=payload.student_id,
            doc_type=payload.doc_type,
            purpose=payload.purpose or "",
            user=user,
            class_id=payload.class_id,
            ip=ip,
            validity_days=payload.validity_days,
            extra=extra,
        )
        # Retorna PDF diretamente + headers com metadados
        filename = f"sigesc-{payload.doc_type}-{result['code']}.pdf"
        return Response(
            content=result["pdf_bytes"],
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-SIGESC-Code": result["code"] or "",
                "X-SIGESC-Valid-Until": result["valid_until"],
                "X-SIGESC-Snapshot-Id": result["snapshot_id"],
                "X-SIGESC-Public-Hash": result["public_hash"],
            },
        )

    @router.get("")
    async def list_documents(
        request: Request,
        student_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = Query(50, le=200),
    ):
        user = await _require(request)
        filt: dict = {}
        if student_id:
            filt["student_id"] = student_id
        if doc_type:
            filt["doc_type"] = doc_type
        # Escopo: usa mesma lógica dos snapshots
        scope = snap_svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope:
            filt["mantenedora_id"] = scope["mantenedora_id"]
        if "entity_ids" in scope:
            filt["school_id"] = {"$in": scope["entity_ids"]}

        cursor = db.school_documents_log.find(filt, {"_id": 0}).sort(
            "emitted_at", -1
        ).limit(limit)
        items = await cursor.to_list(length=limit)
        return {"items": items, "total": len(items)}

    @router.get("/{code}/pdf")
    async def get_pdf(code: str, request: Request):
        """Regenera PDF a partir do snapshot imutável (dados congelados)."""
        user = await _require(request)
        normalized = vsvc.normalize_code(code)
        if not normalized:
            raise HTTPException(400, "Código inválido")
        vdoc = await db.verifiable_documents.find_one(
            {"code": normalized}, {"_id": 0}
        )
        if not vdoc:
            raise HTTPException(404, "Documento não encontrado")
        # Scope
        scope = snap_svc.get_scope_for_user(user)
        if scope is None:
            raise HTTPException(403, "Sem escopo")
        if "mantenedora_id" in scope and scope["mantenedora_id"] != vdoc.get("mantenedora_id"):
            raise HTTPException(403, "Fora do seu escopo")
        if "entity_ids" in scope and vdoc.get("entity_id") not in scope["entity_ids"]:
            # student entity: verifica via school_documents_log
            log = await db.school_documents_log.find_one(
                {"code": normalized}, {"_id": 0, "school_id": 1}
            )
            if not log or log.get("school_id") not in scope["entity_ids"]:
                raise HTTPException(403, "Fora do seu escopo")

        snap = await db.ai_analysis_snapshots.find_one(
            {"id": vdoc.get("snapshot_id")}, {"_id": 0, "expires_at_dt": 0}
        )
        if not snap:
            raise HTTPException(404, "Snapshot do documento não encontrado")

        # Reconstrói o PDF a partir do snapshot congelado
        from services.school_doc_templates import build_school_document_pdf
        payload = snap.get("payload_snapshot") or {}
        output = snap.get("ai_output") or {}
        doc_type = payload.get("doc_type") or snap.get("analysis_type")
        student = payload.get("student") or {}
        school = payload.get("school") or {}
        cls = payload.get("class") or {}
        municipio = payload.get("municipality") or {}
        ctx = {
            "doc_type": doc_type,
            "purpose": payload.get("purpose") or "",
            "student_name": student.get("full_name"),
            "student_birth_date": student.get("birth_date"),
            "enrollment_number": student.get("enrollment_number"),
            "school_name": school.get("name"),
            "class_name": cls.get("name"),
            "grade_level": cls.get("grade_level"),
            "academic_year": cls.get("academic_year"),
            "shift": cls.get("shift"),
            "secretariat_name": "Secretaria Municipal de Educação",
            "city": municipio.get("city"),
            "state": municipio.get("state"),
            "issuer_name": (snap.get("created_by") or {}).get("email") or "Secretaria",
            "issuer_role": {
                "secretario": "Secretário(a) Escolar",
                "auxiliar_secretaria": "Auxiliar de Secretaria",
                "admin": "Administrador(a)",
                "super_admin": "Administrador(a) do Sistema",
                "diretor": "Diretor(a) Escolar",
            }.get((snap.get("created_by") or {}).get("role"), "Secretaria"),
            "code": normalized,
            "valid_until": output.get("valid_until"),
            "frequencia_pct": (payload.get("extra") or {}).get("frequencia_pct"),
            "bimestre": (payload.get("extra") or {}).get("bimestre"),
            "serie_concluida": (payload.get("extra") or {}).get("serie_concluida"),
        }
        pdf_bytes = build_school_document_pdf(doc_type, ctx)
        filename = f"sigesc-{doc_type}-{normalized}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post("/{code}/revoke")
    async def revoke(code: str, request: Request):
        user = await _require(request)
        if user.get("role") not in ("super_admin", "admin", "admin_teste",
                                    "gerente", "secretario"):
            raise HTTPException(403, "Apenas admin/secretario pode revogar")
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        reason = (body or {}).get("reason") or "Revogação administrativa"
        try:
            r = await vsvc.revoke_document(db, code=code, reason=reason, user=user)
        except KeyError:
            raise HTTPException(404, "Documento não encontrado")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return r

    return router
