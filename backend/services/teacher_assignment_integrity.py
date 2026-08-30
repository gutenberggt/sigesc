"""Integridade curricular para gravação de alocações docentes.

P0-F7.9B — fronteira fail-closed de escrita curricular.
P0-F7.9D7.8 — hardening preventivo de carga horária semanal.

Este módulo NÃO duplica regras curriculares: reutiliza a normalização e o
classificador canônico de ``utils.curriculum_resolver`` e a SSoT de carga
horária ``utils.curricular_workload_policy``. Aqui existe apenas a política de
escrita de ``teacher_assignments``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from utils.curriculum_resolver import _curricular_fit, _norm_scalar, _series_tokens
from utils.curricular_workload_policy import (
    CurricularWorkloadPolicyError,
    resolve_curricular_workload,
)


ACTIVE_ASSIGNMENT_STATUSES = frozenset({"ativo", "active"})


@dataclass(frozen=True)
class TeacherAssignmentIntegrityError(ValueError):
    code: str
    message: str
    fit: Mapping[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


def is_active_teacher_assignment_status(value: Any) -> bool:
    """Reconhece os dois tokens históricos de vínculo ativo."""
    return str(value or "").strip().lower() in ACTIVE_ASSIGNMENT_STATUSES


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


def _class_series_source(class_info: Mapping[str, Any]) -> Any:
    """Preserva a representação da turma para a SSoT de carga horária."""
    series = class_info.get("series")
    if series:
        return series
    return class_info.get("grade_level")


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


def validate_teacher_assignment_workload(
    *,
    class_info: Mapping[str, Any],
    course: Mapping[str, Any],
    weekly_workload: Any,
) -> dict[str, Any]:
    """Valida carga semanal de vínculo ativo contra a SSoT institucional.

    A política canônica atualmente cobre Geografia, História e Ciências. Para
    componentes fora dessa matriz específica, o comportamento legado é
    preservado (``applies=False``). Para componentes cobertos, a carga semanal
    é obrigatória e precisa coincidir exatamente com o valor resolvido pela
    SSoT, inclusive em turmas multisseriadas.
    """
    try:
        workload = resolve_curricular_workload(
            component_name=course.get("name"),
            class_level=_explicit_class_level(class_info),
            class_series=_class_series_source(class_info),
        )
    except CurricularWorkloadPolicyError as exc:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_WORKLOAD_POLICY_UNRESOLVED",
            "A carga horária canônica do componente não pôde ser resolvida para esta turma.",
            {
                "workload_policy_error": exc.code,
                "workload_policy_message": exc.message,
            },
        ) from exc

    if workload.get("applies") is not True:
        return {
            "allowed": True,
            "workload_policy": "NOT_APPLICABLE",
            "workload": workload,
        }

    if weekly_workload is None or str(weekly_workload).strip() == "":
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_WEEKLY_WORKLOAD_REQUIRED",
            "A carga horária semanal é obrigatória para este componente curricular.",
            {"workload": workload},
        )

    try:
        actual = float(weekly_workload)
        expected = float(workload["canonical_weekly_workload"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_WEEKLY_WORKLOAD_INVALID",
            "A carga horária semanal informada é inválida.",
            {"workload": workload},
        ) from exc

    if actual != expected:
        raise TeacherAssignmentIntegrityError(
            "TEACHER_ASSIGNMENT_WEEKLY_WORKLOAD_MISMATCH",
            (
                "A carga horária semanal informada diverge da matriz curricular canônica "
                f"({actual:g}h informada; {expected:g}h esperada)."
            ),
            {
                "workload": workload,
                "actual_weekly_workload": actual,
                "expected_weekly_workload": expected,
            },
        )

    return {
        "allowed": True,
        "workload_policy": "CANONICAL_WEEKLY_WORKLOAD_MATCH",
        "canonical_weekly_workload": workload["canonical_weekly_workload"],
        "workload": workload,
    }
