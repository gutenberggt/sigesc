"""Dry-run piloto read-only para uma Assessment Policy candidata.

Diferente do Shadow Runner oficial, que resolve apenas policies publicadas, este
runner recebe explicitamente um draft/validated completo. Ele existe para
validação pedagógica antes da publicação e nunca participa do runtime de Notas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional, Sequence

from .assisted_config import AssistedPolicyConfiguration, preview_assisted_configuration
from .canonical import calculate_rule_hash
from .context_builder import build_assessment_policy_context
from .exceptions import AssessmentPolicyError, POLICY_CONTEXT_MISMATCH
from .models import AssessmentPolicy, PolicyStatus
from .resolver import scope_matches_context
from .shadow import (
    LegacyGradeFieldMapping,
    LegacyGradeSnapshot,
    ShadowBatchReport,
    compare_legacy_grade_batch,
    legacy_grade_snapshot_from_document,
    validate_shadow_mapping,
)
from .shadow_runner import ShadowGradeReader


PILOT_NOT_READY = "ASSESSMENT_POLICY_PILOT_NOT_READY"
PILOT_TENANT_MISMATCH = "ASSESSMENT_POLICY_PILOT_TENANT_MISMATCH"
PILOT_GRADE_TENANT_MISMATCH = "ASSESSMENT_POLICY_PILOT_GRADE_TENANT_MISMATCH"


@dataclass(frozen=True)
class CandidatePilotIssue:
    grade_id: Optional[str]
    student_id: Optional[str]
    class_id: Optional[str]
    course_id: Optional[str]
    error_code: str
    error_message: str
    error_details: Optional[Any] = None


@dataclass(frozen=True)
class CandidatePilotReport:
    mantenedora_id: str
    policy_id: str
    policy_key: str
    policy_version: int
    policy_status: str
    policy_rule_hash: str
    academic_year: int
    reference_date: date
    scanned: int
    in_scope: int
    skipped_out_of_scope: int
    compared: int
    unresolved: int
    comparable: int
    matches: int
    differences: int
    match_rate: Optional[float]
    report: ShadowBatchReport
    issues: tuple[CandidatePilotIssue, ...]


def _issue(document: dict, exc: AssessmentPolicyError) -> CandidatePilotIssue:
    def as_text(field: str) -> Optional[str]:
        value = document.get(field)
        return None if value is None else str(value)

    return CandidatePilotIssue(
        grade_id=as_text("id"),
        student_id=as_text("student_id"),
        class_id=as_text("class_id"),
        course_id=as_text("course_id"),
        error_code=exc.code,
        error_message=exc.message,
        error_details=exc.details,
    )


def _source_fields(mapping: LegacyGradeFieldMapping) -> tuple[str, ...]:
    return tuple(
        sorted(
            set(mapping.period_field_map.keys())
            | set(mapping.recovery_field_map.keys())
        )
    )


async def run_candidate_dry_run(
    db,
    *,
    policy: AssessmentPolicy,
    mapping: LegacyGradeFieldMapping,
    reference_date: date,
    class_ids: Optional[Sequence[str]] = None,
    tolerance: Any = "0.01",
    limit: Optional[int] = None,
    current_year: Optional[int] = None,
) -> CandidatePilotReport:
    """Compara Grade legado com uma policy candidata sem qualquer escrita."""

    if policy.status not in {PolicyStatus.DRAFT, PolicyStatus.VALIDATED}:
        raise AssessmentPolicyError(
            PILOT_NOT_READY,
            "Dry-run piloto aceita somente policy draft ou validated.",
            details={"status": policy.status.value},
        )

    runtime_mapping = validate_shadow_mapping(policy, mapping)
    preview = preview_assisted_configuration(
        AssistedPolicyConfiguration(
            policy=policy,
            legacy_mapping={
                "period_field_map": dict(runtime_mapping.period_field_map),
                "recovery_field_map": dict(runtime_mapping.recovery_field_map),
            },
            tolerance=str(tolerance),
        )
    )
    if not preview.can_dry_run:
        raise AssessmentPolicyError(
            PILOT_NOT_READY,
            "Policy candidata ainda possui pendências e não pode ser usada no dry-run piloto.",
            details={
                "issues": [item.model_dump(mode="json") for item in preview.issues],
            },
        )

    tenant = str(policy.mantenedora_id or "").strip()
    if not tenant:
        raise AssessmentPolicyError(
            PILOT_TENANT_MISMATCH,
            "Policy candidata não possui mantenedora_id.",
        )

    year = int(policy.academic_year)
    if reference_date.year != year:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "reference_date deve pertencer ao academic_year da policy candidata.",
            details={"academic_year": year, "reference_date": reference_date.isoformat()},
        )
    if not (policy.effective_from <= reference_date <= policy.effective_until):
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "reference_date está fora da vigência da policy candidata.",
            details={
                "effective_from": policy.effective_from.isoformat(),
                "effective_until": policy.effective_until.isoformat(),
                "reference_date": reference_date.isoformat(),
            },
        )
    if limit is not None and int(limit) <= 0:
        raise AssessmentPolicyError(
            POLICY_CONTEXT_MISMATCH,
            "limit deve ser positivo quando informado.",
            details={"limit": limit},
        )

    reader = ShadowGradeReader(db)
    tenant_classes = await reader.list_tenant_classes(tenant, year)
    if class_ids is None:
        selected_class_ids = tuple(sorted(tenant_classes))
    else:
        selected_class_ids = tuple(
            sorted({str(item).strip() for item in class_ids if str(item).strip()})
        )
        outside = sorted(set(selected_class_ids) - set(tenant_classes))
        if outside:
            raise AssessmentPolicyError(
                PILOT_TENANT_MISMATCH,
                "class_ids contém turma fora da mantenedora/ano da policy candidata.",
                details={"class_ids": outside},
            )

    documents = await reader.list_grade_documents(
        class_ids=selected_class_ids,
        academic_year=year,
        source_fields=_source_fields(runtime_mapping),
        limit=(int(limit) if limit is not None else None),
    )

    snapshots: list[LegacyGradeSnapshot] = []
    issues: list[CandidatePilotIssue] = []
    skipped = 0

    for document in documents:
        try:
            snapshot = legacy_grade_snapshot_from_document(document)
            explicit_tenant = str(document.get("mantenedora_id") or "").strip()
            if explicit_tenant and explicit_tenant != tenant:
                raise AssessmentPolicyError(
                    PILOT_GRADE_TENANT_MISMATCH,
                    "Grade legado declara mantenedora diferente da policy candidata.",
                    details={
                        "grade_mantenedora_id": explicit_tenant,
                        "mantenedora_id": tenant,
                        "grade_id": snapshot.grade_id,
                    },
                )

            school_id = tenant_classes.get(snapshot.class_id)
            if not school_id:
                raise AssessmentPolicyError(
                    PILOT_TENANT_MISMATCH,
                    "Grade legado referencia turma fora do tenant do piloto.",
                    details={"class_id": snapshot.class_id},
                )

            context = await build_assessment_policy_context(
                db,
                mantenedora_id=tenant,
                school_id=school_id,
                class_id=snapshot.class_id,
                student_id=snapshot.student_id,
                component_id=snapshot.course_id,
                academic_year=year,
                reference_date=reference_date,
                current_year=current_year,
            )

            if not scope_matches_context(policy.scope, context):
                skipped += 1
                continue

            snapshots.append(snapshot)
        except AssessmentPolicyError as exc:
            issues.append(_issue(document, exc))

    comparison = compare_legacy_grade_batch(
        policy,
        snapshots,
        runtime_mapping,
        tolerance=tolerance,
    )

    return CandidatePilotReport(
        mantenedora_id=tenant,
        policy_id=policy.id,
        policy_key=policy.policy_key,
        policy_version=policy.version,
        policy_status=policy.status.value,
        policy_rule_hash=calculate_rule_hash(policy),
        academic_year=year,
        reference_date=reference_date,
        scanned=len(documents),
        in_scope=len(snapshots),
        skipped_out_of_scope=skipped,
        compared=comparison.total,
        unresolved=len(issues),
        comparable=comparison.comparable,
        matches=comparison.matches,
        differences=comparison.differences,
        match_rate=comparison.match_rate,
        report=comparison,
        issues=tuple(issues),
    )
