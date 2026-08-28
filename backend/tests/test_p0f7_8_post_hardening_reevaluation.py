from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_8_1_bounded_reevaluation.py"
OLD_SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_8_post_hardening_reevaluation.py"

spec = importlib.util.spec_from_file_location("p0f781", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _fit(rank: int, classification: str) -> dict:
    return {"rank": rank, "classification": classification}


def test_old_high_cost_entrypoint_is_removed() -> None:
    assert OLD_SCRIPT.exists() is False


def test_read_only_and_resource_safety_guards_pass() -> None:
    mod.assert_read_only()
    mod.assert_resource_safety()


def test_script_has_fixed_small_resource_budget() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert mod.MAX_CASES == 3
    assert mod.MAX_DATABASE_QUERY_CALLS == 9
    assert mod.MAX_TRACKED_COURSES_PER_CASE <= 4
    assert "db.enrollments" not in source
    assert "db.students" not in source
    assert "db.grades" not in source
    assert "db.attendance" not in source
    assert "resolve_curriculum(" not in source
    assert ".to_list(5000)" not in source
    assert ".to_list(10000)" not in source


def test_resolver_hardening_contract_is_present_without_full_replay() -> None:
    contract = mod.validate_resolver_hardening_contract()
    assert contract["curricular_rank_precedes_evidence_score"] is True
    assert contract["unknown_course_level_is_review"] is True
    assert contract["resolver_mutator_surface_detected"] is False
    assert contract["full_resolver_replay_per_student_performed"] is False
    assert len(contract["resolver_sha256"]) == 64


def test_case_1_strong_source_preference_is_not_database_action() -> None:
    policy = mod.classify_pair_policy(
        _fit(3, "EXPLICIT_SERIES_FULL_MATCH"),
        _fit(2, "SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW"),
    )
    assert policy["state"] == "STRONG_CURRICULAR_PREFERENCE_SOURCE"
    assert policy["curricular_preference"] == "source"
    assert policy["component_adjudication_required"] is False
    assert policy["automatic_database_action"] is False


def test_case_2_both_level_mismatch_stays_blocked() -> None:
    policy = mod.classify_pair_policy(
        _fit(1, "LEVEL_MISMATCH"),
        _fit(1, "LEVEL_MISMATCH"),
    )
    assert policy["state"] == "BOTH_CURRICULARLY_INCOMPATIBLE_REQUIRES_ADJUDICATION"
    assert policy["curricular_preference"] is None
    assert policy["component_adjudication_required"] is True
    assert policy["automatic_database_action"] is False


def test_case_3_same_review_rank_stays_blocked() -> None:
    policy = mod.classify_pair_policy(
        _fit(2, "PARTIAL_EXPLICIT_SERIES_MATCH_REQUIRES_REVIEW"),
        _fit(2, "SERIES_SCOPE_CONFLICT_REQUIRES_REVIEW"),
    )
    assert policy["state"] == "BOTH_REVIEW_TIER_REQUIRES_ADJUDICATION"
    assert policy["curricular_preference"] is None
    assert policy["component_adjudication_required"] is True
    assert policy["automatic_database_action"] is False


def test_p0f75_classifications_map_to_hardened_ranks() -> None:
    assert mod._expected_rank_from_p0f75("EXPLICIT_SERIES_FULL_MATCH") == 3
    assert mod._expected_rank_from_p0f75("PER_SERIES_MATRIX_FULL_MATCH") == 3
    assert mod._expected_rank_from_p0f75("LEVEL_MISMATCH_PRECEDES_SERIES") == 1
    assert mod._expected_rank_from_p0f75("NO_SERIES_MATCH") == 1
    assert mod._expected_rank_from_p0f75(
        "MATRIX_FULL_BUT_EXPLICIT_SCOPE_CONFLICT_REQUIRES_REVIEW"
    ) == 2
    assert mod._expected_rank_from_p0f75("PARTIAL_SERIES_MATCH_REQUIRES_REVIEW") == 2
    assert mod._expected_rank_from_p0f75("LEVEL_ONLY_NO_SERIES_SCOPE") == 2
