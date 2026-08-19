"""
Bulletins router — Boletim Online (Passo 5 — MVP, Fev/2026).

Endpoint canônico, READ-ONLY ABSOLUTO:
- GET /api/students/{student_id}/bulletin?academic_year=YYYY

Princípio: boletim é PROJEÇÃO. Consome ``bulletin_builder`` que por sua vez
consome ``compute_composite_closure`` (NUNCA o diário vivo).

PR #54: professor só acessa estudante pertencente ao seu roster avaliativo
canônico do Diário por Vínculo. Tenant/escola isolados não são autorização
pedagógica suficiente.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import AuthMiddleware
from services.teacher_grade_access import (
    TeacherGradeAccessError,
    ensure_teacher_student_grade_access,
)
from tenant_scope import apply_tenant_filter, get_mantenedora_scope
from utils.bulletin_builder import (
    build_student_bulletin,
    build_student_dependency_bulletin,
    list_student_bulletins,
)

logger = logging.getLogger(__name__)

ROLES_VIEW_BULLETIN = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "apoio_pedagogico", "professor",
    "semed", "semed1", "semed2", "semed3",
    "aluno", "responsavel",
}


async def _ensure_can_view_student(
    db,
    user,
    student_id: str,
    request: Request,
    *,
    academic_year: int,
) -> set[str]:
    """Valida acesso e retorna turmas autorizadas quando o papel é professor."""
    role = user.get("role")
    if role not in ROLES_VIEW_BULLETIN:
        raise HTTPException(status_code=403, detail="Sem permissão.")

    if role == "aluno":
        uid = user.get("student_id") or user.get("linked_student_id")
        if not uid or uid != student_id:
            raise HTTPException(status_code=403, detail="Estudante só vê o próprio boletim.")
        return set()

    if role == "responsavel":
        allowed = set(user.get("dependents") or user.get("student_ids") or [])
        if student_id not in allowed:
            raise HTTPException(status_code=403, detail="Responsável só vê estudantes vinculados.")
        return set()

    if role == "professor":
        try:
            _, memberships = await ensure_teacher_student_grade_access(
                db,
                user,
                student_id=student_id,
                academic_year=academic_year,
                active_mantenedora_id=get_mantenedora_scope(user, request),
            )
        except TeacherGradeAccessError as exc:
            raise HTTPException(
                status_code=403,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        return memberships

    # Demais perfis institucionais mantêm o tenant scope existente.
    stu_filter = apply_tenant_filter({"id": student_id}, user, request)
    student = await db.students.find_one(stu_filter, {"_id": 0, "id": 1})
    if not student:
        raise HTTPException(status_code=404, detail="Estudante não encontrado")
    return set()


def setup_bulletins_router(db) -> APIRouter:
    router = APIRouter(prefix="/students", tags=["Bulletins (Boletim Online)"])

    @router.get("/{student_id}/bulletin")
    async def get_student_bulletin(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        """Retorna o boletim canônico do estudante no ano (read-model)."""
        user = await AuthMiddleware.get_current_user(request)
        await _ensure_can_view_student(
            db,
            user,
            student_id,
            request,
            academic_year=academic_year,
        )

        tenant = get_mantenedora_scope(user, request)
        bulletin = await build_student_bulletin(
            db,
            student_id=student_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        if bulletin.get("student") is None:
            raise HTTPException(status_code=404, detail="Estudante não encontrado")
        return bulletin

    @router.get("/{student_id}/bulletins-index")
    async def get_student_bulletins_index(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        """Catálogo de boletins disponíveis (regular + dependência por turma)."""
        user = await AuthMiddleware.get_current_user(request)
        memberships = await _ensure_can_view_student(
            db,
            user,
            student_id,
            request,
            academic_year=academic_year,
        )
        items = await list_student_bulletins(
            db,
            student_id=student_id,
            academic_year=academic_year,
        )
        if user.get("role") == "professor":
            items = [
                item
                for item in items
                if str(item.get("class_id") or "") in memberships
            ]
        return {
            "student_id": student_id,
            "academic_year": academic_year,
            "items": items,
            "total": len(items),
        }

    @router.get("/{student_id}/dependency-bulletin")
    async def get_student_dependency_bulletin(
        student_id: str,
        request: Request,
        target_class_id: str = Query(..., min_length=1),
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        """Boletim de dependência para turma específica."""
        user = await AuthMiddleware.get_current_user(request)
        memberships = await _ensure_can_view_student(
            db,
            user,
            student_id,
            request,
            academic_year=academic_year,
        )
        if user.get("role") == "professor" and target_class_id not in memberships:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "TEACHER_DEPENDENCY_BULLETIN_SCOPE_DENIED",
                    "message": "A turma da dependência não pertence ao escopo avaliativo do professor.",
                },
            )

        tenant = get_mantenedora_scope(user, request)
        bulletin = await build_student_dependency_bulletin(
            db,
            student_id=student_id,
            target_class_id=target_class_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        if bulletin.get("student") is None:
            raise HTTPException(status_code=404, detail="Estudante não encontrado")
        return bulletin

    return router


def setup_admin_bulletins_router(db) -> APIRouter:
    """Alias compatível em ``/api/bulletins/student/{student_id}``."""
    router = APIRouter(prefix="/bulletins", tags=["Bulletins (alias)"])

    @router.get("/student/{student_id}")
    async def alias_get(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        from utils.bulletin_builder import build_student_bulletin as _build

        user = await AuthMiddleware.get_current_user(request)
        await _ensure_can_view_student(
            db,
            user,
            student_id,
            request,
            academic_year=academic_year,
        )

        tenant = get_mantenedora_scope(user, request)
        bulletin = await _build(
            db,
            student_id=student_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        if bulletin.get("student") is None:
            raise HTTPException(status_code=404, detail="Estudante não encontrado")
        return bulletin

    return router
