from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "audit_p0f7_sealed_decisions_execution_preflight.py"
)
spec = importlib.util.spec_from_file_location("p0f7", SCRIPT)
assert spec and spec.loader
p0f7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p0f7)

P0F6_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "build_p0f6_private_human_adjudication_station.py"
)
p0f6_spec = importlib.util.spec_from_file_location("p0f6_test_contract", P0F6_PATH)
assert p0f6_spec and p0f6_spec.loader
p0f6 = importlib.util.module_from_spec(p0f6_spec)
p0f6_spec.loader.exec_module(p0f6)


def _unit(unit_id: str, field: str, source_value, target_value) -> dict:
    return {
        "review_unit_id": unit_id,
        "unit_type": "GRADE_FIELD_DECISION",
        "field_name": field,
        "student_id": "student-1",
        "context": {
            "school_id": "school-1",
            "class_id": "class-1",
            "academic_year": 2026,
            "student_id": "student-1",
        },
        "source_document_ids": ["grade-source"],
        "target_document_ids": ["grade-target"],
        "source_actor": {},
        "target_actor": {},
        "source_value": source_value,
        "target_value": target_value,
        "decision_contract": {
            "status": "PENDING_HUMAN_DECISION",
            "allowed_decisions": [
                "KEEP_SOURCE",
                "KEEP_TARGET",
                "MANUAL_RECONCILIATION",
            ],
            "automatic_recommendation": None,
            "decision": None,
            "decision_note": None,
        },
    }


def _packet() -> dict:
    units = [
        _unit("u-source", "b1", 10, 5),
        _unit("u-target", "b2", 7, 8),
        _unit("u-manual", "b3", 6, 9),
    ]
    packet = {
        "phase": p0f6.P0F5_PHASE,
        "manifest_version": 1,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": "PASS",
        "generated_at_utc": "2026-08-28T00:00:00+00:00",
        "academic_year": 2026,
        "mantenedora_id": "tenant-1",
        "source_p0f4_manifest_sha256": "p0f4-sha",
        "summary": {
            "duplicate_identity_groups": 1,
            "p0f4_conflicts": 1,
            "conflicts_expanded": 1,
            "complete_conflict_coverage": True,
            "review_units": 3,
            "review_units_by_collection": {"grades": 3},
            "review_units_by_type": {"GRADE_FIELD_DECISION": 3},
            "unresolved_review_conflicts": 0,
            "pending_human_decisions": 3,
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "safety": {
            "automatic_recommendation": False,
            "automatic_resolution": False,
        },
        "unresolved_conflicts": [],
        "cases": [
            {
                "group_number": 1,
                "identity": {"display_name": "Ciências"},
                "source_id": "course-source",
                "target_id": "course-target",
                "p0f4_conflicts": 1,
                "review_units": 3,
                "conflicts": [
                    {
                        "conflict_id": "conflict-1",
                        "collection": "grades",
                        "key_sha256": "key-1",
                        "p0f3_classification": "VALUE_CONFLICT",
                        "field_names": ["b1", "b2", "b3"],
                        "review_units": units,
                        "expansion_error": None,
                        "automatic_resolution": False,
                    }
                ],
                "automatic_resolution": False,
                "database_mutation": False,
            }
        ],
    }
    packet["manifest_sha256"] = p0f6.canonical_sha256(packet)
    return packet


def _sealed(packet: dict) -> dict:
    sealed = {
        "phase": p0f6.SEALED_DECISION_PHASE,
        "manifest_version": 1,
        "status": "SEALED_COMPLETE_HUMAN_DECISIONS",
        "generated_at_utc": "2026-08-28T01:00:00+00:00",
        "source_p0f5_manifest_sha256": packet["manifest_sha256"],
        "source_review_unit_count": 3,
        "reviewer": {
            "name": "Responsável",
            "role": "Gestor",
            "identifier": None,
            "authorized_acknowledgement": True,
        },
        "summary": {
            "decisions": 3,
            "decision_counts": {
                "KEEP_SOURCE": 1,
                "KEEP_TARGET": 1,
                "MANUAL_RECONCILIATION": 1,
            },
            "complete_decision_coverage": True,
            "pending_human_decisions": 0,
            "automatic_recommendation": False,
            "automatic_resolution": False,
            "database_mutation": False,
        },
        "safety": {
            "decision_values_are_human_supplied": True,
            "no_automatic_decision": True,
            "no_database_access": True,
            "no_database_mutation": True,
            "not_authorization_for_executor": True,
        },
        "decisions": [
            {
                "review_unit_id": "u-source",
                "decision": "KEEP_SOURCE",
                "decision_note": None,
            },
            {
                "review_unit_id": "u-target",
                "decision": "KEEP_TARGET",
                "decision_note": None,
            },
            {
                "review_unit_id": "u-manual",
                "decision": "MANUAL_RECONCILIATION",
                "decision_note": "Necessária conciliação humana final.",
            },
        ],
    }
    sealed["decision_manifest_sha256"] = p0f6.canonical_sha256(sealed)
    return sealed


def _p0f3() -> dict:
    return {
        "phase": "P0F3-DUPLICATE-COURSE-SEMANTIC-COLLISION-READ-ONLY-2026",
        "status": "PASS",
        "summary": {"database_mutation": False},
        "cases": [
            {
                "group_number": 1,
                "identity": {"display_name": "Ciências"},
                "source_id": "course-source",
                "target_id": "course-target",
                "reference_counts": {
                    "grades": {"course-source": 1, "course-target": 1},
                    "attendance": {"course-source": 2, "course-target": 1},
                    "teacher_assignments": {
                        "course-source": 1,
                        "course-target": 1,
                    },
                },
                "unsupported_reference_count": 0,
                "hard_conflicts": 1,
                "analyses": {
                    "grades": {
                        "classifications": {
                            "VALUE_CONFLICT": 1,
                            "COMPLEMENTARY_MERGEABLE": 2,
                        },
                        "hard_conflicts": 1,
                        "collision_items": 3,
                    },
                    "attendance": {
                        "classifications": {"EXACT_EQUIVALENT": 1},
                        "hard_conflicts": 0,
                        "collision_items": 1,
                    },
                    "learning_objects": {
                        "classifications": {},
                        "hard_conflicts": 0,
                        "collision_items": 0,
                    },
                    "teacher_assignments": {
                        "classifications": {
                            "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW": 1
                        },
                        "hard_conflicts": 0,
                        "collision_items": 1,
                    },
                    "teacher_class_assignments": {
                        "classifications": {},
                        "hard_conflicts": 0,
                        "collision_items": 0,
                    },
                    "class_schedules": {
                        "same_day_slot_collisions": 0,
                        "unresolved_slot_identities": 0,
                        "hard_conflicts": 0,
                        "collision_items": 0,
                    },
                    "student_dependencies": {
                        "hard_conflicts": 0,
                        "collision_items": 0,
                    },
                },
            }
        ],
    }


def _current_docs() -> dict:
    return {
        "grades": {
            "grade-source": {
                "id": "grade-source",
                "course_id": "course-source",
                "student_id": "student-1",
                "class_id": "class-1",
                "academic_year": 2026,
                "b1": 10,
                "b2": 7,
                "b3": 6,
            },
            "grade-target": {
                "id": "grade-target",
                "course_id": "course-target",
                "student_id": "student-1",
                "class_id": "class-1",
                "academic_year": 2026,
                "b1": 5,
                "b2": 8,
                "b3": 9,
            },
        }
    }


def test_preflight_separates_deterministic_manual_and_semantic_blockers():
    packet = _packet()
    sealed = _sealed(packet)
    report = p0f7.build_preflight(packet, sealed, _p0f3(), _current_docs())

    assert report["status"] == "PASS"
    assert report["summary"]["review_units"] == 3
    assert report["summary"]["decision_counts"] == {
        "KEEP_SOURCE": 1,
        "KEEP_TARGET": 1,
        "MANUAL_RECONCILIATION": 1,
    }
    assert report["summary"]["deterministic_human_decision_units"] == 2
    assert report["summary"]["manual_reconciliation_units"] == 1
    assert report["summary"]["human_target_change_intents"] == 1
    assert report["summary"]["human_target_preserve_intents"] == 1
    assert report["summary"]["snapshot_drift_units"] == 0
    assert report["summary"]["executor_readiness"] == "BLOCKED"
    assert report["summary"]["p0f7_1_structured_manual_reconciliation_required"] is True
    assert report["summary"]["final_executor_write_count"] is None

    reasons = [row["reason"] for row in report["blockers"]]
    assert "MANUAL_RECONCILIATION_REQUIRES_STRUCTURED_VALUE" in reasons
    assert "TEACHER_ASSIGNMENT_SEMANTIC_REVIEW_REQUIRED" in reasons

    assert len(report["human_operation_intents"]) == 3
    assert all("source_value" not in row for row in report["human_operation_intents"])
    assert all("target_value" not in row for row in report["human_operation_intents"])
    assert report["safety"]["sensitive_academic_values_copied_to_report"] is False
    assert report["safety"]["not_authorization_for_executor"] is True
    assert report["safety"]["database_mutation"] is False


def test_preflight_detects_snapshot_value_drift():
    packet = _packet()
    sealed = _sealed(packet)
    docs = _current_docs()
    docs["grades"]["grade-target"]["b1"] = 4

    report = p0f7.build_preflight(packet, sealed, _p0f3(), docs)

    assert report["summary"]["snapshot_drift_units"] == 1
    assert report["summary"]["blocker_counts"]["REVIEW_UNIT_VALUE_DRIFT"] == 1
    assert report["summary"]["executor_readiness"] == "BLOCKED"


def test_preflight_rejects_tampered_sealed_manifest():
    packet = _packet()
    sealed = _sealed(packet)
    sealed["decisions"][0]["decision"] = "KEEP_TARGET"

    with pytest.raises(ValueError, match="SEALED_DECISION_MANIFEST_SHA_MISMATCH"):
        p0f7.validate_chain(packet, sealed)


def test_preflight_rejects_manual_without_note_even_with_recomputed_sha():
    packet = _packet()
    sealed = _sealed(packet)
    sealed["decisions"][2]["decision_note"] = ""
    sealed.pop("decision_manifest_sha256")
    sealed["decision_manifest_sha256"] = p0f6.canonical_sha256(sealed)

    with pytest.raises(ValueError, match="SEALED_MANUAL_NOTE_REQUIRED:u-manual"):
        p0f7.validate_chain(packet, sealed)


def test_private_output_is_0600_and_report_sha_is_canonical(tmp_path: Path):
    report = p0f7.build_preflight(_packet(), _sealed(_packet()), _p0f3(), _current_docs())
    out = tmp_path / "p0f7.json"
    p0f7._private_write_json(out, report)

    assert oct(out.stat().st_mode & 0o777) == "0o600"
    stored = json.loads(out.read_text(encoding="utf-8"))
    expected_sha = stored.pop("manifest_sha256")
    assert p0f7._canonical_sha256(stored) == expected_sha


def test_script_has_no_database_mutator_surface():
    p0f7.assert_read_only()
    source = SCRIPT.read_text(encoding="utf-8")
    executable = "\n".join(
        line for line in source.splitlines()
        if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"')
    )
    for token in p0f7.MUTATOR_TOKENS:
        assert token not in executable
