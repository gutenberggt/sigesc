"""Academic Outcome Engine puro da Assessment Policy v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from numbers import Real
from typing import Any, Mapping, Optional, Sequence

from .canonical import calculate_rule_hash
from .exceptions import (
    AssessmentPolicyError,
    OUTCOME_ATTENDANCE_INVALID,
    OUTCOME_DEPENDENCY_AMBIGUOUS,
    OUTCOME_DUPLICATE_COMPONENT,
    OUTCOME_POLICY_INVALID,
    OUTCOME_VALUE_INVALID,
    POLICY_INTEGRITY_ERROR,
)
from .models import (
    AssessmentMode,
    AssessmentPolicy,
    AttendanceBasis,
    ComponentOutcomeStrategy,
    DependencyMode,
    PolicyStatus,
)
from .validator import validate_policy


class AcademicOutcomeStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    WITH_DEPENDENCY = "with_dependency"
    DEPENDENCY_ONLY = "dependency_only"
    NOT_APPROVED_COMPONENT = "not_approved_component"
    NOT_APPROVED_ATTENDANCE = "not_approved_attendance"
    NOT_APPROVED_COMPONENT_AND_ATTENDANCE = (
        "not_approved_component_and_attendance"
    )


@dataclass(frozen=True)
class ComponentOutcomeInput:
    component_id: str
    final_average: Optional[float] = None
    is_final: bool = False
    required: bool = True
    counts_for_outcome: bool = True


@dataclass(frozen=True)
class AttendanceEvidence:
    global_percentage: Optional[float] = None
    stage_percentage: Optional[float] = None
    component_percentages: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class AcademicOutcomeResult:
    status: AcademicOutcomeStatus
    failed_component_ids: tuple[str, ...]
    incomplete_component_ids: tuple[str, ...]
    failed_attendance_component_ids: tuple[str, ...]
    missing_attendance_component_ids: tuple[str, ...]
    attendance_failed: bool
    attendance_complete: bool
    dependency_mode: Optional[DependencyMode]
    reason_codes: tuple[str, ...]
    component_threshold: Optional[float]
    attendance_threshold: Optional[float]
    attendance_basis: Optional[str]
    council_override_available: bool
    policy_id: str
    policy_key: str
    policy_version: int
    policy_status: str
    rule_hash: str


def _decimal(value: Any, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, Real)):
        raise AssessmentPolicyError(
            OUTCOME_VALUE_INVALID,
            "Valor acadêmico deve ser numérico.",
            details={"field": field_name, "value": value},
        )
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise AssessmentPolicyError(
            OUTCOME_VALUE_INVALID,
            "Valor acadêmico deve ser finito.",
            details={"field": field_name, "value": str(value)},
        )
    return result


def _attendance_decimal(value: Any, *, field_name: str) -> Decimal:
    result = _decimal(value, field_name=field_name)
    if result < 0 or result > 100:
        raise AssessmentPolicyError(
            OUTCOME_ATTENDANCE_INVALID,
            "Percentual de frequência deve estar entre 0 e 100.",
            details={"field": field_name, "value": str(result)},
        )
    return result


def _validate_final_average_scale(
    policy: AssessmentPolicy,
    value: Decimal,
    *,
    component_id: str,
) -> None:
    if policy.assessment.mode == AssessmentMode.NUMERIC:
        scale = policy.assessment.numeric_scale
        if scale is None:
            raise AssessmentPolicyError(
                OUTCOME_POLICY_INVALID,
                "Política numérica não possui escala para validar resultado final.",
            )
        minimum = Decimal(str(scale.minimum))
        maximum = Decimal(str(scale.maximum))
    elif policy.assessment.mode == AssessmentMode.CONCEPTUAL:
        values = [
            Decimal(str(entry.numeric_value))
            for entry in (policy.assessment.conceptual_scale or [])
        ]
        if not values:
            raise AssessmentPolicyError(
                OUTCOME_POLICY_INVALID,
                "Política conceitual não possui escala para validar resultado final.",
            )
        minimum = min(values)
        maximum = max(values)
    else:
        # DESCRIPTIVE/SKILL_BASED podem ter um Outcome futuro próprio. A v1 não
        # inventa uma escala numérica para esses modos.
        raise AssessmentPolicyError(
            OUTCOME_POLICY_INVALID,
            "Outcome v1 com média mínima exige política numeric ou conceptual.",
            details={"assessment_mode": policy.assessment.mode.value},
        )

    if value < minimum or value > maximum:
        raise AssessmentPolicyError(
            OUTCOME_VALUE_INVALID,
            "Média final do componente está fora da escala da política.",
            details={
                "component_id": component_id,
                "value": str(value),
                "minimum": str(minimum),
                "maximum": str(maximum),
            },
        )


def _validate_outcome_policy(policy: AssessmentPolicy) -> str:
    calculated_hash = calculate_rule_hash(policy)
    immutable_states = {
        PolicyStatus.PUBLISHED,
        PolicyStatus.SUPERSEDED,
        PolicyStatus.RETIRED,
    }
    if policy.status in immutable_states:
        if not policy.rule_hash or policy.rule_hash != calculated_hash:
            raise AssessmentPolicyError(
                POLICY_INTEGRITY_ERROR,
                "Política publicada/histórica possui hash ausente ou divergente.",
                details={
                    "policy_id": policy.id,
                    "policy_status": policy.status.value,
                    "stored_rule_hash": policy.rule_hash,
                    "calculated_rule_hash": calculated_hash,
                },
            )

    requires_publish_contract = policy.status in {
        PolicyStatus.VALIDATED,
        PolicyStatus.PUBLISHED,
        PolicyStatus.SUPERSEDED,
        PolicyStatus.RETIRED,
    }
    report = validate_policy(policy, for_publish=requires_publish_contract)
    errors = [
        issue.model_dump(mode="json")
        for issue in report.issues
        if issue.severity == "error"
    ]
    if errors:
        raise AssessmentPolicyError(
            OUTCOME_POLICY_INVALID,
            "A política possui inconsistências e não pode produzir resultado acadêmico.",
            details={"issues": errors},
        )

    if policy.status not in immutable_states:
        if policy.rule_hash is not None and policy.rule_hash != calculated_hash:
            raise AssessmentPolicyError(
                OUTCOME_POLICY_INVALID,
                "rule_hash informado não corresponde à política usada no outcome.",
                details={
                    "stored_rule_hash": policy.rule_hash,
                    "calculated_rule_hash": calculated_hash,
                },
            )

    if (
        policy.academic_outcome.component_strategy
        != ComponentOutcomeStrategy.ALL_REQUIRED_COMPONENTS
    ):
        raise AssessmentPolicyError(
            OUTCOME_POLICY_INVALID,
            "Estratégia de componentes não é executável pela Outcome v1.",
            details={
                "component_strategy": policy.academic_outcome.component_strategy.value,
            },
        )

    return calculated_hash


def _validate_unique_components(
    components: Sequence[ComponentOutcomeInput],
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for component in components:
        component_id = str(component.component_id or "").strip()
        if not component_id:
            raise AssessmentPolicyError(
                OUTCOME_VALUE_INVALID,
                "component_id é obrigatório no Academic Outcome.",
            )
        if component_id in seen:
            duplicates.add(component_id)
        seen.add(component_id)
    if duplicates:
        raise AssessmentPolicyError(
            OUTCOME_DUPLICATE_COMPONENT,
            "O mesmo componente foi informado mais de uma vez no Academic Outcome.",
            details={"component_ids": sorted(duplicates)},
        )


def _dependency_mode_for_failed_count(
    policy: AssessmentPolicy,
    failed_count: int,
) -> Optional[DependencyMode]:
    dependency = policy.academic_outcome.dependency
    if not dependency.enabled or failed_count <= 0:
        return None

    matches = []
    for item in dependency.outcomes:
        if failed_count < item.min_failed_components:
            continue
        if (
            item.max_failed_components is not None
            and failed_count > item.max_failed_components
        ):
            continue
        matches.append(item.mode)

    if len(matches) > 1:
        raise AssessmentPolicyError(
            OUTCOME_DEPENDENCY_AMBIGUOUS,
            "Mais de uma faixa de dependência corresponde à quantidade de componentes não atingidos.",
            details={
                "failed_count": failed_count,
                "modes": sorted(mode.value for mode in matches),
            },
        )
    return matches[0] if matches else None


def calculate_academic_outcome(
    policy: AssessmentPolicy,
    components: Sequence[ComponentOutcomeInput],
    attendance: Optional[AttendanceEvidence] = None,
) -> AcademicOutcomeResult:
    """Calcula resultado pedagógico sem mutar matrícula, notas ou dependências."""

    rule_hash = _validate_outcome_policy(policy)
    _validate_unique_components(components)

    outcome_rule = policy.academic_outcome
    included = [component for component in components if component.counts_for_outcome]

    failed_components: list[str] = []
    incomplete_components: list[str] = []
    evaluated_components: list[str] = []

    threshold = outcome_rule.minimum_component_average
    threshold_decimal = Decimal(str(threshold)) if threshold is not None else None

    if threshold_decimal is not None:
        if not included:
            incomplete_components.append("__NO_EVALUATIVE_COMPONENTS__")

        for component in included:
            component_id = str(component.component_id).strip()
            has_final = component.is_final and component.final_average is not None

            if component.required and not has_final:
                incomplete_components.append(component_id)
                continue
            if not has_final:
                # Componente opcional sem fechamento não bloqueia o outcome.
                continue

            average = _decimal(
                component.final_average,
                field_name=f"components.{component_id}.final_average",
            )
            _validate_final_average_scale(
                policy,
                average,
                component_id=component_id,
            )
            evaluated_components.append(component_id)
            if average < threshold_decimal:
                failed_components.append(component_id)

    attendance_threshold = outcome_rule.minimum_attendance_percentage
    attendance_complete = True
    attendance_failed = False
    failed_attendance_components: list[str] = []
    missing_attendance_components: list[str] = []

    if attendance_threshold is not None:
        attendance_complete = False
        evidence = attendance or AttendanceEvidence()
        minimum_attendance = Decimal(str(attendance_threshold))
        basis = outcome_rule.attendance_basis

        if basis == AttendanceBasis.GLOBAL:
            if evidence.global_percentage is not None:
                value = _attendance_decimal(
                    evidence.global_percentage,
                    field_name="attendance.global_percentage",
                )
                attendance_complete = True
                attendance_failed = value < minimum_attendance

        elif basis == AttendanceBasis.STAGE:
            if evidence.stage_percentage is not None:
                value = _attendance_decimal(
                    evidence.stage_percentage,
                    field_name="attendance.stage_percentage",
                )
                attendance_complete = True
                attendance_failed = value < minimum_attendance

        elif basis == AttendanceBasis.COMPONENT:
            # Obrigatórios sempre precisam de evidência. Opcionais passam a
            # participar quando têm avaliação final e contam para o outcome.
            attendance_targets = [
                component
                for component in included
                if component.required
                or (component.is_final and component.final_average is not None)
            ]
            if attendance_targets:
                attendance_complete = True
                for component in attendance_targets:
                    component_id = str(component.component_id).strip()
                    raw = evidence.component_percentages.get(component_id)
                    if raw is None:
                        attendance_complete = False
                        missing_attendance_components.append(component_id)
                        continue
                    value = _attendance_decimal(
                        raw,
                        field_name=(
                            f"attendance.component_percentages.{component_id}"
                        ),
                    )
                    if value < minimum_attendance:
                        attendance_failed = True
                        failed_attendance_components.append(component_id)
            else:
                attendance_complete = False
        else:
            raise AssessmentPolicyError(
                OUTCOME_POLICY_INVALID,
                "Base de frequência exigida não é suportada pela Outcome v1.",
                details={"attendance_basis": str(basis)},
            )

    reason_codes: list[str] = []
    if incomplete_components:
        reason_codes.append("COMPONENT_DATA_INCOMPLETE")
    if attendance_threshold is not None and not attendance_complete:
        reason_codes.append("ATTENDANCE_DATA_INCOMPLETE")

    council_available = bool(
        outcome_rule.council.enabled
        and outcome_rule.council.can_override_academic_result
    )

    if incomplete_components or (
        attendance_threshold is not None and not attendance_complete
    ):
        status = AcademicOutcomeStatus.IN_PROGRESS
        dependency_mode = None
    else:
        component_failed = bool(failed_components)

        if component_failed and attendance_failed:
            status = AcademicOutcomeStatus.NOT_APPROVED_COMPONENT_AND_ATTENDANCE
            dependency_mode = None
            reason_codes.extend(["COMPONENT_THRESHOLD_NOT_MET", "ATTENDANCE_THRESHOLD_NOT_MET"])
        elif attendance_failed:
            status = AcademicOutcomeStatus.NOT_APPROVED_ATTENDANCE
            dependency_mode = None
            reason_codes.append("ATTENDANCE_THRESHOLD_NOT_MET")
        elif component_failed:
            dependency_mode = _dependency_mode_for_failed_count(
                policy,
                len(failed_components),
            )
            if dependency_mode == DependencyMode.WITH_DEPENDENCY:
                status = AcademicOutcomeStatus.WITH_DEPENDENCY
                reason_codes.append("DEPENDENCY_WITH_REGULAR_ENROLLMENT")
            elif dependency_mode == DependencyMode.DEPENDENCY_ONLY:
                status = AcademicOutcomeStatus.DEPENDENCY_ONLY
                reason_codes.append("DEPENDENCY_ONLY")
            else:
                status = AcademicOutcomeStatus.NOT_APPROVED_COMPONENT
                reason_codes.append("COMPONENT_THRESHOLD_NOT_MET")
        else:
            status = AcademicOutcomeStatus.APPROVED
            dependency_mode = None
            reason_codes.append("ALL_POLICY_REQUIREMENTS_MET")

    return AcademicOutcomeResult(
        status=status,
        failed_component_ids=tuple(sorted(failed_components)),
        incomplete_component_ids=tuple(sorted(incomplete_components)),
        failed_attendance_component_ids=tuple(sorted(failed_attendance_components)),
        missing_attendance_component_ids=tuple(sorted(missing_attendance_components)),
        attendance_failed=attendance_failed,
        attendance_complete=attendance_complete,
        dependency_mode=dependency_mode,
        reason_codes=tuple(reason_codes),
        component_threshold=threshold,
        attendance_threshold=attendance_threshold,
        attendance_basis=(
            outcome_rule.attendance_basis.value
            if outcome_rule.attendance_basis is not None
            else None
        ),
        council_override_available=council_available,
        policy_id=policy.id,
        policy_key=policy.policy_key,
        policy_version=policy.version,
        policy_status=policy.status.value,
        rule_hash=rule_hash,
    )
