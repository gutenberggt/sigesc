"""Shadow/Dry-run puro para comparar legado persistido com o motor v1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
from numbers import Real
from typing import Any, Mapping, Optional, Sequence

from .calculator import calculate_assessment
from .exceptions import (
    AssessmentPolicyError,
    SHADOW_LEGACY_VALUE_INVALID,
    SHADOW_MAPPING_INVALID,
    SHADOW_TOLERANCE_INVALID,
)
from .models import AssessmentPolicy


class ShadowClassification(str, Enum):
    MATCH = "match"
    DIFFERENT = "different"
    BOTH_INCOMPLETE = "both_incomplete"
    NEW_INCOMPLETE = "new_incomplete"
    LEGACY_MISSING = "legacy_missing"
    ERROR = "error"


@dataclass(frozen=True)
class LegacyGradeFieldMapping:
    """Mapeamento explícito do schema legado para códigos da política."""

    period_field_map: Mapping[str, str]
    recovery_field_map: Mapping[str, str]


@dataclass(frozen=True)
class LegacyGradeSnapshot:
    grade_id: str
    student_id: str
    class_id: str
    course_id: str
    academic_year: int
    fields: Mapping[str, Any]
    legacy_final_average: Optional[Any]
    legacy_status: Optional[str] = None


@dataclass(frozen=True)
class ShadowComparison:
    grade_id: str
    student_id: str
    class_id: str
    course_id: str
    academic_year: int
    classification: ShadowClassification
    legacy_final_average: Optional[float]
    new_current_average: Optional[float]
    new_final_average: Optional[float]
    new_is_final: Optional[bool]
    delta: Optional[float]
    absolute_delta: Optional[float]
    legacy_status: Optional[str]
    policy_id: str
    policy_version: int
    rule_hash: str
    mapping_hash: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[Any] = None


@dataclass(frozen=True)
class ShadowBatchReport:
    total: int
    matches: int
    differences: int
    both_incomplete: int
    new_incomplete: int
    legacy_missing: int
    errors: int
    comparable: int
    match_rate: Optional[float]
    max_absolute_delta: Optional[float]
    policy_ids: tuple[str, ...]
    rule_hashes: tuple[str, ...]
    mapping_hash: str
    comparisons: tuple[ShadowComparison, ...]


def _clean_mapping(mapping: Mapping[str, str], *, field_name: str) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for raw_source, raw_target in mapping.items():
        source = str(raw_source or "").strip()
        target = str(raw_target or "").strip()
        if not source or not target:
            raise AssessmentPolicyError(
                SHADOW_MAPPING_INVALID,
                "Mapeamento shadow não pode conter campo/código vazio.",
                details={"field": field_name, "source": raw_source, "target": raw_target},
            )
        cleaned[source] = target

    targets = list(cleaned.values())
    if len(targets) != len(set(targets)):
        raise AssessmentPolicyError(
            SHADOW_MAPPING_INVALID,
            "Dois campos legados não podem apontar para o mesmo código da política.",
            details={"field": field_name, "targets": targets},
        )
    return cleaned


def validate_shadow_mapping(
    policy: AssessmentPolicy,
    mapping: LegacyGradeFieldMapping,
) -> LegacyGradeFieldMapping:
    period_map = _clean_mapping(mapping.period_field_map, field_name="period_field_map")
    recovery_map = _clean_mapping(
        mapping.recovery_field_map,
        field_name="recovery_field_map",
    )

    reused_sources = sorted(set(period_map) & set(recovery_map))
    if reused_sources:
        raise AssessmentPolicyError(
            SHADOW_MAPPING_INVALID,
            "Um campo legado não pode alimentar simultaneamente período e recuperação.",
            details={"source_fields": reused_sources},
        )

    policy_periods = {period.code for period in policy.assessment.periods}
    mapped_periods = set(period_map.values())
    unknown_periods = sorted(mapped_periods - policy_periods)
    if unknown_periods:
        raise AssessmentPolicyError(
            SHADOW_MAPPING_INVALID,
            "Mapeamento referencia período inexistente na política.",
            details={"period_codes": unknown_periods},
        )

    required_periods = {
        period.code
        for period in policy.assessment.periods
        if period.required_for_final
    }
    missing_required_periods = sorted(required_periods - mapped_periods)
    if missing_required_periods:
        raise AssessmentPolicyError(
            SHADOW_MAPPING_INVALID,
            "Mapeamento não cobre todos os períodos obrigatórios da política.",
            details={"period_codes": missing_required_periods},
        )

    policy_recoveries = {group.input_code for group in policy.recovery.groups}
    mapped_recoveries = set(recovery_map.values())
    unknown_recoveries = sorted(mapped_recoveries - policy_recoveries)
    if unknown_recoveries:
        raise AssessmentPolicyError(
            SHADOW_MAPPING_INVALID,
            "Mapeamento referencia entrada de recuperação inexistente na política.",
            details={"input_codes": unknown_recoveries},
        )

    if policy.recovery.enabled:
        missing_recoveries = sorted(policy_recoveries - mapped_recoveries)
        if missing_recoveries:
            raise AssessmentPolicyError(
                SHADOW_MAPPING_INVALID,
                "Política com recuperação exige mapeamento explícito de todas as entradas de recuperação.",
                details={"input_codes": missing_recoveries},
            )
    elif recovery_map:
        raise AssessmentPolicyError(
            SHADOW_MAPPING_INVALID,
            "Política sem recuperação não deve receber recovery_field_map.",
            details={"source_fields": sorted(recovery_map)},
        )

    return LegacyGradeFieldMapping(
        period_field_map=period_map,
        recovery_field_map=recovery_map,
    )


def canonical_mapping_json(mapping: LegacyGradeFieldMapping) -> str:
    payload = {
        "period_field_map": dict(sorted(mapping.period_field_map.items())),
        "recovery_field_map": dict(sorted(mapping.recovery_field_map.items())),
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def calculate_mapping_hash(mapping: LegacyGradeFieldMapping) -> str:
    digest = hashlib.sha256(canonical_mapping_json(mapping).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def legacy_grade_snapshot_from_document(document: Mapping[str, Any]) -> LegacyGradeSnapshot:
    identity = {
        "grade_id": document.get("id"),
        "student_id": document.get("student_id"),
        "class_id": document.get("class_id"),
        "course_id": document.get("course_id"),
        "academic_year": document.get("academic_year"),
    }
    missing = [
        name
        for name, value in identity.items()
        if value is None or not str(value).strip()
    ]
    if missing:
        raise AssessmentPolicyError(
            SHADOW_LEGACY_VALUE_INVALID,
            "Snapshot legado não possui identidade acadêmica completa.",
            details={"missing_fields": missing},
        )

    try:
        academic_year = int(identity["academic_year"])
    except (TypeError, ValueError):
        raise AssessmentPolicyError(
            SHADOW_LEGACY_VALUE_INVALID,
            "academic_year legado é inválido.",
            details={"academic_year": identity["academic_year"]},
        )

    return LegacyGradeSnapshot(
        grade_id=str(identity["grade_id"]),
        student_id=str(identity["student_id"]),
        class_id=str(identity["class_id"]),
        course_id=str(identity["course_id"]),
        academic_year=academic_year,
        fields=dict(document),
        legacy_final_average=document.get("final_average"),
        legacy_status=(
            str(document.get("status"))
            if document.get("status") is not None
            else None
        ),
    )


def _legacy_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (Decimal, Real)):
        raise AssessmentPolicyError(
            SHADOW_LEGACY_VALUE_INVALID,
            "final_average legado deve ser numérico ou nulo.",
            details={"value": value},
        )
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise AssessmentPolicyError(
            SHADOW_LEGACY_VALUE_INVALID,
            "final_average legado deve ser finito.",
            details={"value": str(value)},
        )
    return result


def _tolerance_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise AssessmentPolicyError(
            SHADOW_TOLERANCE_INVALID,
            "Tolerância shadow deve ser decimal não negativo.",
        )
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        raise AssessmentPolicyError(
            SHADOW_TOLERANCE_INVALID,
            "Tolerância shadow deve ser decimal não negativo.",
            details={"value": value},
        )
    if not result.is_finite() or result < 0:
        raise AssessmentPolicyError(
            SHADOW_TOLERANCE_INVALID,
            "Tolerância shadow deve ser decimal não negativo.",
            details={"value": str(value)},
        )
    return result


def _inputs_from_snapshot(
    snapshot: LegacyGradeSnapshot,
    mapping: LegacyGradeFieldMapping,
) -> tuple[dict[str, Any], dict[str, Any]]:
    periods = {
        target: snapshot.fields.get(source)
        for source, target in mapping.period_field_map.items()
    }
    recoveries = {
        target: snapshot.fields.get(source)
        for source, target in mapping.recovery_field_map.items()
    }
    return periods, recoveries


def compare_legacy_grade_snapshot(
    policy: AssessmentPolicy,
    snapshot: LegacyGradeSnapshot,
    mapping: LegacyGradeFieldMapping,
    *,
    tolerance: Any = "0.01",
    _mapping_already_validated: bool = False,
) -> ShadowComparison:
    validated_mapping = (
        mapping
        if _mapping_already_validated
        else validate_shadow_mapping(policy, mapping)
    )
    mapping_hash = calculate_mapping_hash(validated_mapping)
    tolerance_decimal = _tolerance_decimal(tolerance)

    base = {
        "grade_id": snapshot.grade_id,
        "student_id": snapshot.student_id,
        "class_id": snapshot.class_id,
        "course_id": snapshot.course_id,
        "academic_year": snapshot.academic_year,
        "legacy_status": snapshot.legacy_status,
        "policy_id": policy.id,
        "policy_version": policy.version,
        "rule_hash": policy.rule_hash or "",
        "mapping_hash": mapping_hash,
    }

    try:
        legacy = _legacy_decimal(snapshot.legacy_final_average)
        period_results, recovery_results = _inputs_from_snapshot(
            snapshot,
            validated_mapping,
        )
        calculated = calculate_assessment(
            policy,
            period_results,
            recovery_results,
        )
        new_final = (
            Decimal(str(calculated.final_average))
            if calculated.final_average is not None
            else None
        )

        delta: Optional[Decimal] = None
        absolute_delta: Optional[Decimal] = None
        if legacy is None and new_final is None:
            classification = ShadowClassification.BOTH_INCOMPLETE
        elif legacy is not None and new_final is None:
            classification = ShadowClassification.NEW_INCOMPLETE
        elif legacy is None and new_final is not None:
            classification = ShadowClassification.LEGACY_MISSING
        else:
            delta = new_final - legacy
            absolute_delta = abs(delta)
            classification = (
                ShadowClassification.MATCH
                if absolute_delta <= tolerance_decimal
                else ShadowClassification.DIFFERENT
            )

        return ShadowComparison(
            **base,
            classification=classification,
            legacy_final_average=(float(legacy) if legacy is not None else None),
            new_current_average=calculated.current_average,
            new_final_average=calculated.final_average,
            new_is_final=calculated.is_final,
            delta=(float(delta) if delta is not None else None),
            absolute_delta=(
                float(absolute_delta)
                if absolute_delta is not None
                else None
            ),
            rule_hash=calculated.rule_hash,
        )
    except AssessmentPolicyError as exc:
        legacy_value = None
        try:
            parsed_legacy = _legacy_decimal(snapshot.legacy_final_average)
            legacy_value = (
                float(parsed_legacy)
                if parsed_legacy is not None
                else None
            )
        except AssessmentPolicyError:
            pass

        return ShadowComparison(
            **base,
            classification=ShadowClassification.ERROR,
            legacy_final_average=legacy_value,
            new_current_average=None,
            new_final_average=None,
            new_is_final=None,
            delta=None,
            absolute_delta=None,
            error_code=exc.code,
            error_message=exc.message,
            error_details=exc.details,
        )


def compare_legacy_grade_batch(
    policy: AssessmentPolicy,
    snapshots: Sequence[LegacyGradeSnapshot],
    mapping: LegacyGradeFieldMapping,
    *,
    tolerance: Any = "0.01",
) -> ShadowBatchReport:
    validated_mapping = validate_shadow_mapping(policy, mapping)
    mapping_hash = calculate_mapping_hash(validated_mapping)
    tolerance_decimal = _tolerance_decimal(tolerance)

    comparisons = tuple(
        compare_legacy_grade_snapshot(
            policy,
            snapshot,
            validated_mapping,
            tolerance=tolerance_decimal,
            _mapping_already_validated=True,
        )
        for snapshot in snapshots
    )

    def count(classification: ShadowClassification) -> int:
        return sum(item.classification == classification for item in comparisons)

    matches = count(ShadowClassification.MATCH)
    differences = count(ShadowClassification.DIFFERENT)
    comparable = matches + differences
    deltas = [
        Decimal(str(item.absolute_delta))
        for item in comparisons
        if item.absolute_delta is not None
    ]

    return ShadowBatchReport(
        total=len(comparisons),
        matches=matches,
        differences=differences,
        both_incomplete=count(ShadowClassification.BOTH_INCOMPLETE),
        new_incomplete=count(ShadowClassification.NEW_INCOMPLETE),
        legacy_missing=count(ShadowClassification.LEGACY_MISSING),
        errors=count(ShadowClassification.ERROR),
        comparable=comparable,
        match_rate=(matches / comparable if comparable else None),
        max_absolute_delta=(float(max(deltas)) if deltas else None),
        policy_ids=tuple(sorted({item.policy_id for item in comparisons})),
        rule_hashes=tuple(sorted({item.rule_hash for item in comparisons})),
        mapping_hash=mapping_hash,
        comparisons=comparisons,
    )
