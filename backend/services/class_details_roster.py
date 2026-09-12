"""Roster canônico usado pelos detalhes da turma e pelo PDF correspondente.

Preserva estudantes que já pertenceram à turma, exceto matrícula cancelada,
porque os estados de movimentação continuam fazendo parte do histórico escolar
da própria turma.
"""
from datetime import datetime
from typing import Any, Dict, List


INACTIVE_ENROLLMENT_STATUSES = [
    "transferred",
    "dropout",
    "relocated",
    "progressed",
    "reclassified",
]

ACTION_TYPE_LABELS = {
    "transferencia_saida": "Transferido",
    "remanejamento": "Remanejado",
    "progressao": "Progredido",
    "reclassificacao": "Reclassificado",
    "desistencia": "Desistente",
    "cancelamento": "Cancelado",
}

SPECIAL_PROGRAMS = {"aee", "recomposicao_aprendizagem", "reforco_escolar"}


async def build_class_students(db, class_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Monta a lista de estudantes exibida em Detalhes da Turma.

    Inclui:
    - matrículas ativas da turma;
    - vínculos legados diretos em ``students.class_id``;
    - vínculos de programas especiais já suportados pelo SIGESC;
    - estudantes transferidos, desistentes, remanejados, progredidos e
      reclassificados que já pertenceram à turma.

    Matrículas ``cancelled`` permanecem fora desta lista e continuam disponíveis
    apenas na visão específica de auditoria de matrículas canceladas.
    """
    class_id = class_doc.get("id")
    if not class_id:
        return []

    academic_year = class_doc.get("academic_year", datetime.now().year)
    atendimento = (class_doc.get("atendimento_programa") or "").strip().lower()
    is_special_class = atendimento in SPECIAL_PROGRAMS

    active_enrollments = await db.enrollments.find(
        {"class_id": class_id, "status": "active"},
        {
            "_id": 0,
            "student_id": 1,
            "enrollment_number": 1,
            "student_series": 1,
            "academic_year": 1,
        },
    ).to_list(1000)

    enrollment_map: Dict[str, Dict[str, Any]] = {}
    active_student_ids = set()
    for enrollment in active_enrollments:
        student_id = enrollment.get("student_id")
        if not student_id:
            continue
        active_student_ids.add(student_id)
        if student_id not in enrollment_map or enrollment.get("academic_year") == academic_year:
            enrollment_map[student_id] = {
                "enrollment_number": enrollment.get("enrollment_number"),
                "student_series": enrollment.get("student_series"),
            }

    inactive_enrollments = await db.enrollments.find(
        {
            "class_id": class_id,
            "status": {"$in": INACTIVE_ENROLLMENT_STATUSES},
        },
        {
            "_id": 0,
            "student_id": 1,
            "enrollment_number": 1,
            "student_series": 1,
            "academic_year": 1,
        },
    ).to_list(1000)

    inactive_student_ids = set()
    for enrollment in inactive_enrollments:
        student_id = enrollment.get("student_id")
        if not student_id or student_id in active_student_ids:
            continue
        inactive_student_ids.add(student_id)
        if student_id not in enrollment_map or enrollment.get("academic_year") == academic_year:
            enrollment_map[student_id] = {
                "enrollment_number": enrollment.get("enrollment_number"),
                "student_series": enrollment.get("student_series"),
            }

    direct_students = await db.students.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    direct_student_ids = {student.get("id") for student in direct_students if student.get("id")}

    program_student_ids = set()
    if is_special_class:
        program_students = await db.students.find(
            {
                "atendimento_programa_class_id": class_id,
                "status": {"$in": ["active", "Ativo"]},
            },
            {"_id": 0, "id": 1, "enrollment_number": 1},
        ).to_list(1000)

        for student in program_students:
            student_id = student.get("id")
            if not student_id:
                continue
            program_student_ids.add(student_id)
            if student_id not in enrollment_map:
                enrollment_map[student_id] = {
                    "enrollment_number": student.get("enrollment_number"),
                    "student_series": None,
                }

        if atendimento == "aee":
            plans = await db.planos_aee.find(
                {"school_id": class_doc.get("school_id")},
                {"_id": 0, "student_id": 1},
            ).to_list(1000)
            for plan in plans:
                student_id = plan.get("student_id")
                if (
                    student_id
                    and student_id not in active_student_ids
                    and student_id not in direct_student_ids
                    and student_id not in program_student_ids
                ):
                    program_student_ids.add(student_id)
                    if student_id not in enrollment_map:
                        student = await db.students.find_one(
                            {"id": student_id},
                            {"_id": 0, "enrollment_number": 1},
                        )
                        enrollment_map[student_id] = {
                            "enrollment_number": student.get("enrollment_number") if student else None,
                            "student_series": None,
                        }

            attendances = await db.atendimentos_aee.find(
                {"school_id": class_doc.get("school_id")},
                {"_id": 0, "student_id": 1},
            ).to_list(1000)
            for attendance in attendances:
                student_id = attendance.get("student_id")
                if (
                    student_id
                    and student_id not in active_student_ids
                    and student_id not in direct_student_ids
                    and student_id not in program_student_ids
                ):
                    program_student_ids.add(student_id)
                    if student_id not in enrollment_map:
                        student = await db.students.find_one(
                            {"id": student_id},
                            {"_id": 0, "enrollment_number": 1},
                        )
                        enrollment_map[student_id] = {
                            "enrollment_number": student.get("enrollment_number") if student else None,
                            "student_series": None,
                        }

    all_student_ids = list(
        active_student_ids
        .union(direct_student_ids)
        .union(inactive_student_ids)
        .union(program_student_ids)
    )

    action_info_map: Dict[str, Dict[str, Any]] = {}
    if inactive_student_ids:
        history_entries = await db.student_history.find(
            {
                "student_id": {"$in": list(inactive_student_ids)},
                "class_id": class_id,
                "action_type": {"$in": list(ACTION_TYPE_LABELS.keys())},
            },
            {
                "_id": 0,
                "student_id": 1,
                "action_type": 1,
                "action_date": 1,
            },
        ).sort("action_date", -1).to_list(1000)

        for entry in history_entries:
            student_id = entry.get("student_id")
            if student_id and student_id not in action_info_map:
                action_info_map[student_id] = {
                    "action_label": ACTION_TYPE_LABELS.get(entry.get("action_type"), ""),
                    "action_date": entry.get("action_date", ""),
                }

    if not all_student_ids:
        return []

    student_docs = await db.students.find(
        {"id": {"$in": all_student_ids}},
        {
            "_id": 0,
            "id": 1,
            "full_name": 1,
            "birth_date": 1,
            "guardian_name": 1,
            "guardian_phone": 1,
            "guardian_relationship": 1,
            "mother_name": 1,
            "mother_phone": 1,
            "father_name": 1,
            "father_phone": 1,
            "enrollment_number": 1,
        },
    ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

    result = []
    for student in student_docs:
        student_id = student.get("id")
        guardian_name = (
            student.get("guardian_name")
            or student.get("mother_name")
            or student.get("father_name")
            or "-"
        )
        guardian_phone = (
            student.get("guardian_phone")
            or student.get("mother_phone")
            or student.get("father_phone")
            or ""
        )
        enrollment_info = enrollment_map.get(student_id, {})
        enrollment_number = enrollment_info.get("enrollment_number") or student.get("enrollment_number")
        action_info = action_info_map.get(student_id, {})

        result.append(
            {
                "id": student_id,
                "full_name": student.get("full_name"),
                "enrollment_number": enrollment_number,
                "student_series": enrollment_info.get("student_series") or class_doc.get("grade_level"),
                "birth_date": student.get("birth_date"),
                "guardian_name": guardian_name,
                "guardian_phone": guardian_phone,
                "action_label": action_info.get("action_label", ""),
                "action_date": action_info.get("action_date", ""),
            }
        )

    return result
