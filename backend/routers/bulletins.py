"""
Bulletins router — Boletim Online (Passo 5 — MVP, Fev/2026).

Único endpoint canônico, READ-ONLY ABSOLUTO:
- GET /api/students/{student_id}/bulletin?academic_year=YYYY

Princípio: boletim é PROJEÇÃO. Consome `bulletin_builder` que por sua vez
consome `compute_composite_closure` (NUNCA o diário vivo).

PROIBIDO nesta V1:
- ❌ POST/PUT/DELETE
- ❌ PDF/HTML/QR/Hash/Assinatura/Snapshot
- ❌ render_jobs (camada Fase 6)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth_middleware import AuthMiddleware
from tenant_scope import apply_tenant_filter, get_mantenedora_scope
from utils.bulletin_builder import build_student_bulletin

logger = logging.getLogger(__name__)

ROLES_VIEW_BULLETIN = {
    "super_admin", "admin", "admin_teste", "gerente", "secretario", "diretor",
    "coordenador", "apoio_pedagogico", "professor",
    "semed", "semed1", "semed2", "semed3",
    # Aluno e responsável: acesso restringido em runtime (ver lógica abaixo).
    "aluno", "responsavel",
}


def setup_bulletins_router(db) -> APIRouter:
    router = APIRouter(prefix="/students", tags=["Bulletins (Boletim Online)"])

    # -------------------------------------------------------------------
    @router.get("/{student_id}/bulletin")
    async def get_student_bulletin(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        """Retorna o boletim canônico do aluno no ano (read-model)."""
        user = await AuthMiddleware.get_current_user(request)
        role = user.get("role")
        if role not in ROLES_VIEW_BULLETIN:
            raise HTTPException(status_code=403, detail="Sem permissão.")

        # Aluno só pode ver o próprio boletim
        if role == "aluno":
            user_student_id = user.get("student_id") or user.get("linked_student_id")
            if not user_student_id or user_student_id != student_id:
                raise HTTPException(
                    status_code=403,
                    detail="Aluno só pode acessar o próprio boletim.",
                )
        # Responsável só vê alunos vinculados (relação guardian-student)
        elif role == "responsavel":
            allowed_ids = set(user.get("dependents") or user.get("student_ids") or [])
            if student_id not in allowed_ids:
                raise HTTPException(
                    status_code=403,
                    detail="Responsável só pode acessar alunos vinculados.",
                )
        else:
            # Demais roles: validar tenant scope
            stu_filter = apply_tenant_filter({"id": student_id}, user, request)
            student = await db.students.find_one(stu_filter, {"_id": 0, "id": 1})
            if not student:
                raise HTTPException(status_code=404, detail="Aluno não encontrado")

        tenant = get_mantenedora_scope(user, request)
        bulletin = await build_student_bulletin(
            db,
            student_id=student_id,
            academic_year=academic_year,
            mantenedora_id=tenant,
        )
        # Caso aluno not found (skipped tenant filter para aluno/responsavel)
        if bulletin.get("student") is None:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return bulletin

    return router


def setup_admin_bulletins_router(db) -> APIRouter:
    """Variante usada quando precisamos do prefixo /api/bulletins (não obrigatório).

    Mantida apenas para retrocompatibilidade futura. O endpoint canônico
    permanece em /api/students/{id}/bulletin.
    """
    router = APIRouter(prefix="/bulletins", tags=["Bulletins (alias)"])

    @router.get("/student/{student_id}")
    async def alias_get(
        student_id: str,
        request: Request,
        academic_year: int = Query(..., ge=1900, le=2100),
    ):
        # Reusa a lógica do endpoint canônico via redirecionamento interno.
        from utils.bulletin_builder import build_student_bulletin as _build
        user = await AuthMiddleware.get_current_user(request)
        role = user.get("role")
        if role not in ROLES_VIEW_BULLETIN:
            raise HTTPException(status_code=403, detail="Sem permissão.")
        if role == "aluno":
            uid = user.get("student_id") or user.get("linked_student_id")
            if not uid or uid != student_id:
                raise HTTPException(status_code=403, detail="Sem permissão.")
        elif role == "responsavel":
            allowed = set(user.get("dependents") or user.get("student_ids") or [])
            if student_id not in allowed:
                raise HTTPException(status_code=403, detail="Sem permissão.")
        else:
            stu_filter = apply_tenant_filter({"id": student_id}, user, request)
            student = await db.students.find_one(stu_filter, {"_id": 0, "id": 1})
            if not student:
                raise HTTPException(status_code=404, detail="Aluno não encontrado")

        tenant = get_mantenedora_scope(user, request)
        bulletin = await _build(
            db, student_id=student_id, academic_year=academic_year,
            mantenedora_id=tenant,
        )
        if bulletin.get("student") is None:
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        return bulletin

    return router
