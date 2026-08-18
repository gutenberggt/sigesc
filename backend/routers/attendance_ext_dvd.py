"""Guard DVD para o PDF legado de frequência.

O endpoint antigo permanece disponível para gestão/consolidação. Professor com
vínculo DVD ativo deve gerar o PDF por assignment_id, impedindo que o caminho
legado exponha registros consolidados de outros docentes da mesma turma.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Query, Request

from auth_middleware import AuthMiddleware


def _remove_route(router, path: str, method: str):
    for route in list(router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            router.routes.remove(route)
            return route.endpoint
    return None


async def _professor_has_dvd_in_year(db, user: dict, class_id: str, academic_year: int) -> bool:
    if user.get("role") != "professor" or not user.get("id"):
        return False
    return bool(await db.teacher_class_assignments.find_one(
        {
            "teacher_id": user.get("id"),
            "class_id": class_id,
            "deleted": False,
            "diary_settings.enabled": True,
            "valid_from": {"$lte": f"{academic_year}-12-31"},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{academic_year}-01-01"}}],
        },
        {"_id": 0, "id": 1},
    ))


def install_attendance_ext_dvd_setup() -> None:
    from routers import attendance_ext as attendance_ext_mod

    if getattr(attendance_ext_mod, "_dvd_phase4_setup_wrapped", False):
        return

    original_setup = attendance_ext_mod.setup_router

    def wrapped_setup(db, audit_service=None, sandbox_db=None, **kwargs):
        result = original_setup(db, audit_service, sandbox_db, **kwargs)
        if getattr(attendance_ext_mod.router, "_dvd_phase4_pdf_guard", False):
            return result

        legacy_pdf = _remove_route(
            attendance_ext_mod.router,
            "/attendance/pdf/bimestre/{class_id}",
            "GET",
        )
        if legacy_pdf is None:
            return result

        @attendance_ext_mod.router.get("/attendance/pdf/bimestre/{class_id}")
        async def dvd_aware_legacy_pdf(
            class_id: str,
            request: Request,
            bimestre: int = Query(..., ge=1, le=4),
            academic_year: Optional[int] = None,
            course_id: Optional[str] = None,
        ):
            user = await AuthMiddleware.get_current_user(request)
            current_db = (
                sandbox_db
                if user.get("is_sandbox") and sandbox_db is not None
                else db
            )
            year = academic_year or datetime.now().year
            if await _professor_has_dvd_in_year(current_db, user, class_id, year):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "DVD_ASSIGNMENT_REQUIRED",
                        "message": (
                            "Em turma DVD, o PDF do professor deve ser gerado a partir "
                            "de Meus Diários para preservar o vínculo docente."
                        ),
                    },
                )

            values = {
                "class_id": class_id,
                "request": request,
                "bimestre": bimestre,
                "academic_year": academic_year,
                "course_id": course_id,
            }
            accepted = {
                name: values[name]
                for name in inspect.signature(legacy_pdf).parameters
                if name in values
            }
            return await legacy_pdf(**accepted)

        attendance_ext_mod.router._dvd_phase4_pdf_guard = True
        return result

    attendance_ext_mod.setup_router = wrapped_setup
    attendance_ext_mod._dvd_phase4_setup_wrapped = True
