"""Build the bounded P0-F7.9A curricular-allocation forensic snapshot collector.

The generator runs locally and reads only the sealed P0-F7.5 report. It emits a
small mongosh JavaScript collector for Case 2 (MULTI 3º E 4º ETAPA). The
collector is read-only, tenant-scoped from the class record and capped at eight
queries. No student, enrollment, grade or attendance collection is accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

P0F75_PHASE = "P0F7.5-SERIES-APPLICABILITY-READ-ONLY-2026"
SNAPSHOT_PHASE = "P0F7.9A-CURRICULAR-ALLOCATION-FORENSIC-SNAPSHOT-2026"
SNAPSHOT_MODE = "READ_ONLY_BOUNDED_MONGOSH_CLASS_FORENSICS"
TARGET_CASE = 2
QUERY_BUDGET = 8
MAX_ASSIGNMENTS = 200
MAX_COURSES = 200
MAX_STAFF = 100
MAX_ALLOCATIONS = 200
MAX_DVD_ROWS = 200
MAX_SCHEDULES = 20
MAX_AUDIT_LOGS = 500


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


def _verify_embedded_sha(payload: Mapping[str, Any]) -> str:
    stored = _norm(payload.get("manifest_sha256"))
    if not stored:
        raise ValueError("P0F7_5_SHA_MISSING")
    canonical = dict(payload)
    canonical.pop("manifest_sha256", None)
    actual = _canonical_sha256(canonical)
    if actual != stored:
        raise ValueError("P0F7_5_SHA_MISMATCH")
    return stored


def _target(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("phase") != P0F75_PHASE:
        raise ValueError("P0F7_5_PHASE_MISMATCH")
    if report.get("status") != "PASS" or report.get("group_name") != "Geografia":
        raise ValueError("P0F7_5_STATUS_OR_GROUP_MISMATCH")
    sha = _verify_embedded_sha(report)

    cases = report.get("cases") or []
    case = next(
        (row for row in cases if int(row.get("case_number") or 0) == TARGET_CASE),
        None,
    )
    if not isinstance(case, Mapping):
        raise ValueError("P0F7_5_CASE_2_MISSING")

    class_meta = case.get("class") or {}
    school_meta = case.get("school") or {}
    class_id = _norm(class_meta.get("class_id") or class_meta.get("id"))
    school_id = _norm(school_meta.get("school_id") or school_meta.get("id"))
    year = int(class_meta.get("academic_year") or 0)
    if not class_id or not school_id or year <= 0:
        raise ValueError("CASE_2_NATURAL_KEY_INCOMPLETE")

    return {
        "case_number": TARGET_CASE,
        "class_id": class_id,
        "school_id": school_id,
        "academic_year": year,
        "source_p0f7_5_manifest_sha256": sha,
    }


def build_js(report: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(c.isalnum() or c in "_.-" for c in db_name):
        raise ValueError("DB_NAME_INVALID")

    request = json.dumps(_target(report), ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    phase = json.dumps(SNAPSHOT_PHASE)
    mode = json.dumps(SNAPSHOT_MODE)

    return f'''const PHASE = {phase};
const MODE = {mode};
const QUERY_BUDGET = {QUERY_BUDGET};
const MAX_ASSIGNMENTS = {MAX_ASSIGNMENTS};
const MAX_COURSES = {MAX_COURSES};
const MAX_STAFF = {MAX_STAFF};
const MAX_ALLOCATIONS = {MAX_ALLOCATIONS};
const MAX_DVD_ROWS = {MAX_DVD_ROWS};
const MAX_SCHEDULES = {MAX_SCHEDULES};
const MAX_AUDIT_LOGS = {MAX_AUDIT_LOGS};
const req = {request};
const targetDb = db.getSiblingDB({database});
const result = {{
  phase: PHASE,
  mode: MODE,
  generated_at_utc: new Date().toISOString(),
  source_p0f7_5_manifest_sha256: req.source_p0f7_5_manifest_sha256,
  query_budget: QUERY_BUDGET,
  query_calls: 0,
  class: null,
  teacher_assignments: [],
  courses: [],
  staff: [],
  teacher_allocations: [],
  teacher_class_assignments: [],
  class_schedules: [],
  assignment_audit_logs: []
}};

const cls = targetDb.classes.findOne(
  {{id:req.class_id}},
  {{_id:0,id:1,name:1,school_id:1,academic_year:1,mantenedora_id:1,nivel_ensino:1,education_level:1,grade_level:1,series:1,course_ids:1}}
);
result.query_calls += 1;
if (!cls) throw new Error("TARGET_CLASS_NOT_FOUND");
const tenant = String(cls.mantenedora_id || "");
if (!tenant) throw new Error("TARGET_CLASS_TENANT_MISSING_FAIL_CLOSED");
if (String(cls.school_id || "") !== String(req.school_id)) throw new Error("TARGET_CLASS_SCHOOL_DRIFT");
if (String(cls.academic_year || "") !== String(req.academic_year)) throw new Error("TARGET_CLASS_YEAR_DRIFT");
result.class = cls;

const assignments = targetDb.teacher_assignments.find(
  {{
    mantenedora_id:tenant,
    class_id:req.class_id,
    school_id:req.school_id,
    academic_year:{{$in:[req.academic_year,String(req.academic_year)]}}
  }},
  {{
    _id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,
    status:1,carga_horaria_semanal:1,ignore_workload:1,is_substituicao:1,
    substituted_staff_id:1,data_inicio_substituicao:1,data_fim_substituicao:1,
    created_at:1,updated_at:1,observacoes:1,mantenedora_id:1
  }}
).sort({{created_at:1,id:1}}).limit(MAX_ASSIGNMENTS).toArray();
result.query_calls += 1;
if (assignments.length >= MAX_ASSIGNMENTS) throw new Error("TEACHER_ASSIGNMENT_BOUND_REACHED");
result.teacher_assignments = assignments;

const courseIds = [...new Set(assignments.map(x => String(x.course_id || "")).filter(Boolean))];
const staffIds = [...new Set(assignments.map(x => String(x.staff_id || "")).filter(Boolean))];
const assignmentIds = [...new Set(assignments.map(x => String(x.id || "")).filter(Boolean))];

const courses = targetDb.courses.find(
  {{mantenedora_id:tenant,id:{{$in:courseIds}}}},
  {{
    _id:0,id:1,name:1,nivel_ensino:1,grade_levels:1,carga_horaria_por_serie:1,
    workload:1,active:1,status:1,atendimento_programa:1,optativo:1,
    created_at:1,updated_at:1,deleted_at:1,mantenedora_id:1
  }}
).limit(MAX_COURSES).toArray();
result.query_calls += 1;
if (courses.length >= MAX_COURSES) throw new Error("COURSE_BOUND_REACHED");
result.courses = courses;

const staff = targetDb.staff.find(
  {{mantenedora_id:tenant,id:{{$in:staffIds}}}},
  {{_id:0,id:1,nome:1,full_name:1,cargo:1,status:1,user_id:1,mantenedora_id:1}}
).limit(MAX_STAFF).toArray();
result.query_calls += 1;
if (staff.length >= MAX_STAFF) throw new Error("STAFF_BOUND_REACHED");
result.staff = staff;

const allocations = targetDb.teacher_allocations.find(
  {{
    mantenedora_id:tenant,
    class_id:req.class_id,
    academic_year:{{$in:[req.academic_year,String(req.academic_year)]}}
  }},
  {{_id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,status:1,academic_year:1,created_at:1,updated_at:1,mantenedora_id:1}}
).limit(MAX_ALLOCATIONS).toArray();
result.query_calls += 1;
if (allocations.length >= MAX_ALLOCATIONS) throw new Error("TEACHER_ALLOCATION_BOUND_REACHED");
result.teacher_allocations = allocations;

const dvdRows = targetDb.teacher_class_assignments.find(
  {{class_id:req.class_id,deleted:{{$ne:true}}}},
  {{_id:0,id:1,teacher_id:1,class_id:1,component_id:1,school_id:1,valid_from:1,valid_until:1,deleted:1,created_at:1,updated_at:1}}
).limit(MAX_DVD_ROWS).toArray();
result.query_calls += 1;
if (dvdRows.length >= MAX_DVD_ROWS) throw new Error("DVD_ASSIGNMENT_BOUND_REACHED");
result.teacher_class_assignments = dvdRows;

const schedules = targetDb.class_schedules.find(
  {{class_id:req.class_id}},
  {{_id:0,id:1,class_id:1,school_id:1,academic_year:1,schedule_slots:1,slots:1,created_at:1,updated_at:1,mantenedora_id:1}}
).limit(MAX_SCHEDULES).toArray();
result.query_calls += 1;
if (schedules.length >= MAX_SCHEDULES) throw new Error("CLASS_SCHEDULE_BOUND_REACHED");
result.class_schedules = schedules;

const auditLogs = targetDb.audit_logs.find(
  {{collection:"teacher_assignments",document_id:{{$in:assignmentIds}}}},
  {{_id:0,id:1,action:1,collection:1,document_id:1,user_id:1,user_role:1,created_at:1,timestamp:1,description:1,old_value:1,new_value:1,extra_data:1,school_id:1,academic_year:1}}
).sort({{created_at:1,timestamp:1}}).limit(MAX_AUDIT_LOGS).toArray();
result.query_calls += 1;
if (auditLogs.length >= MAX_AUDIT_LOGS) throw new Error("AUDIT_LOG_BOUND_REACHED");
result.assignment_audit_logs = auditLogs;

if (result.query_calls !== QUERY_BUDGET) {{
  throw new Error(`QUERY_BUDGET_MISMATCH_${{result.query_calls}}_${{QUERY_BUDGET}}`);
}}
print("P0F79A_SNAPSHOT_JSON=" + JSON.stringify(result));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9A bounded mongosh forensic collector")
    parser.add_argument("--series", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", dest="js_path", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.series), args.db)
    args.js_path.parent.mkdir(parents=True, exist_ok=True)
    args.js_path.write_text(js, encoding="utf-8")
    print(f"P0F7_9A_COLLECTOR_BUILT=YES path={args.js_path}")
    print(f"P0F7_9A_QUERY_BUDGET={QUERY_BUDGET}")
    print("SENSITIVE_COLLECTIONS=NOT_ACCESSED")


if __name__ == "__main__":
    main()
