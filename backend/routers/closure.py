"""
Closure router — Fechamento Temporal Composto.

[Fev/2026] Passo 3 da governança temporal pedagógica.

Expõe a lógica de `utils/temporal_closure.py` para o frontend (boletim,
histórico escolar futuro) sem permitir mutação.

Endpoints (somente leitura nesta V1):

- GET /api/closure/student/{student_id}/composite?academic_year=YYYY
    Retorna o fechamento composto completo (periodos + bimestres).

- GET /api/closure/student/{student_id}/window?academic_year=YYYY&class_id=...
    Retorna a janela em que a turma é dona do aluno no ano.

- GET /api/closure/class/{class_id}/students?academic_year=YYYY
    Lista alunos que tiveram a turma como proprietária em algum período do ano,
    com a janela de cada um (suporta boletim de turma com fechamento composto).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope
from utils.temporal_closure import (
    compute_class_window_for_student,
    compute_composite_closure,
    compute_temporal_periods,
)

logger = logging.getLogger(__name__)

ROLES_VIEW_CLOSURE = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "apoio_pedagogico", "professor",
    "semed", "semed1", "semed2", "semed3",
}


def setup_closure_router(db) -> APIRouter:
    router = APIRouter(prefix="/closure", tags=["Closure (Fechamento Temporal)"])

    async def _require_role(request: Request) -> dict:
        user = await AuthMiddleware.get_current_user(request)
        if user.get("role") not in ROLES_VIEW_CLOSURE:
            raise HTTPException(status_code=403, detail="Sem permissão para fechamento.")
        return user

    # -------------------------------------------------------------------
    @router.get("/student/{student_id}/composite")
    async def get_student_composite_closure(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        """Retorna períodos + bimestres atribuídos do aluno no ano."""
        user = await _require_role(request)
        tenant = get_mantenedora_scope(user, request)

        # Valida que aluno existe E pertence ao tenant.
        stu_filter = apply_tenant_filter({"id": student_id}, user, request)
        student = await db.students.find_one(stu_filter, {"_id": 0, "id": 1})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        closure = await compute_composite_closure(
            db,
            student_id=student_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        return closure

    # -------------------------------------------------------------------
    @router.get("/student/{student_id}/window")
    async def get_student_class_window(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
        class_id: str = Query(..., min_length=1),
    ):
        """Retorna a janela onde uma turma é dona do aluno (ou 404 se nunca foi)."""
        user = await _require_role(request)
        tenant = get_mantenedora_scope(user, request)

        stu_filter = apply_tenant_filter({"id": student_id}, user, request)
        student = await db.students.find_one(stu_filter, {"_id": 0, "id": 1})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        window = await compute_class_window_for_student(
            db,
            student_id=student_id,
            class_id=class_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        if not window:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "NO_WINDOW_FOR_CLASS",
                    "message": "Aluno nunca foi dono desta turma neste ano.",
                },
            )
        return {"academic_year": academic_year, "student_id": student_id, **window}

    # -------------------------------------------------------------------
    @router.get("/class/{class_id}/students")
    async def get_class_closure_students(
        class_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
        include_inactive: bool = Query(False),
    ):
        """Lista alunos com janelas onde `class_id` é dono dentro do ano.

        Une duas fontes:
        - alunos com matrícula direta na turma (período sole)
        - alunos com eventos acadêmicos cuja origem ou destino é esta turma
        """
        user = await _require_role(request)
        tenant = get_mantenedora_scope(user, request)

        # 1. Alunos com matrícula na turma
        enr_filter: dict = {
            "class_id": class_id,
            "academic_year": academic_year,
        }
        if not include_inactive:
            enr_filter["status"] = {"$in": [
                "active", "approved", "matricula_ativa",
                "moved_out",  # mantém aluno listado mesmo após movimentação
            ]}
        enr_filter = apply_tenant_filter(enr_filter, user, request)
        student_ids = set()
        async for enr in db.enrollments.find(enr_filter, {"_id": 0, "student_id": 1}):
            sid = enr.get("student_id")
            if sid:
                student_ids.add(sid)

        # 2. Alunos com eventos cuja origem OU destino é a turma
        ev_filter: dict = {
            "$or": [
                {"origin_class_id": class_id},
                {"destination_class_id": class_id},
            ],
            "academic_year": academic_year,
            "approval_status": "approved",
            "superseded_by_event_id": None,
        }
        ev_filter = apply_tenant_filter(ev_filter, user, request)
        async for ev in db.academic_events.find(ev_filter, {"_id": 0, "student_id": 1}):
            sid = ev.get("student_id")
            if sid:
                student_ids.add(sid)

        results = []
        for sid in sorted(student_ids):
            window = await compute_class_window_for_student(
                db,
                student_id=sid,
                class_id=class_id,
                academic_year=academic_year,
                mantenedora_id=tenant,
            )
            if window is None:
                continue
            results.append({
                "student_id": sid,
                **window,
            })

        return {
            "academic_year": academic_year,
            "class_id": class_id,
            "total": len(results),
            "students": results,
        }

    # -------------------------------------------------------------------
    @router.get("/student/{student_id}/periods")
    async def get_student_periods(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        """Endpoint enxuto: apenas a lista de períodos (sem bimestres).

        Útil para badge de "histórico de movimentações" no perfil do aluno.
        """
        user = await _require_role(request)
        tenant = get_mantenedora_scope(user, request)

        stu_filter = apply_tenant_filter({"id": student_id}, user, request)
        student = await db.students.find_one(stu_filter, {"_id": 0, "id": 1})
        if not student:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")

        periods = await compute_temporal_periods(
            db,
            student_id=student_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        return {
            "student_id": student_id,
            "academic_year": academic_year,
            "is_composite": len(periods) > 1,
            "periods": periods,
        }

    return router
