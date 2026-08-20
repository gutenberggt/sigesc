"""Testes do Conflict Checker alinhado ao Policy Resolver."""

from datetime import date

import pytest

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.conflict_checker import (
    AssessmentPolicyConflictChecker,
    policies_conflict_for_resolution,
    scopes_overlap,
)
from assessment_policy.models import (
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    CalculationRule,
    CalculationStrategy,
    NumericScale,
    PeriodRule,
    PolicyScope,
    PolicyStatus,
)


def _policy(
    policy_id: str,
    *,
    tenant: str = "tenant-a",
    scope: PolicyScope | None = None,
    start: date = date(2026, 1, 1),
    end: date = date(2026, 12, 31),
    status: PolicyStatus = PolicyStatus.PUBLISHED,
) -> AssessmentPolicy:
    p = AssessmentPolicy(
        id=policy_id,
        policy_key=policy_id.upper(),
        version=1,
        mantenedora_id=tenant,
        name=policy_id,
        status=status,
        academic_year=2026,
        effective_from=start,
        effective_until=end,
        scope=scope or PolicyScope(),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10),
            periods=[PeriodRule(code="b1", label="B1", weight=1)],
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        ),
    )
    return p.model_copy(update={"rule_hash": calculate_rule_hash(p)})


def test_scope_overlap_supports_general_against_specific():
    assert scopes_overlap(PolicyScope(), PolicyScope(series=["1º ANO"])) is True


def test_scope_overlap_normalizes_text_series():
    assert scopes_overlap(
        PolicyScope(series=["1º ANO"]),
        PolicyScope(series=["1° ano"]),
    ) is True


def test_disjoint_series_do_not_overlap():
    assert scopes_overlap(
        PolicyScope(series=["1º ANO"]),
        PolicyScope(series=["2º ANO"]),
    ) is False


def test_equal_specificity_and_overlap_is_publish_conflict():
    left = _policy(
        "left",
        scope=PolicyScope(school_ids=["school-1"], series=["1º ANO"]),
    )
    right = _policy(
        "right",
        scope=PolicyScope(school_ids=["school-1"], modalities=["regular"]),
    )
    assert policies_conflict_for_resolution(left, right) is True


def test_more_specific_override_is_allowed():
    general = _policy("general", scope=PolicyScope(school_ids=["school-1"]))
    override = _policy(
        "override",
        scope=PolicyScope(school_ids=["school-1"], series=["1º ANO"]),
    )
    assert policies_conflict_for_resolution(override, general) is False


def test_disjoint_effective_periods_are_allowed():
    first = _policy("first", end=date(2026, 6, 30))
    second = _policy("second", start=date(2026, 7, 1))
    assert policies_conflict_for_resolution(second, first) is False


def test_cross_tenant_never_conflicts():
    left = _policy("left", tenant="tenant-a")
    right = _policy("right", tenant="tenant-b")
    assert policies_conflict_for_resolution(left, right) is False


class FakeRepository:
    def __init__(self, policies):
        self.policies = policies
        self.call = None

    async def list_by_tenant(self, mantenedora_id, *, academic_year=None, statuses=None):
        self.call = (mantenedora_id, academic_year, tuple(statuses or []))
        return self.policies


@pytest.mark.asyncio
async def test_checker_returns_only_real_ambiguity_ids():
    candidate = _policy(
        "candidate",
        scope=PolicyScope(school_ids=["school-1"], series=["1º ANO"]),
        status=PolicyStatus.VALIDATED,
    )
    ambiguous = _policy(
        "ambiguous",
        scope=PolicyScope(school_ids=["school-1"], modalities=["regular"]),
    )
    lower_specificity = _policy(
        "general",
        scope=PolicyScope(school_ids=["school-1"]),
    )
    disjoint = _policy(
        "disjoint",
        scope=PolicyScope(school_ids=["school-2"], series=["1º ANO"]),
    )
    repo = FakeRepository([ambiguous, lower_specificity, disjoint])

    conflicts = await AssessmentPolicyConflictChecker(repo).find_publish_conflicts(candidate)

    assert conflicts == ("ambiguous",)
    assert repo.call[0] == "tenant-a"
    assert repo.call[1] == 2026
    assert repo.call[2] == (PolicyStatus.PUBLISHED,)
