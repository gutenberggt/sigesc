"""Guards DVD para superfícies estendidas de Frequência.

O PDF e os alertas legados permanecem disponíveis para gestão/consolidação.
Professor em turma DVD usa `assignment_id`, evitando exposição de dados de
outros vínculos e reutilizando o relatório canônico autorizado do próprio DVD.
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
            "deleted": {"$ne": True},
            "diary_settings.enabled": True,
            "valid_from": {"$lte": f"{academic_year}-12-31"},
            "$or": [{"valid_until": None}, {"valid_until": {"$gte": f"{academic_year}-01-01"}}],
        },
        {"_id": 0, "id": 1},
    ))


def _accepted_call(endpoint, values: dict):
    return {
        name: values[name]
        for name in inspect.signature(endpoint).parameters
        if name in values
    }


def install_attendance_ext_dvd_setup() -> None:
    from routers import attendance_ext as attendance_ext_mod

    if getattr(attendance_ext_mod, "_dvd_phase4_setup_wrapped", False):
        return

    original_setup = attendance_ext_mod.setup_router

    def wrapped_setup(db, audit_service=None, sandbox_db=None, **kwargs):
        result = original_setup(db, audit_service, sandbox_db, **kwargs)
        if getattr(attendance_ext_mod.router, "_dvd_phase4_ext_guard", False):
            return result

        legacy_pdf = _remove_route(
            attendance_ext_mod.router,
            "/attendance/pdf/bimestre/{class_id}",
            "GET",
        )
        legacy_alerts = _remove_route(
            attendance_ext_mod.router,
            "/attendance/alerts",
            "GET",
        )

        if legacy_pdf is not None:
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

                return await legacy_pdf(**_accepted_call(legacy_pdf, {
                    "class_id": class_id,
                    "request": request,
                    "bimestre": bimestre,
                    "academic_year": academic_year,
                    "course_id": course_id,
                }))

        if legacy_alerts is not None:
            @attendance_ext_mod.router.get("/attendance/alerts")
            async def dvd_aware_alerts(
                request: Request,
                school_id: Optional[str] = None,
                academic_year: Optional[int] = None,
                assignment_id: Optional[str] = None,
            ):
                user = await AuthMiddleware.get_current_user(request)
                current_db = (
                    sandbox_db
                    if user.get("is_sandbox") and sandbox_db is not None
                    else db
                )
                year = academic_year or datetime.now().year

                if assignment_id:
                    # Import local evita ciclo no bootstrap. `_dvd_report` já passa
                    # pelo autorizador central e, após o adaptador de paridade,
                    # inclui o histórico class_daily legitimamente herdado.
                    from routers.attendance_dvd import _dvd_report

                    report = await _dvd_report(
                        current_db,
                        user,
                        request,
                        assignment_id,
                        year,
                        None,
                    )
                    report_school = (report.get("class") or {}).get("school_id") or report.get("school_id")
                    if school_id and report_school and school_id != report_school:
                        raise HTTPException(
                            status_code=403,
                            detail={
                                "code": "SCHOOL_MISMATCH",
                                "message": "O vínculo não pertence à escola informada.",
                            },
                        )

                    if report.get("documentary_only"):
                        return {
                            "academic_year": year,
                            "assignment_id": assignment_id,
                            "class_id": report.get("class_id"),
                            "documentary_only": True,
                            "total_alerts": 0,
                            "alerts": [],
                        }

                    class_info = report.get("class") or {}
                    alerts = []
                    for row in report.get("students") or []:
                        percentage = float(row.get("attendance_percentage") or 0)
                        total = int(row.get("total") or 0)
                        if total <= 0 or percentage >= 75:
                            continue
                        alerts.append({
                            "student_id": row.get("student_id"),
                            "student_name": row.get("student_name"),
                            "class_id": report.get("class_id") or class_info.get("id"),
                            "class_name": class_info.get("name"),
                            "school_id": report_school,
                            "attendance_percentage": percentage,
                            "total_records": total,
                            "absent": int(row.get("absent") or 0),
                        })
                    alerts.sort(key=lambda item: item["attendance_percentage"])
                    return {
                        "academic_year": year,
                        "assignment_id": assignment_id,
                        "class_id": report.get("class_id") or class_info.get("id"),
                        "documentary_only": False,
                        "total_alerts": len(alerts),
                        "alerts": alerts,
                    }

                return await legacy_alerts(**_accepted_call(legacy_alerts, {
                    "request": request,
                    "school_id": school_id,
                    "academic_year": academic_year,
                }))

        attendance_ext_mod.router._dvd_phase4_ext_guard = True
        return result

    attendance_ext_mod.setup_router = wrapped_setup
    attendance_ext_mod._dvd_phase4_setup_wrapped = True
