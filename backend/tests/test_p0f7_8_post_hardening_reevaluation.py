from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_8_2_offline_snapshot.py"
OLD_SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_8_post_hardening_reevaluation.py"
BOUNDED_SCRIPT = ROOT / "backend" / "scripts" / "audit_p0f7_8_1_bounded_reevaluation.py"
POWERSHELL = ROOT / "scripts" / "p0f7_8_2_analyze_local.ps1"

spec = importlib.util.spec_from_file_location("p0f782", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def _fit(rank: int, classification: str) -> dict:
    return {"rank": rank, "classification": classification}


def _minimal_snapshot() -> dict:
    return {
        "phase": mod.SNAPSHOT_PHASE,
        "mode": "READ_ONLY_MINIMAL_MONGOSH",
        "query_budget": 9,
        "query_calls": 9,
        "cases": [
            {"case_number": 1, "class": {}, "courses": [], "assignments": []},
            {"case_number": 2, "class": {}, "courses": [], "assignments": []},
            {"case_number": 3, "class": {}, "courses": [], "assignments": []},
        ],
    }


def test_all_production_python_auditor_entrypoints_are_removed() -> None:
    assert OLD_SCRIPT.exists() is False
    assert BOUNDED_SCRIPT.exists() is False


def test_offline_analyzer_has_no_database_or_remote_runtime() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = [
        "from motor", "import motor", "pymongo", "AsyncIOMotorClient",
        "MongoClient(", "subprocess.", "docker exec", "MONGO_URL", "DB_NAME",
    ]
    assert not any(token in source for token in forbidden)
    assert "--apply" not in source


def test_powershell_wrapper_is_local_only() -> None:
    source = POWERSHELL.read_text(encoding="utf-8")
    forbidden = ["ssh.exe", "scp.exe", "docker exec", "mongosh", "Invoke-WebRequest"]
    assert not any(token in source for token in forbidden)
    assert "PRODUCTION_ACCESS=NO" in source


def test_snapshot_contract_is_three_cases_and_nine_reads() -> None:
    result = mod.validate_snapshot(_minimal_snapshot())
    assert len(result["snapshot_sha256"]) == 64
    assert sorted(result["cases"]) == [1, 2, 3]


def test_snapshot_privacy_guard_rejects_student_keys() -> None:
    snapshot = _minimal_snapshot()
    snapshot["cases"][0]["student_id"] = "forbidden"
    with pytest.raises(ValueError, match="SNAPSHOT_PRIVACY_GUARD_FAILED"):
        mod.validate_snapshot(snapshot)


def test_resolver_hardening_contract_is_reused_offline() -> None:
    contract = mod.validate_resolver_hardening_contract()
    assert contract["curricular_rank_precedes_evidence_score"] is True
    assert contract["unknown_course_level_is_review"] is True
    assert contract["resolver_mutator_surface_detected"] is False
    assert contract["database_client_available_in_analyzer"] is False
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
