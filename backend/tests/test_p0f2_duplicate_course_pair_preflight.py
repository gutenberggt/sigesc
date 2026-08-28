from __future__ import annotations

import importlib.util
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "audit_duplicate_course_pair_preflight_p0f2.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "audit_duplicate_course_pair_preflight_p0f2",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase_is_explicit_and_read_only():
    module = load_module()
    assert module.PHASE_ID == "P0F2-DUPLICATE-COURSE-PAIR-PREFLIGHT-READ-ONLY-2026"
    assert module.MANIFEST_VERSION == 1
    module.assert_read_only()


def test_no_apply_or_rollback_mode_exists():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--apply"' not in source
    assert '"--rollback"' not in source


def test_duplicate_identity_matches_p0f_semantics():
    module = load_module()
    a = {"mantenedora_id": "TENANT", "name": "Ciências", "nivel_ensino": "FINAL"}
    b = {"mantenedora_id": "TENANT", "name": "CIÊNCIAS", "nivel_ensino": "final"}
    assert module.course_identity_key(a) == module.course_identity_key(b)


def test_historical_kept_candidate_requires_current_group_id():
    module = load_module()
    history = [
        {
            "extra_data": {
                "consolidated": [
                    {
                        "removed_ids": ["old-1"],
                        "kept_id": "current-a",
                    }
                ]
            }
        },
        {
            "extra_data": {
                "consolidated": [
                    {
                        "removed_ids": ["old-2"],
                        "kept_id": "outside-group",
                    }
                ]
            }
        },
    ]
    candidates, edges = module.historical_kept_candidates(
        history,
        {"current-a", "current-b"},
    )
    assert candidates == ["current-a"]
    assert {"removed_id": "old-1", "kept_id": "current-a"} in edges
    assert "outside-group" not in candidates


def test_multiple_historical_kept_candidates_block_automatic_direction():
    module = load_module()
    assert module.classify_pair(
        kept_candidates=["a", "b"],
        scope_overlap_signals=0,
    ) == "NO_UNIQUE_HISTORICAL_KEPT_BLOCKED"


def test_unique_historical_kept_still_requires_review_without_overlap():
    module = load_module()
    assert module.classify_pair(
        kept_candidates=["a"],
        scope_overlap_signals=0,
    ) == "HISTORICAL_KEPT_NO_SCOPE_OVERLAP_REQUIRES_REVIEW"


def test_scope_overlap_never_declares_safe_merge():
    module = load_module()
    assert module.classify_pair(
        kept_candidates=["a"],
        scope_overlap_signals=3,
    ) == "HISTORICAL_KEPT_WITH_SCOPE_OVERLAP_REQUIRES_REVIEW"


def test_teacher_assignment_scope_uses_staff_class_year():
    module = load_module()
    row = {
        "staff_id": "staff-1",
        "class_id": "class-1",
        "academic_year": 2026,
        "course_id": "course-x",
    }
    assert module.scope_key("teacher_assignments", row) == (
        ("staff_id", "staff-1"),
        ("class_id", "class-1"),
        ("academic_year", "2026"),
    )


def test_scope_requires_structural_identifier():
    module = load_module()
    assert module.scope_key(
        "attendance",
        {"academic_year": 2026, "date": "2026-08-01"},
    ) is None


def test_compact_summary_omits_full_audit_payload():
    module = load_module()
    report = {
        "phase": module.PHASE_ID,
        "mode": "READ_ONLY_PREFLIGHT",
        "status": "PASS",
        "summary": {"database_mutation": False},
        "cases": [
            {
                "group_number": 1,
                "identity": {"display_name": "História"},
                "course_ids": ["a", "b"],
                "historical_canonical_candidate": "a",
                "hypothetical_directions": [{"source_id": "b", "target_id": "a"}],
                "scope_overlap_signals": 1,
                "shared_document_signals": 0,
                "forensic_classification": "HISTORICAL_KEPT_WITH_SCOPE_OVERLAP_REQUIRES_REVIEW",
                "collection_analysis": [
                    {
                        "collection": "grades",
                        "reference_counts": {"a": 10, "b": 5},
                        "shared_scope_count": 1,
                        "shared_document_count": 0,
                        "shared_scope_examples": [{"student_id": "secret"}],
                    }
                ],
            }
        ],
        "manifest_sha256": "abc",
    }
    compact = module.compact_summary(report)
    assert compact["cases"][0]["collections"][0]["shared_scope_count"] == 1
    assert "shared_scope_examples" not in compact["cases"][0]["collections"][0]


def test_manifest_sha_is_deterministic():
    module = load_module()
    a = {"z": 1, "a": [2, 3]}
    b = {"a": [2, 3], "z": 1}
    assert module._canonical_json_sha256(a) == module._canonical_json_sha256(b)
