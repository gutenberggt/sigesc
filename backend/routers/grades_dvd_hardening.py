"""Hardening residual da Fase 5 — Notas/Conceitos por Vínculo Docente.

Complementa ``grades_dvd`` em dois cenários que não podem cair no legado:

1. um documento já possui ``grade_ownership`` histórico, mas o assignment vivo
   foi alterado (ex.: component_id mudou) e deixa de ser candidato atual;
2. o sync pull do professor precisa paginar **depois** de filtrar por autoria,
   e não filtrar uma página consolidada já montada.

A camada é propositalmente pequena e instalada sobre o mesmo APIRouter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request

from auth_middleware import AuthMiddleware
from models import GradeCreate, GradeUpdate
from services.grade_assignment_scope import (
    GRADE_OWNERSHIP_FIELDS,
    GradeAssignmentScopeError,
    resolve_own_grade_assignment,
)
from tenant_scope import apply_tenant_filter, get_mantenedora_scope


def _remove_route(base_router, path: str, method: str):
    for route in list(base_router.routes):
        if (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        ):
            endpoint = route.endpoint
            base_router.routes.remove(route)
            return endpoint
    return None


async def _has_historical_ownership(
    current_db,
    *,
    class_id: str,
    course_id: str,
    academic_year: int,
) -> bool:
    doc = await current_db.grades.find_one(
        {
            "class_id": class_id,
            "course_id": course_id,
            "academic_year": academic_year,
            "grade_ownership": {"$exists": True, "$ne": {}},
        },
        {"_id": 0, "id": 1},
    )
    return bool(doc)


async def _active_context_or_none(
    current_db,
    user: dict,
    request: Request,
    *,
    class_id: str,
    course_id: str,
):
    try:
        return await resolve_own_grade_assignment(
            current_db,
            user,
            class_id=class_id,
            course_id=course_id,
            on_date=datetime.now(timezone.utc).date().isoformat(),
            active_mantenedora_id=get_mantenedora_scope(user, request),
        )
    except GradeAssignmentScopeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


async def _block_historical_write_bypass(
    current_db,
    user: dict,
    request: Request,
    *,
    class_id: str,
    course_id: str,
    academic_year: int,
) -> None:
    if user.get("role") != "professor":
        return
    context = await _active_context_or_none(
        current_db,
        user,
        request,
        class_id=class_id,
        course_id=course_id,
    )
    if context is not None:
        return
    if await _has_historical_ownership(
        current_db,
        class_id=class_id,
        course_id=course_id,
        academic_year=academic_year,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DVD_HISTORICAL_OWNERSHIP_REQUIRES_ACTIVE_ASSIGNMENT",
                "message": (
                    "Há autoria DVD histórica neste componente, mas não existe vínculo ativo "
                    "compatível para nova escrita. A correção deve ser realizada pela gestão."
                ),
            },
        )


def _mask_grade_for_teacher(grade: dict, teacher_id: str) -> Optional[dict]:
    ownership = grade.get("grade_ownership") or {}
    owned = {
        field
        for field, snapshot in ownership.items()
        if isinstance(snapshot, dict) and snapshot.get("teacher_id") == teacher_id
    }
    if not owned:
        return None
    out = dict(grade)
    for field in GRADE_OWNERSHIP_FIELDS:
        if field not in owned:
            out[field] = None
    out["grade_ownership"] = {
        field: dict(snapshot)
        for field, snapshot in ownership.items()
        if field in owned and isinstance(snapshot, dict)
    }
    foreign_value = any(
        grade.get(field) is not None and field not in owned
        for field in ("b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery")
    )
    if foreign_value:
        out["final_average"] = None
        out["status"] = "cursando"
    out["dvd_owned_fields"] = sorted(owned)
    out["dvd_locked_fields"] = []
    return out


def install_grades_dvd_hardening(base_router, db, *, sandbox_db=None):
    if getattr(base_router, "_dvd_phase5_hardening_installed", False):
        return base_router

    def _db_for_user(user):
        if user.get("is_sandbox"):
            return sandbox_db if sandbox_db is not None else db
        return db

    current_list = _remove_route(base_router, "/grades", "GET")
    current_by_class = _remove_route(
        base_router, "/grades/by-class/{class_id}/{course_id}", "GET"
    )
    current_create = _remove_route(base_router, "/grades", "POST")
    current_update = _remove_route(base_router, "/grades/{grade_id}", "PUT")
    current_batch = _remove_route(base_router, "/grades/batch", "POST")

    @base_router.get("")
    async def hardened_list(
        request: Request,
        student_id: Optional[str] = None,
        class_id: Optional[str] = None,
        course_id: Optional[str] = None,
        academic_year: Optional[int] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        result = await current_list(
            request,
            student_id,
            class_id,
            course_id,
            academic_year,
            assignment_id,
        )
        if user.get("role") != "professor" or (class_id and course_id):
            return result
        visible = []
        for grade in result:
            own = _mask_grade_for_teacher(grade, user.get("id"))
            if own is not None:
                visible.append(own)
        return visible

    @base_router.get("/by-class/{class_id}/{course_id}")
    async def hardened_by_class(
        class_id: str,
        course_id: str,
        request: Request,
        academic_year: Optional[int] = None,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        year = academic_year or datetime.now().year
        current_db = _db_for_user(user)
        if user.get("role") == "professor":
            context = await _active_context_or_none(
                current_db,
                user,
                request,
                class_id=class_id,
                course_id=course_id,
            )
            historical_only = (
                context is None
                and await _has_historical_ownership(
                    current_db,
                    class_id=class_id,
                    course_id=course_id,
                    academic_year=year,
                )
            )
            if historical_only:
                # O endpoint DVD interno cairia no legado porque o assignment vivo
                # deixou de ser compatível. Nesse caso, usa a rota legada capturada
                # por ele e mascara imediatamente o resultado pela autoria histórica.
                try:
                    result = await current_by_class(
                        class_id,
                        course_id,
                        request,
                        academic_year,
                        assignment_id,
                    )
                except HTTPException as exc:
                    # Se o adaptador interno bloquear antes da leitura, não
                    # reabrimos um caminho paralelo: fail-closed.
                    raise exc
                for item in result:
                    grade = item.get("grade")
                    if grade:
                        own = _mask_grade_for_teacher(grade, user.get("id"))
                        item["grade"] = own or {
                            **grade,
                            "b1": None,
                            "b2": None,
                            "b3": None,
                            "b4": None,
                            "rec_s1": None,
                            "rec_s2": None,
                            "recovery": None,
                            "observations": None,
                            "final_average": None,
                            "status": "cursando",
                            "grade_ownership": {},
                        }
                return result
        return await current_by_class(
            class_id,
            course_id,
            request,
            academic_year,
            assignment_id,
        )

    @base_router.post("")
    async def hardened_create(
        grade_data: GradeCreate,
        request: Request,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        payload = grade_data.model_dump()
        await _block_historical_write_bypass(
            _db_for_user(user),
            user,
            request,
            class_id=payload["class_id"],
            course_id=payload["course_id"],
            academic_year=payload["academic_year"],
        )
        return await current_create(grade_data, request, assignment_id)

    @base_router.put("/{grade_id}")
    async def hardened_update(
        grade_id: str,
        grade_update: GradeUpdate,
        request: Request,
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        current_db = _db_for_user(user)
        existing = await current_db.grades.find_one({"id": grade_id}, {"_id": 0})
        if existing:
            await _block_historical_write_bypass(
                current_db,
                user,
                request,
                class_id=existing["class_id"],
                course_id=existing["course_id"],
                academic_year=existing["academic_year"],
            )
        return await current_update(grade_id, grade_update, request, assignment_id)

    @base_router.post("/batch")
    async def hardened_batch(
        request: Request,
        grades: list[dict],
        assignment_id: Optional[str] = None,
    ):
        user = await AuthMiddleware.get_current_user(request)
        if grades:
            first = grades[0]
            await _block_historical_write_bypass(
                _db_for_user(user),
                user,
                request,
                class_id=first["class_id"],
                course_id=first["course_id"],
                academic_year=first["academic_year"],
            )
        return await current_batch(request, grades, assignment_id)

    # ----------------------- Sync offline -----------------------
    import routers.sync as sync_mod

    current_process = sync_mod.process_sync_operation
    current_fetch = sync_mod.fetch_collection_data_paginated

    async def hardened_process(db_arg, user, op, request=None):
        if op.collection == "grades" and user.get("role") == "professor":
            data = op.data or {}
            class_id = data.get("class_id")
            course_id = data.get("course_id")
            year = data.get("academic_year")
            if class_id and course_id and year:
                context = await _active_context_or_none(
                    db_arg,
                    user,
                    request,
                    class_id=class_id,
                    course_id=course_id,
                )
                if (
                    context is None
                    and await _has_historical_ownership(
                        db_arg,
                        class_id=class_id,
                        course_id=course_id,
                        academic_year=int(year),
                    )
                ):
                    return sync_mod.SyncPushResult(
                        recordId=op.recordId,
                        success=False,
                        error=(
                            "409: DVD_HISTORICAL_OWNERSHIP_REQUIRES_ACTIVE_ASSIGNMENT"
                        ),
                    )
        return await current_process(db_arg, user, op, request)

    async def hardened_fetch(
        db_arg,
        user,
        collection,
        class_id,
        academic_year,
        last_sync,
        page=1,
        page_size=100,
        request=None,
    ):
        if collection != "grades" or user.get("role") != "professor":
            return await current_fetch(
                db_arg,
                user,
                collection,
                class_id,
                academic_year,
                last_sync,
                page,
                page_size,
                request,
            )

        query: dict[str, Any] = {}
        if class_id:
            query["class_id"] = class_id
        if academic_year:
            try:
                query["academic_year"] = int(academic_year)
            except (TypeError, ValueError):
                query["academic_year"] = academic_year

        ownership_or = [
            {f"grade_ownership.{field}.teacher_id": user.get("id")}
            for field in GRADE_OWNERSHIP_FIELDS
        ]
        and_clauses: list[dict] = [{"$or": ownership_or}]
        if last_sync:
            and_clauses.append(
                {
                    "$or": [
                        {"created_at": {"$gte": last_sync}},
                        {"updated_at": {"$gte": last_sync}},
                    ]
                }
            )
        query["$and"] = and_clauses
        query = apply_tenant_filter(query, user, request)

        safe_page = max(1, int(page or 1))
        safe_size = max(1, min(500, int(page_size or 100)))
        skip = (safe_page - 1) * safe_size
        total = await db_arg.grades.count_documents(query)
        docs = await db_arg.grades.find(query, {"_id": 0}).skip(skip).limit(safe_size).to_list(safe_size)
        masked = []
        for grade in docs:
            own = _mask_grade_for_teacher(grade, user.get("id"))
            if own is not None:
                masked.append(own)
        return masked, total

    sync_mod.process_sync_operation = hardened_process
    sync_mod.fetch_collection_data_paginated = hardened_fetch

    base_router._dvd_phase5_hardening_installed = True
    return base_router
