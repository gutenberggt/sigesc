"""
Endpoints administrativos para criação em massa de usuários de alunos.

Requer role='super_admin'.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from auth_middleware import AuthMiddleware
from services.student_account_service import build_plan_for_students, apply_plan

router = APIRouter(prefix="/admin/student-users", tags=["Admin Bulk Students"])


class BulkCreateRequest(BaseModel):
    mantenedora_id: Optional[str] = None
    school_ids: Optional[List[str]] = None
    include_inactive: bool = False
    apply: bool = False  # False = dry-run (só retorna plano)


def setup_router(db, audit_service=None, sandbox_db=None, **kwargs):

    def _get_db(user: dict):
        return sandbox_db if user.get("is_sandbox") and sandbox_db is not None else db

    @router.post("/bulk-create")
    async def bulk_create_student_users(body: BulkCreateRequest, request: Request):
        """
        Cria usuários (role='aluno') para alunos ativos conforme regra:
        - email = primeironomeultimosobrenomeMM@sigesc.com
        - senha = DDMMYYYY (data de nascimento)

        Passo 1: chamar com apply=false (DRY-RUN) para ver o plano.
        Passo 2: chamar com apply=true para gravar de fato.

        Só super_admin pode executar.
        """
        current_user = await AuthMiddleware.get_current_user(request)
        if current_user.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Apenas super_admin pode executar esta operação")
        current_db = _get_db(current_user)

        plan = await build_plan_for_students(
            current_db,
            mantenedora_id=body.mantenedora_id,
            school_ids=body.school_ids,
            include_inactive=body.include_inactive,
        )

        result = {
            "mode": "APPLY" if body.apply else "DRY_RUN",
            "totals": plan["totals"],
            "preview_to_create": plan["to_create"][:20],  # amostra apenas
            "skipped": plan["skipped"],
            "already_has_user": plan["already_has_user"][:20],
        }

        if body.apply:
            apply_res = await apply_plan(current_db, plan)
            result["applied"] = apply_res
            if audit_service:
                try:
                    await audit_service.log(
                        user_id=current_user.get("id"),
                        user_email=current_user.get("email"),
                        action="bulk_create",
                        collection="users",
                        entity_id="bulk",
                        details={
                            "mantenedora_id": body.mantenedora_id,
                            "school_ids": body.school_ids,
                            "inserted": apply_res.get("inserted"),
                            "errors": len(apply_res.get("errors") or []),
                        },
                    )
                except Exception:
                    pass

        return result

    return router
