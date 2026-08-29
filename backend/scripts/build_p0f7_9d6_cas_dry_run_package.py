"""P0-F7.9D6 — build a non-executable CAS remediation package.

Consumes only the sealed D4 plan and the sealed D5 last-mile preflight report.
No database, network, subprocess or production access is performed. The output
materializes deterministic compare-and-swap filters, intended course-id changes,
compensating rollback contracts and receipt templates for later review.

This phase is deliberately DRY-RUN ONLY. It does not contain a database writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
D5_PHASE = "P0F7.9D5-OFFLINE-LAST-MILE-PREFLIGHT-2026"
OUTPUT_PHASE = "P0F7.9D6-CAS-DRY-RUN-PACKAGE-2026"
OUTPUT_MODE = "DRY_RUN_ONLY_NON_EXECUTABLE"
EXPECTED_ENTRIES = 23
EXPECTED_STRATEGY = "CAS_WITH_COMPENSATING_ROLLBACK_REQUIRED"
ACTIVE_STATUSES = ["active", "ativo"]


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


def _unsigned_hash(payload: Mapping[str, Any], signature_field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(signature_field, None)
    return _canonical_sha256(unsigned)


def _validate_sources(plan: Mapping[str, Any], d5: Mapping[str, Any]) -> tuple[str, int, str]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS" or plan.get("mode") != PLAN_MODE:
        raise ValueError("P0F7_9D4_PLAN_INVALID")
    plan_sha = _norm(plan.get("plan_sha256"))
    if not plan_sha or plan_sha != _unsigned_hash(plan, "plan_sha256"):
        raise ValueError("P0F7_9D4_PLAN_SHA256_INVALID")
    if (plan.get("execution_contract") or {}).get("executable") is not False:
        raise ValueError("P0F7_9D4_PLAN_MUST_BE_NON_EXECUTABLE")

    if d5.get("phase") != D5_PHASE or d5.get("status") != "PASS":
        raise ValueError("P0F7_9D5_REPORT_INVALID")
    d5_sha = _norm(d5.get("report_sha256"))
    if not d5_sha or d5_sha != _unsigned_hash(d5, "report_sha256"):
        raise ValueError("P0F7_9D5_REPORT_SHA256_INVALID")
    if _norm(d5.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D6_PLAN_CHAIN_MISMATCH")

    tenant = _norm(plan.get("mantenedora_id"))
    year = int(plan.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9D6_CONTEXT_INVALID")
    if _norm(d5.get("mantenedora_id")) != tenant or int(d5.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D6_CONTEXT_DRIFT")

    entries = list(plan.get("entries") or [])
    summary = d5.get("summary") or {}
    if len(entries) != EXPECTED_ENTRIES or int(summary.get("sealed_entries") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D6_ENTRY_COUNT_INVALID")
    if int(summary.get("clear_for_execution_authorization") or 0) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D6_NOT_ALL_ENTRIES_CLEAR")
    for field in (
        "active_target_already_exists",
        "source_drift_review_required",
        "target_curriculum_rejected",
    ):
        if int(summary.get(field) or 0) != 0:
            raise ValueError(f"P0F7_9D6_PREFLIGHT_BLOCKED:{field}")
    if summary.get("proposal_only") is not True or summary.get("production_write_authorized") is not False:
        raise ValueError("P0F7_9D6_D5_AUTHORIZATION_STATE_INVALID")

    topology = d5.get("topology") or {}
    if topology.get("multi_document_transactions_available") is not False:
        raise ValueError("P0F7_9D6_EXPECTED_STANDALONE_TOPOLOGY")
    strategy = _norm(topology.get("required_future_execution_strategy"))
    if strategy != EXPECTED_STRATEGY:
        raise ValueError("P0F7_9D6_EXECUTION_STRATEGY_DRIFT")

    execution = d5.get("execution_contract") or {}
    if execution.get("executable") is not False:
        raise ValueError("P0F7_9D5_REPORT_MUST_BE_NON_EXECUTABLE")
    return tenant, year, d5_sha


def build_package(plan: Mapping[str, Any], d5: Mapping[str, Any]) -> dict[str, Any]:
    tenant, year, d5_sha = _validate_sources(plan, d5)
    d5_by_id: dict[str, Mapping[str, Any]] = {}
    for row in d5.get("results") or []:
        assignment_id = _norm((row or {}).get("assignment_id"))
        if not assignment_id or assignment_id in d5_by_id:
            raise ValueError("P0F7_9D6_D5_RESULT_ID_INVALID_OR_DUPLICATE")
        d5_by_id[assignment_id] = row

    package_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in plan.get("entries") or []:
        assignment_id = _norm(entry.get("assignment_id"))
        if not assignment_id or assignment_id in seen:
            raise ValueError("P0F7_9D6_PLAN_ENTRY_ID_INVALID_OR_DUPLICATE")
        seen.add(assignment_id)

        d5_row = d5_by_id.get(assignment_id)
        if not d5_row or _norm(d5_row.get("preflight")) != "CLEAR_FOR_EXECUTION_AUTHORIZATION":
            raise ValueError(f"P0F7_9D6_D5_ENTRY_NOT_CLEAR:{assignment_id}")

        school_id = _norm(entry.get("school_id"))
        class_id = _norm(entry.get("class_id"))
        source_course_id = _norm((entry.get("source") or {}).get("course_id"))
        target_course_id = _norm((entry.get("target") or {}).get("course_id"))
        if not all((school_id, class_id, source_course_id, target_course_id)) or source_course_id == target_course_id:
            raise ValueError(f"P0F7_9D6_ENTRY_SCOPE_INVALID:{assignment_id}")

        for field, expected in {
            "school_id": school_id,
            "class_id": class_id,
            "source_course_id": source_course_id,
            "target_course_id": target_course_id,
        }.items():
            if _norm(d5_row.get(field)) != expected:
                raise ValueError(f"P0F7_9D6_D5_{field.upper()}_DRIFT:{assignment_id}")

        cas_filter = {
            "mantenedora_id": tenant,
            "academic_year": year,
            "school_id": school_id,
            "class_id": class_id,
            "id": assignment_id,
            "course_id": source_course_id,
            "status_any_of": ACTIVE_STATUSES,
            "staff_id_must_be_present": True,
        }
        rollback_filter = {
            "mantenedora_id": tenant,
            "academic_year": year,
            "school_id": school_id,
            "class_id": class_id,
            "id": assignment_id,
            "course_id": target_course_id,
            "status_any_of": ACTIVE_STATUSES,
            "staff_id_must_be_present": True,
        }
        item: dict[str, Any] = {
            "ordinal": int(entry.get("ordinal") or 0),
            "assignment_id": assignment_id,
            "school_id": school_id,
            "class_id": class_id,
            "academic_year": year,
            "source_course_id": source_course_id,
            "target_course_id": target_course_id,
            "sealed_write_policy": _norm((entry.get("target") or {}).get("write_policy")),
            "cas": {
                "filter": cas_filter,
                "intended_change": {"field": "course_id", "from": source_course_id, "to": target_course_id},
                "expected_match_count": 1,
                "target_active_duplicate_must_not_exist": True,
                "postcondition_course_id_equals": target_course_id,
            },
            "compensating_rollback": {
                "filter": rollback_filter,
                "intended_change": {"field": "course_id", "from": target_course_id, "to": source_course_id},
                "expected_match_count": 1,
                "postcondition_course_id_equals": source_course_id,
            },
            "receipt_template": {
                "assignment_id": assignment_id,
                "ordinal": int(entry.get("ordinal") or 0),
                "before_course_id": source_course_id,
                "after_course_id": target_course_id,
                "cas_match_count": None,
                "postcondition_verified": False,
                "rollback_attempted": False,
                "rollback_verified": False,
            },
        }
        item["entry_sha256"] = _canonical_sha256(item)
        package_entries.append(item)

    package_entries.sort(key=lambda item: int(item.get("ordinal") or 0))
    if [int(item.get("ordinal") or 0) for item in package_entries] != list(range(1, EXPECTED_ENTRIES + 1)):
        raise ValueError("P0F7_9D6_ORDINAL_SEQUENCE_INVALID")

    package: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": OUTPUT_MODE,
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": _norm(plan.get("plan_sha256")),
        "source_p0f7_9d5_report_sha256": d5_sha,
        "strategy": EXPECTED_STRATEGY,
        "summary": {
            "entries": len(package_entries),
            "clear_last_mile_preflight": len(package_entries),
            "dry_run_only": True,
            "production_write_authorized": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "execution_contract": {
            "executable": False,
            "writer_implementation_present": False,
            "dry_run_only": True,
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "future_writer_phase_required": "P0-F7.9D7",
            "requires_separate_explicit_production_write_authorization": True,
            "required_strategy": EXPECTED_STRATEGY,
            "before_first_future_write": [
                "re-run P0-F7.9D5 immediately before execution",
                "require all 23 entries CLEAR_FOR_EXECUTION_AUTHORIZATION",
                "require the D4 plan hash and D5 report chain to match this package",
                "capture a bounded before-state receipt for every assignment",
            ],
            "per_entry_future_write_contract": [
                "re-read the source under the exact CAS filter",
                "require exactly one matching active source document",
                "re-check no active staff/class/target/year duplicate exists",
                "apply course_id only",
                "verify the postcondition immediately",
                "on any failure stop forward progress and compensate already-applied entries in reverse order",
                "verify each compensation before continuing rollback",
            ],
        },
        "entries": package_entries,
        "safety": {
            "production_access": False,
            "database_access": False,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
            "student_records_read": 0,
            "teacher_names_read": 0,
        },
    }
    package["package_sha256"] = _canonical_sha256(package)
    return package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D6 non-executable CAS dry-run package")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--d5-report", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    package = build_package(_load(args.plan), _load(args.d5_report))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(package["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D6_CAS_DRY_RUN_PACKAGE=PASS")
    print(f"PACKAGE={args.json}")
    print(f"PACKAGE_SHA256={package['package_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
