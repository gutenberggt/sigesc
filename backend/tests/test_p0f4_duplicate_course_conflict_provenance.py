from __future__ import annotations

import importlib.util
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "audit_duplicate_course_conflict_provenance_p0f4.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "audit_duplicate_course_conflict_provenance_p0f4", SCRIPT
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_is_explicit_and_read_only():
    m = load_module()
    assert m.PHASE_ID == "P0F4-DUPLICATE-COURSE-CONFLICT-PROVENANCE-READ-ONLY-2026"
    assert m.MANIFEST_VERSION == 1
    m.assert_read_only()


def test_no_apply_or_rollback_mode_exists():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--apply"' not in source
    assert '"--rollback"' not in source


def test_safe_metadata_is_allow_list_and_redacts_pedagogical_payloads():
    m = load_module()
    raw = {
        "id": "doc-1",
        "student_id": "student-1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_by": "user-1",
        "version": 3,
        "b1": 8.5,
        "records": [{"student_id": "student-1", "status": "F"}],
        "content": "conteudo-pedagogico-secreto",
        "observations": "observacao-secreta",
        "methodology": "metodologia-secreta",
    }
    safe = m.safe_metadata(raw)
    assert safe == {
        "id": "doc-1",
        "student_id": "student-1",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_by": "user-1",
        "version": 3,
    }
    rendered = str(safe)
    assert "8.5" not in rendered
    assert "conteudo-pedagogico-secreto" not in rendered
    assert "observacao-secreta" not in rendered
    assert "metodologia-secreta" not in rendered
    assert "status" not in rendered


def test_payload_fields_are_not_allowed_metadata_fields():
    m = load_module()
    forbidden = {
        "b1", "b2", "b3", "b4", "rec_s1", "rec_s2", "recovery",
        "records", "content", "observations", "methodology", "resources",
        "skill_codigos", "adaptation_ids", "evidencia_aprendizagem",
        "pratica_pedagogica",
    }
    assert forbidden.isdisjoint(set(m.SAFE_METADATA_FIELDS))


def test_provenance_state_bilateral_with_audit():
    m = load_module()
    state = m.classify_provenance(
        [{"created_at": "2026-01-01"}],
        [{"recorded_by": "u2"}],
        1,
        2,
    )
    assert state == "BILATERAL_PROVENANCE_WITH_AUDIT"


def test_provenance_state_bilateral_without_complete_audit():
    m = load_module()
    state = m.classify_provenance(
        [{"created_at": "2026-01-01"}],
        [{"created_at": "2026-01-02"}],
        1,
        0,
    )
    assert state == "BILATERAL_PROVENANCE_NO_COMPLETE_AUDIT"


def test_provenance_state_partial_and_sparse():
    m = load_module()
    assert m.classify_provenance(
        [{"created_at": "2026-01-01"}], [], 0, 0
    ) == "PARTIAL_PROVENANCE"
    assert m.classify_provenance([], [], 0, 0) == "SPARSE_PROVENANCE"


def test_resolution_requirements_never_choose_a_winner():
    m = load_module()
    assert m.resolution_requirement("grades") == "PEDAGOGICAL_GRADE_DECISION_REQUIRED"
    assert m.resolution_requirement("attendance") == "ATTENDANCE_DECISION_REQUIRED"
    assert m.resolution_requirement("learning_objects") == "PEDAGOGICAL_CONTENT_DECISION_REQUIRED"
    assert m.resolution_requirement("unknown") == "UNSUPPORTED_CONFLICT_TYPE_BLOCKED"


def test_hard_example_filter_is_collection_specific():
    m = load_module()
    analysis = {
        "examples": [
            {"classification": "VALUE_CONFLICT", "key_sha256": "a"},
            {"classification": "COMPLEMENTARY_MERGEABLE", "key_sha256": "b"},
            {"classification": "EXACT_EQUIVALENT", "key_sha256": "c"},
        ]
    }
    out = m._hard_examples(analysis, "grades")
    assert [row["key_sha256"] for row in out] == ["a"]


def test_audit_summary_contains_no_old_or_new_values():
    m = load_module()
    rows = [
        {
            "document_id": "d1", "action": "update", "timestamp": "2026-01-02",
            "user_id": "u1", "old_value": {"b1": 3}, "new_value": {"b1": 8},
        },
        {
            "document_id": "d1", "action": "create", "timestamp": "2026-01-01",
            "user": {"id": "u2", "full_name": "Nome Privado"},
        },
    ]
    summary = m.summarize_audit(rows)
    assert summary["event_count"] == 2
    assert summary["action_counts"] == {"create": 1, "update": 1}
    assert summary["actor_count"] == 2
    rendered = str(summary)
    assert "old_value" not in rendered
    assert "new_value" not in rendered
    assert "Nome Privado" not in rendered
    assert "b1" not in rendered


def test_compact_summary_excludes_conflict_details_and_metadata():
    m = load_module()
    report = {
        "phase": m.PHASE_ID,
        "mode": "READ_ONLY_CONFLICT_PROVENANCE_DOSSIER",
        "status": "PASS",
        "summary": {"p0f3_hard_conflicts": 1},
        "cases": [{
            "group_number": 1,
            "identity": {"display_name": "Ciências"},
            "source_id": "src",
            "target_id": "tgt",
            "p0f3_hard_conflicts": 1,
            "conflicts_documented": 1,
            "conflicts_by_collection": {"grades": 1},
            "resolution_requirements": {"PEDAGOGICAL_GRADE_DECISION_REQUIRED": 1},
            "provenance_states": {"BILATERAL_PROVENANCE_WITH_AUDIT": 1},
            "conflicts": [{
                "source_metadata": [{"student_id": "private-ish-id"}],
                "target_metadata": [{"student_id": "other-id"}],
            }],
        }],
        "manifest_sha256": "abc",
    }
    compact = m.compact_summary(report)
    rendered = str(compact)
    assert "private-ish-id" not in rendered
    assert "other-id" not in rendered
    assert "conflicts" not in compact["cases"][0]


def test_p0f3_script_dependency_exists():
    m = load_module()
    assert m.P0F3_PATH.exists()
