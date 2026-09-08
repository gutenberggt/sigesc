"""Paridade histórica de Notas/Conceitos no Diário por Vínculo.

A Fase 5 protege corretamente autoria por campo em ``grade_ownership``. Nos
cutovers históricos, porém, notas anteriores ao DVD permaneceram fisicamente em
``grades`` sem esse mapa de autoria.

Esta camada mantém a VISIBILIDADE histórica segura e compõe a ponte P0 de
ESCRITA histórica em módulo separado. A prova de continuidade não é duplicada:
ela usa a SSoT geral de cutover do DVD por meio de
``services.grade_cutover_history``.

Leitura:
- revalida a origem legada indicada por ``cutover_provenance``;
- torna campos legados sem ownership visíveis somente na leitura do vínculo;
- marca esses campos em ``dvd_read_only_fields``;
- mantém campos pertencentes a outro assignment mascarados;
- faz o PDF usar exatamente a mesma projeção segura;
- não cria ``grade_ownership`` retroativo.

Escrita pré-cutover:
- é instalada por ``grades_historical_backfill_dvd``;
- continua usando ``grades_dvd`` + ``grade_assignment_scope`` como motor de
  persistência/autoria;
- só atravessa ``valid_from`` técnico com prova de cutover revalidada.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from pdf_cache import get_mantenedora_cached
from services.grade_assignment_scope import (
    GRADE_OWNERSHIP_FIELDS,
    GRADE_VALUE_FIELDS,
    GradeAssignmentContext,
    owned_fields_for_assignment,
)
from services.grade_cutover_history import (
    LEGACY_HISTORY_FLAG,
    LEGACY_SOURCE_FLAG,
    LEGACY_YEAR_FLAG,
    safe_cutover_legacy_assignment as _safe_cutover_legacy_assignment,
)


async def _decorate_context_with_legacy_history(
    db,
    context: Optional[GradeAssignmentContext],
    academic_year: int,
) -> Optional[GradeAssignmentContext]:
    """Marca leitura usando a função local patchável pela generalização DVD."""
    if context is None:
        return None

    legacy = await _safe_cutover_legacy_assignment(db, context, academic_year)
    if not legacy:
        return context

    snapshot = dict(context.snapshot)
    snapshot[LEGACY_HISTORY_FLAG] = True
    snapshot[LEGACY_SOURCE_FLAG] = legacy.get("id")
    snapshot[LEGACY_YEAR_FLAG] = int(academic_year)
    return replace(context, snapshot=snapshot)


def _project_grade_for_assignment(
    grade: Mapping[str, Any],
    context: GradeAssignmentContext,
) -> dict[str, Any]:
    """Projeta OWNED + LEGADO validado sem converter legado em autoria.

    Regra por campo:
    - owner == assignment atual: visível/editável conforme motor normal;
    - sem chave em grade_ownership + cutover validado: visível/read-only;
    - owner de outro assignment ou snapshot inválido: mascarado.
    """
    out = dict(grade)
    ownership = grade.get("grade_ownership") or {}
    owned = set(owned_fields_for_assignment(grade, context.assignment_id))
    legacy_allowed = bool(context.snapshot.get(LEGACY_HISTORY_FLAG))

    legacy_fields = {
        field
        for field in GRADE_OWNERSHIP_FIELDS
        if legacy_allowed
        and grade.get(field) is not None
        and field not in ownership
    }
    visible_fields = owned | legacy_fields

    foreign_fields = {
        field
        for field in GRADE_OWNERSHIP_FIELDS
        if grade.get(field) is not None and field not in visible_fields
    }

    for field in GRADE_OWNERSHIP_FIELDS:
        if field not in visible_fields:
            out[field] = None

    # Nunca expõe snapshots pertencentes a outro vínculo.
    out["grade_ownership"] = {
        field: dict(snapshot)
        for field, snapshot in ownership.items()
        if field in owned and isinstance(snapshot, Mapping)
    }

    foreign_value = any(field in foreign_fields for field in GRADE_VALUE_FIELDS)
    if foreign_value:
        out["final_average"] = None
        out["status"] = "cursando"

    locked = {
        field
        for field in GRADE_OWNERSHIP_FIELDS
        if grade.get(field) is not None and field not in owned
    }

    out["dvd_assignment_id"] = context.assignment_id
    out["dvd_owned_fields"] = sorted(owned)
    out["dvd_locked_fields"] = sorted(locked)
    out["dvd_read_only_fields"] = sorted(legacy_fields)
    out["legacy_history"] = bool(legacy_fields)
    if legacy_fields and owned:
        out["history_source"] = "grades_mixed"
    elif legacy_fields:
        out["history_source"] = "grades_legacy"
    else:
        out["history_source"] = "grades_dvd"
    return out


async def _dvd_pdf_with_history(
    current_db,
    context: GradeAssignmentContext,
    *,
    class_id: str,
    course_id: str,
    bimestres: str,
    academic_year: int,
    student_series: Optional[str],
):
    """Mesmo layout da Fase 5, usando a projeção histórica segura por campo."""
    from pdf_generator import generate_grades_report_pdf

    tenant_id = context.snapshot.get("mantenedora_id")
    class_info = await current_db.classes.find_one(
        {"id": class_id, "mantenedora_id": tenant_id},
        {"_id": 0},
    )
    course = await current_db.courses.find_one(
        {"id": course_id, "mantenedora_id": tenant_id},
        {"_id": 0},
    )
    if not class_info:
        raise HTTPException(status_code=404, detail="Turma do vínculo não encontrada")
    if not course:
        raise HTTPException(status_code=404, detail="Componente do vínculo não encontrado")

    school = await current_db.schools.find_one(
        {
            "id": context.snapshot.get("school_id"),
            "mantenedora_id": tenant_id,
        },
        {"_id": 0},
    ) or {"name": ""}
    mantenedora = await current_db.mantenedoras.find_one(
        {"id": tenant_id},
        {"_id": 0},
    ) or await get_mantenedora_cached(current_db) or {}

    enrollments = await current_db.enrollments.find(
        {"class_id": class_id, "status": "active"},
        {"_id": 0, "student_id": 1, "enrollment_number": 1, "student_series": 1},
    ).to_list(1000)
    direct_students = await current_db.students.find(
        {"class_id": class_id, "status": {"$in": ["active", "Ativo"]}},
        {"_id": 0, "id": 1, "enrollment_number": 1, "student_series": 1},
    ).to_list(1000)

    enrollment_map = {
        item.get("student_id"): {
            "enrollment_number": item.get("enrollment_number"),
            "student_series": item.get("student_series", ""),
        }
        for item in enrollments
        if item.get("student_id")
    }
    for student in direct_students:
        sid = student.get("id")
        if sid and sid not in enrollment_map:
            enrollment_map[sid] = {
                "enrollment_number": student.get("enrollment_number"),
                "student_series": student.get("student_series", ""),
            }

    student_ids = list(enrollment_map)
    students = []
    if student_ids:
        students = await current_db.students.find(
            {"id": {"$in": student_ids}},
            {
                "_id": 0,
                "id": 1,
                "full_name": 1,
                "enrollment_number": 1,
                "student_series": 1,
            },
        ).sort("full_name", 1).collation({"locale": "pt", "strength": 1}).to_list(1000)

    if student_series:
        from utils.serie_canonical import canonicalize_serie

        def _series_match(a, b):
            ca = canonicalize_serie(a or "")
            cb = canonicalize_serie(b or "")
            if ca and cb:
                return ca == cb
            return (a or "").strip().lower() == (b or "").strip().lower()

        students = [
            student
            for student in students
            if _series_match(
                enrollment_map.get(student["id"], {}).get("student_series")
                or student.get("student_series"),
                student_series,
            )
        ]

    grades = await current_db.grades.find(
        {
            "class_id": class_id,
            "course_id": course_id,
            "academic_year": academic_year,
        },
        {"_id": 0},
    ).to_list(1000)
    grades_map = {grade.get("student_id"): grade for grade in grades}

    students_data = []
    for student in students:
        grade = grades_map.get(student["id"], {})
        projected = _project_grade_for_assignment(grade, context)
        students_data.append(
            {
                "full_name": student.get("full_name", ""),
                "enrollment_number": (
                    enrollment_map.get(student["id"], {}).get("enrollment_number")
                    or student.get("enrollment_number", "")
                ),
                **{
                    field: projected.get(field)
                    for field in GRADE_VALUE_FIELDS
                },
                "final_average": projected.get("final_average"),
                "status": projected.get("status", "cursando"),
            }
        )

    bims = [
        int(value.strip())
        for value in bimestres.split(",")
        if value.strip().isdigit()
    ]
    buffer = generate_grades_report_pdf(
        school=school,
        class_info=class_info,
        course=course,
        students_data=students_data,
        bimestres=bims,
        academic_year=academic_year,
        grade_level=student_series or class_info.get("grade_level", ""),
        mantenedora=mantenedora,
        teacher_names=[context.snapshot.get("teacher_name") or ""],
    )

    class_name = (class_info.get("name") or "turma").replace(" ", "_")
    course_name = (course.get("name") or "comp").replace(" ", "_")
    filename = f"notas_{class_name}_{course_name}_{academic_year}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def install_grades_dvd_parity(base_router, db, *, sandbox_db=None):
    """Instala ponte histórica de escrita + paridade de leitura após a Fase 5."""
    if getattr(base_router, "_dvd_grades_history_parity_installed", False):
        return base_router

    from routers import grades_dvd as dvd_mod
    from routers.grades_historical_backfill_dvd import (
        install_grades_historical_backfill_dvd,
    )

    # O backfill de escrita é composto aqui porque este instalador já é executado
    # depois do adapter + hardening da Fase 5. Nenhuma nova rota é criada.
    install_grades_historical_backfill_dvd()

    if not hasattr(dvd_mod, "_history_parity_original_context_or_legacy"):
        dvd_mod._history_parity_original_context_or_legacy = dvd_mod._context_or_legacy
        original_context = dvd_mod._context_or_legacy

        async def context_with_legacy_history(
            current_db,
            user,
            request,
            *,
            class_id: str,
            course_id: str,
            academic_year: int,
            assignment_id: Optional[str] = None,
        ):
            context = await original_context(
                current_db,
                user,
                request,
                class_id=class_id,
                course_id=course_id,
                academic_year=academic_year,
                assignment_id=assignment_id,
            )
            return await _decorate_context_with_legacy_history(
                current_db,
                context,
                academic_year,
            )

        dvd_mod._context_or_legacy = context_with_legacy_history

    if not hasattr(dvd_mod, "_history_parity_original_mask_grade_for_assignment"):
        dvd_mod._history_parity_original_mask_grade_for_assignment = dvd_mod._mask_grade_for_assignment
        original_mask = dvd_mod._mask_grade_for_assignment

        def mask_grade_with_legacy_history(
            grade: Mapping[str, Any],
            context: GradeAssignmentContext,
            *,
            mask_foreign: bool,
        ) -> dict[str, Any]:
            if not mask_foreign or not context.snapshot.get(LEGACY_HISTORY_FLAG):
                return original_mask(grade, context, mask_foreign=mask_foreign)
            return _project_grade_for_assignment(grade, context)

        dvd_mod._mask_grade_for_assignment = mask_grade_with_legacy_history

    if not hasattr(dvd_mod, "_history_parity_original_dvd_pdf"):
        dvd_mod._history_parity_original_dvd_pdf = dvd_mod._dvd_pdf
        original_pdf = dvd_mod._dvd_pdf

        async def dvd_pdf_with_legacy_history(
            current_db,
            context: GradeAssignmentContext,
            *,
            class_id: str,
            course_id: str,
            bimestres: str,
            academic_year: int,
            student_series: Optional[str],
        ):
            if not context.snapshot.get(LEGACY_HISTORY_FLAG):
                return await original_pdf(
                    current_db,
                    context,
                    class_id=class_id,
                    course_id=course_id,
                    bimestres=bimestres,
                    academic_year=academic_year,
                    student_series=student_series,
                )
            return await _dvd_pdf_with_history(
                current_db,
                context,
                class_id=class_id,
                course_id=course_id,
                bimestres=bimestres,
                academic_year=academic_year,
                student_series=student_series,
            )

        dvd_mod._dvd_pdf = dvd_pdf_with_legacy_history

    base_router._dvd_grades_history_parity_installed = True
    return base_router
