"""Build the P0-F7.9D5 read-only last-mile execution-preflight collector.

Consumes only the sealed P0-F7.9D4 remediation plan. The generated mongosh
JavaScript performs a bounded, read-only re-read of the exact source
teacher_assignments, possible destination collisions, current classes and
current target courses. It also records a sanitized MongoDB topology summary
from ``hello`` so a later writer can choose transaction semantics correctly.

No writer primitive is emitted by this builder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
OUTPUT_PHASE = "P0F7.9D5-LAST-MILE-PREFLIGHT-SNAPSHOT-2026"
OUTPUT_MODE = "READ_ONLY_BOUNDED_LAST_MILE_EXECUTION_PREFLIGHT"
QUERY_BUDGET = 5
EXPECTED_ENTRIES = 23
MAX_MATCHING_ASSIGNMENTS = 200
MAX_CLASSES = 50
MAX_COURSES = 50


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
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _plan_sha256(plan: Mapping[str, Any]) -> str:
    unsigned = dict(plan)
    unsigned.pop("plan_sha256", None)
    return _canonical_sha256(unsigned)


def _context(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS":
        raise ValueError("P0F7_9D4_PLAN_INVALID")
    if plan.get("mode") != PLAN_MODE:
        raise ValueError("P0F7_9D4_PLAN_MODE_INVALID")
    if (plan.get("execution_contract") or {}).get("executable") is not False:
        raise ValueError("P0F7_9D4_PLAN_MUST_BE_NON_EXECUTABLE")
    stored_sha = _norm(plan.get("plan_sha256"))
    computed_sha = _plan_sha256(plan)
    if not stored_sha or stored_sha != computed_sha:
        raise ValueError("P0F7_9D4_PLAN_SHA256_INVALID")

    tenant = _norm(plan.get("mantenedora_id"))
    year = int(plan.get("academic_year") or 0)
    entries = list(plan.get("entries") or [])
    if not tenant or year <= 0 or len(entries) != EXPECTED_ENTRIES:
        raise ValueError("P0F7_9D5_PLAN_CONTEXT_INVALID")

    requests: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        assignment_id = _norm(entry.get("assignment_id"))
        school_id = _norm(entry.get("school_id"))
        class_id = _norm(entry.get("class_id"))
        source_course_id = _norm((entry.get("source") or {}).get("course_id"))
        target_course_id = _norm((entry.get("target") or {}).get("course_id"))
        pre = entry.get("preconditions") or {}
        if (
            not assignment_id
            or assignment_id in seen
            or not school_id
            or not class_id
            or not source_course_id
            or not target_course_id
            or source_course_id == target_course_id
        ):
            raise ValueError("P0F7_9D5_PLAN_ENTRY_INVALID")
        if _norm(pre.get("assignment_id_equals")) != assignment_id:
            raise ValueError("P0F7_9D5_PLAN_PRECONDITION_ASSIGNMENT_DRIFT")
        if _norm(pre.get("school_id_equals")) != school_id or _norm(pre.get("class_id_equals")) != class_id:
            raise ValueError("P0F7_9D5_PLAN_PRECONDITION_SCOPE_DRIFT")
        if _norm(pre.get("course_id_equals")) != source_course_id:
            raise ValueError("P0F7_9D5_PLAN_PRECONDITION_COURSE_DRIFT")
        seen.add(assignment_id)
        requests.append(
            {
                "assignment_id": assignment_id,
                "school_id": school_id,
                "class_id": class_id,
                "source_course_id": source_course_id,
                "target_course_id": target_course_id,
            }
        )

    return {
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": stored_sha,
        "requests": requests,
    }


def build_js(plan: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = _context(plan)
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
if (!tenant || !year || !Array.isArray(req.requests) || req.requests.length !== {EXPECTED_ENTRIES}) throw new Error("P0F79D5_CONTEXT_INVALID");
const yearFilter = {{$in:[year,String(year)]}};
const sourceIds = req.requests.map(x => String(x.assignment_id));
const classIds = [...new Set(req.requests.map(x => String(x.class_id)))];
const targetCourseIds = [...new Set(req.requests.map(x => String(x.target_course_id)))];
const targetPairs = req.requests.map(x => ({{school_id:String(x.school_id),class_id:String(x.class_id),course_id:String(x.target_course_id)}}));
const structuralOr = [{{id:{{$in:sourceIds}}}}].concat(targetPairs);
const assignmentFilter = {{mantenedora_id:tenant,academic_year:yearFilter,$or:structuralOr}};
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  mantenedora_id: tenant,
  academic_year: year,
  sealed_plan_sha256: req.sealed_plan_sha256,
  source_entries: req.requests.length,
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  topology: {{}},
  counts: {{}},
  teacher_assignments: [],
  classes: [],
  target_courses: []
}};
const helloRaw = adminDb.runCommand({{hello:1}});
result.query_calls += 1;
if (!helloRaw || Number(helloRaw.ok || 0) !== 1) throw new Error("P0F79D5_HELLO_FAILED");
result.topology = {{
  set_name: String(helloRaw.setName || ""),
  msg: String(helloRaw.msg || ""),
  logical_session_timeout_minutes: helloRaw.logicalSessionTimeoutMinutes == null ? null : Number(helloRaw.logicalSessionTimeoutMinutes),
  max_wire_version: helloRaw.maxWireVersion == null ? null : Number(helloRaw.maxWireVersion),
  is_writable_primary: Boolean(helloRaw.isWritablePrimary),
  secondary: Boolean(helloRaw.secondary)
}};
result.counts.matching_assignments = targetDb.teacher_assignments.countDocuments(assignmentFilter);
result.query_calls += 1;
if (result.counts.matching_assignments > MAX_MATCHING_ASSIGNMENTS) throw new Error("P0F79D5_ASSIGNMENT_BOUND_REACHED");
result.teacher_assignments = targetDb.teacher_assignments.find(
  assignmentFilter,
  {{_id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,status:1,mantenedora_id:1}}
).sort({{id:1}}).limit(MAX_MATCHING_ASSIGNMENTS + 1).toArray();
result.query_calls += 1;
if (result.teacher_assignments.length !== Number(result.counts.matching_assignments)) throw new Error("P0F79D5_ASSIGNMENT_FETCH_COUNT_DRIFT");
result.classes = targetDb.classes.find(
  {{mantenedora_id:tenant,academic_year:yearFilter,id:{{$in:classIds}}}},
  {{_id:0,id:1,school_id:1,academic_year:1,mantenedora_id:1,nivel_ensino:1,education_level:1,series:1,grade_level:1}}
).sort({{id:1}}).limit(MAX_CLASSES + 1).toArray();
result.query_calls += 1;
if (result.classes.length > MAX_CLASSES) throw new Error("P0F79D5_CLASS_BOUND_REACHED");
result.target_courses = targetDb.courses.find(
  {{mantenedora_id:tenant,id:{{$in:targetCourseIds}}}},
  {{_id:0,id:1,name:1,nivel_ensino:1,grade_levels:1,carga_horaria_por_serie:1,mantenedora_id:1,status:1,active:1,created_at:1}}
).sort({{id:1}}).limit(MAX_COURSES + 1).toArray();
result.query_calls += 1;
if (result.target_courses.length > MAX_COURSES) throw new Error("P0F79D5_COURSE_BOUND_REACHED");
result.counts.classes = result.classes.length;
result.counts.target_courses = result.target_courses.length;
if (result.query_calls !== QUERY_BUDGET) throw new Error("P0F79D5_QUERY_BUDGET_MISMATCH");
print("P0F79D5_LAST_MILE_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D5 bounded last-mile preflight collector")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.plan), args.db)
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8")
    print(f"P0F7_9D5_LAST_MILE_COLLECTOR_BUILT=YES path={args.js}")
    print(f"P0F7_9D5_QUERY_BUDGET={QUERY_BUDGET}")
    print(f"P0F7_9D5_MAX_MATCHING_ASSIGNMENTS={MAX_MATCHING_ASSIGNMENTS}")
    print("PRODUCTION_WRITES=0")
    print("STUDENT_DATA_ACCESS=0")


if __name__ == "__main__":
    main()
