"""Testes dos contratos puros do OperationalBinding — Sprint 008/Fase 1."""

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from assessment_policy.canonical import calculate_rule_hash
from assessment_policy.models import (
    AssessmentMode,
    AssessmentPolicy,
    AssessmentRule,
    CalculationRule,
    CalculationStrategy,
    NumericScale,
    PeriodRule,
)
from assessment_policy.operational_binding import (
    AssessmentPolicyOperationalBinding,
    BINDING_MAPPING_HASH_MISMATCH,
    BINDING_MAPPING_INVALID,
    BINDING_POLICY_HASH_INVALID,
    BINDING_POLICY_IDENTITY_MISMATCH,
    BINDING_POLICY_RULE_HASH_MISMATCH,
    OperationalBindingStatus,
    calculate_operational_mapping_hash,
    canonical_operational_binding_json,
    canonical_operational_binding_payload,
    canonical_operational_mapping_json,
    validate_operational_binding,
)
from assessment_policy.shadow import (
    LegacyGradeFieldMapping,
    calculate_mapping_hash,
    canonical_mapping_json,
)


MODULE = Path("backend/assessment_policy/operational_binding.py")


def _policy() -> AssessmentPolicy:
    return AssessmentPolicy(
        id="policy-2026",
        policy_key="MUNICIPAL_2026",
        version=1,
        mantenedora_id="tenant-a",
        name="Política Municipal 2026",
        academic_year=2026,
        effective_from=date(2026, 1, 1),
        effective_until=date(2026, 12, 31),
        assessment=AssessmentRule(
            mode=AssessmentMode.NUMERIC,
            numeric_scale=NumericScale(minimum=0, maximum=10),
            periods=[
                PeriodRule(code="p1", label="1º Bimestre", weight=2),
                PeriodRule(code="p2", label="2º Bimestre", weight=3),
            ],
            calculation=CalculationRule(
                strategy=CalculationStrategy.WEIGHTED_AVERAGE,
                decimal_places=2,
            ),
        ),
    )


def _binding(
    *,
    policy=None,
    period_map=None,
    status=OperationalBindingStatus.DRAFT,
    mapping_hash=None,
    policy_rule_hash=None,
    **overrides,
) -> AssessmentPolicyOperationalBinding:
    policy = policy or _policy()
    values = {
        "id": "binding-2026-v1",
        "mantenedora_id": policy.mantenedora_id,
        "policy_id": policy.id,
        "policy_key": policy.policy_key,
        "policy_version": policy.version,
        "policy_rule_hash": policy_rule_hash or calculate_rule_hash(policy),
        "binding_version": 1,
        "revision": 1,
        "source_schema": "grades:v1",
        "period_field_map": period_map
        or {
            "legacy_b1": "p1",
            "legacy_b2": "p2",
        },
        "recovery_field_map": {},
        "status": status,
        "mapping_hash": mapping_hash,
    }
    if status != OperationalBindingStatus.DRAFT:
        values["validated_by"] = "super-admin"
        values["validated_at"] = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    values.update(overrides)
    return AssessmentPolicyOperationalBinding(**values)


def test_mapping_hash_reuses_shadow_canonicalization_exactly():
    binding = _binding()
    runtime = LegacyGradeFieldMapping(
        period_field_map=binding.period_field_map,
        recovery_field_map=binding.recovery_field_map,
    )

    assert canonical_operational_mapping_json(binding) == canonical_mapping_json(runtime)
    assert calculate_operational_mapping_hash(binding) == calculate_mapping_hash(runtime)


def test_mapping_and_binding_canonicalization_are_order_independent():
    left = _binding(
        period_map={
            "legacy_b1": "p1",
            "legacy_b2": "p2",
        }
    )
    right = _binding(
        period_map={
            "legacy_b2": "p2",
            "legacy_b1": "p1",
        }
    )

    assert canonical_operational_mapping_json(left) == canonical_operational_mapping_json(right)
    assert calculate_operational_mapping_hash(left) == calculate_operational_mapping_hash(right)
    assert canonical_operational_binding_json(left) == canonical_operational_binding_json(right)


def test_canonical_binding_excludes_lifecycle_and_audit_metadata():
    draft = _binding()
    mapping_hash = calculate_operational_mapping_hash(draft)
    validated = _binding(
        status=OperationalBindingStatus.VALIDATED,
        mapping_hash=mapping_hash,
        revision=9,
        created_by="creator",
        created_at=datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc),
    )

    assert canonical_operational_binding_json(draft) == canonical_operational_binding_json(validated)
    payload = canonical_operational_binding_payload(validated)
    for forbidden in (
        "id",
        "revision",
        "status",
        "mapping_hash",
        "created_by",
        "created_at",
        "validated_by",
        "validated_at",
    ):
        assert forbidden not in payload


def test_mapping_change_changes_mapping_hash_and_canonical_binding():
    original = _binding()
    changed = _binding(
        period_map={
            "legacy_first_period": "p1",
            "legacy_b2": "p2",
        }
    )

    assert calculate_operational_mapping_hash(original) != calculate_operational_mapping_hash(changed)
    assert canonical_operational_binding_json(original) != canonical_operational_binding_json(changed)


def test_contract_strips_identity_and_mapping_text():
    policy = _policy()
    binding = AssessmentPolicyOperationalBinding(
        id=" binding-1 ",
        mantenedora_id=" tenant-a ",
        policy_id=" policy-2026 ",
        policy_key=" MUNICIPAL_2026 ",
        policy_version=1,
        policy_rule_hash=calculate_rule_hash(policy),
        binding_version=1,
        source_schema=" grades:v1 ",
        period_field_map={
            " legacy_b1 ": " p1 ",
            " legacy_b2 ": " p2 ",
        },
    )

    assert binding.id == "binding-1"
    assert binding.source_schema == "grades:v1"
    assert binding.period_field_map == {
        "legacy_b1": "p1",
        "legacy_b2": "p2",
    }


def test_contract_rejects_duplicate_target_inside_same_mapping():
    policy = _policy()
    with pytest.raises(ValidationError):
        _binding(
            policy=policy,
            period_map={
                "legacy_b1": "p1",
                "legacy_other": "p1",
            },
        )


def test_contract_rejects_duplicate_source_after_normalization():
    policy = _policy()
    with pytest.raises(ValidationError):
        _binding(
            policy=policy,
            period_map={
                "legacy_b1": "p1",
                " legacy_b1 ": "p2",
            },
        )


def test_contract_rejects_source_reused_between_period_and_recovery():
    policy = _policy()
    with pytest.raises(ValidationError):
        AssessmentPolicyOperationalBinding(
            id="binding-1",
            mantenedora_id=policy.mantenedora_id,
            policy_id=policy.id,
            policy_key=policy.policy_key,
            policy_version=policy.version,
            policy_rule_hash=calculate_rule_hash(policy),
            binding_version=1,
            source_schema="grades:v1",
            period_field_map={"same_field": "p1", "legacy_b2": "p2"},
            recovery_field_map={"same_field": "recovery-1"},
        )


def test_draft_cannot_carry_persisted_mapping_hash():
    policy = _policy()
    with pytest.raises(ValidationError):
        _binding(
            policy=policy,
            mapping_hash="sha256:" + ("0" * 64),
        )


def test_validated_binding_requires_hash_and_validation_metadata():
    with pytest.raises(ValidationError):
        AssessmentPolicyOperationalBinding(
            id="binding-1",
            mantenedora_id="tenant-a",
            policy_id="policy-2026",
            policy_key="MUNICIPAL_2026",
            policy_version=1,
            policy_rule_hash="sha256:" + ("1" * 64),
            binding_version=1,
            source_schema="grades:v1",
            period_field_map={"legacy_b1": "p1", "legacy_b2": "p2"},
            status=OperationalBindingStatus.VALIDATED,
        )


def test_exact_binding_validates_against_policy_without_io():
    policy = _policy()
    binding = _binding(policy=policy)

    report = validate_operational_binding(policy, binding)

    assert report.valid is True
    assert report.issues == []
    assert report.calculated_policy_rule_hash == calculate_rule_hash(policy)
    assert report.calculated_mapping_hash == calculate_operational_mapping_hash(binding)


def test_identity_mismatch_fails_closed():
    policy = _policy()
    binding = _binding(policy=policy, policy_id="other-policy")

    report = validate_operational_binding(policy, binding)

    assert report.valid is False
    issue = next(item for item in report.issues if item.code == BINDING_POLICY_IDENTITY_MISMATCH)
    assert issue.details["policy_id"]["expected"] == policy.id
    assert issue.details["policy_id"]["received"] == "other-policy"


def test_changed_policy_content_makes_binding_stale_by_rule_hash():
    original = _policy()
    binding = _binding(policy=original)
    changed = original.model_copy(
        update={
            "assessment": original.assessment.model_copy(
                update={
                    "periods": [
                        PeriodRule(code="p1", label="1º Bimestre", weight=3),
                        PeriodRule(code="p2", label="2º Bimestre", weight=3),
                    ]
                }
            )
        }
    )

    report = validate_operational_binding(changed, binding)

    assert report.valid is False
    assert BINDING_POLICY_RULE_HASH_MISMATCH in {item.code for item in report.issues}


def test_corrupted_persisted_policy_hash_fails_closed():
    policy = _policy()
    corrupted = policy.model_copy(update={"rule_hash": "sha256:" + ("f" * 64)})
    binding = _binding(policy=policy)

    report = validate_operational_binding(corrupted, binding)

    assert report.valid is False
    assert BINDING_POLICY_HASH_INVALID in {item.code for item in report.issues}


def test_semantically_incomplete_mapping_is_rejected_by_shadow_contract():
    policy = _policy()
    binding = _binding(
        policy=policy,
        period_map={"legacy_b1": "p1"},
    )

    report = validate_operational_binding(policy, binding)

    assert report.valid is False
    issue = next(item for item in report.issues if item.code == BINDING_MAPPING_INVALID)
    assert issue.details["source_code"] == "ASSESSMENT_SHADOW_MAPPING_INVALID"
    assert report.calculated_mapping_hash is None


def test_persisted_mapping_hash_must_match_current_mapping():
    policy = _policy()
    draft = _binding(policy=policy)
    validated = _binding(
        policy=policy,
        status=OperationalBindingStatus.VALIDATED,
        mapping_hash="sha256:" + ("0" * 64),
    )

    assert calculate_operational_mapping_hash(draft) != validated.mapping_hash
    report = validate_operational_binding(policy, validated)

    assert report.valid is False
    assert BINDING_MAPPING_HASH_MISMATCH in {item.code for item in report.issues}


def test_module_contract_has_no_io_router_publish_or_cutover_dependencies():
    source = MODULE.read_text(encoding="utf-8")
    forbidden = [
        "from motor",
        "import motor",
        "pymongo",
        "fastapi",
        "APIRouter",
        "insert_one",
        "update_one",
        "replace_one",
        "delete_one",
        "calculate_and_update_grade",
        "grade_calculator",
        '@router.',
        "/publish",
        "/cutover",
    ]
    found = [item for item in forbidden if item in source]
    assert found == []
