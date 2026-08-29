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

from scripts.build_p0f7_9d7_authorized_executor_js import (  # noqa: E402
    AUTHORIZATION_MARKER,
    build_js,
)


def _sha(payload):
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _fixtures():
    tenant = "tenant-1"
    year = 2026
    plan_entries = []
    d5_results = []
    package_entries = []
    receipts = []

    for index in range(1, 24):
        assignment_id = f"a-{index:02d}"
        school_id = f"s-{((index - 1) % 5) + 1}"
        class_id = f"c-{index:02d}"
        source_id = f"source-{index:02d}"
        target_id = f"target-{index:02d}"
        plan_entries.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "academic_year": year,
                "source": {"course_id": source_id},
                "target": {"course_id": target_id, "write_policy": "LEVEL_MATCH_NO_SERIES_SCOPE"},
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
        package_entries.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "source_course_id": source_id,
                "target_course_id": target_id,
            }
        )
        receipts.append(
            {
                "ordinal": index,
                "assignment_id": assignment_id,
                "postcondition_verified": True,
                "rollback_verified": True,
            }
        )

    plan = {
        "phase": "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026",
        "status": "PASS",
        "mode": "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE",
        "mantenedora_id": tenant,
        "academic_year": year,
        "execution_contract": {"executable": False},
        "entries": plan_entries,
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

    package = {
        "phase": "P0F7.9D6-CAS-DRY-RUN-PACKAGE-2026",
        "status": "PASS",
        "mode": "DRY_RUN_ONLY_NON_EXECUTABLE",
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": plan["plan_sha256"],
        "source_p0f7_9d5_report_sha256": d5["report_sha256"],
        "strategy": "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED",
        "summary": {
            "entries": 23,
            "dry_run_only": True,
            "production_write_authorized": False,
        },
        "execution_contract": {
            "executable": False,
            "writer_implementation_present": False,
        },
        "entries": package_entries,
    }
    package["package_sha256"] = _sha(package)

    report = {
        "phase": "P0F7.9D6-OFFLINE-CAS-DRY-RUN-2026",
        "status": "PASS",
        "package_sha256": package["package_sha256"],
        "summary": {
            "entries": 23,
            "cas_match_verified": 23,
            "postconditions_verified": 23,
            "rollback_verified": 23,
            "active_collisions": 0,
            "dry_run_only": True,
            "production_write_authorized": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "receipts": receipts,
    }
    report["report_sha256"] = _sha(report)
    return plan, d5, package, report


def test_requires_explicit_authorization():
    plan, d5, package, report = _fixtures()
    with pytest.raises(ValueError, match="EXPLICIT_AUTHORIZATION_REQUIRED"):
        build_js(plan, d5, package, report, "sigesc", authorized=False)


def test_builds_exact_23_entry_cas_executor_with_reverse_rollback():
    plan, d5, package, report = _fixtures()
    js = build_js(plan, d5, package, report, "sigesc", authorized=True)
    assert AUTHORIZATION_MARKER in js
    assert "updateOne(" in js
    assert "applied.length - 1" in js
    assert "P0F79D7_EXECUTION_JSON=" in js
    assert "expected_entries: 23" in js
    assert "P0F79D7_FINAL_POSTCONDITION_FAILED" in js
    assert "P0F79D7_POSTWRITE_COLLISION" in js
    assert "updateMany(" not in js
    assert "deleteOne(" not in js
    assert "deleteMany(" not in js
    assert "insertOne(" not in js
    assert "insertMany(" not in js
    assert "replaceOne(" not in js
    assert "updated_at" not in js


def test_rejects_stale_d6_package_after_fresh_d5():
    plan, d5, package, report = _fixtures()
    stale = copy.deepcopy(package)
    stale["source_p0f7_9d5_report_sha256"] = "0" * 64
    unsigned = dict(stale)
    unsigned.pop("package_sha256", None)
    stale["package_sha256"] = _sha(unsigned)
    report["package_sha256"] = stale["package_sha256"]
    unsigned_report = dict(report)
    unsigned_report.pop("report_sha256", None)
    report["report_sha256"] = _sha(unsigned_report)
    with pytest.raises(ValueError, match="PACKAGE_D5_CHAIN_MISMATCH"):
        build_js(plan, d5, stale, report, "sigesc", authorized=True)


def test_rejects_any_blocked_last_mile_entry():
    plan, d5, package, report = _fixtures()
    d5["summary"]["clear_for_execution_authorization"] = 22
    unsigned = dict(d5)
    unsigned.pop("report_sha256", None)
    d5["report_sha256"] = _sha(unsigned)
    package["source_p0f7_9d5_report_sha256"] = d5["report_sha256"]
    unsigned_package = dict(package)
    unsigned_package.pop("package_sha256", None)
    package["package_sha256"] = _sha(unsigned_package)
    report["package_sha256"] = package["package_sha256"]
    unsigned_report = dict(report)
    unsigned_report.pop("report_sha256", None)
    report["report_sha256"] = _sha(unsigned_report)
    with pytest.raises(ValueError, match="D5_NOT_ALL_CLEAR"):
        build_js(plan, d5, package, report, "sigesc", authorized=True)
