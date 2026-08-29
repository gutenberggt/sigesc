"""P0-F7.9D4 — build a sealed, proposal-only remediation plan.

Consumes only the sealed P0-F7.9D2 safe-target report and the sealed
P0-F7.9D3 collision-preflight report. No production/database/network access is
performed. The output is deliberately non-executable: it records deterministic
preconditions, intended course-id substitutions, rollback values, source-chain
hashes and the execution contract that a later explicitly authorized writer
must satisfy fail-closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

D2_PHASE = "P0F7.9D2-SAFE-TARGET-RESOLUTION-2026"
D3_PHASE = "P0F7.9D3-OFFLINE-COLLISION-PREFLIGHT-2026"
OUTPUT_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
EXPECTED_PREFLIGHT = "CLEAR_FOR_REMEDIATION_PLANNING"
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


def _validate_sources(d2: Mapping[str, Any], d3: Mapping[str, Any]) -> tuple[str, int]:
    if d2.get("phase") != D2_PHASE or d2.get("status") != "PASS":
        raise ValueError("P0F7_9D2_REPORT_INVALID")
    if d2.get("summary", {}).get("proposal_only") is not True:
        raise ValueError("P0F7_9D2_NOT_PROPOSAL_ONLY")
    if d3.get("phase") != D3_PHASE or d3.get("status") != "PASS":
        raise ValueError("P0F7_9D3_REPORT_INVALID")
    if d3.get("summary", {}).get("proposal_only") is not True:
        raise ValueError("P0F7_9D3_NOT_PROPOSAL_ONLY")
    if _norm(d3.get("source_p0f7_9d2_report_sha256")) != _canonical_sha256(d2):
        raise ValueError("P0F7_9D4_D2_D3_CHAIN_MISMATCH")

    tenant = _norm(d2.get("mantenedora_id"))
    year = int(d2.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9D4_CONTEXT_INVALID")
    if _norm(d3.get("mantenedora_id")) != tenant or int(d3.get("academic_year") or 0) != year:
        raise ValueError("P0F7_9D4_CONTEXT_DRIFT")

    d2_unique = int(d2.get("summary", {}).get("unique_safe_target") or 0)
    d3_summary = d3.get("summary") or {}
    d3_source = int(d3_summary.get("unique_safe_target_source") or 0)
    clear = int(d3_summary.get("clear_for_remediation_planning") or 0)
    collisions = int(d3_summary.get("active_target_already_exists") or 0)
    drift = int(d3_summary.get("source_drift_review_required") or 0)
    if d2_unique <= 0 or d3_source != d2_unique:
        raise ValueError("P0F7_9D4_SOURCE_COUNT_DRIFT")
    if clear != d2_unique or collisions != 0 or drift != 0:
        raise ValueError("P0F7_9D4_NOT_ALL_UNIQUE_TARGETS_CLEAR")
    return tenant, year


def _d2_resolution_by_assignment(d2: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in d2.get("resolutions") or []:
        if _norm(row.get("resolution")) != "UNIQUE_SAFE_TARGET":
            continue
        assignment_id = _norm(row.get("assignment_id"))
        targets = list(row.get("validated_targets") or [])
        if not assignment_id or assignment_id in out or len(targets) != 1:
            raise ValueError("P0F7_9D4_D2_UNIQUE_TARGET_ROW_INVALID")
        out[assignment_id] = row
    return out


def build_plan(d2: Mapping[str, Any], d3: Mapping[str, Any]) -> dict[str, Any]:
    tenant, year = _validate_sources(d2, d3)
    d2_by_assignment = _d2_resolution_by_assignment(d2)
    d3_rows = list(d3.get("results") or [])
    if len(d3_rows) != len(d2_by_assignment):
        raise ValueError("P0F7_9D4_RESULT_COUNT_DRIFT")

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in d3_rows:
        assignment_id = _norm(row.get("assignment_id"))
        if not assignment_id or assignment_id in seen:
            raise ValueError("P0F7_9D4_ASSIGNMENT_ID_INVALID_OR_DUPLICATE")
        seen.add(assignment_id)
        if _norm(row.get("preflight")) != EXPECTED_PREFLIGHT:
            raise ValueError(f"P0F7_9D4_PREFLIGHT_NOT_CLEAR:{assignment_id}")
        if list(row.get("active_collision_assignment_ids") or []):
            raise ValueError(f"P0F7_9D4_ACTIVE_COLLISION_PRESENT:{assignment_id}")
        if not bool(row.get("staff_id_present")):
            raise ValueError(f"P0F7_9D4_STAFF_ID_NOT_VERIFIED:{assignment_id}")

        d2_row = d2_by_assignment.get(assignment_id)
        if not d2_row:
            raise ValueError(f"P0F7_9D4_D2_ROW_MISSING:{assignment_id}")
        target = list(d2_row.get("validated_targets") or [])[0]
        source_course_id = _norm(d2_row.get("source_course_id"))
        target_course_id = _norm(target.get("course_id"))
        if not source_course_id or not target_course_id or source_course_id == target_course_id:
            raise ValueError(f"P0F7_9D4_COURSE_TRANSITION_INVALID:{assignment_id}")
        if _norm(row.get("source_course_id")) != source_course_id:
            raise ValueError(f"P0F7_9D4_SOURCE_COURSE_DRIFT:{assignment_id}")
        if _norm(row.get("target_course_id")) != target_course_id:
            raise ValueError(f"P0F7_9D4_TARGET_COURSE_DRIFT:{assignment_id}")

        school_id = _norm(d2_row.get("school_id"))
        class_id = _norm(d2_row.get("class_id"))
        if _norm(row.get("school_id")) != school_id or _norm(row.get("class_id")) != class_id:
            raise ValueError(f"P0F7_9D4_SCOPE_DRIFT:{assignment_id}")

        entry: dict[str, Any] = {
            "assignment_id": assignment_id,
            "school_id": school_id,
            "class_id": class_id,
            "class_name": d2_row.get("class_name"),
            "academic_year": year,
            "integrity_code": d2_row.get("integrity_code"),
            "source": {
                "course_id": source_course_id,
                "course_name": d2_row.get("source_course_name"),
                "course_level": d2_row.get("source_course_level"),
            },
            "target": {
                "course_id": target_course_id,
                "course_name": target.get("course_name"),
                "course_level": target.get("course_level"),
                "write_policy": target.get("write_policy"),
                "fit_classification": target.get("fit_classification"),
                "fit_rank": target.get("fit_rank"),
            },
            "preconditions": {
                "mantenedora_id_equals": tenant,
                "academic_year_equals": year,
                "assignment_id_equals": assignment_id,
                "school_id_equals": school_id,
                "class_id_equals": class_id,
                "course_id_equals": source_course_id,
                "status_any_of": ACTIVE_STATUSES,
                "staff_id_must_be_present": True,
                "target_active_duplicate_must_not_exist": True,
                "current_curricular_validator_must_accept_target": True,
            },
            "intended_mutation": {
                "field": "course_id",
                "from": source_course_id,
                "to": target_course_id,
            },
            "rollback": {
                "field": "course_id",
                "from": target_course_id,
                "to": source_course_id,
            },
            "preflight": EXPECTED_PREFLIGHT,
        }
        entry["entry_sha256"] = _canonical_sha256(entry)
        entries.append(entry)

    entries.sort(key=lambda item: (_norm(item.get("school_id")), _norm(item.get("class_id")), _norm(item.get("assignment_id"))))
    for index, entry in enumerate(entries, start=1):
        entry["ordinal"] = index
        prior_hash = entry.pop("entry_sha256")
        entry["entry_sha256_pre_ordinal"] = prior_hash
        entry["entry_sha256"] = _canonical_sha256({k: v for k, v in entry.items() if k != "entry_sha256"})

    plan: dict[str, Any] = {
        "phase": OUTPUT_PHASE,
        "status": "PASS",
        "mode": "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE",
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_p0f7_9d2_report_sha256": _canonical_sha256(d2),
        "source_p0f7_9d3_report_sha256": _canonical_sha256(d3),
        "summary": {
            "planned_assignments": len(entries),
            "clear_preflight": len(entries),
            "active_collisions": 0,
            "source_drift": 0,
            "database_mutation": False,
            "production_writes": False,
            "remediation_executed": False,
        },
        "execution_contract": {
            "executable": False,
            "requires_separate_explicit_production_write_authorization": True,
            "before_each_future_write": [
                "re-read the exact assignment under tenant/year/school/class/id scope",
                "require current course_id to equal the sealed source course_id",
                "require status to remain active",
                "require staff_id to remain present",
                "re-run the current teacher_assignment curriculum SSoT for the sealed target",
                "re-check that no active staff/class/target/year duplicate exists",
                "require exactly one source document to match all sealed preconditions",
            ],
            "future_write_scope": "course_id only, plus audit metadata explicitly defined by the future executor",
            "failure_policy": "FAIL_CLOSED_NO_PARTIAL_GUESSING",
            "postconditions": [
                "source assignment id remains unchanged",
                "course_id equals sealed target",
                "assignment remains in the same tenant/school/class/year",
                "no active duplicate tuple exists",
                "current curricular validator accepts the resulting assignment",
            ],
            "rollback_contract": "use each entry.rollback only through a separately authorized fail-closed executor",
        },
        "entries": entries,
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
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D4 sealed remediation plan")
    parser.add_argument("--d2-report", required=True, type=Path)
    parser.add_argument("--d3-report", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = build_plan(_load(args.d2_report), _load(args.d3_report))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan["summary"], ensure_ascii=False, indent=2))
    print("P0F7_9D4_SEALED_REMEDIATION_PLAN=PASS")
    print(f"PLAN={args.json}")
    print(f"PLAN_SHA256={plan['plan_sha256']}")
    print("PRODUCTION_ACCESS=NO")
    print("DATABASE_MUTATION=NO")
    print("PRODUCTION_WRITES=NO")
    print("REMEDIATION_EXECUTED=NO")


if __name__ == "__main__":
    main()
