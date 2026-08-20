"""Testes do Recovery Engine da Assessment Policy v1."""

from datetime import date
from decimal import Decimal

import pytest

from assessment_policy.calculator import calculate_assessment
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    CALCULATION_POLICY_INVALID,
    RECOVERY_NO_ELIGIBLE_PERIOD,
    RECOVERY_NOT_ENABLED,
    RECOVERY_RULE_INCOMPLETE,
    RECOVERY_TIE_UNRESOLVED,
    RECOVERY_UNKNOWN_INPUT,
)
from assessment_policy.models import (
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    CalculationRule,
    CalculationStrategy,
    ConceptScaleEntry,
    NumericScale,
    PeriodRule,
    RecoveryGroup,
    RecoveryRule,
    RecoveryTieBreak,
)
from assessment_policy.recovery import apply_recoveries
from assessment_policy.validator import validate_policy


def _periods(*, equal_weights=False):
    return [
        PeriodRule(code="b1", label="B1", weight=1 if equal_weights else 2),
        PeriodRule(code="b2", label="B2", weight=1 if equal_weights else 3),
        PeriodRule(code="b3", label="B3", weight=1 if equal_weights else 2),
        PeriodRule(code="b4", label="B4", weight=1 if equal_weights else 3),
    ]


def _policy(
    *,
    enabled=True,
    tie_break=RecoveryTieBreak.HIGHEST_WEIGHT,
    only_if_improves=True,
    equal_weights=False,
    groups=None,
    conceptual=False,
):
    if groups is None:
        groups = [
            RecoveryGroup(
                code="r1",
                label="Recuperação 1",
                input_code="rec_s1",
                period_codes=["b1", "b2"],
                tie_break=tie_break,
                only_if_improves=only_if_improves,
            ),
            RecoveryGroup(
                code="r2",
                label="Recuperação 2",
                input_code="rec_s2",
                period_codes=["b3", "b4"],
                tie_break=tie_break,
                only_if_improves=only_if_improves,
            ),
        ]

    if conceptual:
        assessment = AssessmentRule(
            mode=AssessmentMode.CONCEPTUAL,
            conceptual_scale=[
                ConceptScaleEntry(code="C", label="Consolidado", numeric_value=10),
                ConceptScaleEntry(code="ED", label="Em Desenvolvimento", numeric_value=7.5),
                ConceptScaleEntry(code="ND", label="Não Desenvolvido", numeric_value=5),
            ],
            periods=_periods(equal_weights=equal_weights),
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        )
    else:
        assessment = AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10),
            periods=_periods(equal_weights=equal_weights),
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        )

    return AssessmentPolicy(
        id="policy-recovery",
        policy_key="RECOVERY",
        version=1,
        mantenedora_id="tenant-a",
        name="Política com Recuperação",
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        assessment=assessment,
        recovery=RecoveryRule(enabled=enabled, groups=groups),
    )


def test_highest_weight_breaks_equal_grade_tie_toward_b2():
    result = calculate_assessment(
        _policy(),
        {"b1": 5, "b2": 5, "b3": 8, "b4": 8},
        {"rec_s1": 10},
    )

    assert result.final_values["b1"] == 5.0
    assert result.final_values["b2"] == 10.0
    application = result.recoveries_applied[0]
    assert application["target_period"] == "b2"
    assert application["applied"] is True
    assert result.final_average == 8.0


def test_highest_weight_fails_if_equal_grade_and_equal_weight_remain_tied():
    policy = _policy(equal_weights=True)

    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(
            policy,
            {"b1": 5, "b2": 5},
            {"rec_s1": 10},
        )

    assert exc.value.code == RECOVERY_TIE_UNRESOLVED
    assert exc.value.details["candidate_periods"] == ["b1", "b2"]


def test_earliest_and_latest_period_tie_breaks_are_deterministic():
    earliest = _policy(
        tie_break=RecoveryTieBreak.EARLIEST_PERIOD,
        equal_weights=True,
    )
    early_result = calculate_assessment(
        earliest,
        {"b1": 5, "b2": 5},
        {"rec_s1": 8},
    )
    assert early_result.recoveries_applied[0]["target_period"] == "b1"

    latest = _policy(
        tie_break=RecoveryTieBreak.LATEST_PERIOD,
        equal_weights=True,
    )
    late_result = calculate_assessment(
        latest,
        {"b1": 5, "b2": 5},
        {"rec_s1": 8},
    )
    assert late_result.recoveries_applied[0]["target_period"] == "b2"


def test_only_if_improves_true_never_reduces_original_result():
    result = calculate_assessment(
        _policy(only_if_improves=True),
        {"b1": 7, "b2": 8},
        {"rec_s1": 6},
    )

    assert result.final_values["b1"] == 7.0
    application = result.recoveries_applied[0]
    assert application["applied"] is False
    assert application["reason"] == "not_improved"
    assert application["before_value"] == 7.0
    assert application["after_value"] == 7.0


def test_only_if_improves_false_replaces_even_with_lower_recovery():
    result = calculate_assessment(
        _policy(only_if_improves=False),
        {"b1": 7, "b2": 8},
        {"rec_s1": 6},
    )

    assert result.final_values["b1"] == 6.0
    assert result.recoveries_applied[0]["applied"] is True


def test_recovery_input_requires_at_least_one_graded_target_period():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(
            _policy(),
            {"b3": 8},
            {"rec_s1": 9},
        )

    assert exc.value.code == RECOVERY_NO_ELIGIBLE_PERIOD


def test_recovery_input_fails_when_recovery_is_disabled():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(
            _policy(enabled=False, groups=[]),
            {"b1": 5},
            {"rec_s1": 8},
        )

    assert exc.value.code == RECOVERY_NOT_ENABLED


def test_direct_recovery_engine_reports_not_enabled_explicitly():
    with pytest.raises(AssessmentPolicyError) as exc:
        apply_recoveries(
            _policy(enabled=False, groups=[]),
            {"b1": Decimal("5")},
            {"rec_s1": Decimal("8")},
        )
    assert exc.value.code == RECOVERY_NOT_ENABLED


def test_unknown_recovery_input_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(
            _policy(),
            {"b1": 5},
            {"rec_unknown": 8},
        )
    assert exc.value.code == RECOVERY_UNKNOWN_INPUT


def test_none_unknown_recovery_input_is_ignored():
    result = calculate_assessment(
        _policy(),
        {"b1": 5},
        {"rec_unknown": None},
    )
    assert result.current_average == 5.0
    assert result.recoveries_applied == ()


def test_recovery_rule_must_define_only_if_improves_when_input_is_used():
    policy = _policy(only_if_improves=None)

    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(
            policy,
            {"b1": 5, "b2": 7},
            {"rec_s1": 8},
        )
    assert exc.value.code == RECOVERY_RULE_INCOMPLETE


def test_conceptual_recovery_uses_same_policy_scale_as_period_results():
    result = calculate_assessment(
        _policy(conceptual=True),
        {"b1": "ND", "b2": "ED", "b3": "ED", "b4": "C"},
        {"rec_s1": "C"},
    )

    assert result.original_values["b1"] == 5.0
    assert result.final_values["b1"] == 10.0
    assert result.recoveries_applied[0]["input_value"] == 10.0


def test_two_disjoint_recovery_groups_apply_without_order_dependency():
    result = calculate_assessment(
        _policy(),
        {"b1": 5, "b2": 6, "b3": 4, "b4": 8},
        {"rec_s1": 7, "rec_s2": 9},
    )

    assert result.final_values == {
        "b1": 7.0,
        "b2": 6.0,
        "b3": 9.0,
        "b4": 8.0,
    }
    assert [item["target_period"] for item in result.recoveries_applied] == ["b1", "b3"]


def test_overlapping_recovery_groups_are_invalid_policy_in_v1():
    groups = [
        RecoveryGroup(
            code="r1",
            label="R1",
            input_code="rec1",
            period_codes=["b1", "b2"],
            only_if_improves=True,
        ),
        RecoveryGroup(
            code="r2",
            label="R2",
            input_code="rec2",
            period_codes=["b2", "b3"],
            only_if_improves=True,
        ),
    ]
    policy = _policy(groups=groups)
    report = validate_policy(policy)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_RECOVERY_PERIOD_OVERLAP"
        for issue in report.issues
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_assessment(policy, {"b1": 5, "b2": 6, "b3": 7})
    assert exc.value.code == CALCULATION_POLICY_INVALID
