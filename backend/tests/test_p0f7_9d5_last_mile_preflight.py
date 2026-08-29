from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.audit_p0f7_9d5_last_mile_preflight_offline import build_report
from scripts.build_p0f7_9d5_last_mile_snapshot_js import build_js


def canonical(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def make_plan():
    entries = []
    for index in range(1, 24):
        assignment_id = f"a-{index:02d}"
        school_id = "school-1"
        class_id = f"class-{index:02d}"
        source_id = f"source-{index:02d}"
        target_id = f"target-{index:02d}"
        entries.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "academic_year": 2026,
                "source": {"course_id": source_id},
                "target": {
                    "course_id": target_id,
                    "write_policy": "LEVEL_MATCH_NO_SERIES_SCOPE",
                },
                "preconditions": {
                    "assignment_id_equals": assignment_id,
                    "school_id_equals": school_id,
                    "class_id_equals": class_id,
                    "course_id_equals": source_id,
                },
            }
        )
    plan = {
        "phase": "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026",
        "status": "PASS",
        "mode": "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "summary": {"planned_assignments": 23},
        "execution_contract": {"executable": False},
        "entries": entries,
    }
    plan["plan_sha256"] = canonical(plan)
    return plan


def make_snapshot(plan, *, replica=True):
    assignments = []
    classes = []
    courses = []
    for entry in plan["entries"]:
        assignments.append(
            {
                "id": entry["assignment_id"],
                "staff_id": f"staff-{entry['ordinal']:02d}",
                "school_id": entry["school_id"],
                "class_id": entry["class_id"],
                "course_id": entry["source"]["course_id"],
                "academic_year": 2026,
                "status": "ativo",
                "mantenedora_id": "tenant-1",
            }
        )
        classes.append(
            {
                "id": entry["class_id"],
                "school_id": entry["school_id"],
                "academic_year": 2026,
                "mantenedora_id": "tenant-1",
                "education_level": "fundamental_anos_finais",
                "grade_level": "6º ANO",
            }
        )
        courses.append(
            {
                "id": entry["target"]["course_id"],
                "name": "Componente",
                "nivel_ensino": "fundamental_anos_finais",
                "mantenedora_id": "tenant-1",
            }
        )
    topology = {
        "set_name": "rs0" if replica else "",
        "msg": "",
        "logical_session_timeout_minutes": 30 if replica else None,
        "max_wire_version": 17,
        "is_writable_primary": True,
        "secondary": False,
    }
    return {
        "phase": "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026",
        "mode": "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT",
        "mantenedora_id": "tenant-1",
        "academic_year": 2026,
        "sealed_plan_sha256": plan["plan_sha256"],
        "source_entries": 23,
        "query_budget": 5,
        "query_calls": 5,
        "topology": topology,
        "counts": {
            "matching_assignments": len(assignments),
            "classes": len(classes),
            "target_courses": len(courses),
        },
        "teacher_assignments": assignments,
        "classes": classes,
        "target_courses": courses,
    }


def test_builder_emits_read_only_bounded_collector():
    js = build_js(make_plan(), "sigesc")
    assert "P0F79D5_LAST_MILE_JSON=" in js
    assert "countDocuments" in js
    assert "runCommand({hello:1})" in js
    assert "MAX_MATCHING_ASSIGNMENTS = 200" in js
    lowered = js.casefold()
    for forbidden in ("updateone", "updatemany", "insertone", "deleteone", "bulkwrite"):
        assert forbidden not in lowered


def test_all_23_clear_and_replica_set_requires_transaction():
    plan = make_plan()
    report = build_report(plan, make_snapshot(plan, replica=True))
    assert report["status"] == "PASS"
    assert report["summary"]["clear_for_execution_authorization"] == 23
    assert report["summary"]["active_target_already_exists"] == 0
    assert report["summary"]["source_drift_review_required"] == 0
    assert report["summary"]["target_curriculum_rejected"] == 0
    assert report["topology"]["classification"] == "REPLICA_SET_TRANSACTION_CAPABLE"
    assert report["topology"]["required_future_execution_strategy"] == "MONGODB_MULTI_DOCUMENT_TRANSACTION_REQUIRED"
    assert report["execution_contract"]["executable"] is False


def test_active_target_collision_is_fail_closed():
    plan = make_plan()
    snapshot = make_snapshot(plan)
    first = plan["entries"][0]
    snapshot["teacher_assignments"].append(
        {
            "id": "collision-1",
            "staff_id": "staff-01",
            "school_id": first["school_id"],
            "class_id": first["class_id"],
            "course_id": first["target"]["course_id"],
            "academic_year": 2026,
            "status": "ativo",
            "mantenedora_id": "tenant-1",
        }
    )
    snapshot["counts"]["matching_assignments"] += 1
    report = build_report(plan, snapshot)
    assert report["summary"]["clear_for_execution_authorization"] == 22
    assert report["summary"]["active_target_already_exists"] == 1


def test_curriculum_drift_is_rejected_and_standalone_uses_cas_rollback():
    plan = make_plan()
    snapshot = make_snapshot(plan, replica=False)
    snapshot["target_courses"][0]["nivel_ensino"] = "eja_final"
    report = build_report(plan, snapshot)
    assert report["summary"]["target_curriculum_rejected"] == 1
    assert report["summary"]["clear_for_execution_authorization"] == 22
    assert report["topology"]["classification"] == "STANDALONE_OR_TRANSACTION_UNAVAILABLE"
    assert report["topology"]["required_future_execution_strategy"] == "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED"


def test_plan_hash_tamper_fails_closed():
    plan = make_plan()
    snapshot = make_snapshot(plan)
    tampered = copy.deepcopy(plan)
    tampered["entries"][0]["target"]["course_id"] = "different-target"
    with pytest.raises(ValueError, match="PLAN_SHA256_INVALID"):
        build_report(tampered, snapshot)
