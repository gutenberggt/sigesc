"""
Router CRUD de eventos acadêmicos.

[Fev/2026] Implementa /app/docs/ACADEMIC_EVENT_CONTRACT.md V1.

Princípios:
- Eventos NUNCA são deletados — apenas substituídos via supersession.
- Edição material exige fluxo §10: rationale ≥30, role autorizado,
  X-Academic-Event-Confirm: true, snapshot before/after no audit_trail.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope

logger = logging.getLogger(__name__)

EVENT_TYPES = ("transfer", "remanejamento", "reclassificacao", "progressao_parcial")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "superseded")
ROLES_CREATE_EVENT = {"super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor"}
ROLES_APPROVE_EVENT = {"super_admin", "admin", "gerente", "secretario", "diretor"}
ROLES_VIEW_EVENT = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "apoio_pedagogico", "professor",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
class AcademicEventCreate(BaseModel):
    event_type: str
    effective_date: str  # YYYY-MM-DD (no tz institucional)
    student_id: str
    origin_class_id: str
    destination_class_id: str
    origin_school_id: Optional[str] = None
    destination_school_id: Optional[str] = None
    origin_teacher_id: Optional[str] = None
    destination_teacher_id: Optional[str] = None
    academic_year: int
    rationale: str = Field(..., min_length=30)
    approval_required: bool = True


class AcademicEventSupersedeRequest(BaseModel):
    """Cria um novo evento que supersedes o anterior — operação §10."""
    new_payload: AcademicEventCreate
    rationale: str = Field(..., min_length=30)


# ===========================================================================
def setup_academic_events_router(db, audit_service=None):
    router = APIRouter(prefix="/academic-events", tags=["Academic Events"])

    async def _require_role(request: Request, allowed: set[str]) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in allowed:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        return user

    def _validate_event_type(et: str) -> None:
        if et not in EVENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_EVENT_TYPE", "expected": list(EVENT_TYPES)},
            )

    # -------------------------------------------------------------------
    @router.post("", response_model=dict)
    async def create_event(payload: AcademicEventCreate, request: Request):
        user = await _require_role(request, ROLES_CREATE_EVENT)
        _validate_event_type(payload.event_type)

        if payload.origin_class_id == payload.destination_class_id:
            raise HTTPException(
                status_code=422,
                detail={"code": "ORIGIN_EQUALS_DESTINATION"},
            )

        tenant = get_mantenedora_scope(user, request)
        now = _now_iso()
        event = {
            "id": str(uuid.uuid4()),
            "event_type": payload.event_type,
            "effective_date": payload.effective_date,
            "student_id": payload.student_id,
            "origin_class_id": payload.origin_class_id,
            "destination_class_id": payload.destination_class_id,
            "origin_school_id": payload.origin_school_id,
            "destination_school_id": payload.destination_school_id,
            "origin_teacher_id": payload.origin_teacher_id,
            "destination_teacher_id": payload.destination_teacher_id,
            "mantenedora_id": tenant,
            "academic_year": payload.academic_year,
            "rationale": payload.rationale,
            "approval_required": payload.approval_required,
            "approval_status": "pending" if payload.approval_required else "approved",
            "approved_by_user_id": None if payload.approval_required else user.get("id"),
            "approved_at": None if payload.approval_required else now,
            "rejection_reason": None,
            "created_by_user_id": user.get("id"),
            "created_at": now,
            "supersedes_event_id": None,
            "superseded_by_event_id": None,
            "audit_trail": [
                {"action": "created", "by_user_id": user.get("id"), "at": now,
                 "snapshot_after": {"event_type": payload.event_type,
                                    "effective_date": payload.effective_date}},
            ],
        }
        await db.academic_events.insert_one(event)
        event.pop("_id", None)
        logger.info("[academic-events] criado %s tipo=%s aluno=%s", event["id"], event["event_type"], event["student_id"])
        return {"id": event["id"], "approval_status": event["approval_status"], "event": event}

    # -------------------------------------------------------------------
    @router.get("/{event_id}", response_model=dict)
    async def get_event(event_id: str, request: Request):
        user = await _require_role(request, ROLES_VIEW_EVENT)
        flt = apply_tenant_filter({"id": event_id}, user, request)
        ev = await db.academic_events.find_one(flt, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento não encontrado.")
        return ev

    # -------------------------------------------------------------------
    @router.get("/student/{student_id}", response_model=dict)
    async def list_events_for_student(student_id: str, request: Request):
        user = await _require_role(request, ROLES_VIEW_EVENT)
        flt = apply_tenant_filter({"student_id": student_id}, user, request)
        items = await db.academic_events.find(flt, {"_id": 0}).sort("effective_date", -1).to_list(100)
        return {"student_id": student_id, "items": items, "total": len(items)}

    # -------------------------------------------------------------------
    @router.post("/{event_id}/approve", response_model=dict)
    async def approve_event(event_id: str, request: Request):
        user = await _require_role(request, ROLES_APPROVE_EVENT)
        ev = await db.academic_events.find_one({"id": event_id}, {"_id": 0})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento não encontrado.")
        if ev["approval_status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_TRANSITION",
                        "current": ev["approval_status"]},
            )
        now = _now_iso()
        await db.academic_events.update_one(
            {"id": event_id},
            {
                "$set": {"approval_status": "approved",
                         "approved_by_user_id": user.get("id"),
                         "approved_at": now},
                "$push": {"audit_trail": {"action": "approved",
                                          "by_user_id": user.get("id"), "at": now}},
            },
        )
        return {"id": event_id, "approval_status": "approved", "approved_at": now}

    # -------------------------------------------------------------------
    @router.post("/{event_id}/reject", response_model=dict)
    async def reject_event(event_id: str, request: Request):
        user = await _require_role(request, ROLES_APPROVE_EVENT)
        body = await request.json()
        reason = (body.get("reason") or "").strip()
        if len(reason) < 30:
            raise HTTPException(
                status_code=422,
                detail={"code": "RATIONALE_TOO_SHORT", "min_chars": 30},
            )
        ev = await db.academic_events.find_one({"id": event_id}, {"_id": 0, "approval_status": 1})
        if not ev:
            raise HTTPException(status_code=404, detail="Evento não encontrado.")
        if ev["approval_status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_TRANSITION", "current": ev["approval_status"]},
            )
        now = _now_iso()
        await db.academic_events.update_one(
            {"id": event_id},
            {
                "$set": {"approval_status": "rejected",
                         "rejection_reason": reason,
                         "approved_by_user_id": user.get("id"),
                         "approved_at": now},
                "$push": {"audit_trail": {"action": "rejected",
                                          "by_user_id": user.get("id"),
                                          "at": now, "reason": reason}},
            },
        )
        return {"id": event_id, "approval_status": "rejected"}

    # -------------------------------------------------------------------
    @router.post("/{event_id}/supersede", response_model=dict)
    async def supersede_event(event_id: str, payload: AcademicEventSupersedeRequest, request: Request):
        """Substitui um evento por outro — fluxo §10 obrigatório.

        Headers obrigatórios:
            X-Academic-Event-Confirm: true
        """
        user = await _require_role(request, ROLES_APPROVE_EVENT)
        if request.headers.get("X-Academic-Event-Confirm") != "true":
            raise HTTPException(
                status_code=428,
                detail={"code": "CONFIRMATION_REQUIRED",
                        "message": "Header X-Academic-Event-Confirm: true exigido."},
            )

        old_ev = await db.academic_events.find_one({"id": event_id}, {"_id": 0})
        if not old_ev:
            raise HTTPException(status_code=404, detail="Evento não encontrado.")
        if old_ev.get("superseded_by_event_id"):
            raise HTTPException(
                status_code=409,
                detail={"code": "ALREADY_SUPERSEDED",
                        "superseded_by_event_id": old_ev["superseded_by_event_id"]},
            )

        _validate_event_type(payload.new_payload.event_type)
        tenant = get_mantenedora_scope(user, request)
        now = _now_iso()
        new_ev = {
            "id": str(uuid.uuid4()),
            "event_type": payload.new_payload.event_type,
            "effective_date": payload.new_payload.effective_date,
            "student_id": payload.new_payload.student_id,
            "origin_class_id": payload.new_payload.origin_class_id,
            "destination_class_id": payload.new_payload.destination_class_id,
            "origin_school_id": payload.new_payload.origin_school_id,
            "destination_school_id": payload.new_payload.destination_school_id,
            "origin_teacher_id": payload.new_payload.origin_teacher_id,
            "destination_teacher_id": payload.new_payload.destination_teacher_id,
            "mantenedora_id": tenant,
            "academic_year": payload.new_payload.academic_year,
            "rationale": payload.rationale,
            "approval_required": True,
            "approval_status": "approved",
            "approved_by_user_id": user.get("id"),
            "approved_at": now,
            "rejection_reason": None,
            "created_by_user_id": user.get("id"),
            "created_at": now,
            "supersedes_event_id": old_ev["id"],
            "superseded_by_event_id": None,
            "audit_trail": [
                {"action": "created_via_supersession", "by_user_id": user.get("id"), "at": now,
                 "snapshot_before": {"event_id": old_ev["id"],
                                     "event_type": old_ev["event_type"],
                                     "effective_date": old_ev["effective_date"]},
                 "snapshot_after": {"event_type": payload.new_payload.event_type,
                                    "effective_date": payload.new_payload.effective_date}},
            ],
        }
        await db.academic_events.insert_one(new_ev)
        new_ev.pop("_id", None)

        # Marca o antigo como superseded
        await db.academic_events.update_one(
            {"id": old_ev["id"]},
            {
                "$set": {"approval_status": "superseded",
                         "superseded_by_event_id": new_ev["id"]},
                "$push": {"audit_trail": {"action": "superseded",
                                          "by_user_id": user.get("id"), "at": now,
                                          "by_event_id": new_ev["id"]}},
            },
        )
        return {"old_event_id": old_ev["id"], "new_event": new_ev}

    return router
