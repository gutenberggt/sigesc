"""Validação sem efeitos colaterais da Assessment Policy v1."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .canonical import calculate_rule_hash
from .models import AssessmentMode, AssessmentPolicy


class PolicyValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    code: str
    field: str
    message: str


class PolicyValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: List[PolicyValidationIssue] = Field(default_factory=list)
    calculated_rule_hash: Optional[str] = None


def _issue(
    issues: List[PolicyValidationIssue],
    code: str,
    field: str,
    message: str,
    severity: Literal["error", "warning"] = "error",
) -> None:
    issues.append(
        PolicyValidationIssue(
            severity=severity,
            code=code,
            field=field,
            message=message,
        )
    )


def _ranges_overlap(left, right) -> bool:
    left_max = left.max_failed_components
    right_max = right.max_failed_components
    return (
        (left_max is None or right.min_failed_components <= left_max)
        and (right_max is None or left.min_failed_components <= right_max)
    )


def validate_policy(policy: AssessmentPolicy, *, for_publish: bool = False) -> PolicyValidationReport:
    """Valida coerência sem acessar banco, tenant ou outras entidades.

    Validações que dependem de existência/pertencimento de escola, turma,
    componente e mantenedora são responsabilidade do Registry/Resolver.
    """

    issues: List[PolicyValidationIssue] = []

    period_codes = [period.code for period in policy.assessment.periods]
    if len(period_codes) != len(set(period_codes)):
        _issue(
            issues,
            "ASSESSMENT_POLICY_DUPLICATE_PERIOD",
            "assessment.periods",
            "Códigos de período devem ser únicos.",
        )

    if policy.assessment.mode == AssessmentMode.CONCEPTUAL:
        scale = policy.assessment.conceptual_scale or []
        codes = [entry.code for entry in scale]
        values = [entry.numeric_value for entry in scale]

        if len(scale) < 2:
            _issue(
                issues,
                "ASSESSMENT_POLICY_CONCEPTUAL_SCALE_TOO_SMALL",
                "assessment.conceptual_scale",
                "Escala conceitual deve possuir pelo menos dois conceitos.",
            )
        if len(codes) != len(set(codes)):
            _issue(
                issues,
                "ASSESSMENT_POLICY_DUPLICATE_CONCEPT_CODE",
                "assessment.conceptual_scale",
                "Códigos de conceito devem ser únicos.",
            )
        if len(values) != len(set(values)):
            _issue(
                issues,
                "ASSESSMENT_POLICY_DUPLICATE_CONCEPT_VALUE",
                "assessment.conceptual_scale",
                "Valores numéricos dos conceitos devem ser únicos para permitir conversão determinística.",
            )

    if policy.recovery.enabled and not policy.recovery.groups:
        _issue(
            issues,
            "ASSESSMENT_POLICY_RECOVERY_GROUP_REQUIRED",
            "recovery.groups",
            "Recuperação habilitada exige pelo menos um grupo configurado.",
        )

    if not policy.recovery.enabled and policy.recovery.groups:
        _issue(
            issues,
            "ASSESSMENT_POLICY_RECOVERY_GROUP_IGNORED",
            "recovery.groups",
            "Existem grupos de recuperação, mas recovery.enabled=false.",
            severity="warning",
        )

    recovery_codes = set()
    recovery_input_codes = set()
    recovery_period_owner = {}
    valid_period_codes = set(period_codes)

    for index, group in enumerate(policy.recovery.groups):
        field = f"recovery.groups.{index}"

        if group.code in recovery_codes:
            _issue(
                issues,
                "ASSESSMENT_POLICY_DUPLICATE_RECOVERY_GROUP",
                field,
                f"Grupo de recuperação duplicado: {group.code}.",
            )
        recovery_codes.add(group.code)

        if group.input_code in recovery_input_codes:
            _issue(
                issues,
                "ASSESSMENT_POLICY_DUPLICATE_RECOVERY_INPUT",
                field,
                f"Entrada de recuperação duplicada: {group.input_code}.",
            )
        recovery_input_codes.add(group.input_code)

        unknown_periods = sorted(set(group.period_codes) - valid_period_codes)
        if unknown_periods:
            _issue(
                issues,
                "ASSESSMENT_POLICY_RECOVERY_UNKNOWN_PERIOD",
                f"{field}.period_codes",
                "Grupo de recuperação referencia períodos inexistentes: "
                + ", ".join(unknown_periods),
            )

        if policy.recovery.enabled:
            for period_code in group.period_codes:
                previous_group = recovery_period_owner.get(period_code)
                if previous_group is not None and previous_group != group.code:
                    _issue(
                        issues,
                        "ASSESSMENT_POLICY_RECOVERY_PERIOD_OVERLAP",
                        f"{field}.period_codes",
                        "Período de recuperação não pode pertencer a mais de um grupo na v1: "
                        f"{period_code} ({previous_group} e {group.code}).",
                    )
                else:
                    recovery_period_owner[period_code] = group.code

        if for_publish and group.only_if_improves is None:
            _issue(
                issues,
                "ASSESSMENT_POLICY_RECOVERY_IMPROVEMENT_RULE_REQUIRED",
                f"{field}.only_if_improves",
                "Antes da publicação é obrigatório definir se a recuperação pode reduzir o resultado original.",
            )

    minimum_average = policy.academic_outcome.minimum_component_average
    if minimum_average is not None:
        if policy.assessment.mode == AssessmentMode.NUMERIC:
            scale = policy.assessment.numeric_scale
            if scale and not (scale.minimum <= minimum_average <= scale.maximum):
                _issue(
                    issues,
                    "ASSESSMENT_POLICY_MINIMUM_AVERAGE_OUT_OF_SCALE",
                    "academic_outcome.minimum_component_average",
                    "Média mínima deve estar dentro da escala numérica configurada.",
                )
        elif policy.assessment.mode == AssessmentMode.CONCEPTUAL:
            values = [
                entry.numeric_value
                for entry in (policy.assessment.conceptual_scale or [])
            ]
            if values and not (min(values) <= minimum_average <= max(values)):
                _issue(
                    issues,
                    "ASSESSMENT_POLICY_MINIMUM_AVERAGE_OUT_OF_SCALE",
                    "academic_outcome.minimum_component_average",
                    "Média mínima deve estar dentro dos valores numéricos da escala conceitual.",
                )

    # `require_all_components=False` não recebe interpretação mágica. A v1
    # possui uma única estratégia explícita, all_required_components.
    if not policy.academic_outcome.require_all_components:
        _issue(
            issues,
            "ASSESSMENT_POLICY_COMPONENT_STRATEGY_UNSUPPORTED",
            "academic_outcome.require_all_components",
            "Outcome v1 não atribui semântica a require_all_components=false; configure uma estratégia explícita suportada.",
        )

    dependency = policy.academic_outcome.dependency
    if dependency.enabled and not dependency.outcomes:
        _issue(
            issues,
            "ASSESSMENT_POLICY_DEPENDENCY_OUTCOME_REQUIRED",
            "academic_outcome.dependency.outcomes",
            "Dependência habilitada exige ao menos uma faixa de resultado.",
        )
    if not dependency.enabled and dependency.outcomes:
        _issue(
            issues,
            "ASSESSMENT_POLICY_DEPENDENCY_OUTCOME_IGNORED",
            "academic_outcome.dependency.outcomes",
            "Existem faixas de dependência, mas dependency.enabled=false.",
            severity="warning",
        )
    if dependency.enabled and minimum_average is None:
        _issue(
            issues,
            "ASSESSMENT_POLICY_DEPENDENCY_REQUIRES_COMPONENT_THRESHOLD",
            "academic_outcome.minimum_component_average",
            "Dependência por componentes exige média mínima por componente.",
        )

    seen_dependency_modes = set()
    for index, item in enumerate(dependency.outcomes):
        field = f"academic_outcome.dependency.outcomes.{index}"
        if item.mode in seen_dependency_modes:
            _issue(
                issues,
                "ASSESSMENT_POLICY_DUPLICATE_DEPENDENCY_MODE",
                field,
                f"Modo de dependência duplicado na v1: {item.mode.value}.",
            )
        seen_dependency_modes.add(item.mode)

    for left_index, left in enumerate(dependency.outcomes):
        for right_index in range(left_index + 1, len(dependency.outcomes)):
            right = dependency.outcomes[right_index]
            if _ranges_overlap(left, right):
                _issue(
                    issues,
                    "ASSESSMENT_POLICY_DEPENDENCY_RANGE_OVERLAP",
                    "academic_outcome.dependency.outcomes",
                    "Faixas de quantidade de componentes não atingidos não podem se sobrepor: "
                    f"{left.mode.value} e {right.mode.value}.",
                )

    minimum_attendance = policy.academic_outcome.minimum_attendance_percentage
    attendance_basis = policy.academic_outcome.attendance_basis
    if (minimum_attendance is None) != (attendance_basis is None):
        _issue(
            issues,
            "ASSESSMENT_POLICY_ATTENDANCE_CONTRACT_INCOMPLETE",
            "academic_outcome",
            "Frequência mínima e base de frequência devem ser configuradas em conjunto.",
        )

    if policy.academic_outcome.council.can_override_academic_result:
        if not policy.academic_outcome.council.enabled:
            _issue(
                issues,
                "ASSESSMENT_POLICY_COUNCIL_OVERRIDE_WITHOUT_COUNCIL",
                "academic_outcome.council",
                "Override de resultado exige conselho habilitado.",
            )
        if not policy.academic_outcome.council.requires_audit_event:
            _issue(
                issues,
                "ASSESSMENT_POLICY_COUNCIL_OVERRIDE_REQUIRES_AUDIT",
                "academic_outcome.council.requires_audit_event",
                "Override de resultado por conselho deve exigir evento de auditoria.",
            )

    if for_publish and not policy.normative_sources:
        _issue(
            issues,
            "ASSESSMENT_POLICY_NORMATIVE_SOURCE_REQUIRED",
            "normative_sources",
            "Política publicada deve registrar ao menos uma fonte normativa ou política interna formal.",
        )

    calculated_hash = calculate_rule_hash(policy)
    if policy.rule_hash is not None and policy.rule_hash != calculated_hash:
        _issue(
            issues,
            "ASSESSMENT_POLICY_HASH_MISMATCH",
            "rule_hash",
            "rule_hash informado não corresponde ao conteúdo canônico da política.",
        )

    valid = not any(issue.severity == "error" for issue in issues)
    return PolicyValidationReport(
        valid=valid,
        issues=issues,
        calculated_rule_hash=calculated_hash,
    )
