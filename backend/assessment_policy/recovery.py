"""Recovery Engine puro da Assessment Policy v1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from .exceptions import (
    AssessmentPolicyError,
    RECOVERY_NO_ELIGIBLE_PERIOD,
    RECOVERY_NOT_ENABLED,
    RECOVERY_RULE_INCOMPLETE,
    RECOVERY_TIE_UNRESOLVED,
    RECOVERY_UNKNOWN_INPUT,
)
from .models import AssessmentPolicy, RecoveryStrategy, RecoveryTieBreak


@dataclass(frozen=True)
class RecoveryApplication:
    group_code: str
    input_code: str
    input_value: Decimal
    target_period: str
    before_value: Decimal
    after_value: Decimal
    applied: bool
    reason: str
    tie_break: RecoveryTieBreak


@dataclass(frozen=True)
class RecoveryExecutionResult:
    values: dict[str, Decimal]
    applications: tuple[RecoveryApplication, ...]


def _period_order(policy: AssessmentPolicy) -> dict[str, int]:
    return {
        period.code: index
        for index, period in enumerate(policy.assessment.periods)
    }


def _period_weights(policy: AssessmentPolicy) -> dict[str, Decimal]:
    return {
        period.code: Decimal(str(period.weight))
        for period in policy.assessment.periods
    }


def _resolve_lowest_target(
    policy: AssessmentPolicy,
    *,
    period_values: Mapping[str, Decimal],
    period_codes: list[str],
    tie_break: RecoveryTieBreak,
) -> str:
    eligible = [code for code in period_codes if code in period_values]
    if not eligible:
        raise AssessmentPolicyError(
            RECOVERY_NO_ELIGIBLE_PERIOD,
            "Recuperação informada não possui período lançado elegível para substituição.",
            details={"period_codes": list(period_codes)},
        )

    lowest = min(period_values[code] for code in eligible)
    candidates = [code for code in eligible if period_values[code] == lowest]
    if len(candidates) == 1:
        return candidates[0]

    order = _period_order(policy)
    if tie_break == RecoveryTieBreak.HIGHEST_WEIGHT:
        weights = _period_weights(policy)
        highest = max(weights[code] for code in candidates)
        candidates = [code for code in candidates if weights[code] == highest]
    elif tie_break == RecoveryTieBreak.EARLIEST_PERIOD:
        earliest = min(order[code] for code in candidates)
        candidates = [code for code in candidates if order[code] == earliest]
    elif tie_break == RecoveryTieBreak.LATEST_PERIOD:
        latest = max(order[code] for code in candidates)
        candidates = [code for code in candidates if order[code] == latest]

    if len(candidates) != 1:
        raise AssessmentPolicyError(
            RECOVERY_TIE_UNRESOLVED,
            "A estratégia de desempate da recuperação não determinou um único período.",
            details={
                "tie_break": tie_break.value,
                "candidate_periods": sorted(candidates),
            },
        )
    return candidates[0]


def apply_recoveries(
    policy: AssessmentPolicy,
    period_values: Mapping[str, Decimal],
    recovery_values: Mapping[str, Decimal] | None = None,
) -> RecoveryExecutionResult:
    """Aplica recuperações decodificadas sem efeitos colaterais.

    `period_values` e `recovery_values` já devem estar na escala numérica efetiva
    da política. Conversão de conceitos/validação de escala pertence ao
    Calculator, mantendo esta função focada apenas na regra de substituição.
    """

    supplied = dict(recovery_values or {})
    values = dict(period_values)
    if not supplied:
        return RecoveryExecutionResult(values=values, applications=())

    if not policy.recovery.enabled:
        raise AssessmentPolicyError(
            RECOVERY_NOT_ENABLED,
            "Foram informadas recuperações para uma política que não habilita recuperação.",
            details={"input_codes": sorted(supplied)},
        )

    groups_by_input = {group.input_code: group for group in policy.recovery.groups}
    unknown = sorted(set(supplied) - set(groups_by_input))
    if unknown:
        raise AssessmentPolicyError(
            RECOVERY_UNKNOWN_INPUT,
            "Entrada de recuperação não existe na política.",
            details={"input_codes": unknown},
        )

    applications: list[RecoveryApplication] = []
    for group in policy.recovery.groups:
        if group.input_code not in supplied:
            continue

        if group.strategy != RecoveryStrategy.REPLACE_LOWEST:
            raise AssessmentPolicyError(
                RECOVERY_RULE_INCOMPLETE,
                "Estratégia de recuperação não é executável pelo Recovery Engine v1.",
                details={
                    "group_code": group.code,
                    "strategy": group.strategy.value,
                },
            )
        if group.only_if_improves is None:
            raise AssessmentPolicyError(
                RECOVERY_RULE_INCOMPLETE,
                "A política deve declarar se a recuperação só substitui quando melhora o resultado.",
                details={
                    "group_code": group.code,
                    "input_code": group.input_code,
                },
            )

        target = _resolve_lowest_target(
            policy,
            period_values=values,
            period_codes=group.period_codes,
            tie_break=group.tie_break,
        )
        before = values[target]
        recovery_value = supplied[group.input_code]
        should_apply = (not group.only_if_improves) or recovery_value > before
        after = recovery_value if should_apply else before
        if should_apply:
            values[target] = recovery_value

        applications.append(
            RecoveryApplication(
                group_code=group.code,
                input_code=group.input_code,
                input_value=recovery_value,
                target_period=target,
                before_value=before,
                after_value=after,
                applied=should_apply,
                reason="applied" if should_apply else "not_improved",
                tie_break=group.tie_break,
            )
        )

    return RecoveryExecutionResult(
        values=values,
        applications=tuple(applications),
    )
