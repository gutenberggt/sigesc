from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_8_post_hardening_reevaluation.py"

spec = importlib.util.spec_from_file_location("p0f78", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _fit(rank: int, classification: str) -> dict:
    return {"rank": rank, "classification": classification}


def test_read_only_guard_passes() -> None:
    mod.assert_read_only()


def test_resolver_hardening_contract_is_present() -> None:
    contract = mod.validate_resolver_hardening_contract()
    assert contract["curricular_rank_precedes_evidence_score"] is True
    assert contract["unknown_course_level_is_review"] is True
    assert contract["resolver_mutator_surface_detected"] is False
    assert len(contract["resolver_sha256"]) == 64


def test_case_1_strong_source_preference_is_policy_result_not_database_action() -> None:
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


def test_candidate_roles_do_not_encode_student_information() -> None:
    alternatives = {"eja-course"}
    assert mod._candidate_role(
        "source-course",
        source_course_id="source-course",
        target_course_id="target-course",
        alternative_ids=alternatives,
    ) == "source"
    assert mod._candidate_role(
        "target-course",
        source_course_id="source-course",
        target_course_id="target-course",
        alternative_ids=alternatives,
    ) == "target"
    assert mod._candidate_role(
        "eja-course",
        source_course_id="source-course",
        target_course_id="target-course",
        alternative_ids=alternatives,
    ) == "alternative_exact_level"
