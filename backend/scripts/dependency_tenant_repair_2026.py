#!/usr/bin/env python3
"""SIGESC — reparo cirúrgico de tenant para vínculos legados de Dependência 2026.

O alvo é derivado exclusivamente dos audit_logs de criação pertencentes ao tenant
ancorado pela escola. O script não insere vínculos, não altera notas/frequências e
não modifica status de estudante. Em apply, somente preenche mantenedora_id vazio
nos quatro student_dependencies cuja identidade acadêmica coincide com o audit log.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

YEAR = 2026
EXPECTED_TARGETS = 4
ANCHOR = "E M E I E F Monsenhor Augusto Dias de Brito"
EXPECTED_IMAGE = "mongo:7"


def emit(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, input=input_text, text=True, capture_output=True)


def mongosh(container: str, js: str) -> str:
    cp = run(["docker", "exec", "-i", container, "mongosh", "--quiet", "--file", "/dev/stdin"], input_text=js)
    if cp.returncode != 0:
        emit("DEP_TENANT_REPAIR_MONGOSH_FAILED")
        raise SystemExit(40)
    return cp.stdout


def marker(text: str, prefix: str) -> str:
    vals = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
    if len(vals) != 1:
        raise RuntimeError(f"marker_count:{prefix}:{len(vals)}")
    return vals[0]


def js_program(mode: str, run_id: str) -> str:
    return f'''
const d=db.getSiblingDB("sigesc");
const year={YEAR};
const expected={EXPECTED_TARGETS};
const anchorName={json.dumps(ANCHOR)};
const mode={json.dumps(mode)};
const runId={json.dumps(run_id)};
const norm=v=>(v===undefined||v===null)?"":String(v);
const yearEq=v=>norm(v)===String(year);
const anchors=d.schools.find({{name:anchorName}},{{_id:0,id:1,mantenedora_id:1}}).toArray();
if(anchors.length!==1||!anchors[0].mantenedora_id){{print("DEP_TENANT_REPAIR_ERROR=ANCHOR_TENANT_NOT_UNIQUE");quit(51);}}
const tenant=anchors[0].mantenedora_id;
const tenantSchools=d.schools.find({{mantenedora_id:tenant}},{{_id:0,id:1}}).toArray();
const schoolIds=new Set(tenantSchools.map(x=>x.id).filter(Boolean));
const tenantUsers=d.users.find({{mantenedora_id:tenant}},{{_id:0,id:1}}).toArray();
const userIds=new Set(tenantUsers.map(x=>x.id).filter(Boolean));
const tenantLog=log=>{{
  if(norm(log.mantenedora_id)===norm(tenant)) return true;
  if(norm(log.mantenedora_id)!=="") return false;
  return !!((log.school_id&&schoolIds.has(log.school_id))||(log.user_id&&userIds.has(log.user_id)));
}};
const logs=d.audit_logs.find({{collection:"student_dependencies",action:"create"}},{{_id:0,document_id:1,mantenedora_id:1,user_id:1,school_id:1,new_value:1}}).toArray()
  .filter(tenantLog).filter(x=>x.document_id&&yearEq((x.new_value||{{}}).academic_year));
const ids=[...new Set(logs.map(x=>x.document_id))];
if(ids.length!==expected){{print("DEP_TENANT_REPAIR_ERROR=TARGET_COUNT:"+ids.length);quit(52);}}
const base={{}};
for(const log of logs) if(!base[log.document_id]) base[log.document_id]=log.new_value||{{}};
const core=x=>[x.student_id,x.school_id,x.class_id,x.course_id,norm(x.academic_year),norm(x.origin_academic_year),x.status].join("|");
const plan={{target_count:ids.length,tenant_patch:0,tenant_existing:0,inactive_students:0,grade_records:0,attendance_records:0,conflicts:[]}};
const inactive=new Set();
for(const id of ids){{
  const expectedDep=base[id]||{{}};
  const live=d.student_dependencies.findOne({{id}});
  if(!live){{plan.conflicts.push("DEPENDENCY_DOCUMENT_MISSING");continue;}}
  if(core(live)!==core(expectedDep)) plan.conflicts.push("DEPENDENCY_CORE_MISMATCH");
  if(!live.school_id||!schoolIds.has(live.school_id)) plan.conflicts.push("DEPENDENCY_SCHOOL_OUTSIDE_TENANT");
  if(expectedDep.school_id&&norm(expectedDep.school_id)!==norm(live.school_id)) plan.conflicts.push("AUDIT_SCHOOL_MISMATCH");
  const liveTenant=norm(live.mantenedora_id);
  if(liveTenant==="") plan.tenant_patch++;
  else if(liveTenant===norm(tenant)) plan.tenant_existing++;
  else plan.conflicts.push("DEPENDENCY_TENANT_CONFLICT");
  const stu=d.students.findOne({{id:live.student_id,mantenedora_id:tenant}},{{_id:0,status:1,dependency_mode:1}});
  if(!stu) plan.conflicts.push("STUDENT_NOT_IN_TENANT");
  else {{
    const st=String(stu.status||"active").toLowerCase();
    if(!["active","ativo"].includes(st)) inactive.add(live.student_id);
    if(!["with_dependency","dependency_only"].includes(String(stu.dependency_mode||"none"))) plan.conflicts.push("STUDENT_MODE_INVALID");
  }}
}}
plan.inactive_students=inactive.size;
plan.grade_records=d.grades.countDocuments({{dependency_id:{{$in:ids}}}});
plan.attendance_records=(d.attendance.aggregate([
  {{$match:{{"records.dependency_id":{{$in:ids}}}}}},
  {{$project:{{n:{{$size:{{$filter:{{input:{{$ifNull:["$records",[]]}},as:"r",cond:{{$in:["$$r.dependency_id",ids]}}}}}}}}}}}},
  {{$group:{{_id:null,total:{{$sum:"$n"}}}}}}
]).toArray()[0]||{{total:0}}).total;
const types=[...new Set(plan.conflicts)].sort();
print("DEP_TENANT_REPAIR_TARGETS="+plan.target_count);
print("DEP_TENANT_REPAIR_PLAN_PATCH="+plan.tenant_patch);
print("DEP_TENANT_REPAIR_PLAN_EXISTING="+plan.tenant_existing);
print("DEP_TENANT_REPAIR_INACTIVE_STUDENTS="+plan.inactive_students);
print("DEP_TENANT_REPAIR_GRADE_RECORDS="+plan.grade_records);
print("DEP_TENANT_REPAIR_ATTENDANCE_RECORDS="+plan.attendance_records);
print("DEP_TENANT_REPAIR_CONFLICTS="+types.length);
if(types.length){{print("DEP_TENANT_REPAIR_CONFLICT_TYPES="+types.join(","));print("PRODUCTION_DATABASE_TOUCHED=NO");quit(53);}}
if(mode==="preview"){{
  print("DEP_TENANT_REPAIR_MODE=PREVIEW");
  print("PRODUCTION_DATABASE_TOUCHED=NO");
  quit(0);
}}
const now=new Date().toISOString();
let patched=0,audits=0;
for(const id of ids){{
  const before=d.student_dependencies.findOne({{id}});
  if(norm(before.mantenedora_id)===norm(tenant)) continue;
  const res=d.student_dependencies.updateOne(
    {{id,$or:[{{mantenedora_id:{{$exists:false}}}},{{mantenedora_id:null}},{{mantenedora_id:""}}]}},
    {{$set:{{mantenedora_id:tenant}}}}
  );
  if(res.matchedCount!==1||res.modifiedCount!==1){{print("DEP_TENANT_REPAIR_ERROR=CONCURRENT_CHANGE");print("PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY");quit(71);}}
  patched++;
  d.audit_logs.insertOne({{
    action:"restore",collection:"student_dependencies",document_id:String(id),mantenedora_id:tenant,
    user_id:"system:dependency-tenant-repair-2026",school_id:before.school_id||null,academic_year:year,
    old_value:{{mantenedora_id:before.mantenedora_id??null}},new_value:{{mantenedora_id:tenant}},
    description:"Backfill forense de mantenedora_id em vínculo legado de Dependência 2026",
    timestamp_utc:now,timestamp_local:now,restoration_run_id:runId
  }});
  audits++;
}}
const verified=d.student_dependencies.countDocuments({{id:{{$in:ids}},mantenedora_id:tenant}});
if(verified!==expected){{print("DEP_TENANT_REPAIR_ERROR=POST_VERIFY:"+verified);print("PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY");quit(72);}}
const gradesAfter=d.grades.countDocuments({{dependency_id:{{$in:ids}}}});
const attendanceAfter=(d.attendance.aggregate([
  {{$match:{{"records.dependency_id":{{$in:ids}}}}}},
  {{$project:{{n:{{$size:{{$filter:{{input:{{$ifNull:["$records",[]]}},as:"r",cond:{{$in:["$$r.dependency_id",ids]}}}}}}}}}}}},
  {{$group:{{_id:null,total:{{$sum:"$n"}}}}}}
]).toArray()[0]||{{total:0}}).total;
if(gradesAfter!==plan.grade_records||attendanceAfter!==plan.attendance_records){{print("DEP_TENANT_REPAIR_ERROR=ACADEMIC_DATA_CHANGED");print("PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY");quit(73);}}
print("DEP_TENANT_REPAIR_APPLY_PATCHED="+patched);
print("DEP_TENANT_REPAIR_APPLY_AUDIT_EVENTS="+audits);
print("DEP_TENANT_REPAIR_POST_VISIBLE="+verified);
print("DEP_TENANT_REPAIR_POST_GRADE_RECORDS="+gradesAfter);
print("DEP_TENANT_REPAIR_POST_ATTENDANCE_RECORDS="+attendanceAfter);
print("DEP_TENANT_REPAIR_MODE=APPLY");
print("PRODUCTION_DATABASE_TOUCHED=YES_AUTHORIZED_TENANT_BACKFILL_ONLY");
'''


def main() -> int:
    if len(sys.argv) != 4:
        emit("DEP_TENANT_REPAIR_USAGE_ERROR")
        return 2
    mongo_container, run_id, mode = sys.argv[1:]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", mongo_container) or not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        emit("DEP_TENANT_REPAIR_ARGUMENT_INVALID")
        return 2
    if mode not in {"preview", "apply"}:
        emit("DEP_TENANT_REPAIR_MODE_INVALID")
        return 2
    image = run(["docker", "inspect", "-f", "{{.Config.Image}}", mongo_container])
    if image.returncode != 0 or image.stdout.strip() != EXPECTED_IMAGE:
        emit("DEP_TENANT_REPAIR_MONGO_IMAGE_MISMATCH")
        emit("PRODUCTION_DATABASE_TOUCHED=NO")
        return 3
    out = mongosh(mongo_container, js_program(mode, run_id))
    for line in out.splitlines():
        if line.startswith("DEP_TENANT_REPAIR_") or line.startswith("PRODUCTION_DATABASE_TOUCHED="):
            emit(line)
    if "DEP_TENANT_REPAIR_ERROR=" in out or "DEP_TENANT_REPAIR_CONFLICTS=0" not in out:
        return 4
    if mode == "apply" and "DEP_TENANT_REPAIR_MODE=APPLY" not in out:
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
