"""Build the P0-F7.9D7.2 bounded read-only duplicate-pair forensic snapshot.

Consumes the sealed D4 plan plus the D7.1 intra-batch collision report and emits
one mongosh JavaScript collector. The generated collector reads only the two
blocked teacher_assignments, their audit summaries, the affected class, the
three involved courses, and schedule-slot counts. It contains no mutation
primitive and no student-data query.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

PLAN_PHASE = "P0F7.9D4-SEALED-REMEDIATION-PLAN-2026"
PLAN_MODE = "SEALED_PROPOSAL_ONLY_NON_EXECUTABLE"
D71_PHASE = "P0F7.9D7.1-INTRA-BATCH-COLLISION-PREFLIGHT-2026"
OUTPUT_PHASE = "P0F7.9D7.2-DUPLICATE-PAIR-FORENSIC-SNAPSHOT-2026"
OUTPUT_MODE = "READ_ONLY_BOUNDED_DUPLICATE_PAIR_FORENSIC"
AUTHORIZED_PLAN_SHA256 = "6d39d8425c0555b36b69c8f5d00832fc8f93e1c4f38c35c0f29ea8e72fcf1312"
EXPECTED_BLOCKED = 2
EXPECTED_GROUPS = 1
QUERY_BUDGET = 5
MAX_AUDIT_EVENTS = 200
MAX_SCHEDULE_DOCS = 20


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


def _unsigned_hash(payload: Mapping[str, Any], signature_field: str) -> str:
    unsigned = dict(payload)
    unsigned.pop(signature_field, None)
    return _canonical_sha256(unsigned)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return payload


def _context(plan: Mapping[str, Any], d71: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("phase") != PLAN_PHASE or plan.get("status") != "PASS" or plan.get("mode") != PLAN_MODE:
        raise ValueError("P0F7_9D72_PLAN_INVALID")
    plan_sha = _norm(plan.get("plan_sha256"))
    if not plan_sha or plan_sha != _unsigned_hash(plan, "plan_sha256"):
        raise ValueError("P0F7_9D72_PLAN_SHA_INVALID")
    if plan_sha != AUTHORIZED_PLAN_SHA256:
        raise ValueError("P0F7_9D72_PLAN_NOT_EXPECTED")

    if d71.get("phase") != D71_PHASE or d71.get("status") != "PASS":
        raise ValueError("P0F7_9D72_D71_INVALID")
    d71_sha = _norm(d71.get("report_sha256"))
    if not d71_sha or d71_sha != _unsigned_hash(d71, "report_sha256"):
        raise ValueError("P0F7_9D72_D71_SHA_INVALID")
    if _norm(d71.get("sealed_plan_sha256")) != plan_sha:
        raise ValueError("P0F7_9D72_D71_PLAN_CHAIN_MISMATCH")

    summary = d71.get("summary") or {}
    if int(summary.get("entries") or 0) != 23:
        raise ValueError("P0F7_9D72_D71_ENTRY_COUNT_INVALID")
    if int(summary.get("safe_noncolliding") or 0) != 21:
        raise ValueError("P0F7_9D72_D71_SAFE_COUNT_INVALID")
    if int(summary.get("blocked_intra_batch") or 0) != EXPECTED_BLOCKED:
        raise ValueError("P0F7_9D72_D71_BLOCKED_COUNT_INVALID")
    if int(summary.get("collision_groups") or 0) != EXPECTED_GROUPS:
        raise ValueError("P0F7_9D72_D71_GROUP_COUNT_INVALID")
    if summary.get("execution_gate_open") is not False:
        raise ValueError("P0F7_9D72_D71_GATE_MUST_BE_CLOSED")
    if summary.get("production_writes") is not False or summary.get("remediation_executed") is not False:
        raise ValueError("P0F7_9D72_D71_SAFETY_INVALID")

    plan_by_id = {
        _norm(row.get("assignment_id")): row
        for row in (plan.get("entries") or [])
        if _norm(row.get("assignment_id"))
    }
    blocked = list(d71.get("blocked_entries") or [])
    if len(blocked) != EXPECTED_BLOCKED:
        raise ValueError("P0F7_9D72_BLOCKED_ENTRIES_INVALID")

    requests: list[dict[str, Any]] = []
    class_ids: set[str] = set()
    school_ids: set[str] = set()
    course_ids: set[str] = set()
    years: set[int] = set()
    for row in blocked:
        assignment_id = _norm(row.get("assignment_id"))
        plan_row = plan_by_id.get(assignment_id)
        if not plan_row:
            raise ValueError(f"P0F7_9D72_BLOCKED_NOT_IN_PLAN:{assignment_id}")
        class_id = _norm(plan_row.get("class_id"))
        school_id = _norm(plan_row.get("school_id"))
        source_course_id = _norm((plan_row.get("source") or {}).get("course_id"))
        target_course_id = _norm((plan_row.get("target") or {}).get("course_id"))
        year = int(plan_row.get("academic_year") or 0)
        if not assignment_id or not class_id or not school_id or not source_course_id or not target_course_id or year <= 0:
            raise ValueError("P0F7_9D72_BLOCKED_CONTEXT_INCOMPLETE")
        if _norm(row.get("source_course_id")) != source_course_id or _norm(row.get("target_course_id")) != target_course_id:
            raise ValueError(f"P0F7_9D72_BLOCKED_COURSE_DRIFT:{assignment_id}")
        requests.append(
            {
                "ordinal": int(plan_row.get("ordinal") or 0),
                "assignment_id": assignment_id,
                "class_id": class_id,
                "school_id": school_id,
                "source_course_id": source_course_id,
                "target_course_id": target_course_id,
            }
        )
        class_ids.add(class_id)
        school_ids.add(school_id)
        years.add(year)
        course_ids.add(source_course_id)
        course_ids.add(target_course_id)

    if len(class_ids) != 1 or len(school_ids) != 1 or len(years) != 1:
        raise ValueError("P0F7_9D72_BLOCKED_PAIR_SCOPE_NOT_SINGLE")
    if len(course_ids) != 3:
        raise ValueError("P0F7_9D72_EXPECTED_THREE_COURSES")
    requests.sort(key=lambda row: row["ordinal"])

    tenant = _norm(plan.get("mantenedora_id"))
    year = next(iter(years))
    if not tenant:
        raise ValueError("P0F7_9D72_TENANT_REQUIRED")
    return {
        "mantenedora_id": tenant,
        "academic_year": year,
        "sealed_plan_sha256": plan_sha,
        "source_d71_report_sha256": d71_sha,
        "class_id": next(iter(class_ids)),
        "school_id": next(iter(school_ids)),
        "assignment_ids": [row["assignment_id"] for row in requests],
        "course_ids": sorted(course_ids),
        "requests": requests,
    }


def build_js(plan: Mapping[str, Any], d71: Mapping[str, Any], db_name: str) -> str:
    if not db_name or not all(ch.isalnum() or ch in "_.-" for ch in db_name):
        raise ValueError("DB_NAME_INVALID")
    ctx = _context(plan, d71)
    request = json.dumps(ctx, ensure_ascii=False, separators=(",", ":"))
    database = json.dumps(db_name, ensure_ascii=False)
    return f'''const PHASE={json.dumps(OUTPUT_PHASE)};
const MODE={json.dumps(OUTPUT_MODE)};
const QUERY_BUDGET={QUERY_BUDGET};
const MAX_AUDIT_EVENTS={MAX_AUDIT_EVENTS};
const MAX_SCHEDULE_DOCS={MAX_SCHEDULE_DOCS};
const req={request};
const targetDb=db.getSiblingDB({database});
const tenant=String(req.mantenedora_id||"");
const year=Number(req.academic_year||0);
const yearFilter={{$in:[year,String(year)]}};
if(!tenant||!year||!Array.isArray(req.assignment_ids)||req.assignment_ids.length!==2) throw new Error("P0F79D72_CONTEXT_INVALID");

const out={{
  phase:PHASE,mode:MODE,generated_at_utc:new Date().toISOString(),
  mantenedora_id:tenant,academic_year:year,
  sealed_plan_sha256:req.sealed_plan_sha256,
  source_d71_report_sha256:req.source_d71_report_sha256,
  query_budget:QUERY_BUDGET,query_calls:0,
  requests:req.requests,
  teacher_assignments:[],audit_summaries:{{}},class_record:null,courses:[],schedule_slot_counts_by_course:{{}}
}};

out.teacher_assignments=targetDb.teacher_assignments.find(
  {{mantenedora_id:tenant,academic_year:yearFilter,id:{{$in:req.assignment_ids}}}},
  {{_id:0,id:1,staff_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,status:1,carga_horaria_semanal:1,is_substituicao:1,substituted_staff_id:1,data_inicio_substituicao:1,data_fim_substituicao:1,created_at:1,updated_at:1,created_by:1,updated_by:1,mantenedora_id:1}}
).sort({{id:1}}).limit(3).toArray();
out.query_calls+=1;
if(out.teacher_assignments.length!==2) throw new Error("P0F79D72_ASSIGNMENT_COUNT_INVALID:"+out.teacher_assignments.length);

const auditRows=targetDb.audit_logs.find(
  {{collection:"teacher_assignments",document_id:{{$in:req.assignment_ids}}}},
  {{_id:0,document_id:1,action:1,operation:1,timestamp:1,timestamp_utc:1}}
).sort({{timestamp_utc:1,timestamp:1}}).limit(MAX_AUDIT_EVENTS+1).toArray();
out.query_calls+=1;
if(auditRows.length>MAX_AUDIT_EVENTS) throw new Error("P0F79D72_AUDIT_BOUND_REACHED");
for(const id of req.assignment_ids) out.audit_summaries[id]={{event_count:0,first_event_at:null,last_event_at:null,action_counts:{{}}}};
for(const row of auditRows){{
  const id=String(row.document_id||"");
  if(!out.audit_summaries[id]) continue;
  const s=out.audit_summaries[id];
  const ts=String(row.timestamp_utc||row.timestamp||"");
  const action=String(row.action||row.operation||"unknown");
  s.event_count+=1;
  if(!s.first_event_at||ts<s.first_event_at) s.first_event_at=ts||null;
  if(!s.last_event_at||ts>s.last_event_at) s.last_event_at=ts||null;
  s.action_counts[action]=(s.action_counts[action]||0)+1;
}}

out.class_record=targetDb.classes.findOne(
  {{mantenedora_id:tenant,academic_year:yearFilter,id:String(req.class_id),school_id:String(req.school_id)}},
  {{_id:0,id:1,name:1,school_id:1,academic_year:1,mantenedora_id:1,nivel_ensino:1,education_level:1,grade_level:1,series:1,course_ids:1}}
);
out.query_calls+=1;
if(!out.class_record) throw new Error("P0F79D72_CLASS_NOT_FOUND");

out.courses=targetDb.courses.find(
  {{mantenedora_id:tenant,id:{{$in:req.course_ids}}}},
  {{_id:0,id:1,name:1,nivel_ensino:1,grade_levels:1,workload:1,carga_horaria_por_serie:1,active:1,status:1,created_at:1,mantenedora_id:1}}
).sort({{id:1}}).limit(4).toArray();
out.query_calls+=1;
if(out.courses.length!==3) throw new Error("P0F79D72_COURSE_COUNT_INVALID:"+out.courses.length);

const schedules=targetDb.class_schedules.find(
  {{mantenedora_id:tenant,academic_year:yearFilter,class_id:String(req.class_id)}},
  {{_id:0,schedule_slots:1}}
).limit(MAX_SCHEDULE_DOCS+1).toArray();
out.query_calls+=1;
if(schedules.length>MAX_SCHEDULE_DOCS) throw new Error("P0F79D72_SCHEDULE_BOUND_REACHED");
for(const cid of req.course_ids) out.schedule_slot_counts_by_course[cid]=0;
for(const sched of schedules){{
  for(const slot of (sched.schedule_slots||[])){{
    const cid=String(slot.course_id||"");
    if(Object.prototype.hasOwnProperty.call(out.schedule_slot_counts_by_course,cid)) out.schedule_slot_counts_by_course[cid]+=1;
  }}
}}

if(out.query_calls!==QUERY_BUDGET) throw new Error("P0F79D72_QUERY_BUDGET_MISMATCH");
print("P0F79D72_PAIR_JSON="+JSON.stringify(out));
'''


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build P0-F7.9D7.2 duplicate-pair forensic collector")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--d71-report", required=True, type=Path)
    parser.add_argument("--db", required=True)
    parser.add_argument("--js", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    js = build_js(_load(args.plan), _load(args.d71_report), args.db)
    args.js.parent.mkdir(parents=True, exist_ok=True)
    args.js.write_text(js, encoding="utf-8")
    print(f"P0F7_9D72_COLLECTOR_BUILT=YES path={args.js}")
    print(f"P0F7_9D72_QUERY_BUDGET={QUERY_BUDGET}")
    print("PRODUCTION_WRITES=0")
    print("STUDENT_DATA_ACCESS=0")


if __name__ == "__main__":
    main()
