"""Construção read-only do contexto canônico para o Policy Resolver."""

from __future__ import annotations

from datetime import date
from typing import Optional

from .exceptions import AssessmentPolicyError, POLICY_CONTEXT_MISMATCH
from .resolver import AssessmentPolicyContext
from .series_resolver import normalize_series, resolve_effective_student_series


async def build_assessment_policy_context(
    db,
    *,
    mantenedora_id: str,
    school_id: str,
    class_id: str,
    student_id: str,
    academic_year: int,
    reference_date: date,
    component_id: Optional[str] = None,
    current_year: Optional[int] = None,
) -> AssessmentPolicyContext:
    """Monta contexto com evidência acadêmica sem escrever no banco.

    O contexto só transporta um `component_id` depois de comprovar que o
    componente pertence ao tenant e é compatível com as restrições explícitas
    de escola, nível e série do cadastro de Componentes Curriculares.
    """

    class_info = await db.classes.find_one(
        {"id": class_id, "mantenedora_id": mantenedora_id},
        {
            "_id": 0,
            "id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "academic_year": 1,
            "grade_level": 1,
            "education_level": 1,
            "nivel_ensino": 1,
            "modality": 1,
            "modalidade": 1,
            "is_multi_grade": 1,
            "series": 1,
        },
    )
    if not class_info:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "Turma não pertence à mantenedora informada ou não existe.",
            details={"mantenedora_id": mantenedora_id, "class_id": class_id},
        )

    class_school_id = str(class_info.get("school_id") or "")
    if not class_school_id or class_school_id != str(school_id):
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "Escola informada não corresponde à turma no tenant ativo.",
            details={
                "school_id": school_id,
                "class_school_id": class_school_id or None,
                "class_id": class_id,
            },
        )

    class_year = class_info.get("academic_year")
    if class_year not in (None, ""):
        try:
            if int(class_year) != int(academic_year):
                raise AssessmentPolicyError(
                    POLICY_CONTEXT_MISMATCH,
                    "Ano letivo informado não corresponde ao ano da turma.",
                    details={
                        "academic_year": int(academic_year),
                        "class_academic_year": class_year,
                        "class_id": class_id,
                    },
                )
        except (TypeError, ValueError):
            raise AssessmentPolicyError(
                POLICY_CONTEXT_MISMATCH,
                "Ano letivo da turma é inválido para resolução da política.",
                details={"class_academic_year": class_year, "class_id": class_id},
            )

    enrollment_rows = await db.enrollments.find(
        {
            "student_id": student_id,
            "class_id": class_id,
            "academic_year": {"$in": [int(academic_year), str(int(academic_year))]},
        },
        {
            "_id": 0,
            "id": 1,
            "student_id": 1,
            "class_id": 1,
            "student_series": 1,
            "academic_year": 1,
            "status": 1,
        },
    ).to_list(100)

    student = await db.students.find_one(
        {"id": student_id},
        {
            "_id": 0,
            "id": 1,
            "class_id": 1,
            "school_id": 1,
            "mantenedora_id": 1,
            "student_series": 1,
            "status": 1,
        },
    )

    resolved_current_year = int(current_year if current_year is not None else date.today().year)

    # Matrícula anual é evidência histórica. Sem ela, o vínculo direto do aluno
    # só pode provar contexto no ano corrente e na mesma turma/escola.
    has_enrollment_membership = bool(enrollment_rows)
    has_current_direct_membership = bool(
        int(academic_year) == resolved_current_year
        and student
        and str(student.get("class_id") or "") == str(class_id)
        and str(student.get("school_id") or school_id) == str(school_id)
    )

    if not has_enrollment_membership and not has_current_direct_membership:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "Não há evidência de que o estudante pertença à turma no ano letivo informado.",
            details={
                "student_id": student_id,
                "class_id": class_id,
                "academic_year": int(academic_year),
            },
        )

    if student and student.get("mantenedora_id") not in (None, "", mantenedora_id):
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "Estudante pertence a outra mantenedora.",
            details={
                "student_id": student_id,
                "student_mantenedora_id": student.get("mantenedora_id"),
                "mantenedora_id": mantenedora_id,
            },
        )

    effective_series = resolve_effective_student_series(
        enrollment_rows=enrollment_rows,
        student=student,
        class_info=class_info,
        academic_year=int(academic_year),
        current_year=resolved_current_year,
    )

    education_stage = class_info.get("education_level") or class_info.get("nivel_ensino")
    modality = class_info.get("modality") or class_info.get("modalidade")

    if component_id is not None:
        component = await db.courses.find_one(
            {"id": str(component_id), "mantenedora_id": mantenedora_id},
            {
                "_id": 0,
                "id": 1,
                "mantenedora_id": 1,
                "school_id": 1,
                "nivel_ensino": 1,
                "grade_levels": 1,
                "name": 1,
            },
        )
        if not component:
            raise AssessmentPolicyError(
                POLICY_CONTEXT_MISMATCH,
                "Componente curricular não pertence à mantenedora informada ou não existe.",
                details={
                    "component_id": component_id,
                    "mantenedora_id": mantenedora_id,
                },
            )

        component_school = str(component.get("school_id") or "")
        if component_school and component_school != str(school_id):
            raise AssessmentPolicyError(
                POLICY_CONTEXT_MISMATCH,
                "Componente curricular está restrito a outra escola.",
                details={
                    "component_id": component_id,
                    "component_school_id": component_school,
                    "school_id": school_id,
                },
            )

        component_stage = str(component.get("nivel_ensino") or "").strip()
        if component_stage and normalize_series(component_stage) != normalize_series("global"):
            if not education_stage or normalize_series(component_stage) != normalize_series(education_stage):
                raise AssessmentPolicyError(
                    POLICY_CONTEXT_MISMATCH,
                    "Componente curricular não é compatível com o nível de ensino da turma.",
                    details={
                        "component_id": component_id,
                        "component_nivel_ensino": component_stage,
                        "class_education_stage": education_stage,
                    },
                )

        component_grade_levels = component.get("grade_levels") or []
        if component_grade_levels and not any(
            normalize_series(item) == normalize_series(effective_series.value)
            for item in component_grade_levels
        ):
            raise AssessmentPolicyError(
                POLICY_CONTEXT_MISMATCH,
                "Componente curricular não é aplicável à série efetiva do estudante.",
                details={
                    "component_id": component_id,
                    "student_series": effective_series.value,
                    "component_grade_levels": component_grade_levels,
                },
            )

    return AssessmentPolicyContext(
        mantenedora_id=str(mantenedora_id),
        school_id=str(school_id),
        class_id=str(class_id),
        student_id=str(student_id),
        component_id=(str(component_id) if component_id is not None else None),
        academic_year=int(academic_year),
        reference_date=reference_date,
        student_series=effective_series.value,
        education_stage=(str(education_stage) if education_stage else None),
        modality=(str(modality) if modality else None),
    )
