from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_p0f7_2_teacher_assignment_forensic.py"
P0F3_PATH = ROOT / "scripts" / "audit_duplicate_course_semantic_collision_p0f3.py"
P0F6_PATH = ROOT / "scripts" / "build_p0f6_private_human_adjudication_station.py"
P0F7_PATH = ROOT / "scripts" / "audit_p0f7_sealed_decisions_execution_preflight.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p0f72 = _load(SCRIPT, "p0f72_test")
p0f3 = _load(P0F3_PATH, "p0f3_for_p0f72")
p0f6 = _load(P0F6_PATH, "p0f6_for_p0f72")
p0f7 = _load(P0F7_PATH, "p0f7_for_p0f72")


def _review_unit() -> dict:
    return {
        "review_unit_id": "u1",
        "unit_type": "GRADE_FIELD_DECISION",
        "field_name": "b1",
        "student_id": "student-1",
        "context": {"academic_year": 2026},
        "source_document_ids": ["grade-source"],
        "target_document_ids": ["grade-target"],
        "source_actor": {}, "target_actor": {},
        "source_value": 8, "target_value": 9,
        "decision_contract": {
            "status": "PENDING_HUMAN_DECISION",
            "allowed_decisions": ["KEEP_SOURCE", "KEEP_TARGET", "MANUAL_RECONCILIATION"],
            "automatic_recommendation": None,
            "decision": None, "decision_note": None,
        },
    }


def _packet() -> dict:
    packet = {
        "phase": p0f6.P0F5_PHASE,
        "manifest_version": 1,
        "mode": "READ_ONLY_PRIVATE_HUMAN_REVIEW_PACKET",
        "status": "PASS",
        "generated_at_utc": "2026-08-28T00:00:00+00:00",
        "academic_year": 2026,
        "mantenedora_id": "tenant-1",
        "source_p0f4_manifest_sha256": "p0f4",
        "summary": {
            "duplicate_identity_groups": 1, "p0f4_conflicts": 1,
            "conflicts_expanded": 1, "complete_conflict_coverage": True,
            "review_units": 1, "review_units_by_collection": {"grades": 1},
            "review_units_by_type": {"GRADE_FIELD_DECISION": 1},
            "unresolved_review_conflicts": 0, "pending_human_decisions": 1,
            "automatic_resolution": False, "database_mutation": False,
        },
        "safety": {"automatic_recommendation": False, "automatic_resolution": False},
        "unresolved_conflicts": [],
        "cases": [{
            "group_number": 1,
            "identity": {"display_name": "Geografia", "mantenedora_id": "tenant-1"},
            "source_id": "course-source", "target_id": "course-target",
            "p0f4_conflicts": 1, "review_units": 1,
            "conflicts": [{
                "conflict_id": "conflict-1", "collection": "grades",
                "key_sha256": "key", "p0f3_classification": "VALUE_CONFLICT",
                "field_names": ["b1"], "review_units": [_review_unit()],
                "expansion_error": None, "automatic_resolution": False,
            }],
            "automatic_resolution": False, "database_mutation": False,
        }],
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
        "source_review_unit_count": 1,
        "reviewer": {"name": "R", "role": "G", "identifier": None, "authorized_acknowledgement": True},
        "summary": {"decisions": 1, "decision_counts": {"KEEP_TARGET": 1}, "complete_decision_coverage": True, "pending_human_decisions": 0, "automatic_recommendation": False, "automatic_resolution": False, "database_mutation": False},
        "safety": {"decision_values_are_human_supplied": True, "no_automatic_decision": True, "no_database_access": True, "no_database_mutation": True, "not_authorization_for_executor": True},
        "decisions": [{"review_unit_id": "u1", "decision": "KEEP_TARGET", "decision_note": None}],
    }
    sealed["decision_manifest_sha256"] = p0f6.canonical_sha256(sealed)
    return sealed


def _p0f3_report() -> dict:
    empty = {"classifications": {}, "hard_conflicts": 0, "collision_items": 0}
    return {
        "phase": p0f3.PHASE_ID, "status": "PASS", "summary": {"database_mutation": False},
        "cases": [{
            "group_number": 1, "identity": {"display_name": "Geografia"},
            "source_id": "course-source", "target_id": "course-target",
            "reference_counts": {"grades": {"course-source": 1, "course-target": 1}, "teacher_assignments": {"course-source": 1, "course-target": 1}},
            "unsupported_reference_count": 0, "hard_conflicts": 1,
            "analyses": {
                "grades": {"classifications": {"VALUE_CONFLICT": 1}, "hard_conflicts": 1, "collision_items": 1},
                "attendance": dict(empty), "learning_objects": dict(empty),
                "teacher_assignments": {"classifications": {"DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW": 1}, "hard_conflicts": 0, "collision_items": 1},
                "teacher_class_assignments": dict(empty),
                "class_schedules": {"same_day_slot_collisions": 0, "unresolved_slot_identities": 0, "hard_conflicts": 0, "collision_items": 0},
                "student_dependencies": dict(empty),
            },
        }],
    }


def _current_docs() -> dict:
    return {"grades": {
        "grade-source": {"id": "grade-source", "course_id": "course-source", "student_id": "student-1", "class_id": "class-1", "academic_year": 2026, "b1": 8},
        "grade-target": {"id": "grade-target", "course_id": "course-target", "student_id": "student-1", "class_id": "class-1", "academic_year": 2026, "b1": 9},
    }}


def _preflight(packet: dict, sealed: dict) -> dict:
    return p0f7.build_preflight(packet, sealed, _p0f3_report(), _current_docs())


def _source_assignment(**overrides) -> dict:
    row = {"id": "ta-source", "course_id": "course-source", "staff_id": "staff-1", "class_id": "class-1", "academic_year": 2026, "status": "ativo", "school_id": "school-1", "carga_horaria_semanal": 4, "is_substituicao": False, "substituted_staff_id": None, "data_inicio_substituicao": None, "data_fim_substituicao": None}
    row.update(overrides)
    return row


def _target_assignment(**overrides) -> dict:
    row = {"id": "ta-target", "course_id": "course-target", "staff_id": "staff-1", "class_id": "class-1", "academic_year": 2026, "status": "ativo", "school_id": "school-1", "carga_horaria_semanal": 6, "is_substituicao": False, "substituted_staff_id": None, "data_inicio_substituicao": None, "data_fim_substituicao": None}
    row.update(overrides)
    return row


def test_validate_artifacts_locates_exact_geografia_blocker():
    packet = _packet(); sealed = _sealed(packet); preflight = _preflight(packet, sealed)
    v = p0f72.validate_artifacts(packet, sealed, preflight, "Geografia")
    assert v["source_id"] == "course-source"
    assert v["target_id"] == "course-target"
    assert v["expected_count"] == 1
    assert v["expected_classification"] == "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW"


def test_build_divergent_pairs_reports_exact_fields_without_recommendation():
    pairs = p0f72.build_divergent_pairs([_source_assignment()], [_target_assignment()], p0f3)
    assert len(pairs) == 1
    assert pairs[0]["classification"] == "DIVERGENT_ACTIVE_ASSIGNMENT_REQUIRES_REVIEW"
    assert pairs[0]["field_names"] == ["carga_horaria_semanal"]


def test_exact_duplicate_is_not_human_review_pair():
    target = _target_assignment(carga_horaria_semanal=4)
    assert p0f72.build_divergent_pairs([_source_assignment()], [target], p0f3) == []


def test_substitution_is_fail_closed_review():
    target = _target_assignment(is_substituicao=True, substituted_staff_id="staff-2")
    pairs = p0f72.build_divergent_pairs([_source_assignment()], [target], p0f3)
    assert len(pairs) == 1
    assert pairs[0]["classification"] == "SUBSTITUTION_COEXISTENCE_REQUIRES_REVIEW"


def test_safe_assignment_view_exposes_only_assignment_metadata():
    view = p0f72._safe_assignment_view(_source_assignment(created_by="user-1"), {"user-1": "Gestor"})
    assert view["carga_horaria_semanal"] == 4
    assert view["created_by"]["name"] == "Gestor"
    assert "student_id" not in view
    assert "course_id" not in view


def test_audit_summary_has_metadata_not_payload_values():
    events = [{"document_id": "ta-source", "action": "create", "timestamp": "2026-01-01T10:00:00Z", "user_id": "user-1"}, {"document_id": "ta-source", "action": "update", "timestamp": "2026-02-01T10:00:00Z", "user_id": "user-1"}]
    summary = p0f72._audit_summary(events, {"user-1": "Gestor"})
    assert summary["event_count"] == 2
    assert summary["action_counts"] == {"create": 1, "update": 1}
    assert summary["actors"][0]["name"] == "Gestor"
    assert "old_value" not in summary and "new_value" not in summary


def test_rejects_tampered_p0f7_preflight():
    packet = _packet(); sealed = _sealed(packet); preflight = _preflight(packet, sealed)
    preflight["summary"]["blockers"] = 99
    with pytest.raises(ValueError, match="P0F7_SHA_MISMATCH"):
        p0f72.validate_artifacts(packet, sealed, preflight, "Geografia")


def test_private_json_is_0600(tmp_path: Path):
    payload = {"phase": p0f72.PHASE_ID, "status": "PASS"}
    out = tmp_path / "forensic.json"
    p0f72._private_write_json(out, payload)
    assert oct(out.stat().st_mode & 0o777) == "0o600"
    assert json.loads(out.read_text(encoding="utf-8"))["status"] == "PASS"


def test_script_has_no_mutator_or_apply_surface():
    p0f72.assert_read_only()
    source = SCRIPT.read_text(encoding="utf-8")
    executable = "\n".join(line for line in source.splitlines() if "MUTATOR_TOKENS" not in line and not line.lstrip().startswith('"'))
    for token in p0f72.MUTATOR_TOKENS:
        assert token not in executable
    assert "--apply" not in source
