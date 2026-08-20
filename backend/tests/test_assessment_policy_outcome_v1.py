"""Testes do Academic Outcome Engine Multi-Mantenedora v1."""

from datetime import date

import pytest

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    OUTCOME_ATTENDANCE_INVALID,
    OUTCOME_DUPLICATE_COMPONENT,
    OUTCOME_POLICY_INVALID,
    OUTCOME_VALUE_INVALID,
    POLICY_INTEGRITY_ERROR,
)
from assessment_policy.models import (
    AcademicOutcomeRule,
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    AttendanceBasis,
    CalculationRule,
    CalculationStrategy,
    CouncilRule,
    DependencyMode,
    DependencyOutcomeRange,
    DependencyRule,
    NormativeSource,
    NumericScale,
    PeriodRule,
    PolicyStatus,
)
from assessment_policy.outcome import (
    AcademicOutcomeStatus,
    AttendanceEvidence,
    ComponentOutcomeInput,
    calculate_academic_outcome,
)
from assessment_policy.validator import validate_policy


def _policy(
    *,
    minimum_average=5.0,
    minimum_attendance=75.0,
    attendance_basis=AttendanceBasis.GLOBAL,
    require_all_components=True,
    dependency=None,
    council=None,
    status=PolicyStatus.DRAFT,
):
    policy = AssessmentPolicy(
        id="policy-outcome",
        policy_key="OUTCOME",
        version=1,
        mantenedora_id="tenant-a",
        name="Política de Resultado",
        status=status,
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10),
            periods=[PeriodRule(code="b1", label="B1", weight=1)],
            calculation=CalculationRule(strategy=CalculationStrategy.WEIGHTED_AVERAGE),
        ),
        academic_outcome=AcademicOutcomeRule(
            minimum_component_average=minimum_average,
            require_all_components=require_all_components,
            minimum_attendance_percentage=minimum_attendance,
            attendance_basis=(attendance_basis if minimum_attendance is not None else None),
            dependency=dependency or DependencyRule(),
            council=council or CouncilRule(),
        ),
        normative_sources=[
            NormativeSource(type="internal_policy", title="Política formal de teste")
        ],
    )
    if status in {
        PolicyStatus.VALIDATED,
        PolicyStatus.PUBLISHED,
        PolicyStatus.SUPERSEDED,
        PolicyStatus.RETIRED,
    }:
        policy = policy.model_copy(update={"rule_hash": calculate_rule_hash(policy)})
    return policy


def _component(
    component_id,
    average=7.0,
    *,
    is_final=True,
    required=True,
    counts=True,
):
    return ComponentOutcomeInput(
        component_id=component_id,
        final_average=average,
        is_final=is_final,
        required=required,
        counts_for_outcome=counts,
    )


def test_approved_when_all_components_and_global_attendance_meet_policy():
    result = calculate_academic_outcome(
        _policy(),
        [_component("math", 5.0), _component("port", 7.5)],
        AttendanceEvidence(global_percentage=75.0),
    )

    assert result.status == AcademicOutcomeStatus.APPROVED
    assert result.failed_component_ids == ()
    assert result.attendance_failed is False
    assert result.attendance_complete is True
    assert result.reason_codes == ("ALL_POLICY_REQUIREMENTS_MET",)


def test_required_component_without_final_result_keeps_in_progress():
    result = calculate_academic_outcome(
        _policy(),
        [_component("math", None, is_final=False), _component("port", 8)],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.IN_PROGRESS
    assert result.incomplete_component_ids == ("math",)
    assert "COMPONENT_DATA_INCOMPLETE" in result.reason_codes


def test_no_evaluative_component_with_component_threshold_is_in_progress():
    result = calculate_academic_outcome(
        _policy(),
        [_component("aee", None, is_final=False, counts=False)],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.IN_PROGRESS
    assert result.incomplete_component_ids == ("__NO_EVALUATIVE_COMPONENTS__",)


def test_optional_component_without_result_does_not_block_closure():
    result = calculate_academic_outcome(
        _policy(),
        [
            _component("math", 7),
            _component("optional", None, is_final=False, required=False),
        ],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.APPROVED
    assert result.incomplete_component_ids == ()


def test_optional_component_with_final_result_counts_when_enabled_for_outcome():
    result = calculate_academic_outcome(
        _policy(),
        [
            _component("math", 7),
            _component("optional", 4, required=False),
        ],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_COMPONENT
    assert result.failed_component_ids == ("optional",)


def test_component_marked_out_of_outcome_never_changes_result():
    result = calculate_academic_outcome(
        _policy(),
        [
            _component("math", 7),
            _component("formative", 0, counts=False),
        ],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.APPROVED
    assert result.failed_component_ids == ()


def test_missing_required_global_attendance_keeps_in_progress():
    result = calculate_academic_outcome(
        _policy(),
        [_component("math", 7)],
        AttendanceEvidence(),
    )

    assert result.status == AcademicOutcomeStatus.IN_PROGRESS
    assert result.attendance_complete is False
    assert "ATTENDANCE_DATA_INCOMPLETE" in result.reason_codes


def test_global_attendance_below_threshold_not_approved():
    result = calculate_academic_outcome(
        _policy(),
        [_component("math", 8)],
        AttendanceEvidence(global_percentage=74.99),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_ATTENDANCE
    assert result.attendance_failed is True
    assert result.dependency_mode is None


def test_stage_attendance_basis_uses_stage_evidence_only():
    policy = _policy(attendance_basis=AttendanceBasis.STAGE)

    passed = calculate_academic_outcome(
        policy,
        [_component("math", 8)],
        AttendanceEvidence(global_percentage=10, stage_percentage=80),
    )
    assert passed.status == AcademicOutcomeStatus.APPROVED

    failed = calculate_academic_outcome(
        policy,
        [_component("math", 8)],
        AttendanceEvidence(global_percentage=100, stage_percentage=70),
    )
    assert failed.status == AcademicOutcomeStatus.NOT_APPROVED_ATTENDANCE


def test_component_attendance_requires_each_participating_component_evidence():
    policy = _policy(attendance_basis=AttendanceBasis.COMPONENT)
    result = calculate_academic_outcome(
        policy,
        [_component("math", 8), _component("port", 8)],
        AttendanceEvidence(component_percentages={"math": 90}),
    )

    assert result.status == AcademicOutcomeStatus.IN_PROGRESS
    assert result.missing_attendance_component_ids == ("port",)
    assert result.attendance_complete is False


def test_component_attendance_reports_exact_failed_components():
    policy = _policy(attendance_basis=AttendanceBasis.COMPONENT)
    result = calculate_academic_outcome(
        policy,
        [_component("math", 8), _component("port", 8)],
        AttendanceEvidence(component_percentages={"math": 74, "port": 80}),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_ATTENDANCE
    assert result.failed_attendance_component_ids == ("math",)


def test_component_and_attendance_failure_are_preserved_together():
    result = calculate_academic_outcome(
        _policy(),
        [_component("math", 4), _component("port", 8)],
        AttendanceEvidence(global_percentage=70),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_COMPONENT_AND_ATTENDANCE
    assert result.failed_component_ids == ("math",)
    assert result.attendance_failed is True
    assert result.dependency_mode is None


def _dependency_rule():
    return DependencyRule(
        enabled=True,
        outcomes=[
            DependencyOutcomeRange(
                mode=DependencyMode.WITH_DEPENDENCY,
                min_failed_components=1,
                max_failed_components=2,
            ),
            DependencyOutcomeRange(
                mode=DependencyMode.DEPENDENCY_ONLY,
                min_failed_components=3,
                max_failed_components=None,
            ),
        ],
    )


def test_dependency_ranges_are_policy_driven_not_series_driven():
    policy = _policy(dependency=_dependency_rule())

    one_failed = calculate_academic_outcome(
        policy,
        [_component("a", 4), _component("b", 8)],
        AttendanceEvidence(global_percentage=90),
    )
    assert one_failed.status == AcademicOutcomeStatus.WITH_DEPENDENCY
    assert one_failed.dependency_mode == DependencyMode.WITH_DEPENDENCY

    three_failed = calculate_academic_outcome(
        policy,
        [_component("a", 4), _component("b", 4), _component("c", 4)],
        AttendanceEvidence(global_percentage=90),
    )
    assert three_failed.status == AcademicOutcomeStatus.DEPENDENCY_ONLY
    assert three_failed.dependency_mode == DependencyMode.DEPENDENCY_ONLY


def test_failed_component_without_matching_dependency_range_is_not_approved():
    dependency = DependencyRule(
        enabled=True,
        outcomes=[
            DependencyOutcomeRange(
                mode=DependencyMode.WITH_DEPENDENCY,
                min_failed_components=1,
                max_failed_components=1,
            )
        ],
    )
    result = calculate_academic_outcome(
        _policy(dependency=dependency),
        [_component("a", 4), _component("b", 4)],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_COMPONENT
    assert result.dependency_mode is None


def test_dependency_never_neutralizes_attendance_failure():
    result = calculate_academic_outcome(
        _policy(dependency=_dependency_rule()),
        [_component("a", 4), _component("b", 8)],
        AttendanceEvidence(global_percentage=60),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_COMPONENT_AND_ATTENDANCE
    assert result.dependency_mode is None


def test_require_all_components_false_is_rejected_until_explicit_strategy_exists():
    policy = _policy(require_all_components=False)
    report = validate_policy(policy)
    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_COMPONENT_STRATEGY_UNSUPPORTED"
        for issue in report.issues
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_academic_outcome(
            policy,
            [_component("math", 8)],
            AttendanceEvidence(global_percentage=90),
        )
    assert exc.value.code == OUTCOME_POLICY_INVALID


def test_dependency_requires_component_threshold():
    policy = _policy(
        minimum_average=None,
        dependency=_dependency_rule(),
    )
    report = validate_policy(policy)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_DEPENDENCY_REQUIRES_COMPONENT_THRESHOLD"
        for issue in report.issues
    )


def test_dependency_ranges_cannot_overlap():
    policy = _policy(
        dependency=DependencyRule(
            enabled=True,
            outcomes=[
                DependencyOutcomeRange(
                    mode=DependencyMode.WITH_DEPENDENCY,
                    min_failed_components=1,
                    max_failed_components=3,
                ),
                DependencyOutcomeRange(
                    mode=DependencyMode.DEPENDENCY_ONLY,
                    min_failed_components=3,
                    max_failed_components=None,
                ),
            ],
        )
    )
    report = validate_policy(policy)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_DEPENDENCY_RANGE_OVERLAP"
        for issue in report.issues
    )


def test_duplicate_dependency_mode_is_invalid_even_if_ranges_are_disjoint():
    policy = _policy(
        dependency=DependencyRule(
            enabled=True,
            outcomes=[
                DependencyOutcomeRange(
                    mode=DependencyMode.WITH_DEPENDENCY,
                    min_failed_components=1,
                    max_failed_components=1,
                ),
                DependencyOutcomeRange(
                    mode=DependencyMode.WITH_DEPENDENCY,
                    min_failed_components=2,
                    max_failed_components=2,
                ),
            ],
        )
    )
    report = validate_policy(policy)

    assert report.valid is False
    assert any(
        issue.code == "ASSESSMENT_POLICY_DUPLICATE_DEPENDENCY_MODE"
        for issue in report.issues
    )


def test_council_permission_never_flips_calculated_status():
    policy = _policy(
        council=CouncilRule(
            enabled=True,
            can_override_academic_result=True,
            requires_reason=True,
            requires_audit_event=True,
        )
    )
    result = calculate_academic_outcome(
        policy,
        [_component("math", 4)],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.status == AcademicOutcomeStatus.NOT_APPROVED_COMPONENT
    assert result.council_override_available is True


def test_attendance_only_policy_can_be_evaluated_without_component_threshold():
    policy = _policy(minimum_average=None)
    result = calculate_academic_outcome(
        policy,
        [],
        AttendanceEvidence(global_percentage=80),
    )

    assert result.status == AcademicOutcomeStatus.APPROVED
    assert result.component_threshold is None


def test_policy_without_attendance_requirement_needs_no_attendance_evidence():
    policy = _policy(minimum_attendance=None)
    result = calculate_academic_outcome(policy, [_component("math", 8)])

    assert result.status == AcademicOutcomeStatus.APPROVED
    assert result.attendance_complete is True
    assert result.attendance_threshold is None


def test_invalid_attendance_percentage_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_academic_outcome(
            _policy(),
            [_component("math", 8)],
            AttendanceEvidence(global_percentage=101),
        )
    assert exc.value.code == OUTCOME_ATTENDANCE_INVALID


def test_final_average_outside_assessment_scale_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_academic_outcome(
            _policy(),
            [_component("math", 11)],
            AttendanceEvidence(global_percentage=90),
        )
    assert exc.value.code == OUTCOME_VALUE_INVALID


def test_duplicate_component_input_fails_closed():
    with pytest.raises(AssessmentPolicyError) as exc:
        calculate_academic_outcome(
            _policy(),
            [_component("math", 8), _component("math", 9)],
            AttendanceEvidence(global_percentage=90),
        )
    assert exc.value.code == OUTCOME_DUPLICATE_COMPONENT


def test_published_and_historical_policy_require_valid_hash():
    for status in (
        PolicyStatus.PUBLISHED,
        PolicyStatus.SUPERSEDED,
        PolicyStatus.RETIRED,
    ):
        policy = _policy(status=status)
        result = calculate_academic_outcome(
            policy,
            [_component("math", 8)],
            AttendanceEvidence(global_percentage=90),
        )
        assert result.status == AcademicOutcomeStatus.APPROVED
        assert result.rule_hash == policy.rule_hash

        broken = policy.model_copy(update={"rule_hash": "sha256:deadbeef"})
        with pytest.raises(AssessmentPolicyError) as exc:
            calculate_academic_outcome(
                broken,
                [_component("math", 8)],
                AttendanceEvidence(global_percentage=90),
            )
        assert exc.value.code == POLICY_INTEGRITY_ERROR


def test_outcome_preserves_policy_provenance():
    policy = _policy()
    result = calculate_academic_outcome(
        policy,
        [_component("math", 8)],
        AttendanceEvidence(global_percentage=90),
    )

    assert result.policy_id == policy.id
    assert result.policy_key == policy.policy_key
    assert result.policy_version == policy.version
    assert result.policy_status == "draft"
    assert result.rule_hash == calculate_rule_hash(policy)
