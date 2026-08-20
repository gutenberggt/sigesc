"""Testes da Foundation Shadow/Dry-run da Assessment Policy v1."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.exceptions import (
    AssessmentPolicyError,
    CALCULATION_VALUE_OUT_OF_SCALE,
    SHADOW_CONTEXT_MISMATCH,
    SHADOW_LEGACY_VALUE_INVALID,
    SHADOW_MAPPING_INVALID,
    SHADOW_TOLERANCE_INVALID,
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
from assessment_policy.shadow import (
    LegacyGradeFieldMapping,
    LegacyGradeSnapshot,
    ShadowClassification,
    calculate_mapping_hash,
    canonical_mapping_json,
    compare_legacy_grade_batch,
    compare_legacy_grade_snapshot,
    legacy_grade_snapshot_from_document,
    validate_shadow_mapping,
)


def _periods():
    return [
        PeriodRule(code="p1", label="P1", weight=2),
        PeriodRule(code="p2", label="P2", weight=3),
        PeriodRule(code="p3", label="P3", weight=2),
        PeriodRule(code="p4", label="P4", weight=3),
    ]


def _numeric_policy(*, recovery=False, year=2026):
    groups = []
    if recovery:
        groups = [
            RecoveryGroup(
                code="group-a",
                label="Recuperação A",
                input_code="recover-a",
                period_codes=["p1", "p2"],
                tie_break=RecoveryTieBreak.HIGHEST_WEIGHT,
                only_if_improves=True,
            )
        ]

    return AssessmentPolicy(
        id="shadow-policy",
        policy_key="SHADOW_NUMERIC",
        version=3,
        mantenedora_id="tenant-a",
        name="Política numérica shadow",
        academic_year=year,
        effective_from=date(year, 1, 1),
        effective_until=date(year, 12, 31),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10),
            periods=_periods(),
            calculation=CalculationRule(
                strategy=CalculationStrategy.WEIGHTED_AVERAGE,
                decimal_places=2,
            ),
        ),
        recovery=RecoveryRule(enabled=recovery, groups=groups),
    )


def _conceptual_policy():
    return AssessmentPolicy(
        id="shadow-conceptual",
        policy_key="SHADOW_CONCEPTUAL",
        version=1,
        mantenedora_id="tenant-a",
        name="Política conceitual shadow",
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
                decimal_places=2,
            ),
        ),
    )


def _mapping(*, recovery=False):
    return LegacyGradeFieldMapping(
        period_field_map={
            "legacy_b1": "p1",
            "legacy_b2": "p2",
            "legacy_b3": "p3",
            "legacy_b4": "p4",
        },
        recovery_field_map=(
            {"legacy_recovery_alpha": "recover-a"}
            if recovery
            else {}
        ),
    )


def _snapshot(
    *,
    grade_id="grade-1",
    year=2026,
    legacy_final=6.5,
    b1=5,
    b2=7.5,
    b3=5,
    b4=7.5,
    recovery_value=None,
):
    fields = {
        "legacy_b1": b1,
        "legacy_b2": b2,
        "legacy_b3": b3,
        "legacy_b4": b4,
    }
    if recovery_value is not None:
        fields["legacy_recovery_alpha"] = recovery_value
    return LegacyGradeSnapshot(
        grade_id=grade_id,
        student_id=f"student-{grade_id}",
        class_id="class-1",
        course_id="course-1",
        academic_year=year,
        fields=fields,
        legacy_final_average=legacy_final,
        legacy_status="aprovado",
    )


def test_mapping_hash_is_deterministic_independent_of_dict_order():
    left = LegacyGradeFieldMapping(
        period_field_map={"z": "p4", "a": "p1", "m": "p2", "n": "p3"},
        recovery_field_map={},
    )
    right = LegacyGradeFieldMapping(
        period_field_map={"n": "p3", "m": "p2", "a": "p1", "z": "p4"},
        recovery_field_map={},
    )

    assert canonical_mapping_json(left) == canonical_mapping_json(right)
    assert calculate_mapping_hash(left) == calculate_mapping_hash(right)
    assert calculate_mapping_hash(left).startswith("sha256:")


def test_mapping_requires_all_required_policy_periods():
    incomplete = LegacyGradeFieldMapping(
        period_field_map={"legacy_b1": "p1"},
        recovery_field_map={},
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(_numeric_policy(), incomplete)

    assert exc.value.code == SHADOW_MAPPING_INVALID
    assert exc.value.details["period_codes"] == ["p2", "p3", "p4"]


def test_mapping_rejects_unknown_period_target():
    mapping = LegacyGradeFieldMapping(
        period_field_map={
            "legacy_b1": "p1",
            "legacy_b2": "p2",
            "legacy_b3": "p3",
            "legacy_b4": "does-not-exist",
        },
        recovery_field_map={},
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(_numeric_policy(), mapping)

    assert exc.value.code == SHADOW_MAPPING_INVALID
    assert exc.value.details["period_codes"] == ["does-not-exist"]


def test_mapping_rejects_duplicate_policy_targets():
    mapping = LegacyGradeFieldMapping(
        period_field_map={
            "legacy_b1": "p1",
            "legacy_b2": "p1",
            "legacy_b3": "p3",
            "legacy_b4": "p4",
        },
        recovery_field_map={},
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(_numeric_policy(), mapping)

    assert exc.value.code == SHADOW_MAPPING_INVALID


def test_same_legacy_field_cannot_feed_period_and_recovery():
    mapping = LegacyGradeFieldMapping(
        period_field_map={
            "legacy_b1": "p1",
            "legacy_b2": "p2",
            "legacy_b3": "p3",
            "shared": "p4",
        },
        recovery_field_map={"shared": "recover-a"},
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(_numeric_policy(recovery=True), mapping)

    assert exc.value.code == SHADOW_MAPPING_INVALID
    assert exc.value.details["source_fields"] == ["shared"]


def test_recovery_enabled_policy_requires_complete_explicit_recovery_mapping():
    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(
            _numeric_policy(recovery=True),
            _mapping(recovery=False),
        )

    assert exc.value.code == SHADOW_MAPPING_INVALID
    assert exc.value.details["input_codes"] == ["recover-a"]


def test_mapping_rejects_unknown_recovery_target():
    mapping = LegacyGradeFieldMapping(
        period_field_map=_mapping().period_field_map,
        recovery_field_map={"legacy_recovery_alpha": "unknown-recovery"},
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(_numeric_policy(recovery=True), mapping)

    assert exc.value.code == SHADOW_MAPPING_INVALID
    assert exc.value.details["input_codes"] == ["unknown-recovery"]


def test_recovery_disabled_policy_rejects_recovery_mapping():
    with pytest.raises(AssessmentPolicyError) as exc:
        validate_shadow_mapping(
            _numeric_policy(recovery=False),
            _mapping(recovery=True),
        )

    assert exc.value.code == SHADOW_MAPPING_INVALID


def test_snapshot_from_document_preserves_read_only_identity_and_inputs():
    document = {
        "id": "g-1",
        "student_id": "s-1",
        "class_id": "c-1",
        "course_id": "math",
        "academic_year": "2026",
        "b1": 5,
        "b2": 7.5,
        "final_average": 6.5,
        "status": "aprovado",
    }

    snapshot = legacy_grade_snapshot_from_document(document)

    assert snapshot.grade_id == "g-1"
    assert snapshot.academic_year == 2026
    assert snapshot.fields == document
    assert snapshot.legacy_final_average == 6.5
    assert snapshot.legacy_status == "aprovado"


def test_snapshot_requires_complete_academic_identity():
    with pytest.raises(AssessmentPolicyError) as exc:
        legacy_grade_snapshot_from_document(
            {
                "id": "g-1",
                "student_id": "s-1",
                "class_id": "c-1",
                "academic_year": 2026,
            }
        )

    assert exc.value.code == SHADOW_LEGACY_VALUE_INVALID
    assert "course_id" in exc.value.details["missing_fields"]


def test_exact_same_final_average_is_match():
    policy = _numeric_policy()
    result = compare_legacy_grade_snapshot(
        policy,
        _snapshot(legacy_final=6.5),
        _mapping(),
    )

    assert result.classification == ShadowClassification.MATCH
    assert result.legacy_final_average == 6.5
    assert result.new_final_average == 6.5
    assert result.delta == 0.0
    assert result.absolute_delta == 0.0
    assert result.rule_hash == calculate_rule_hash(policy)
    assert result.mapping_hash == calculate_mapping_hash(_mapping())


def test_difference_inside_declared_tolerance_is_match():
    result = compare_legacy_grade_snapshot(
        _numeric_policy(),
        _snapshot(legacy_final=6.49),
        _mapping(),
        tolerance="0.01",
    )

    assert result.classification == ShadowClassification.MATCH
    assert result.absolute_delta == 0.01


def test_difference_beyond_tolerance_preserves_signed_and_absolute_delta():
    result = compare_legacy_grade_snapshot(
        _numeric_policy(),
        _snapshot(legacy_final=6.0),
        _mapping(),
        tolerance="0.01",
    )

    assert result.classification == ShadowClassification.DIFFERENT
    assert result.delta == 0.5
    assert result.absolute_delta == 0.5


def test_both_incomplete_is_not_forced_to_match_or_difference():
    result = compare_legacy_grade_snapshot(
        _numeric_policy(),
        _snapshot(
            legacy_final=None,
            b1=8,
            b2=None,
            b3=None,
            b4=None,
        ),
        _mapping(),
    )

    assert result.classification == ShadowClassification.BOTH_INCOMPLETE
    assert result.new_current_average == 8.0
    assert result.new_final_average is None
    assert result.new_is_final is False


def test_legacy_final_with_new_incomplete_is_classified_explicitly():
    result = compare_legacy_grade_snapshot(
        _numeric_policy(),
        _snapshot(
            legacy_final=8,
            b1=8,
            b2=None,
            b3=None,
            b4=None,
        ),
        _mapping(),
    )

    assert result.classification == ShadowClassification.NEW_INCOMPLETE
    assert result.legacy_final_average == 8.0
    assert result.new_final_average is None


def test_new_final_with_missing_legacy_final_is_classified_explicitly():
    result = compare_legacy_grade_snapshot(
        _numeric_policy(),
        _snapshot(legacy_final=None),
        _mapping(),
    )

    assert result.classification == ShadowClassification.LEGACY_MISSING
    assert result.new_final_average == 6.5


def test_invalid_legacy_final_average_becomes_record_error_not_global_abort():
    policy = _numeric_policy()
    result = compare_legacy_grade_snapshot(
        policy,
        _snapshot(legacy_final="6,5"),
        _mapping(),
    )

    assert result.classification == ShadowClassification.ERROR
    assert result.error_code == SHADOW_LEGACY_VALUE_INVALID
    assert result.rule_hash == calculate_rule_hash(policy)


def test_calculator_error_becomes_record_error_with_policy_hash():
    policy = _numeric_policy()
    result = compare_legacy_grade_snapshot(
        policy,
        _snapshot(b1=11),
        _mapping(),
    )

    assert result.classification == ShadowClassification.ERROR
    assert result.error_code == CALCULATION_VALUE_OUT_OF_SCALE
    assert result.rule_hash == calculate_rule_hash(policy)


def test_snapshot_year_mismatch_becomes_explicit_record_error():
    policy = _numeric_policy(year=2026)
    result = compare_legacy_grade_snapshot(
        policy,
        _snapshot(year=2025),
        _mapping(),
    )

    assert result.classification == ShadowClassification.ERROR
    assert result.error_code == SHADOW_CONTEXT_MISMATCH
    assert result.error_details == {
        "snapshot_academic_year": 2025,
        "policy_academic_year": 2026,
    }


def test_invalid_tolerance_aborts_comparison_configuration():
    with pytest.raises(AssessmentPolicyError) as exc:
        compare_legacy_grade_snapshot(
            _numeric_policy(),
            _snapshot(),
            _mapping(),
            tolerance="-0.01",
        )

    assert exc.value.code == SHADOW_TOLERANCE_INVALID


def test_recovery_is_driven_only_by_explicit_mapping_not_legacy_field_name():
    policy = _numeric_policy(recovery=True)
    result = compare_legacy_grade_snapshot(
        policy,
        _snapshot(
            legacy_final=8,
            b1=5,
            b2=5,
            b3=8,
            b4=8,
            recovery_value=10,
        ),
        _mapping(recovery=True),
    )

    assert result.classification == ShadowClassification.MATCH
    assert result.new_final_average == 8.0


def test_conceptual_snapshot_can_be_compared_using_policy_scale():
    policy = _conceptual_policy()
    snapshot = _snapshot(
        legacy_final=7.75,
        b1="ED",
        b2="C",
        b3="ND",
        b4="ED",
    )

    result = compare_legacy_grade_snapshot(policy, snapshot, _mapping())

    assert result.classification == ShadowClassification.MATCH
    assert result.new_final_average == 7.75


def test_batch_aggregation_keeps_noncomparable_records_out_of_match_rate():
    policy = _numeric_policy()
    snapshots = [
        _snapshot(grade_id="match", legacy_final=6.5),
        _snapshot(grade_id="diff", legacy_final=6.0),
        _snapshot(
            grade_id="both-incomplete",
            legacy_final=None,
            b1=8,
            b2=None,
            b3=None,
            b4=None,
        ),
        _snapshot(
            grade_id="new-incomplete",
            legacy_final=8,
            b1=8,
            b2=None,
            b3=None,
            b4=None,
        ),
        _snapshot(grade_id="legacy-missing", legacy_final=None),
        _snapshot(grade_id="error", legacy_final="bad"),
    ]

    report = compare_legacy_grade_batch(
        policy,
        snapshots,
        _mapping(),
        tolerance="0.01",
    )

    assert report.total == 6
    assert report.matches == 1
    assert report.differences == 1
    assert report.both_incomplete == 1
    assert report.new_incomplete == 1
    assert report.legacy_missing == 1
    assert report.errors == 1
    assert report.comparable == 2
    assert report.match_rate == 0.5
    assert report.max_absolute_delta == 0.5
    assert report.policy_ids == ("shadow-policy",)
    assert report.rule_hashes == (calculate_rule_hash(policy),)
    assert report.mapping_hash == calculate_mapping_hash(_mapping())


def test_batch_with_no_comparable_records_has_no_match_rate():
    report = compare_legacy_grade_batch(
        _numeric_policy(),
        [
            _snapshot(
                grade_id="incomplete",
                legacy_final=None,
                b1=8,
                b2=None,
                b3=None,
                b4=None,
            )
        ],
        _mapping(),
    )

    assert report.comparable == 0
    assert report.match_rate is None
    assert report.max_absolute_delta is None


def test_invalid_mapping_aborts_batch_before_generating_partial_report():
    incomplete_mapping = LegacyGradeFieldMapping(
        period_field_map={"legacy_b1": "p1"},
        recovery_field_map={},
    )

    with pytest.raises(AssessmentPolicyError) as exc:
        compare_legacy_grade_batch(
            _numeric_policy(),
            [_snapshot()],
            incomplete_mapping,
        )

    assert exc.value.code == SHADOW_MAPPING_INVALID


def test_invalid_batch_tolerance_aborts_before_report():
    with pytest.raises(AssessmentPolicyError) as exc:
        compare_legacy_grade_batch(
            _numeric_policy(),
            [_snapshot()],
            _mapping(),
            tolerance=True,
        )

    assert exc.value.code == SHADOW_TOLERANCE_INVALID


def test_shadow_module_has_no_database_mutation_primitives():
    source = Path(__file__).parents[1] / "assessment_policy" / "shadow.py"
    text = source.read_text(encoding="utf-8")

    forbidden = (
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".replace_one(",
        ".delete_one(",
        ".delete_many(",
        ".bulk_write(",
        "calculate_and_update_grade",
    )
    for token in forbidden:
        assert token not in text, token
