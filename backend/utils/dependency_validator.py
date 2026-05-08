"""
Dependency ID Coherence Validator (Fase 2).

[Fev/2026] Anti-spoof: o backend NÃO confia no payload do navegador.
Toda escrita de attendance ou grade que carregar `dependency_id != null`
DEVE passar por aqui antes de gravar.

Princípio: o frontend pode mentir. O backend valida.

Regras (todas obrigatórias):
1. dependency_id existe na coleção `student_dependencies`.
2. dependência está com `status='active'`.
3. dependência pertence ao mesmo `student_id` declarado no payload.
4. dependência pertence ao mesmo `class_id` e `course_id` da operação.
5. dependência pertence ao mesmo tenant do usuário operador.

Qualquer violação → HTTP 422 com `code=DEPENDENCY_COHERENCE_*` no detail.

Uso:
    from utils.dependency_validator import validate_dependency_link

    await validate_dependency_link(
        db=current_db,
        dependency_id=record.dependency_id,
        student_id=record.student_id,
        class_id=class_id,
        course_id=course_id,
        tenant_id=current_user.get("mantenedora_id"),
    )
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException


async def validate_dependency_link(
    *,
    db,
    dependency_id: str,
    student_id: str,
    class_id: str,
    course_id: Optional[str],
    tenant_id: Optional[str],
) -> dict:
    """Valida coerência de um vínculo dep_id → student/class/course/tenant.

    Returns:
        Documento da dependência (sem `_id`) — útil para logging/audit.

    Raises:
        HTTPException(422) com payload estruturado.
    """
    if not dependency_id:
        raise HTTPException(
            status_code=422,
            detail={"code": "DEPENDENCY_COHERENCE_EMPTY", "message": "dependency_id vazio."},
        )

    dep = await db.student_dependencies.find_one(
        {"id": dependency_id}, {"_id": 0}
    )
    if not dep:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEPENDENCY_COHERENCE_NOT_FOUND",
                "message": "Dependência referenciada não existe.",
                "dependency_id": dependency_id,
            },
        )

    if dep.get("status") != "active":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEPENDENCY_COHERENCE_INACTIVE",
                "message": "Dependência não está ativa — frequência/notas bloqueadas.",
                "dependency_id": dependency_id,
                "status": dep.get("status"),
            },
        )

    if dep.get("student_id") != student_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEPENDENCY_COHERENCE_STUDENT_MISMATCH",
                "message": "dependency_id não pertence a este aluno.",
            },
        )

    if dep.get("class_id") != class_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEPENDENCY_COHERENCE_CLASS_MISMATCH",
                "message": "dependency_id não pertence a esta turma.",
            },
        )

    if course_id and dep.get("course_id") != course_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEPENDENCY_COHERENCE_COURSE_MISMATCH",
                "message": "dependency_id não pertence a este componente.",
            },
        )

    if tenant_id and dep.get("mantenedora_id") and dep.get("mantenedora_id") != tenant_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "DEPENDENCY_COHERENCE_TENANT_MISMATCH",
                "message": "dependency_id pertence a outro tenant.",
            },
        )

    return dep
