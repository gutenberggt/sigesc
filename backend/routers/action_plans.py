"""
Router Action Plans — Planos de Ação (PMPI-GE pilar 3.4).

CRUD completo com workflow de status, responsável e prazo.
- Cada plano pertence a uma mantenedora + escola.
- Campos principais: title, description, priority, status, due_date,
  responsible_user_id, created_by, actions (checklist).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_middleware import AuthMiddleware
from tenant_scope import (apply_tenant_filter, assert_same_tenant,
                          get_mantenedora_scope, is_super_admin)

router = APIRouter(prefix="/action-plans", tags=["Action Plans"])


ALLOWED_STATUS = {"draft", "active", "in_progress", "completed", "cancelled"}
ALLOWED_PRIORITY = {"low", "medium", "high", "critical"}


class ActionItem(BaseModel):
    text: str
    done: bool = False
    done_at: Optional[str] = None


class ActionPlanCreate(BaseModel):
    school_id: str
    title: str = Field(..., min_length=3, max_length=300)
    description: Optional[str] = ""
    priority: str = "medium"
    status: str = "active"
    due_date: Optional[str] = None
    responsible_user_id: Optional[str] = None
    actions: List[ActionItem] = Field(default_factory=list)
    linked_kpi: Optional[str] = None  # ex.: "frequencia", "aulas_lancadas"


class ActionPlanUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    responsible_user_id: Optional[str] = None
    actions: Optional[List[ActionItem]] = None
    linked_kpi: Optional[str] = None


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):
    """Configura o router com dependências."""

    def _get_db(user: dict):
        if user.get("is_sandbox"):
            return sandbox_db if sandbox_db else db
        return db

    def _user_school_ids(user: dict) -> Optional[list]:
        role = user.get("role")
        if role in ("super_admin", "semed", "semed1", "semed2", "semed3",
                    "gerente", "admin", "admin_teste"):
            return None
        links = user.get("school_links") or []
        return [link.get("school_id") for link in links if link.get("school_id")]

    def _can_write(user: dict) -> bool:
        role = user.get("role")
        if role in ("super_admin", "semed", "semed1", "semed2", "semed3",
                    "gerente", "admin", "admin_teste", "diretor", "coordenador"):
            return True
        return False

    @router.get("")
    async def list_plans(
        request: Request,
        school_id: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """Lista planos. Filtra por escola (se informado) e por status."""
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        query = apply_tenant_filter({}, user, request)
        user_schools = _user_school_ids(user)
        if user_schools is not None:
            query["school_id"] = {"$in": user_schools}
        if school_id:
            # se já estava restrito, faz interseção
            if "school_id" in query and isinstance(query["school_id"], dict):
                allowed = query["school_id"].get("$in", [])
                if school_id not in allowed:
                    raise HTTPException(status_code=403, detail="Sem acesso a esta escola")
            query["school_id"] = school_id
        if status:
            if status not in ALLOWED_STATUS:
                raise HTTPException(status_code=400, detail="Status inválido")
            query["status"] = status
        cursor = current_db.action_plans.find(query, {"_id": 0}).sort("created_at", -1)
        items = [x async for x in cursor]
        return {"items": items, "total": len(items)}

    @router.post("")
    async def create_plan(payload: ActionPlanCreate, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not _can_write(user):
            raise HTTPException(status_code=403, detail="Sem permissão para criar planos")
        if payload.priority not in ALLOWED_PRIORITY:
            raise HTTPException(status_code=400, detail="Prioridade inválida")
        if payload.status not in ALLOWED_STATUS:
            raise HTTPException(status_code=400, detail="Status inválido")
        current_db = _get_db(user)
        # Verifica se a escola pertence ao tenant do user
        tenant_id = get_mantenedora_scope(user, request) or user.get("mantenedora_id")
        school = await current_db.schools.find_one(
            {"id": payload.school_id}, {"_id": 0, "id": 1, "name": 1, "mantenedora_id": 1},
        )
        if not school:
            raise HTTPException(status_code=404, detail="Escola não encontrada")
        if not is_super_admin(user):
            if school.get("mantenedora_id") != tenant_id:
                raise HTTPException(status_code=403, detail="Escola de outra mantenedora")
        now = datetime.now(timezone.utc).isoformat()
        plan = {
            "id": str(uuid4()),
            "mantenedora_id": school.get("mantenedora_id") or tenant_id,
            "school_id": payload.school_id,
            "school_name": school.get("name"),
            "title": payload.title.strip(),
            "description": (payload.description or "").strip(),
            "priority": payload.priority,
            "status": payload.status,
            "due_date": payload.due_date,
            "responsible_user_id": payload.responsible_user_id,
            "linked_kpi": payload.linked_kpi,
            "actions": [a.model_dump() for a in payload.actions],
            "created_by": user.get("id"),
            "created_by_name": user.get("full_name") or user.get("email"),
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        await current_db.action_plans.insert_one(dict(plan))
        return plan

    @router.get("/{plan_id}")
    async def get_plan(plan_id: str, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _get_db(user)
        query = apply_tenant_filter({"id": plan_id}, user, request)
        plan = await current_db.action_plans.find_one(query, {"_id": 0})
        if not plan:
            raise HTTPException(status_code=404, detail="Plano não encontrado")
        user_schools = _user_school_ids(user)
        if user_schools is not None and plan.get("school_id") not in user_schools:
            raise HTTPException(status_code=403, detail="Sem acesso a este plano")
        return plan

    @router.put("/{plan_id}")
    async def update_plan(plan_id: str, payload: ActionPlanUpdate, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not _can_write(user):
            raise HTTPException(status_code=403, detail="Sem permissão para editar")
        current_db = _get_db(user)
        query = apply_tenant_filter({"id": plan_id}, user, request)
        existing = await current_db.action_plans.find_one(query, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano não encontrado")
        user_schools = _user_school_ids(user)
        if user_schools is not None and existing.get("school_id") not in user_schools:
            raise HTTPException(status_code=403, detail="Sem acesso a este plano")
        update_data: dict = {}
        payload_dict = payload.model_dump(exclude_unset=True)
        if "priority" in payload_dict and payload_dict["priority"] not in ALLOWED_PRIORITY:
            raise HTTPException(status_code=400, detail="Prioridade inválida")
        if "status" in payload_dict and payload_dict["status"] not in ALLOWED_STATUS:
            raise HTTPException(status_code=400, detail="Status inválido")
        for k, v in payload_dict.items():
            if k == "actions" and v is not None:
                update_data[k] = [a.model_dump() if hasattr(a, "model_dump") else a for a in v]
            else:
                update_data[k] = v
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if payload_dict.get("status") == "completed" and not existing.get("completed_at"):
            update_data["completed_at"] = update_data["updated_at"]
        await current_db.action_plans.update_one({"id": plan_id}, {"$set": update_data})
        updated = await current_db.action_plans.find_one({"id": plan_id}, {"_id": 0})
        return updated

    @router.delete("/{plan_id}")
    async def delete_plan(plan_id: str, request: Request):
        user = await AuthMiddleware.get_current_user(request)
        if not _can_write(user):
            raise HTTPException(status_code=403, detail="Sem permissão para excluir")
        current_db = _get_db(user)
        query = apply_tenant_filter({"id": plan_id}, user, request)
        existing = await current_db.action_plans.find_one(query, {"_id": 0})
        if not existing:
            raise HTTPException(status_code=404, detail="Plano não encontrado")
        await current_db.action_plans.delete_one({"id": plan_id})
        return {"deleted": True, "id": plan_id}

    return router
