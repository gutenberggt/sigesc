"""Integridade curricular para gravação de alocações docentes.

P0-F7.9B — fronteira fail-closed de escrita.

Este módulo NÃO duplica a regra de compatibilidade curricular: reutiliza a
normalização e o classificador canônico de ``utils.curriculum_resolver`` e
aplica apenas a política de escrita de ``teacher_assignments``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from utils.curriculum_resolver import _curricular_fit, _norm_scalar, _series_tokens


@dataclass(frozen=True)
class TeacherAssignmentIntegrityError(ValueError):
    code: str
    message: str
    fit: Mapping[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


def _explicit_class_level(class_info: Mapping[str, Any]) -> str:
    """Exige nível explicitamente persistido na turma; não infere em escrita."""
    return str(
        class_info.get("nivel_ensino")
        or class_info.get("education_level")
        or ""
    ).strip()


def _class_series(class_info: Mapping[str, Any]) -> set[str]:
    series = _series_tokens(class_info.get("series"))
    if not series:
        series = _series_tokens(class_info.get("grade_level"))
    return series


def validate_teacher_assignment_curriculum(
    *,
    class_info: Mapping[str, Any],
    course: Mapping[str, Any],
    school_id: str,
    academic_year: int,
) -> dict[str, Any]:
    """Valida a compatibilidade turma × componente antes de persistir vínculo.

    Política de escrita:
    - turma sem nível explícito: rejeita;
    - componente sem nível: rejeita;
    - nível divergente: rejeita;
    - curso sem escopo de série: aceita quando o nível coincide;
    - curso com escopo explícito/matriz: exige séries conhecidas da turma e
      compatibilidade curricular forte (rank 3);
    - contexto escola/ano divergente da turma: rejeita.

    A função é pura e não acessa banco, rede ou FastAPI.
    """
    class_school_id = str(class_info.get("school_id") or "").strip()
    if not class_school_id or class_school_id != str(school_id or "").strip():
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_CLASS_SCHOOL_MISMATCH",
            "A turma não pertence à escola informada para a alocação.",
        )

    class_year = class_info.get("academic_year")
    try:
        class_year_int = int(class_year)
        assignment_year_int = int(academic_year)
    except (TypeError, ValueError) as exc:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_ACADEMIC_YEAR_INVALID",
            "Ano letivo da turma ou da alocação é inválido.",
        ) from exc

    if class_year_int != assignment_year_int:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_CLASS_YEAR_MISMATCH",
            "O ano letivo da turma diverge do ano informado para a alocação.",
        )

    class_level = _explicit_class_level(class_info)
    if not class_level:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_CLASS_LEVEL_REQUIRED",
            "A turma não possui nível de ensino explícito. Corrija o cadastro antes da alocação.",
        )

    course_level = str(course.get("nivel_ensino") or "").strip()
    if not course_level:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_COURSE_LEVEL_REQUIRED",
            "O componente curricular não possui nível de ensino explícito.",
        )

    if _norm_scalar(class_level) != _norm_scalar(course_level):
        fit = _curricular_fit(
            dict(course),
            class_level=class_level,
            class_series=_class_series(class_info),
        )
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_LEVEL_MISMATCH",
            "O componente curricular é incompatível com o nível de ensino da turma.",
            fit,
        )

    class_series = _class_series(class_info)
    explicit_series = _series_tokens(course.get("grade_levels"))
    matrix_series = _series_tokens(course.get("carga_horaria_por_serie"))

    fit = _curricular_fit(
        dict(course),
        class_level=class_level,
        class_series=class_series,
    )

    # Curso de nível correto sem granularidade por série aplica-se ao nível todo.
    if not explicit_series and not matrix_series:
        return {
            "allowed": True,
            "write_policy": "LEVEL_MATCH_NO_SERIES_SCOPE",
            "fit": fit,
        }

    # Havendo escopo por série, a turma precisa ter série/etapa conhecida.
    if not class_series:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_CLASS_SERIES_REQUIRED",
            "A turma não possui série/etapa suficiente para validar este componente.",
            fit,
        )

    if int(fit.get("rank") or 0) != 3:
        classification = str(fit.get("classification") or "")
        if classification == "NO_SERIES_MATCH":
            code = "TEACHER_ASSIGNMENT_SERIES_MISMATCH"
            message = "O componente curricular não se aplica às séries/etapas da turma."
        else:
            code = "TEACHER_ASSIGNMENT_SERIES_SCOPE_REVIEW_REQUIRED"
            message = (
                "O escopo de séries do componente é parcial ou conflitante para esta turma; "
                "a alocação automática foi bloqueada para revisão curricular."
            )
        raise TeacherAssignmentIntegrityError(code, message, fit)

    return {
        "allowed": True,
        "write_policy": str(fit.get("classification") or "CURRICULAR_MATCH"),
        "fit": fit,
    }
