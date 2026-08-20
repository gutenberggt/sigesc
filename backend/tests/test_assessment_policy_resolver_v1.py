"""Testes puros do Policy Resolver Multi-Mantenedora v1."""

from datetime import date

import pytest

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    POLICY_AMBIGUOUS,
    POLICY_INTEGRITY_ERROR,
    POLICY_REQUIRED,
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
from assessment_policy.resolver import (
    AssessmentPolicyContext,
    AssessmentPolicyResolver,
    policy_specificity,
    resolve_policy_from_candidates,
    scope_matches_context,
)


def _policy(
    policy_id: str,
    *,
    tenant: str = "tenant-a",
    year: int = 2026,
    scope: PolicyScope | None = None,
    effective_from: date = date(2026, 1, 1),
    effective_until: date = date(2026, 12, 31),
) -> AssessmentPolicy:
    policy = AssessmentPolicy(
        id=policy_id,
        policy_key=policy_id.upper(),
        version=1,
        mantenedora_id=tenant,
        name=policy_id,
        status=PolicyStatus.PUBLISHED,
        academic_year=year,
        effective_from=effective_from,
        effective_until=effective_until,
        scope=scope or PolicyScope(),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10, decimal_places=1),
            periods=[PeriodRule(code="b1", label="1º Bimestre", weight=1)],
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        ),
    )
    return policy.model_copy(update={"rule_hash": calculate_rule_hash(policy)})


def _context(**updates) -> AssessmentPolicyContext:
    values = {
        "mantenedora_id": "tenant-a",
        "school_id": "school-1",
        "class_id": "class-1",
        "student_id": "student-1",
        "component_id": "math",
        "academic_year": 2026,
        "reference_date": date(2026, 8, 19),
        "student_series": "1º ANO",
        "education_stage": "fundamental_anos_iniciais",
        "modality": "regular",
    }
    values.update(updates)
    return AssessmentPolicyContext(**values)


def test_scope_matching_normalizes_textual_dimensions_but_not_ids():
    scope = PolicyScope(
        school_ids=["school-1"],
        series=["1° ano"],
        education_stages=["Fundamental Anos Iniciais"],
        modalities=["REGULAR"],
    )
    assert scope_matches_context(scope, _context()) is True
    assert scope_matches_context(scope, _context(school_id="SCHOOL-1")) is False


def test_series_specific_policy_overrides_general_tenant_policy():
    general = _policy("general")
    first_second = _policy(
        "first-second",
        scope=PolicyScope(series=["1º ANO", "2º ANO"]),
    )

    resolved = resolve_policy_from_candidates(_context(), [general, first_second])

    assert resolved.policy.id == "first-second"
    assert resolved.specificity == policy_specificity(first_second.scope)


def test_class_component_policy_has_highest_administrative_precedence():
    school = _policy("school", scope=PolicyScope(school_ids=["school-1"]))
    class_only = _policy("class", scope=PolicyScope(class_ids=["class-1"]))
    exact = _policy(
        "exact",
        scope=PolicyScope(class_ids=["class-1"], component_ids=["math"]),
    )

    resolved = resolve_policy_from_candidates(_context(), [school, class_only, exact])
    assert resolved.policy.id == "exact"


def test_contextual_restriction_breaks_tie_inside_same_admin_tier():
    school_general = _policy(
        "school-general",
        scope=PolicyScope(school_ids=["school-1"]),
    )
    school_series = _policy(
        "school-series",
        scope=PolicyScope(school_ids=["school-1"], series=["1º ANO"]),
    )

    resolved = resolve_policy_from_candidates(
        _context(),
        [school_general, school_series],
    )
    assert resolved.policy.id == "school-series"


def test_equal_specificity_overlap_is_ambiguous_fail_closed():
    left = _policy(
        "left",
        scope=PolicyScope(school_ids=["school-1"], series=["1º ANO"]),
    )
    right = _policy(
        "right",
        scope=PolicyScope(school_ids=["school-1"], modalities=["regular"]),
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_policy_from_candidates(_context(), [left, right])

    assert exc.value.code == POLICY_AMBIGUOUS
    assert exc.value.details["policy_ids"] == ["left", "right"]


def test_cross_tenant_year_and_out_of_effective_period_are_never_candidates():
    candidates = [
        _policy("other-tenant", tenant="tenant-b"),
        _policy(
            "expired",
            effective_from=date(2026, 1, 1),
            effective_until=date(2026, 6, 30),
        ),
        _policy(
            "other-year",
            year=2025,
            effective_from=date(2025, 1, 1),
            effective_until=date(2025, 12, 31),
        ),
    ]

    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_policy_from_candidates(_context(), candidates)

    assert exc.value.code == POLICY_REQUIRED


def test_component_scoped_policy_requires_component_in_context():
    policy = _policy("component", scope=PolicyScope(component_ids=["math"]))

    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_policy_from_candidates(_context(component_id=None), [policy])

    assert exc.value.code == POLICY_REQUIRED


def test_published_policy_hash_is_verified_before_resolution():
    policy = _policy("tampered").model_copy(update={"rule_hash": "sha256:deadbeef"})

    with pytest.raises(AssessmentPolicyError) as exc:
        resolve_policy_from_candidates(_context(), [policy])

    assert exc.value.code == POLICY_INTEGRITY_ERROR


class FakeRepository:
    def __init__(self, policies):
        self.policies = policies
        self.call = None

    async def list_published_candidates(self, mantenedora_id, *, academic_year, reference_date):
        self.call = (mantenedora_id, academic_year, reference_date)
        return self.policies


@pytest.mark.asyncio
async def test_service_queries_repository_with_tenant_year_and_date_only():
    policy = _policy("general")
    repo = FakeRepository([policy])
    context = _context()

    resolved = await AssessmentPolicyResolver(repo).resolve(context)

    assert resolved.policy.id == "general"
    assert repo.call == ("tenant-a", 2026, date(2026, 8, 19))
