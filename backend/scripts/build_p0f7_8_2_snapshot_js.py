"""Build the minimal P0-F7.8.2 mongosh collector locally.

This generator reads the sealed P0-F7.5 report and emits JavaScript containing
only the three documented cases. The generated collector performs exactly three
read queries per case: classes, courses and teacher_assignments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
SNAPSHOT_PHASE = "P0F7.8.2-MINIMAL-MONGOSH-SNAPSHOT-2026"
MAX_CASES = 3
MAX_COURSES_PER_CASE = 4
MAX_ASSIGNMENTS_PER_CASE = 10
QUERY_BUDGET = 9


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _requests(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("phase") != P0F75_PHASE:
        raise ValueError("P0F7_5_PHASE_MISMATCH")
    if report.get("status") != "PASS" or report.get("group_name") != "Geografia":
        raise ValueError("P0F7_5_STATUS_OR_GROUP_MISMATCH")
    cases = report.get("cases") or []
    if len(cases) != MAX_CASES:
        raise ValueError("P0F7_5_CASE_COUNT_MISMATCH")

    output: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda row: int(row.get("case_number") or 0)):
        number = int(case.get("case_number") or 0)
        class_meta = case.get("class") or {}
        teacher_meta = case.get("teacher") or {}
        school_meta = case.get("school") or {}
        class_id = _norm(class_meta.get("class_id") or class_meta.get("id"))
        staff_id = _norm(teacher_meta.get("staff_id") or teacher_meta.get("id"))
        school_id = _norm(school_meta.get("school_id") or school_meta.get("id"))
        year = int(class_meta.get("academic_year") or 0)
        source_id = _norm((case.get("source_course") or {}).get("course_id"))
        target_id = _norm((case.get("target_course") or {}).get("course_id"))
        if number not in {1, 2, 3} or not all((class_id, staff_id, school_id, source_id, target_id)) or year <= 0:
            raise ValueError(f"CASE_{number}_NATURAL_KEY_INCOMPLETE")

        course_ids = [source_id, target_id]
        for candidate in case.get("exact_level_same_name_candidates") or []:
            if candidate.get("is_source") or candidate.get("is_target"):
                continue
            cid = _norm((candidate.get("course") or {}).get("course_id"))
            if cid and cid not in course_ids:
                course_ids.append(cid)
        if len(course_ids) > MAX_COURSES_PER_CASE:
            raise ValueError(f"CASE_{number}_COURSE_BUDGET_EXCEEDED")

        output.append({
            "case_number": number,
            "class_id": class_id,
            "staff_id": staff_id,
            "school_id": school_id,
            "academic_year": year,
            "course_ids": course_ids,
        })
    return output


def build_js(report: dict[str, Any], db_name: str) -> str:
    if not db_name or not all(c.isalnum() or c in "_.-" for c in db_name):
        raise ValueError("DB_NAME_INVALID")
    requests = json.dumps(_requests(report), ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    return f'''const PHASE = {json.dumps(SNAPSHOT_PHASE)};
const MODE = "READ_ONLY_MINIMAL_MONGOSH";
const QUERY_BUDGET = {QUERY_BUDGET};
const MAX_COURSES = {MAX_COURSES_PER_CASE};
const MAX_ASSIGNMENTS = {MAX_ASSIGNMENTS_PER_CASE};
const requests = {requests};
const targetDb = db.getSiblingDB({database});
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  cases: []
}};
for (const req of requests) {{
  const cls = targetDb.classes.findOne(
    {{id:req.class_id}},
    {{_id:0,id:1,name:1,school_id:1,academic_year:1,mantenedora_id:1,nivel_ensino:1,education_level:1,grade_level:1,series:1}}
  );
  result.query_calls += 1;
  if (!cls) throw new Error(`CASE_${{req.case_number}}_CLASS_NOT_FOUND`);
  const tenant = String(cls.mantenedora_id || "");
  if (!tenant) throw new Error(`CASE_${{req.case_number}}_TENANT_MISSING_FAIL_CLOSED`);

  const courses = targetDb.courses.find(
    {{id:{{$in:req.course_ids}},mantenedora_id:tenant}},
    {{_id:0,id:1,name:1,nivel_ensino:1,grade_levels:1,carga_horaria_por_serie:1,workload:1,active:1,mantenedora_id:1}}
  ).limit(MAX_COURSES).toArray();
  result.query_calls += 1;

  const assignments = targetDb.teacher_assignments.find(
    {{
      mantenedora_id:tenant,
      class_id:req.class_id,
      staff_id:req.staff_id,
      school_id:req.school_id,
      academic_year:{{$in:[req.academic_year,String(req.academic_year)]}},
      course_id:{{$in:req.course_ids.slice(0,2)}},
      status:{{$in:["active","Ativo","ativo"]}}
    }},
    {{_id:0,course_id:1,carga_horaria_semanal:1}}
  ).limit(MAX_ASSIGNMENTS).toArray();
  result.query_calls += 1;

  result.cases.push({{case_number:req.case_number,class:cls,courses:courses,assignments:assignments}});
}}
if (result.query_calls !== QUERY_BUDGET) {{
  throw new Error(`QUERY_BUDGET_MISMATCH_${{result.query_calls}}_${{QUERY_BUDGET}}`);
}}
print("P0F782_SNAPSHOT_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.8.2 minimal mongosh snapshot collector")
    parser.add_argument("--series", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", dest="js_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.series), args.db)
    args.js_path.parent.mkdir(parents=True, exist_ok=True)
    args.js_path.write_text(js, encoding="utf-8")
    print(f"P0F7_8_2_COLLECTOR_BUILT=YES path={args.js_path}")
    print(f"P0F7_8_2_QUERY_BUDGET={QUERY_BUDGET}")


if __name__ == "__main__":
    main()
