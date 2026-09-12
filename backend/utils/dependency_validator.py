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

from utils.curriculum_resolver import _series_tokens


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
                "message": "dependency_id não pertence a este estudante.",
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



def _target_error(code: str, message: str, **extra) -> None:
    detail = {"code": code, "message": message}
    detail.update(extra)
    raise HTTPException(status_code=422, detail=detail)


def validate_dependency_target_values(
    *,
    class_doc: dict,
    course_doc: dict,
    effective_course_ids,
    school_id: str,
    course_id: str,
    target_series: Optional[str],
) -> dict:
    """Valida, sem I/O, a coerência curricular do destino da dependência.

    A matrícula regular atual do estudante não participa desta decisão. O vínculo
    é determinado pela turma de destino, sua série efetiva e pelo componente
    efetivamente oferecido nela.
    """
    if class_doc.get("school_id") != school_id:
        _target_error(
            "DEPENDENCY_TARGET_SCHOOL_MISMATCH",
            "A turma selecionada não pertence à escola de destino informada.",
            class_school_id=class_doc.get("school_id"),
            requested_school_id=school_id,
        )

    effective_ids = {str(value) for value in (effective_course_ids or []) if value}
    if course_id not in effective_ids:
        _target_error(
            "DEPENDENCY_TARGET_COURSE_NOT_IN_CLASS",
            "O componente selecionado não integra a matriz/vínculos ativos da turma de destino.",
            class_id=class_doc.get("id"),
            course_id=course_id,
        )

    class_tokens = _series_tokens(class_doc.get("series") or class_doc.get("grade_level"))
    target_tokens = _series_tokens(target_series)
    is_multi_with_choice = bool(class_doc.get("is_multi_grade")) and len(class_tokens) >= 2

    if is_multi_with_choice:
        if not target_tokens:
            _target_error(
                "DEPENDENCY_TARGET_SERIES_REQUIRED",
                "Turma multisseriada exige a série da dependência.",
                class_id=class_doc.get("id"),
            )
        if len(target_tokens) != 1:
            _target_error(
                "DEPENDENCY_TARGET_SERIES_AMBIGUOUS",
                "Selecione uma única série para a dependência.",
                target_series=target_series,
            )
        if not target_tokens.issubset(class_tokens):
            _target_error(
                "DEPENDENCY_TARGET_SERIES_NOT_IN_CLASS",
                "A série selecionada não é atendida pela turma multisseriada de destino.",
                target_series=target_series,
                class_series=class_doc.get("series") or class_doc.get("grade_level"),
            )
        effective_series_tokens = target_tokens
    else:
        regular_tokens = _series_tokens(class_doc.get("grade_level"))
        if target_tokens and regular_tokens and not (target_tokens & regular_tokens):
            _target_error(
                "DEPENDENCY_TARGET_SERIES_NOT_IN_CLASS",
                "A série informada não corresponde à turma de destino.",
                target_series=target_series,
                class_grade_level=class_doc.get("grade_level"),
            )
        effective_series_tokens = target_tokens or regular_tokens or class_tokens

    grade_levels = course_doc.get("grade_levels") or []
    if grade_levels:
        course_tokens = _series_tokens(grade_levels)
        if not course_tokens:
            _target_error(
                "DEPENDENCY_TARGET_COURSE_SERIES_UNVERIFIABLE",
                "O componente possui escopo de série cadastrado, mas ele não pôde ser interpretado com segurança.",
                course_id=course_id,
                grade_levels=grade_levels,
            )
        if not effective_series_tokens:
            _target_error(
                "DEPENDENCY_TARGET_SERIES_CONTEXT_MISSING",
                "Não foi possível determinar a série efetiva da dependência.",
                class_id=class_doc.get("id"),
            )
        if not (course_tokens & effective_series_tokens):
            _target_error(
                "DEPENDENCY_TARGET_COURSE_SERIES_MISMATCH",
                "O componente selecionado não se aplica à série escolhida para a dependência.",
                course_id=course_id,
                target_series=target_series or class_doc.get("grade_level"),
                grade_levels=grade_levels,
            )

    return {
        "class_id": class_doc.get("id"),
        "course_id": course_id,
        "target_series": target_series or class_doc.get("grade_level"),
        "is_multi_grade": bool(class_doc.get("is_multi_grade")),
    }


async def validate_dependency_target(
    *,
    db,
    class_id: str,
    school_id: str,
    course_id: str,
    target_series: Optional[str],
    tenant_id: Optional[str],
) -> dict:
    """Valida criação contra a matriz efetiva da turma de destino.

    Replica o contrato do endpoint `/classes/{id}/curriculum`:
    `class.course_ids ∪ teacher_assignments ativos`.
    """
    cls = await db.classes.find_one(
        {"id": class_id},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "course_ids": 1,
            "is_multi_grade": 1,
            "series": 1,
            "grade_level": 1,
        },
    )
    if not cls:
        raise HTTPException(status_code=404, detail="Turma de destino não encontrada.")
    if tenant_id and cls.get("mantenedora_id") and cls.get("mantenedora_id") != tenant_id:
        _target_error(
            "DEPENDENCY_TARGET_CLASS_TENANT_MISMATCH",
            "A turma de destino pertence a outra mantenedora.",
        )

    effective_ids = []
    seen = set()
    for cid in (cls.get("course_ids") or []):
        if cid and cid not in seen:
            seen.add(cid)
            effective_ids.append(cid)

    async for assignment in db.teacher_assignments.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo", "ativo"]}},
        {"_id": 0, "course_id": 1},
    ):
        cid = assignment.get("course_id")
        if cid and cid not in seen:
            seen.add(cid)
            effective_ids.append(cid)

    course = await db.courses.find_one(
        {"id": course_id},
        {"_id": 0, "id": 1, "mantenedora_id": 1, "grade_levels": 1},
    )
    if not course:
        raise HTTPException(status_code=404, detail="Componente curricular não encontrado.")
    if tenant_id and course.get("mantenedora_id") and course.get("mantenedora_id") != tenant_id:
        _target_error(
            "DEPENDENCY_TARGET_COURSE_TENANT_MISMATCH",
            "O componente selecionado pertence a outra mantenedora.",
        )

    return validate_dependency_target_values(
        class_doc=cls,
        course_doc=course,
        effective_course_ids=effective_ids,
        school_id=school_id,
        course_id=course_id,
        target_series=target_series,
    )
