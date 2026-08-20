"""Calculator puro e determinístico da Assessment Policy v1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from numbers import Real
from typing import Any, Mapping, Optional

from .canonical import calculate_rule_hash
from .exceptions import (
    AssessmentPolicyError,
    CALCULATION_MODE_UNSUPPORTED,
    CALCULATION_POLICY_INVALID,
    CALCULATION_UNKNOWN_CONCEPT,
    CALCULATION_UNKNOWN_PERIOD,
    CALCULATION_VALUE_INVALID,
    CALCULATION_VALUE_OUT_OF_SCALE,
    POLICY_INTEGRITY_ERROR,
    RECOVERY_UNKNOWN_INPUT,
)
from .models import (
    AssessmentMode,
    AssessmentPolicy,
    CalculationStrategy,
    PartialDivisorStrategy,
    PolicyStatus,
)
from .recovery import RecoveryApplication, apply_recoveries
from .validator import validate_policy


@dataclass(frozen=True)
class AssessmentCalculationResult:
    current_average: Optional[float]
    final_average: Optional[float]
    is_final: bool
    original_values: dict[str, Optional[float]]
    final_values: dict[str, Optional[float]]
    period_weights: dict[str, float]
    recoveries_applied: tuple[dict[str, Any], ...]
    current_numerator: Optional[float]
    current_divisor: Optional[float]
    final_numerator: Optional[float]
    final_divisor: Optional[float]
    raw_period_results: dict[str, Any]
    raw_recovery_results: dict[str, Any]
    policy_id: str
    policy_key: str
    policy_version: int
    policy_status: str
    rule_hash: str


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, Real)):
        raise AssessmentPolicyError(
            CALCULATION_VALUE_INVALID,
            "Valor avaliativo deve ser numérico para esta política.",
            details={"field": field, "value": value},
        )
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise AssessmentPolicyError(
            CALCULATION_VALUE_INVALID,
            "Valor avaliativo deve ser finito.",
            details={"field": field, "value": str(value)},
        )
    return result


def _decode_value(policy: AssessmentPolicy, raw: Any, *, field: str) -> Decimal:
    mode = policy.assessment.mode

    if mode == AssessmentMode.NUMERIC:
        value = _decimal(raw, field=field)
        scale = policy.assessment.numeric_scale
        if scale is None:
            raise AssessmentPolicyError(
                CALCULATION_POLICY_INVALID,
                "Política numérica não possui escala configurada.",
                details={"field": "assessment.numeric_scale"},
            )
        minimum = Decimal(str(scale.minimum))
        maximum = Decimal(str(scale.maximum))
        if value < minimum or value > maximum:
            raise AssessmentPolicyError(
                CALCULATION_VALUE_OUT_OF_SCALE,
                "Valor avaliativo está fora da escala numérica da política.",
                details={
                    "field": field,
                    "value": str(value),
                    "minimum": str(minimum),
                    "maximum": str(maximum),
                },
            )
        return value

    if mode == AssessmentMode.CONCEPTUAL:
        scale = policy.assessment.conceptual_scale or []
        if isinstance(raw, str):
            code = raw.strip()
            for entry in scale:
                if entry.code == code:
                    return Decimal(str(entry.numeric_value))
            raise AssessmentPolicyError(
                CALCULATION_UNKNOWN_CONCEPT,
                "Conceito não existe na escala da política.",
                details={
                    "field": field,
                    "concept": code,
                    "allowed_codes": [entry.code for entry in scale],
                },
            )

        value = _decimal(raw, field=field)
        allowed = [Decimal(str(entry.numeric_value)) for entry in scale]
        if value not in allowed:
            raise AssessmentPolicyError(
                CALCULATION_VALUE_OUT_OF_SCALE,
                "Valor numérico não corresponde a nenhum conceito configurado.",
                details={
                    "field": field,
                    "value": str(value),
                    "allowed_values": [str(item) for item in allowed],
                },
            )
        return value

    raise AssessmentPolicyError(
        CALCULATION_MODE_UNSUPPORTED,
        "O Calculator v1 executa somente políticas numeric ou conceptual.",
        details={"assessment_mode": mode.value},
    )


def _validate_calculation_policy(policy: AssessmentPolicy) -> str:
    report = validate_policy(policy, for_publish=False)
    errors = [
        issue.model_dump(mode="json")
        for issue in report.issues
        if issue.severity == "error"
    ]
    if errors:
        raise AssessmentPolicyError(
            CALCULATION_POLICY_INVALID,
            "A política possui inconsistências e não pode ser executada pelo Calculator.",
            details={"issues": errors},
        )

    calculated_hash = calculate_rule_hash(policy)
    if policy.status == PolicyStatus.PUBLISHED:
        if not policy.rule_hash or policy.rule_hash != calculated_hash:
            raise AssessmentPolicyError(
                POLICY_INTEGRITY_ERROR,
                "Política publicada possui hash ausente ou divergente.",
                details={
                    "policy_id": policy.id,
                    "stored_rule_hash": policy.rule_hash,
                    "calculated_rule_hash": calculated_hash,
                },
            )
    elif policy.rule_hash is not None and policy.rule_hash != calculated_hash:
        raise AssessmentPolicyError(
            CALCULATION_POLICY_INVALID,
            "rule_hash informado não corresponde à política usada na simulação.",
            details={
                "stored_rule_hash": policy.rule_hash,
                "calculated_rule_hash": calculated_hash,
            },
        )
    return calculated_hash


def _decode_period_values(
    policy: AssessmentPolicy,
    period_results: Mapping[str, Any],
) -> dict[str, Decimal]:
    allowed = {period.code for period in policy.assessment.periods}
    unknown = sorted(
        str(code)
        for code, raw in period_results.items()
        if raw is not None and code not in allowed
    )
    if unknown:
        raise AssessmentPolicyError(
            CALCULATION_UNKNOWN_PERIOD,
            "Resultado informado para período inexistente na política.",
            details={"period_codes": unknown},
        )

    decoded: dict[str, Decimal] = {}
    for period in policy.assessment.periods:
        raw = period_results.get(period.code)
        if raw is None:
            continue
        decoded[period.code] = _decode_value(
            policy,
            raw,
            field=f"period_results.{period.code}",
        )
    return decoded


def _decode_recovery_values(
    policy: AssessmentPolicy,
    recovery_results: Mapping[str, Any],
) -> dict[str, Decimal]:
    allowed = {group.input_code for group in policy.recovery.groups}
    unknown = sorted(
        str(code)
        for code, raw in recovery_results.items()
        if raw is not None and code not in allowed
    )
    if unknown:
        raise AssessmentPolicyError(
            RECOVERY_UNKNOWN_INPUT,
            "Resultado informado para recuperação inexistente na política.",
            details={"input_codes": unknown},
        )

    decoded: dict[str, Decimal] = {}
    for group in policy.recovery.groups:
        raw = recovery_results.get(group.input_code)
        if raw is None:
            continue
        decoded[group.input_code] = _decode_value(
            policy,
            raw,
            field=f"recovery_results.{group.input_code}",
        )
    return decoded


def _quantize(value: Decimal, decimal_places: int) -> Decimal:
    quantum = Decimal("1").scaleb(-decimal_places)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _participating_periods(
    policy: AssessmentPolicy,
    values: Mapping[str, Decimal],
) -> list[str]:
    return [
        period.code
        for period in policy.assessment.periods
        if period.required_for_final or period.code in values
    ]


def _calculate_fraction(
    policy: AssessmentPolicy,
    values: Mapping[str, Decimal],
    *,
    final: bool,
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    if not values:
        return None, None, None

    rule = policy.assessment.calculation
    if rule is None:
        raise AssessmentPolicyError(
            CALCULATION_POLICY_INVALID,
            "Política avaliativa não possui estratégia de cálculo.",
            details={"field": "assessment.calculation"},
        )

    participants = _participating_periods(policy, values)
    present_codes = [
        period.code
        for period in policy.assessment.periods
        if period.code in values
    ]

    if rule.strategy == CalculationStrategy.WEIGHTED_AVERAGE:
        weights = {
            period.code: Decimal(str(period.weight))
            for period in policy.assessment.periods
        }
        numerator = sum(
            (values[code] * weights[code] for code in present_codes),
            Decimal("0"),
        )
        if final or rule.partial_divisor == PartialDivisorStrategy.SUM_ALL_WEIGHTS:
            divisor = sum((weights[code] for code in participants), Decimal("0"))
        else:
            divisor = sum((weights[code] for code in present_codes), Decimal("0"))

    elif rule.strategy == CalculationStrategy.SIMPLE_AVERAGE:
        numerator = sum((values[code] for code in present_codes), Decimal("0"))
        if final or rule.partial_divisor == PartialDivisorStrategy.SUM_ALL_WEIGHTS:
            divisor = Decimal(len(participants))
        else:
            divisor = Decimal(len(present_codes))
    else:
        raise AssessmentPolicyError(
            CALCULATION_POLICY_INVALID,
            "Estratégia de cálculo não é executável pelo Calculator v1.",
            details={"strategy": str(rule.strategy)},
        )

    if divisor <= 0:
        raise AssessmentPolicyError(
            CALCULATION_POLICY_INVALID,
            "Divisor da política deve ser maior que zero.",
            details={"divisor": str(divisor)},
        )

    average = _quantize(numerator / divisor, rule.decimal_places)
    return numerator, divisor, average


def _is_final(policy: AssessmentPolicy, values: Mapping[str, Decimal]) -> bool:
    if not values:
        return False
    required = {
        period.code
        for period in policy.assessment.periods
        if period.required_for_final
    }
    return required.issubset(values.keys())


def _as_float(value: Optional[Decimal]) -> Optional[float]:
    return None if value is None else float(value)


def _serialize_application(application: RecoveryApplication) -> dict[str, Any]:
    return {
        "group_code": application.group_code,
        "input_code": application.input_code,
        "input_value": float(application.input_value),
        "target_period": application.target_period,
        "before_value": float(application.before_value),
        "after_value": float(application.after_value),
        "applied": application.applied,
        "reason": application.reason,
        "tie_break": application.tie_break.value,
    }


def calculate_assessment(
    policy: AssessmentPolicy,
    period_results: Mapping[str, Any],
    recovery_results: Mapping[str, Any] | None = None,
) -> AssessmentCalculationResult:
    """Calcula um componente sem persistência, status acadêmico ou frequência."""

    rule_hash = _validate_calculation_policy(policy)

    raw_period_results = dict(period_results)
    raw_recovery_results = dict(recovery_results or {})
    decoded_periods = _decode_period_values(policy, raw_period_results)
    decoded_recoveries = _decode_recovery_values(policy, raw_recovery_results)

    recovery_execution = apply_recoveries(
        policy,
        decoded_periods,
        decoded_recoveries,
    )
    final_values_decimal = recovery_execution.values

    is_final = _is_final(policy, final_values_decimal)
    current_num, current_div, current_avg = _calculate_fraction(
        policy,
        final_values_decimal,
        final=False,
    )

    final_num: Optional[Decimal] = None
    final_div: Optional[Decimal] = None
    final_avg: Optional[Decimal] = None
    if is_final:
        final_num, final_div, final_avg = _calculate_fraction(
            policy,
            final_values_decimal,
            final=True,
        )

    period_codes = [period.code for period in policy.assessment.periods]
    original_values = {
        code: _as_float(decoded_periods.get(code))
        for code in period_codes
    }
    final_values = {
        code: _as_float(final_values_decimal.get(code))
        for code in period_codes
    }

    return AssessmentCalculationResult(
        current_average=_as_float(current_avg),
        final_average=_as_float(final_avg),
        is_final=is_final,
        original_values=original_values,
        final_values=final_values,
        period_weights={
            period.code: float(Decimal(str(period.weight)))
            for period in policy.assessment.periods
        },
        recoveries_applied=tuple(
            _serialize_application(item)
            for item in recovery_execution.applications
        ),
        current_numerator=_as_float(current_num),
        current_divisor=_as_float(current_div),
        final_numerator=_as_float(final_num),
        final_divisor=_as_float(final_div),
        raw_period_results=raw_period_results,
        raw_recovery_results=raw_recovery_results,
        policy_id=policy.id,
        policy_key=policy.policy_key,
        policy_version=policy.version,
        policy_status=policy.status.value,
        rule_hash=rule_hash,
    )
