"""Leitura segura de "Meus Diários" — DVD Fase 3.

Esta camada é somente organizadora. Ela lista vínculos DVD vigentes do professor
logado e deriva capacidades do contrato canônico. Não grava conteúdo, frequência
ou notas e não altera o comportamento dos módulos pedagógicos existentes.
"""

from datetime import date
from typing import Any, Mapping, Optional

from services.diary_assignment_access import (
    DiaryAction,
    DiaryAssignmentAccessError,
    authorize_assignment_access,
)


async def _find_many(collection, query: dict, limit: int = 2000) -> list[dict]:
    cursor = collection.find(query, {"_id": 0})
    return await cursor.to_list(limit)


async def list_teacher_diaries(
    db,
    current_user: Mapping[str, Any],
    *,
    academic_year: Optional[int] = None,
    reference_date: Optional[str] = None,
    active_mantenedora_id: Optional[str] = None,
) -> dict:
    """Retorna somente os vínculos DVD vigentes do professor autenticado.

    Invariantes:
    - nunca aceita `teacher_id` externo; usa exclusivamente `current_user.id`;
    - só considera `diary_settings.enabled=true` e assignments não excluídos;
    - cada candidato é revalidado por `authorize_assignment_access`;
    - AEE e etapas fora do DVD v1 são eliminados pelo autorizador canônico;
    - tenant e escola permanecem fail-closed;
    - capacidades são derivadas do perfil, nunca persistidas novamente;
    - frequência/notas podem aparecer como capacidades, mas a Fase 3 não as
      integra funcionalmente aos módulos existentes.
    """
    teacher_id = current_user.get("id")
    if not teacher_id:
        return {"items": [], "total": 0, "blocked_total": 0}

    on_date = reference_date or date.today().isoformat()
    query = {
        "teacher_id": teacher_id,
        "deleted": False,
        "diary_settings.enabled": True,
        "valid_from": {"$lte": on_date},
        "$or": [{"valid_until": None}, {"valid_until": {"$gte": on_date}}],
    }
    candidates = await _find_many(db.teacher_class_assignments, query)

    items: list[dict] = []
    blocked_total = 0

    for assignment in candidates:
        try:
            context = await authorize_assignment_access(
                db,
                current_user,
                assignment.get("id"),
                action=DiaryAction.VIEW,
                on_date=on_date,
                expected_class_id=assignment.get("class_id"),
                active_mantenedora_id=active_mantenedora_id,
            )
        except DiaryAssignmentAccessError:
            blocked_total += 1
            continue

        class_info = await db.classes.find_one(
            {"id": assignment.get("class_id")},
            {
                "_id": 0,
                "id": 1,
                "name": 1,
                "school_id": 1,
                "mantenedora_id": 1,
                "academic_year": 1,
                "education_level": 1,
                "nivel_ensino": 1,
                "grade_level": 1,
                "grade": 1,
                "shift": 1,
                "atendimento_programa": 1,
            },
        )
        if not class_info:
            blocked_total += 1
            continue

        if academic_year is not None:
            class_year = class_info.get("academic_year")
            if class_year is not None and str(class_year) != str(academic_year):
                continue

        school = None
        if class_info.get("school_id"):
            school = await db.schools.find_one(
                {"id": class_info.get("school_id")}, {"_id": 0, "id": 1, "name": 1}
            )

        component = None
        if assignment.get("component_id"):
            component = await db.courses.find_one(
                {"id": assignment.get("component_id")},
                {"_id": 0, "id": 1, "name": 1},
            )

        capabilities = context.settings.capabilities
        attendance_purpose = capabilities.attendance_purpose

        items.append({
            "assignment_id": assignment.get("id"),
            "teacher_id": assignment.get("teacher_id"),
            "class_id": assignment.get("class_id"),
            "class_name": class_info.get("name") or assignment.get("class_name"),
            "school_id": class_info.get("school_id") or assignment.get("school_id"),
            "school_name": school.get("name") if school else None,
            "component_id": assignment.get("component_id"),
            "component_name": component.get("name") if component else None,
            "academic_year": class_info.get("academic_year"),
            "education_level": class_info.get("education_level") or class_info.get("nivel_ensino"),
            "grade_level": class_info.get("grade_level") or class_info.get("grade"),
            "shift": assignment.get("shift") or class_info.get("shift"),
            "valid_from": assignment.get("valid_from"),
            "valid_until": assignment.get("valid_until"),
            "is_substitute": bool(assignment.get("is_substitute")),
            "profile": context.settings.profile.value,
            "student_scope": context.settings.student_scope.value,
            "schema_version": context.settings.schema_version,
            "capabilities": {
                "content_enabled": capabilities.content_enabled,
                "attendance_enabled": capabilities.attendance_enabled,
                "attendance_required": capabilities.attendance_required,
                "attendance_mode": capabilities.attendance_mode.value,
                "attendance_purpose": attendance_purpose.value if attendance_purpose else None,
                "grades_enabled": capabilities.grades_enabled,
            },
        })

    items.sort(key=lambda item: (
        (item.get("school_name") or "").casefold(),
        (item.get("class_name") or "").casefold(),
        (item.get("component_name") or "").casefold(),
        item.get("assignment_id") or "",
    ))

    return {
        "items": items,
        "total": len(items),
        "blocked_total": blocked_total,
        "reference_date": on_date,
        "academic_year": academic_year,
    }
