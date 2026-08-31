from services.legacy_only_canonical_policy import (
    CANONICAL_ENTITLEMENT,
    LegacyOnlyPolicyDecision,
    assert_entitlement_only_projection,
    build_entitlement_only_projection,
    decide_legacy_only_policy,
)


def _base_case(**overrides):
    case = {
        "action": "REQUIRES_REVIEW",
        "review_reasons": ["NO_CANONICAL_TEMPLATE"],
        "teacher_id": "user-1",
        "class_id": "class-1",
        "component_id": "course-1",
        "mantenedora_id": "tenant-1",
        "school_id": "school-1",
        "academic_year": 2026,
        "legacy_binding_count": 1,
        # Sinais abaixo não podem ser usados para inventar envelope DVD.
        "has_grade_evidence": True,
        "course_name": "Matemática",
        "peer_profile": "regular",
        "class_shift": "morning",
    }
    case.update(overrides)
    return case


def test_no_canonical_template_only_becomes_entitlement_only_candidate():
    result = decide_legacy_only_policy(_base_case())
    assert result.decision is LegacyOnlyPolicyDecision.PLAN_CANONICAL_ENTITLEMENT_ONLY


def test_any_additional_review_reason_keeps_case_in_review():
    result = decide_legacy_only_policy(
        _base_case(review_reasons=["NO_CANONICAL_TEMPLATE", "COURSE_UNRESOLVED"])
    )
    assert result.decision is LegacyOnlyPolicyDecision.KEEP_REVIEW
    assert "COURSE_UNRESOLVED" in result.reason


def test_missing_structural_identifier_keeps_case_in_review():
    result = decide_legacy_only_policy(_base_case(mantenedora_id=None))
    assert result.decision is LegacyOnlyPolicyDecision.KEEP_REVIEW
    assert "mantenedora_id" in result.reason


def test_non_target_action_is_noop():
    result = decide_legacy_only_policy(_base_case(action="PLAN_CREATE_CANONICAL_ASSIGNMENT"))
    assert result.decision is LegacyOnlyPolicyDecision.NOOP_NOT_TARGET


def test_projection_preserves_exact_entitlement_identity_and_year():
    projection = build_entitlement_only_projection(_base_case())
    assert projection["assignment_semantics"] == CANONICAL_ENTITLEMENT
    assert projection["teacher_id"] == "user-1"
    assert projection["class_id"] == "class-1"
    assert projection["component_id"] == "course-1"
    assert projection["mantenedora_id"] == "tenant-1"
    assert projection["school_id"] == "school-1"
    assert projection["academic_year"] == 2026
    assert projection["storage_ready"] is False


def test_projection_never_infers_dvd_envelope_from_incidental_evidence():
    projection = build_entitlement_only_projection(_base_case())
    for field in (
        "diary_settings",
        "weekly_slots",
        "valid_from",
        "valid_until",
        "is_substitute",
        "grades_official_owner",
        "shift",
    ):
        assert projection[field] is None
    assert_entitlement_only_projection(projection)


def test_legacy_binding_must_be_unique_when_count_is_available():
    result = decide_legacy_only_policy(_base_case(legacy_binding_count=2))
    assert result.decision is LegacyOnlyPolicyDecision.KEEP_REVIEW
    assert result.reason == "LEGACY_BINDING_NOT_UNIQUE"
