"""Testes do Calculator determinístico da Assessment Policy v1."""

from datetime import date
from decimal import Decimal

import pytest

from assessment_policy.calculator import calculate_assessment
from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    CALCULATION_MODE_UNSUPPORTED,
    CALCULATION_POLICY_INVALID,
    CALCULATION_UNKNOWN_CONCEPT,
    CALCULATION_UNKNOWN_PERIOD,
    CALCULATION_VALUE_INVALID,
    CALCULATION_VALUE_OUT_OF_SCALE,
    POLICY_INTEGRITY_ERROR,
)
from assessment_policy.models import (
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    CalculationRule,
    CalculationStrategy,
    ConceptScaleEntry,
    NumericScale,
    PartialDivisorStrategy,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
)


def _periods(*, optional_b4=False, equal_weights=False):
    return [
        PeriodRule(code="b1", label="B1", weight=1 if equal_weights else 2),
        PeriodRule(code="b2", label="B2", weight=1 if equal_weights else 3),
        PeriodRule(code="b3", label="B3", weight=1 if equal_weights else 2),
        PeriodRule(
            code="b4",
            label="B4",
            weight=1 if equal_weights else 3,
            required_for_final=not optional_b4,
        ),
    ]


def _numeric_policy(
    *,
    strategy=CalculationStrategy.WEIGHTED_AVERAGE,
    partial_divisor=PartialDivisorStrategy.SUM_AVAILABLE_WEIGHTS,
    decimal_places=2,
    optional_b4=False,
    status=PolicyStatus.DRAFT,
):
    policy = AssessmentPolicy(
        id="policy-numeric",
        policy_key="NUMERIC",
        version=1,
        mantenedora_id="tenant-a",
        name="Política Numérica",
        status=status,
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        scope=PolicyScope(),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10, decimal_places=2),
            periods=_periods(optional_b4=optional_b4),
            calculation=CalculationRule(
                strategy=strategy,
                partial_divisor=partial_divisor,
                decimal_places=decimal_places,
            ),
        ),
    )
    if status == PolicyStatus.PUBLISHED:
        policy = policy.model_copy(update={"rule_hash": calculate_rule_hash(policy)})
    return policy


def _conceptual_policy(*, status=PolicyStatus.DRAFT):
    policy = AssessmentPolicy(
        id="policy-conceptual",
        policy_key="CONCEPTUAL",
        version=1,
        mantenedora_id="tenant-a",
        name="Política Conceitual",
        status=status,
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        assessment=AssessmentRule(
            mode=AssessmentMode.CONCEPTUAL,
            conceptual_scale=[
                ConceptScaleEntry(code="C", label="Consolidado", numeric_value=10),
                ConceptScaleEntry(code="ED", label="Em Desenvolvimento", numeric_value=7.5),
                ConceptScaleEntry(code="ND", label="Não Desenvolvido", numeric_value=5),
            ],
            periods=_periods(),
            calculation=CalculationRule(
                strategy=CalculationStrategy.WEIGHTED_AVERAGE,
                partial_divisor=PartialDivisorStrategy.SUM_AVAILABLE_WEIGHTS,
                decimal_places=2,
            ),
        ),
    )
    if status == PolicyStatus.PUBLISHED:
        policy = policy.model_copy(update={"rule_hash": calculate_rule_hash(policy)})
    return policy


def test_weighted_partial_average_uses_only_available_weights_by_default():
    result = calculate_assessment(
        _numeric_policy(),
        {"b1": 5, "b2": 7.5, "b3": None, "b4": None},
    )

    assert result.current_average == 6.5
    assert result.current_numerator == 32.5
    assert result.current_divisor == 5.0
    assert result.final_average is None
    assert result.is_final is False


def test_missing_periods_are_preserved_as_missing_and_never_become_zero():
    result = calculate_assessment(_numeric_policy(), {"b1": 8})

    assert result.original_values == {
        "b1": 8.0,
        "b2": None,
        "b3": None,
        "b4": None,
    }
    assert result.current_average == 8.0
    assert result.final_average is None


def test_partial_sum_all_weights_can_explicitly_penalize_missing_required_periods():
    result = calculate_assessment(
        _numeric_policy(partial_divisor=PartialDivisorStrategy.SUM_ALL_WEIGHTS),
        {"b1": 10},
    )

    assert result.current_numerator == 20.0
    assert result.current_divisor == 10.0
    assert result.current_average == 2.0
    assert result.is_final is False


def test_final_weighted_average_uses_policy_weights():
    result = calculate_assessment(
        _numeric_policy(),
        {"b1": 5, "b2": 7.5, "b3": 5, "b4": 7.5},
    )

    assert result.is_final is True
    assert result.final_numerator == 65.0
    assert result.final_divisor == 10.0
    assert result.final_average == 6.5


def test_optional_absent_period_does_not_penalize_final_average():
    result = calculate_assessment(
        _numeric_policy(optional_b4=True),
        {"b1": 5, "b2": 7.5, "b3": 5},
    )

    assert result.is_final is True
    assert result.final_numerator == 42.5
    assert result.final_divisor == 7.0
    assert result.final_average == 6.07
    assert result.final_values["b4"] is None


def test_simple_average_ignores_period_weights_for_formula():
    result = calculate_assessment(
        _numeric_policy(strategy=CalculationStrategy.SIMPLE_AVERAGE),
        {"b1": 4, "b2": 10},
    )

    assert result.current_numerator == 14.0
    assert result.current_divisor == 2.0
    assert result.current_average == 7.0


def test_rounding_is_decimal_half_up_not_binary_round():
    policy = _numeric_policy(
        strategy=CalculationStrategy.SIMPLE_AVERAGE,
        decimal_places=2,
    )
    result = calculate_assessment(
        policy,
        {"b1": Decimal("2.67"), "b2": Decimal("2.68")},
    )

    assert result.current_average == 2.68


def test_empty_results_produce_no_average_instead_of_zero():
    result = calculate_assessment(
        _numeric_policy(),
        {"b1": None, "b2": None, "b3": None, "b4": None},
    )

    assert result.current_average is None
    assert result.current_numerator is None
    assert result.current_divisor is None
    assert result.final_average is None
    assert result.is_final is False


def test_conceptual_codes_are_converted_only_by_policy_scale():
    result = calculate_assessment(
        _conceptual_policy(),
        {"b1": "ED", "b2": "C", "b3": "ND", "b4": "ED"},
    )

    assert result.original_values == {
        "b1": 7.5,
        "b2": 10.0,
        "b3": 5.0,
        "b4": 7.5,
    }
    assert result.final_numerator == 77.5
    assert result.final_average == 7.75


def test_conceptual_numeric_compatibility_requires_exact_configured_value():
    result = calculate_assessment(_conceptual_policy(), {"b1": 7.5})
    assert result.current_average == 7.5

    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(_conceptual_policy(), {"b1": 8.0})
    assert exc.value.code == CALCULATION_VALUE_OUT_OF_SCALE


def test_unknown_concept_fails_closed_and_is_case_sensitive_after_trim():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(_conceptual_policy(), {"b1": " c "})

    assert exc.value.code == CALCULATION_UNKNOWN_CONCEPT
    assert exc.value.details["allowed_codes"] == ["C", "ED", "ND"]


def test_numeric_value_outside_policy_scale_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(_numeric_policy(), {"b1": 11})

    assert exc.value.code == CALCULATION_VALUE_OUT_OF_SCALE


def test_numeric_string_and_boolean_are_not_silently_coerced():
    with pytest.raises(AssessmentPolicyError) as string_exc:
        calculate_assessment(_numeric_policy(), {"b1": "7.5"})
    assert string_exc.value.code == CALCULATION_VALUE_INVALID

    with pytest.raises(AssessmentPolicyError) as bool_exc:
        calculate_assessment(_numeric_policy(), {"b1": True})
    assert bool_exc.value.code == CALCULATION_VALUE_INVALID


def test_unknown_period_with_value_fails_but_unknown_none_is_ignored():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(_numeric_policy(), {"b1": 7, "b9": 8})
    assert exc.value.code == CALCULATION_UNKNOWN_PERIOD

    result = calculate_assessment(_numeric_policy(), {"b1": 7, "b9": None})
    assert result.current_average == 7.0


def test_descriptive_and_skill_based_are_not_numeric_calculator_modes():
    for mode in (AssessmentMode.DESCRIPTIVE, AssessmentMode.SKILL_BASED):
        policy = AssessmentPolicy(
            id=f"policy-{mode.value}",
            policy_key=mode.value,
            version=1,
            mantenedora_id="tenant-a",
            name=mode.value,
            academic_year=2026,
            effective_from=date(2026, 1, 1),
            effective_until=date(2026, 12, 31),
            assessment=AssessmentRule(mode=mode),
        )
        with pytest.raises(AssessmentPolicyError) as exc:
            calculate_assessment(policy, {})
        assert exc.value.code == CALCULATION_MODE_UNSUPPORTED


def test_published_policy_requires_valid_rule_hash_defense_in_depth():
    valid = _numeric_policy(status=PolicyStatus.PUBLISHED)
    result = calculate_assessment(valid, {"b1": 7})
    assert result.rule_hash == valid.rule_hash

    tampered = valid.model_copy(update={"name": "Nome administrativo alterado"})
    # name não integra o hash da regra; continua íntegro.
    assert calculate_assessment(tampered, {"b1": 7}).rule_hash == valid.rule_hash

    broken = valid.model_copy(
        update={
            "assessment": valid.assessment.model_copy(
                update={
                    "periods": [
                        period.model_copy(update={"weight": period.weight + 1})
                        if period.code == "b1"
                        else period
                        for period in valid.assessment.periods
                    ]
                }
            )
        }
    )
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(broken, {"b1": 7})
    assert exc.value.code in {POLICY_INTEGRITY_ERROR, CALCULATION_POLICY_INVALID}


def test_result_contains_policy_provenance_and_raw_inputs():
    policy = _numeric_policy()
    result = calculate_assessment(policy, {"b1": 7.5})

    assert result.policy_id == policy.id
    assert result.policy_key == policy.policy_key
    assert result.policy_version == 1
    assert result.policy_status == "draft"
    assert result.rule_hash == calculate_rule_hash(policy)
    assert result.raw_period_results == {"b1": 7.5}
