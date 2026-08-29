"""Build the P0-F7.9D3 read-only collision-preflight mongosh collector.

Consumes only the sealed P0-F7.9D2 proposal report. The generated JavaScript
reads a bounded structural subset of teacher_assignments so the offline analyzer
can detect whether changing a UNIQUE_SAFE_TARGET source would collide with an
already-active assignment for the same staff/class/target/year tuple.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SOURCE_PHASE = "P0F7.9D2-SAFE-TARGET-RESOLUTION-2026"
OUTPUT_PHASE = "P0F7.9D3-COLLISION-PREFLIGHT-SNAPSHOT-2026"
OUTPUT_MODE = "READ_ONLY_BOUNDED_TARGET_COLLISION_PREFLIGHT"
QUERY_BUDGET = 2
MAX_SOURCE_PROPOSALS = 50
MAX_MATCHING_ASSIGNMENTS = 200


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _canonical_sha256(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _context(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("phase") != SOURCE_PHASE or report.get("status") != "PASS":
        raise ValueError("P0F7_9D2_REPORT_INVALID")
    if report.get("summary", {}).get("proposal_only") is not True:
        raise ValueError("P0F7_9D2_NOT_PROPOSAL_ONLY")
    tenant = _norm(report.get("mantenedora_id"))
    year = int(report.get("academic_year") or 0)
    if not tenant or year <= 0:
        raise ValueError("P0F7_9D2_CONTEXT_INVALID")

    proposals: list[dict[str, str]] = []
    seen_assignments: set[str] = set()
    for row in report.get("resolutions") or []:
        if _norm(row.get("resolution")) != "UNIQUE_SAFE_TARGET":
            continue
        assignment_id = _norm(row.get("assignment_id"))
        school_id = _norm(row.get("school_id"))
        class_id = _norm(row.get("class_id"))
        source_course_id = _norm(row.get("source_course_id"))
        targets = list(row.get("validated_targets") or [])
        if not assignment_id or assignment_id in seen_assignments:
            raise ValueError("P0F7_9D3_SOURCE_ASSIGNMENT_INVALID_OR_DUPLICATE")
        if not school_id or not class_id or not source_course_id or len(targets) != 1:
            raise ValueError("P0F7_9D3_PROPOSAL_CONTEXT_INVALID")
        target_course_id = _norm(targets[0].get("course_id"))
        if not target_course_id or target_course_id == source_course_id:
            raise ValueError("P0F7_9D3_TARGET_INVALID")
        seen_assignments.add(assignment_id)
        proposals.append({
            "assignment_id": assignment_id,
            "school_id": school_id,
            "class_id": class_id,
            "source_course_id": source_course_id,
            "target_course_id": target_course_id,
        })

    expected = int(report.get("summary", {}).get("unique_safe_target") or 0)
    if len(proposals) != expected or expected <= 0 or expected > MAX_SOURCE_PROPOSALS:
        raise ValueError("P0F7_9D3_PROPOSAL_COUNT_INVALID")
    return {
        "mantenedora_id": tenant,
        "academic_year": year,
        "source_p0f7_9d2_report_sha256": _canonical_sha256(report),
        "proposals": proposals,
    }


def build_js(report: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = _context(report)
    request = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    return f'''const PHASE = {json.dumps(OUTPUT_PHASE)};
const MODE = {json.dumps(OUTPUT_MODE)};
const QUERY_BUDGET = {QUERY_BUDGET};
const MAX_MATCHING_ASSIGNMENTS = {MAX_MATCHING_ASSIGNMENTS};
const req = {request};
const targetDb = db.getSiblingDB({database});
const tenant = String(req.mantenedora_id || "");
const year = Number(req.academic_year || 0);
if (!tenant || !year || !Array.isArray(req.proposals) || !req.proposals.length) throw new Error("P0F79D3_CONTEXT_INVALID");
const yearFilter = {{$in:[year,String(year)]}};
const sourceIds = req.proposals.map(x => String(x.assignment_id));
const targetPairs = req.proposals.map(x => ({{school_id:String(x.school_id),class_id:String(x.class_id),course_id:String(x.target_course_id)}}));
const structuralOr = [{{id:{{$in:sourceIds}}}}].concat(targetPairs);
const filter = {{mantenedora_id:tenant,academic_year:yearFilter,$or:structuralOr}};
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  mantenedora_id: tenant,
  academic_year: year,
  source_p0f7_9d2_report_sha256: req.source_p0f7_9d2_report_sha256,
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  source_proposals: req.proposals.length,
  counts: {{}},
  teacher_assignments: []
}};
result.counts.matching_assignments = targetDb.teacher_assignments.countDocuments(filter);
result.query_calls += 1;
if (result.counts.matching_assignments > MAX_MATCHING_ASSIGNMENTS) throw new Error("P0F79D3_MATCHING_ASSIGNMENT_BOUND_REACHED");
result.teacher_assignments = targetDb.teacher_assignments.find(
  filter,
  {{_id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,status:1,mantenedora_id:1}}
).sort({{id:1}}).limit(MAX_MATCHING_ASSIGNMENTS + 1).toArray();
result.query_calls += 1;
if (result.teacher_assignments.length !== Number(result.counts.matching_assignments)) throw new Error("P0F79D3_FETCH_COUNT_DRIFT");
if (result.query_calls !== QUERY_BUDGET) throw new Error("P0F79D3_QUERY_BUDGET_MISMATCH");
print("P0F79D3_COLLISION_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D3 bounded collision-preflight collector")
    parser.add_argument("--d2-report", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.d2_report), args.db)
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8")
    print(f"P0F7_9D3_COLLISION_COLLECTOR_BUILT=YES path={args.js}")
    print(f"P0F7_9D3_QUERY_BUDGET={QUERY_BUDGET}")
    print(f"P0F7_9D3_MAX_MATCHING_ASSIGNMENTS={MAX_MATCHING_ASSIGNMENTS}")
    print("PRODUCTION_WRITES=0")
    print("STUDENT_DATA_ACCESS=0")


if __name__ == "__main__":
    main()
