"""Regressões da Fase 0 read-only de identidade de matrícula."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_enrollment_identity_phase0_preflight.py"
SPEC = importlib.util.spec_from_file_location("identity_phase0", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)


def test_script_has_no_mongo_write_primitives():
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = [
        ".insert_one(",
        ".insert_many(",
        ".update_one(",
        ".update_many(",
        ".delete_one(",
        ".delete_many(",
        ".replace_one(",
        ".bulk_write(",
        ".find_one_and_",
        ".create_index(",
        ".drop_index(",
    ]
    for token in forbidden:
        assert token not in source, f"preflight deixou de ser read-only: {token}"
    assert "--apply" not in source


def test_first_log_classification_matches_forensic_rules():
    assert MOD.classify_first_log("202604873", "202601616", "202601616") == "LOG_CONFIRMS_ENROLLMENT"
    assert MOD.classify_first_log("202607309", "202607328", "202607309") == "LOG_CONFIRMS_STUDENT"
    assert MOD.classify_first_log("202604876", "202603749", "202603461") == "THIRD_NUMBER_IN_LOG"
    assert MOD.classify_first_log("202500210", "202606946", None) == "NO_LOG"


def test_complementary_evidence_only_promotes_unambiguous_side():
    assert (
        MOD.classify_complementary_evidence(
            "202604876", "202603749", {"202603461", "202603525", "202603749"}
        )
        == "EVIDENCE_SUPPORTS_ENROLLMENT"
    )
    assert (
        MOD.classify_complementary_evidence("202607403", "202607404", {"202607403", "202607404"})
        == "BOTH_IN_HISTORY"
    )
    assert (
        MOD.classify_complementary_evidence("202500027", "202604841", {"202603478"})
        == "ONLY_THIRD_NUMBERS"
    )


def test_safe_candidate_requires_single_regular_and_same_projection():
    candidate = {
        "student_id": "s1",
        "student_number_before": "202699999",
        "target_number": "202601234",
        "primary_enrollment_id": "e1",
        "school_id": "school-1",
        "class_id": "class-1",
    }
    student = {
        "id": "s1",
        "status": "active",
        "enrollment_number": "202699999",
        "school_id": "school-1",
        "class_id": "class-1",
    }
    primary = {
        "id": "e1",
        "student_id": "s1",
        "status": "active",
        "enrollment_number": "202601234",
        "school_id": "school-1",
        "class_id": "class-1",
    }
    blockers = MOD.evaluate_safety(
        candidate=candidate,
        student=student,
        primary=primary,
        active_regular=[primary],
        target_student_owners=set(),
        target_enrollment_owners={"s1"},
    )
    assert blockers == []
    assert MOD.blocker_bucket(blockers) == "READY_SAFE"

    collision = MOD.evaluate_safety(
        candidate=candidate,
        student=student,
        primary=primary,
        active_regular=[primary],
        target_student_owners={"other"},
        target_enrollment_owners={"s1"},
    )
    assert "TARGET_NUMBER_USED_BY_OTHER_STUDENT" in collision
    assert MOD.blocker_bucket(collision) == "BLOCKED_COLLISION"


def test_manifest_hash_is_deterministic_for_key_order():
    left = {"b": 2, "a": {"z": 9, "y": [3, 2, 1]}}
    right = {"a": {"y": [3, 2, 1], "z": 9}, "b": 2}
    assert MOD.manifest_sha256(left) == MOD.manifest_sha256(right)
