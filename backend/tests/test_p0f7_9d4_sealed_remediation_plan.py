from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import build_p0f7_9d4_sealed_remediation_plan as mod  # noqa: E402


def _sources():
    d2 = {
        "phase": mod.D2_PHASE,
        "status": "PASS",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "summary": {
            "confirmed_conflicts": 2,
            "unique_safe_target": 2,
            "multiple_safe_targets_review": 0,
            "no_safe_target": 0,
            "proposal_only": True,
        },
        "resolutions": [
            {
                "assignment_id": "a-2",
                "school_id": "s-1",
                "class_id": "c-2",
                "class_name": "8º ANO B",
                "source_course_id": "old-2",
                "source_course_name": "Ciências",
                "source_course_level": "fundamental_anos_finais",
                "integrity_code": "TEACHER_ASSIGNMENT_SERIES_MISMATCH",
                "resolution": "UNIQUE_SAFE_TARGET",
                "validated_targets": [
                    {
                        "course_id": "new-2",
                        "course_name": "Ciências",
                        "course_level": "fundamental_anos_finais",
                        "write_policy": "EXPLICIT_AND_MATRIX_FULL_MATCH",
                        "fit_classification": "STRONG",
                        "fit_rank": 3,
                    }
                ],
            },
            {
                "assignment_id": "a-1",
                "school_id": "s-1",
                "class_id": "c-1",
                "class_name": "3ª E 4ª ETAPA MULTI",
                "source_course_id": "old-1",
                "source_course_name": "Arte",
                "source_course_level": "fundamental_anos_finais",
                "integrity_code": "TEACHER_ASSIGNMENT_LEVEL_MISMATCH",
                "resolution": "UNIQUE_SAFE_TARGET",
                "validated_targets": [
                    {
                        "course_id": "new-1",
                        "course_name": "Arte",
                        "course_level": "eja_final",
                        "write_policy": "LEVEL_MATCH_NO_SERIES_SCOPE",
                        "fit_classification": "REVIEW",
                        "fit_rank": 2,
                    }
                ],
            },
        ],
    }
    d3 = {
        "phase": mod.D3_PHASE,
        "status": "PASS",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "source_p0f7_9d2_report_sha256": mod._canonical_sha256(d2),
        "summary": {
            "unique_safe_target_source": 2,
            "clear_for_remediation_planning": 2,
            "active_target_already_exists": 0,
            "source_drift_review_required": 0,
            "proposal_only": True,
        },
        "results": [
            {
                "assignment_id": "a-1",
                "school_id": "s-1",
                "class_id": "c-1",
                "source_course_id": "old-1",
                "target_course_id": "new-1",
                "preflight": mod.EXPECTED_PREFLIGHT,
                "active_collision_assignment_ids": [],
                "inactive_collision_assignment_ids": [],
                "staff_id_present": True,
            },
            {
                "assignment_id": "a-2",
                "school_id": "s-1",
                "class_id": "c-2",
                "source_course_id": "old-2",
                "target_course_id": "new-2",
                "preflight": mod.EXPECTED_PREFLIGHT,
                "active_collision_assignment_ids": [],
                "inactive_collision_assignment_ids": ["historical-1"],
                "staff_id_present": True,
            },
        ],
    }
    return d2, d3


def test_build_plan_is_deterministic_and_non_executable():
    d2, d3 = _sources()
    first = mod.build_plan(d2, d3)
    second = mod.build_plan(copy.deepcopy(d2), copy.deepcopy(d3))

    assert first == second
    assert first["status"] == "PASS"
    assert first["mode"] == "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
    assert first["summary"]["planned_assignments"] == 2
    assert first["summary"]["production_writes"] is False
    assert first["execution_contract"]["executable"] is False
    assert first["execution_contract"]["requires_separate_explicit_production_write_authorization"] is True
    assert [row["assignment_id"] for row in first["entries"]] == ["a-1", "a-2"]
    assert first["entries"][0]["intended_mutation"] == {"field": "course_id", "from": "old-1", "to": "new-1"}
    assert first["entries"][0]["rollback"] == {"field": "course_id", "from": "new-1", "to": "old-1"}
    assert len(first["plan_sha256"]) == 64


def test_rejects_any_collision_or_drift_summary():
    d2, d3 = _sources()
    d3["summary"]["clear_for_remediation_planning"] = 1
    d3["summary"]["active_target_already_exists"] = 1
    with pytest.raises(ValueError, match="NOT_ALL_UNIQUE_TARGETS_CLEAR"):
        mod.build_plan(d2, d3)


def test_rejects_d2_d3_chain_mismatch():
    d2, d3 = _sources()
    d3["source_p0f7_9d2_report_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="D2_D3_CHAIN_MISMATCH"):
        mod.build_plan(d2, d3)


def test_rejects_row_target_drift():
    d2, d3 = _sources()
    d3["results"][0]["target_course_id"] = "unexpected-target"
    with pytest.raises(ValueError, match="TARGET_COURSE_DRIFT"):
        mod.build_plan(d2, d3)
