"""Roster de estudantes para a frequência DVD.

Replica as fontes institucionais usadas pela tela histórica de Frequência sem
alterar a coleção de matrículas: ativos, vínculo direto e históricos relevantes.
`shared/group` é bloqueado antes de chegar aqui enquanto não houver membros
canônicos do grupo.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


async def build_attendance_roster(
    db,
    *,
    class_id: str,
    academic_year: int,
    course_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    active_enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active"},
        {
            "_id": 0,
            "student_id": 1,
            "enrollment_number": 1,
            "academic_year": 1,
            "enrollment_date": 1,
        },
    ).to_list(1000)

    active_ids: set[str] = set()
    enrollment_numbers: dict[str, Any] = {}
    enrollment_dates: dict[str, Any] = {}
    for enrollment in active_enrollments:
        sid = enrollment.get("student_id")
        if not sid:
            continue
        active_ids.add(sid)
        if sid not in enrollment_numbers or enrollment.get("academic_year") == academic_year:
            enrollment_numbers[sid] = enrollment.get("enrollment_number")
        if enrollment.get("enrollment_date"):
            enrollment_dates[sid] = enrollment.get("enrollment_date")

    inactive_enrollments = await db.enrollments.find(
        {
            "class_id": class_id,
            "status": {"$in": ["transferred", "dropout", "relocated", "progressed", "reclassified"]},
        },
        {"_id": 0, "student_id": 1, "enrollment_number": 1, "academic_year": 1, "status": 1},
    ).to_list(1000)

    inactive_ids: set[str] = set()
    for enrollment in inactive_enrollments:
        sid = enrollment.get("student_id")
        if not sid or sid in active_ids:
            continue
        inactive_ids.add(sid)
        if sid not in enrollment_numbers or enrollment.get("academic_year") == academic_year:
            enrollment_numbers[sid] = enrollment.get("enrollment_number")

    direct_students = await db.students.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
        {"_id": 0, "id": 1, "enrollment_number": 1},
    ).to_list(1000)
    direct_ids = {s.get("id") for s in direct_students if s.get("id")}
    for student in direct_students:
        sid = student.get("id")
        if sid and sid not in enrollment_numbers:
            enrollment_numbers[sid] = student.get("enrollment_number")

    all_ids = list(active_ids | inactive_ids | direct_ids)
    students = []
    if all_ids:
        students = await db.students.find(
            {"id": {"$in": all_ids}},
            {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "status": 1, "class_id": 1},
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

    action_info: dict[str, dict[str, Any]] = {}
    if inactive_ids:
        action_labels = {
            "transferencia_saida": "Transferido",
            "remanejamento": "Remanejado",
            "progressao": "Progredido",
            "reclassificacao": "Reclassificado",
            "desistencia": "Desistente",
            "cancelamento": "Cancelado",
        }
        history = await db.student_history.find(
            {
                "student_id": {"$in": list(inactive_ids)},
                "class_id": class_id,
                "action_type": {"$in": list(action_labels)},
            },
            {"_id": 0, "student_id": 1, "action_type": 1, "action_date": 1},
        ).sort("action_date", -1).to_list(1000)
        for item in history:
            sid = item.get("student_id")
            if sid and sid not in action_info:
                action_info[sid] = {
                    "action_label": action_labels.get(item.get("action_type"), ""),
                    "action_date": item.get("action_date", ""),
                }

    result = [
        {
            "id": student.get("id"),
            "full_name": student.get("full_name", ""),
            "enrollment_number": enrollment_numbers.get(student.get("id")) or student.get("enrollment_number"),
            "status": None,
            "student_status": student.get("status", "active"),
            "current_class_id": student.get("class_id"),
            "is_transferred_from_class": bool(
                student.get("class_id") and student.get("class_id") != class_id
            ),
            "action_label": action_info.get(student.get("id"), {}).get("action_label", ""),
            "action_date": action_info.get(student.get("id"), {}).get("action_date", ""),
            "enrollment_date": enrollment_dates.get(student.get("id"), ""),
            "is_dependency": False,
            "dependency_id": None,
            "display_label": "",
        }
        for student in students
    ]

    # Dependência é preservada quando o vínculo possui componente explícito.
    if course_id:
        dep_query: dict[str, Any] = {
            "class_id": class_id,
            "course_id": course_id,
            "status": "active",
        }
        if tenant_id:
            dep_query["mantenedora_id"] = tenant_id
        dependencies = await db.student_dependencies.find(dep_query, {"_id": 0}).to_list(200)
        existing = {item.get("id") for item in result}
        dep_ids = [d.get("student_id") for d in dependencies if d.get("student_id") not in existing]
        dep_ids = [sid for sid in dep_ids if sid]
        if dep_ids:
            from utils.diary_constants import DEPENDENCY_DISPLAY_LABEL

            dep_students = await db.students.find(
                {"id": {"$in": dep_ids}},
                {"_id": 0, "id": 1, "full_name": 1, "enrollment_number": 1, "status": 1, "dependency_mode": 1},
            ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(200)
            dep_by_sid = {d.get("student_id"): d for d in dependencies}
            student_by_id = {s.get("id"): s for s in dep_students}
            for sid in dep_ids:
                dep = dep_by_sid.get(sid)
                student = student_by_id.get(sid)
                if not dep or not student:
                    continue
                result.append({
                    "id": sid,
                    "full_name": student.get("full_name", ""),
                    "enrollment_number": student.get("enrollment_number"),
                    "status": None,
                    "student_status": student.get("status", "active"),
                    "current_class_id": None,
                    "is_transferred_from_class": False,
                    "action_label": "",
                    "action_date": "",
                    "enrollment_date": "",
                    "is_dependency": True,
                    "dependency_id": dep.get("id"),
                    "dependency_type": student.get("dependency_mode"),
                    "origin_academic_year": dep.get("origin_academic_year"),
                    "display_label": DEPENDENCY_DISPLAY_LABEL,
                })

    return result
