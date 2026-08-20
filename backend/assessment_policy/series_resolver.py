"""Resolução determinística da série efetiva do estudante.

Esta camada é pura: recebe registros já carregados e não acessa Mongo/HTTP.
A consulta ao banco fica no futuro context builder da Sprint 002.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence
import re
import unicodedata

from .exceptions import (
    AssessmentPolicyError,
    STUDENT_SERIES_AMBIGUOUS,
    STUDENT_SERIES_REQUIRED,
)


@dataclass(frozen=True)
class EffectiveStudentSeries:
    value: str
    source: str
    evidence_id: Optional[str] = None


def normalize_series(value: Any) -> str:
    """Normalização somente para comparação, nunca para persistência/exibição."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("º", " ").replace("°", " ").replace("ª", " ")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^0-9a-zA-Z]+", "", text).casefold()


def _clean_series(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_multi_grade_class(class_info: Mapping[str, Any]) -> bool:
    if class_info.get("is_multi_grade") is True:
        return True

    raw_series = class_info.get("series") or []
    normalized = {
        normalize_series(item)
        for item in raw_series
        if normalize_series(item)
    }
    return len(normalized) > 1


def resolve_effective_student_series(
    *,
    enrollment_rows: Sequence[Mapping[str, Any]],
    student: Optional[Mapping[str, Any]],
    class_info: Mapping[str, Any],
    academic_year: int,
    current_year: int,
) -> EffectiveStudentSeries:
    """Resolve a série usando evidência anual e fallback seguro.

    Precedência:
    1. matrícula do ano/turma (`enrollments.student_series`);
    2. estudante corrente, somente no ano corrente e se ainda pertence à turma;
    3. `class.grade_level`, somente para turma NÃO multisseriada.

    Em multisseriada sem evidência individual, falha fechado.
    """

    enrollment_candidates: dict[str, tuple[str, Optional[str]]] = {}
    for row in enrollment_rows:
        raw = _clean_series(row.get("student_series"))
        if not raw:
            continue
        normalized = normalize_series(raw)
        if normalized:
            enrollment_candidates.setdefault(
                normalized,
                (raw, str(row.get("id")) if row.get("id") else None),
            )

    if len(enrollment_candidates) > 1:
        raise AssessmentPolicyError(
            STUDENT_SERIES_AMBIGUOUS,
            "Há mais de uma série individual registrada para o estudante na mesma turma/ano.",
            details={
                "series": sorted(value for value, _ in enrollment_candidates.values()),
            },
        )

    if len(enrollment_candidates) == 1:
        raw, evidence_id = next(iter(enrollment_candidates.values()))
        return EffectiveStudentSeries(
            value=raw,
            source="enrollment.student_series",
            evidence_id=evidence_id,
        )

    if int(academic_year) == int(current_year) and student:
        class_id = str(class_info.get("id") or "")
        student_class_id = str(student.get("class_id") or "")
        raw = _clean_series(student.get("student_series"))
        if raw and class_id and student_class_id == class_id:
            return EffectiveStudentSeries(
                value=raw,
                source="student.student_series",
                evidence_id=str(student.get("id")) if student.get("id") else None,
            )

    if is_multi_grade_class(class_info):
        raise AssessmentPolicyError(
            STUDENT_SERIES_REQUIRED,
            "Turma multisseriada exige série individual comprovada para resolver a política avaliativa.",
            details={
                "class_id": class_info.get("id"),
                "class_grade_level": class_info.get("grade_level"),
                "class_series": class_info.get("series"),
            },
        )

    fallback = _clean_series(class_info.get("grade_level"))
    if fallback:
        return EffectiveStudentSeries(
            value=fallback,
            source="class.grade_level",
            evidence_id=str(class_info.get("id")) if class_info.get("id") else None,
        )

    raise AssessmentPolicyError(
        STUDENT_SERIES_REQUIRED,
        "Não foi possível resolver uma série confiável para o estudante.",
        details={"class_id": class_info.get("id")},
    )
