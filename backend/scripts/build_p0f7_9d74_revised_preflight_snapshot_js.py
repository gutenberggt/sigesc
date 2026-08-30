"""P0-F7.9D7.4 — build bounded read-only last-mile collector for the revised D7.3.1 plan.

Consumes only the sealed D7.3.1 revised-plan report. The generated mongosh
JavaScript performs five bounded read-only queries: topology, assignment count,
assignment fetch, class fetch and target-course fetch. It contains no writer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SEALED_PHASE = "P0F7.9D7.3-SEALED-DUPLICATE-PAIR-ADJUDICATION-2026"
SEALED_MODE = "LOCAL_OFFLINE_HUMAN_ADJUDICATION_NON_EXECUTABLE"
POLICY_PHASE = "P0F7.9D7.3.1-CURRICULAR-WORKLOAD-POLICY-2026"
EXPECTED_SEALED_REPORT_SHA256 = "b6cfcfd3fec964fe58ebdcc7aea6e9fe1953207d7178da35b7e1bd4dea8c39fb"
OUTPUT_PHASE = "P0F7.9D7.4-REVISED-LAST-MILE-SNAPSHOT-2026"
OUTPUT_MODE = "READ_ONLY_BOUNDED_REVISED_LAST_MILE_PREFLIGHT"
QUERY_BUDGET = 5
EXPECTED_OPERATIONS = 23
MAX_MATCHING_ASSIGNMENTS = 200
MAX_CLASSES = 50
MAX_COURSES = 50


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _unsigned_hash(payload: Mapping[str, Any], field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(field, None)
    return _canonical_sha256(unsigned)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def validate_sealed_report(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("phase") != SEALED_PHASE or report.get("status") != "PASS" or report.get("mode") != SEALED_MODE:
        raise ValueError("P0F7_9D74_SEALED_REPORT_INVALID")
    report_sha = _norm(report.get("report_sha256"))
    if not report_sha or report_sha != _unsigned_hash(report, "report_sha256"):
        raise ValueError("P0F7_9D74_SEALED_REPORT_SHA_INVALID")
    if report_sha != EXPECTED_SEALED_REPORT_SHA256:
        raise ValueError("P0F7_9D74_SEALED_REPORT_NOT_AUTHORIZED_INPUT")

    summary = report.get("summary") or {}
    revised = report.get("revised_plan") or {}
    if (
        summary.get("revised_plan_ready") is not True
        or int(summary.get("revised_document_updates") or 0) != EXPECTED_OPERATIONS
        or summary.get("production_write_authorized") is not False
        or summary.get("database_mutation") is not False
        or summary.get("production_writes") is not False
        or summary.get("remediation_executed") is not False
    ):
        raise ValueError("P0F7_9D74_SEALED_SUMMARY_INVALID")
    if (
        revised.get("ready") is not True
        or revised.get("executable") is not False
        or int(revised.get("operation_count") or 0) != EXPECTED_OPERATIONS
        or revised.get("pair_ordering_rule") != "RETIRE_DUPLICATE_BEFORE_CONSOLIDATE_SURVIVOR"
        or revised.get("rollback_order") != "REVERSE_OPERATION_ORDER"
        or revised.get("requires_fresh_last_mile_preflight") is not True
        or revised.get("requires_new_cas_dry_run") is not True
        or revised.get("requires_new_explicit_production_write_authorization") is not True
        or revised.get("old_23_write_authorization_reusable") is not False
    ):
        raise ValueError("P0F7_9D74_REVISED_PLAN_CONTRACT_INVALID")

    policy = report.get("curricular_workload_policy") or {}
    if (
        policy.get("phase") != POLICY_PHASE
        or _norm(policy.get("component")) != "geografia"
        or _norm(policy.get("class_level")) != "eja_final"
        or sorted(int(v) for v in (policy.get("series") or [])) != [3, 4]
        or int(policy.get("canonical_annual_workload") or 0) != 80
        or int(policy.get("canonical_monthly_workload") or 0) != 10
        or int(policy.get("canonical_weekly_workload") or 0) != 2
        or policy.get("multigrade_rule") != "MAX_ANNUAL_WORKLOAD"
        or policy.get("human_workload_choice_required") is not False
    ):
        raise ValueError("P0F7_9D74_CURRICULAR_POLICY_CHAIN_INVALID")
    formula = policy.get("conversion_formula") or {}
    if (
        formula.get("annual_to_monthly") != "ha / 8 = hm"
        or formula.get("monthly_to_weekly") != "hm / 5 = hs"
        or formula.get("annual_to_weekly_equivalent") != "ha / 40 = hs"
    ):
        raise ValueError("P0F7_9D74_WORKLOAD_FORMULA_INVALID")

    pair = report.get("pair_resolution") or {}
    if (
        _norm(pair.get("survivor_assignment_id")) != "47feaf78-62be-4b62-975b-7b389e11f13d"
        or _norm(pair.get("retired_assignment_id")) != "e62376c8-5e41-4165-b4bb-5040547ae9f3"
        or _norm(pair.get("retirement_status")) != "inativo"
        or int(pair.get("selected_weekly_workload") or 0) != 2
        or pair.get("hard_delete") is not False
    ):
        raise ValueError("P0F7_9D74_PAIR_RESOLUTION_INVALID")

    operations = list(revised.get("operations") or [])
    if len(operations) != EXPECTED_OPERATIONS:
        raise ValueError("P0F7_9D74_OPERATION_COUNT_INVALID")
    if [int((op or {}).get("operation_index") or 0) for op in operations] != list(range(1, EXPECTED_OPERATIONS + 1)):
        raise ValueError("P0F7_9D74_OPERATION_SEQUENCE_INVALID")
    types = [str((op or {}).get("operation_type") or "") for op in operations]
    if types.count("REMAP_COURSE") != 21 or types.count("RETIRE_DUPLICATE_ASSIGNMENT") != 1 or types.count("CONSOLIDATE_SURVIVOR") != 1:
        raise ValueError("P0F7_9D74_OPERATION_PARTITION_INVALID")
    if types[-2:] != ["RETIRE_DUPLICATE_ASSIGNMENT", "CONSOLIDATE_SURVIVOR"]:
        raise ValueError("P0F7_9D74_PAIR_ORDER_INVALID")

    tenant = ""
    year = 0
    seen: set[str] = set()
    normalized_ops: list[dict[str, Any]] = []
    for op in operations:
        op_type = _norm(op.get("operation_type"))
        scope = op.get("scope") or {}
        aid = _norm(scope.get("assignment_id"))
        school_id = _norm(scope.get("school_id"))
        class_id = _norm(scope.get("class_id"))
        op_tenant = _norm(scope.get("mantenedora_id"))
        op_year = int(scope.get("academic_year") or 0)
        if not all((aid, school_id, class_id, op_tenant)) or op_year <= 0 or aid in seen:
            raise ValueError("P0F7_9D74_OPERATION_SCOPE_INVALID")
        seen.add(aid)
        if not tenant:
            tenant, year = op_tenant, op_year
        if op_tenant != tenant or op_year != year:
            raise ValueError("P0F7_9D74_OPERATION_CONTEXT_DRIFT")

        cas = dict(op.get("cas_expected") or {})
        set_fields = dict(op.get("set_fields") or {})
        rollback = dict(op.get("rollback_set_fields") or {})
        if op_type == "REMAP_COURSE":
            if set(set_fields) != {"course_id"} or set(rollback) != {"course_id"} or not _norm(cas.get("course_id")):
                raise ValueError("P0F7_9D74_REMAP_CONTRACT_INVALID")
        elif op_type == "RETIRE_DUPLICATE_ASSIGNMENT":
            if set_fields != {"status": "inativo"} or set(rollback) != {"status"} or op.get("hard_delete") is not False:
                raise ValueError("P0F7_9D74_RETIRE_CONTRACT_INVALID")
            if not _norm(cas.get("course_id")) or "carga_horaria_semanal" not in cas:
                raise ValueError("P0F7_9D74_RETIRE_CAS_INVALID")
        elif op_type == "CONSOLIDATE_SURVIVOR":
            if "course_id" not in set_fields or not _norm(set_fields.get("course_id")) or "course_id" not in rollback:
                raise ValueError("P0F7_9D74_SURVIVOR_CONTRACT_INVALID")
            if not _norm(cas.get("course_id")) or "carga_horaria_semanal" not in cas:
                raise ValueError("P0F7_9D74_SURVIVOR_CAS_INVALID")
            if "carga_horaria_semanal" in set_fields and int(set_fields["carga_horaria_semanal"]) != 2:
                raise ValueError("P0F7_9D74_SURVIVOR_WORKLOAD_INVALID")
        else:
            raise ValueError("P0F7_9D74_OPERATION_TYPE_INVALID")

        normalized_ops.append({
            "operation_index": int(op.get("operation_index") or 0),
            "operation_type": op_type,
            "scope": {
                "mantenedora_id": op_tenant,
                "academic_year": op_year,
                "school_id": school_id,
                "class_id": class_id,
                "assignment_id": aid,
            },
            "cas_expected": cas,
            "set_fields": set_fields,
            "rollback_set_fields": rollback,
        })

    return {
        "sealed_report_sha256": report_sha,
        "mantenedora_id": tenant,
        "academic_year": year,
        "operations": normalized_ops,
    }


def build_js(report: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = validate_sealed_report(report)
    request = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    return f'''const PHASE = {json.dumps(OUTPUT_PHASE)};
const MODE = {json.dumps(OUTPUT_MODE)};
const QUERY_BUDGET = {QUERY_BUDGET};
const MAX_MATCHING_ASSIGNMENTS = {MAX_MATCHING_ASSIGNMENTS};
const MAX_CLASSES = {MAX_CLASSES};
const MAX_COURSES = {MAX_COURSES};
const req = {request};
const targetDb = db.getSiblingDB({database});
const adminDb = db.getSiblingDB("admin");
const tenant = String(req.mantenedora_id || "");
const year = Number(req.academic_year || 0);
if (!tenant || !year || !Array.isArray(req.operations) || req.operations.length !== {EXPECTED_OPERATIONS}) throw new Error("P0F79D74_CONTEXT_INVALID");
const yearFilter = {{$in:[year,String(year)]}};
const sourceIds = req.operations.map(x => String(x.scope.assignment_id));
const classIds = [...new Set(req.operations.map(x => String(x.scope.class_id)))];
const targetCourseIds = [...new Set(req.operations.filter(x => x.set_fields && x.set_fields.course_id).map(x => String(x.set_fields.course_id)))];
const targetPairs = req.operations.filter(x => x.set_fields && x.set_fields.course_id).map(x => ({{school_id:String(x.scope.school_id),class_id:String(x.scope.class_id),course_id:String(x.set_fields.course_id)}}));
const structuralOr = [{{id:{{$in:sourceIds}}}}].concat(targetPairs);
const assignmentFilter = {{mantenedora_id:tenant,academic_year:yearFilter,$or:structuralOr}};
const result = {{phase:PHASE,mode:MODE,generated_at_utc:new Date().toISOString(),mantenedora_id:tenant,academic_year:year,sealed_report_sha256:req.sealed_report_sha256,source_operations:req.operations.length,query_budget:QUERY_BUDGET,query_calls:0,topology:{{}},counts:{{}},teacher_assignments:[],classes:[],target_courses:[]}};
const helloRaw = adminDb.runCommand({{hello:1}}); result.query_calls += 1;
if (!helloRaw || Number(helloRaw.ok || 0) !== 1) throw new Error("P0F79D74_HELLO_FAILED");
result.topology = {{set_name:String(helloRaw.setName || ""),msg:String(helloRaw.msg || ""),logical_session_timeout_minutes:helloRaw.logicalSessionTimeoutMinutes == null ? null : Number(helloRaw.logicalSessionTimeoutMinutes),max_wire_version:helloRaw.maxWireVersion == null ? null : Number(helloRaw.maxWireVersion),is_writable_primary:Boolean(helloRaw.isWritablePrimary),secondary:Boolean(helloRaw.secondary)}};
result.counts.matching_assignments = targetDb.teacher_assignments.countDocuments(assignmentFilter); result.query_calls += 1;
if (result.counts.matching_assignments > MAX_MATCHING_ASSIGNMENTS) throw new Error("P0F79D74_ASSIGNMENT_BOUND_REACHED");
result.teacher_assignments = targetDb.teacher_assignments.find(assignmentFilter,{{_id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,status:1,mantenedora_id:1,carga_horaria_semanal:1}}).sort({{id:1}}).limit(MAX_MATCHING_ASSIGNMENTS + 1).toArray(); result.query_calls += 1;
if (result.teacher_assignments.length !== Number(result.counts.matching_assignments)) throw new Error("P0F79D74_ASSIGNMENT_FETCH_COUNT_DRIFT");
result.classes = targetDb.classes.find({{mantenedora_id:tenant,academic_year:yearFilter,id:{{$in:classIds}}}},{{_id:0,id:1,school_id:1,academic_year:1,mantenedora_id:1,nivel_ensino:1,education_level:1,series:1,grade_level:1}}).sort({{id:1}}).limit(MAX_CLASSES + 1).toArray(); result.query_calls += 1;
if (result.classes.length > MAX_CLASSES) throw new Error("P0F79D74_CLASS_BOUND_REACHED");
result.target_courses = targetDb.courses.find({{mantenedora_id:tenant,id:{{$in:targetCourseIds}}}},{{_id:0,id:1,name:1,nivel_ensino:1,grade_levels:1,carga_horaria_por_serie:1,mantenedora_id:1,status:1,active:1,created_at:1}}).sort({{id:1}}).limit(MAX_COURSES + 1).toArray(); result.query_calls += 1;
if (result.target_courses.length > MAX_COURSES) throw new Error("P0F79D74_COURSE_BOUND_REACHED");
result.counts.classes = result.classes.length; result.counts.target_courses = result.target_courses.length;
if (result.query_calls !== QUERY_BUDGET) throw new Error("P0F79D74_QUERY_BUDGET_MISMATCH");
print("P0F79D74_REVISED_LAST_MILE_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D7.4 bounded revised last-mile collector")
    parser.add_argument("--sealed-report", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.sealed_report), args.db)
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8")
    print(f"P0F7_9D74_REVISED_LAST_MILE_COLLECTOR_BUILT=YES path={args.js}")
    print(f"SEALED_REPORT_SHA256={EXPECTED_SEALED_REPORT_SHA256}")
    print(f"QUERY_BUDGET={QUERY_BUDGET}")
    print("PRODUCTION_WRITES=0")
    print("STUDENT_DATA_ACCESS=0")


if __name__ == "__main__":
    main()
