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

from scripts.build_p0f7_9d6_cas_dry_run_package import build_package  # noqa: E402
from scripts.simulate_p0f7_9d6_cas_dry_run import simulate  # noqa: E402


def _sha(payload):
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _fixtures():
    tenant = "tenant-1"
    year = 2026
    entries = []
    d5_results = []
    assignments = []
    for index in range(1, 24):
        assignment_id = f"a-{index:02d}"
        school_id = f"s-{((index - 1) % 5) + 1}"
        class_id = f"c-{index:02d}"
        source_id = f"source-{index:02d}"
        target_id = f"target-{index:02d}"
        entries.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "academic_year": year,
                "source": {"course_id": source_id, "course_name": "X", "course_level": "old"},
                "target": {
                    "course_id": target_id,
                    "course_name": "X",
                    "course_level": "new",
                    "write_policy": "LEVEL_MATCH_NO_SERIES_SCOPE",
                },
                "preconditions": {},
            }
        )
        d5_results.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "source_course_id": source_id,
                "target_course_id": target_id,
                "preflight": "CLEAR_FOR_EXECUTION_AUTHORIZATION",
            }
        )
        assignments.append(
            {
                "id": assignment_id,
                "staff_id": f"staff-{index:02d}",
                "school_id": school_id,
                "class_id": class_id,
                "course_id": source_id,
                "academic_year": year,
                "status": "active",
                "mantenedora_id": tenant,
            }
        )

    plan = {
        "phase": "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026",
        "status": "PASS",
        "mode": "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE",
        "mantenedora_id": tenant,
        "academic_year": year,
        "execution_contract": {"executable": False},
        "entries": entries,
    }
    plan["plan_sha256"] = _sha(plan)

    d5 = {
        "phase": "P0F7.9D5-OFFLINE-LAST-MILE-PREFLIGHT-2026",
        "status": "PASS",
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": plan["plan_sha256"],
        "summary": {
            "sealed_entries": 23,
            "clear_for_execution_authorization": 23,
            "active_target_already_exists": 0,
            "source_drift_review_required": 0,
            "target_curriculum_rejected": 0,
            "proposal_only": True,
            "production_write_authorized": False,
        },
        "topology": {
            "multi_document_transactions_available": False,
            "required_future_execution_strategy": "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED",
        },
        "execution_contract": {"executable": False},
        "results": d5_results,
    }
    d5["report_sha256"] = _sha(d5)

    snapshot = {
        "phase": "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026",
        "mode": "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT",
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": plan["plan_sha256"],
        "teacher_assignments": assignments,
    }
    return plan, d5, snapshot


def test_builds_non_executable_23_entry_cas_package():
    plan, d5, _ = _fixtures()
    package = build_package(plan, d5)
    assert package["status"] == "PASS"
    assert package["mode"] == "DRY_RUN_ONLY_NON_EXECUTABLE"
    assert package["summary"]["entries"] == 23
    assert package["summary"]["production_writes"] is False
    assert package["execution_contract"]["executable"] is False
    assert package["execution_contract"]["writer_implementation_present"] is False
    assert package["strategy"] == "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED"
    assert len(package["entries"]) == 23


def test_rejects_transaction_strategy_drift():
    plan, d5, _ = _fixtures()
    d5["topology"]["multi_document_transactions_available"] = True
    unsigned = dict(d5)
    unsigned.pop("report_sha256", None)
    d5["report_sha256"] = _sha(unsigned)
    with pytest.raises(ValueError, match="EXPECTED_STANDALONE_TOPOLOGY"):
        build_package(plan, d5)


def test_offline_simulation_verifies_cas_postcondition_and_rollback():
    plan, d5, snapshot = _fixtures()
    package = build_package(plan, d5)
    report = simulate(package, snapshot)
    assert report["status"] == "PASS"
    assert report["summary"]["cas_match_verified"] == 23
    assert report["summary"]["postconditions_verified"] == 23
    assert report["summary"]["rollback_verified"] == 23
    assert report["summary"]["active_collisions"] == 0
    assert report["summary"]["production_writes"] is False
    assert len(report["receipts"]) == 23


def test_offline_simulation_fails_closed_on_source_drift():
    plan, d5, snapshot = _fixtures()
    package = build_package(plan, d5)
    bad = copy.deepcopy(snapshot)
    bad["teacher_assignments"][0]["course_id"] = "unexpected-course"
    with pytest.raises(ValueError, match="DRY_RUN_CAS_DRIFT"):
        simulate(package, bad)
