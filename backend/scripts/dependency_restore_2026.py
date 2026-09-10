#!/usr/bin/env python3
"""SIGESC — recuperação forense dos vínculos de Dependência 2026.

Uso remoto (host de produção):
    python3 - <MONGO_CONTAINER> <RUN_ID> <preview|apply>

O script nunca restaura um dump diretamente no Mongo de produção. O archive mais
recente validado é restaurado apenas em um Mongo temporário com --network none,
sem portas e com /root/sigesc-backups montado read-only. Em modo preview o Mongo
live é somente leitura. Em apply, somente os quatro vínculos reidentificados e os
fragmentos de grade/frequência vinculados a eles podem ser escritos.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

BACKUP_ROOT = Path("/root/sigesc-backups")
EXPECTED_MISSING = 4
EXPECTED_IMAGE = "mongo:7"
BASELINE_SHA = "f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a"
ANCHOR = "E M E I E F Monsenhor Augusto Dias de Brito"
YEAR = 2026


def emit(msg: str) -> None:
    print(msg, flush=True)


def fail(code: int, marker: str):
    emit(marker)
    emit("PRODUCTION_DATABASE_TOUCHED=NO" if code < 70 else "PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY")
    raise SystemExit(code)


def run(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(cmd, input=input_text, text=True, capture_output=True)
    if check and cp.returncode != 0:
        raise RuntimeError(f"command failed rc={cp.returncode}: {cmd[0]}")
    return cp


def docker_mongosh(container: str, js: str) -> str:
    cp = run(["docker", "exec", "-i", container, "mongosh", "--quiet", "--file", "/dev/stdin"], input_text=js, check=False)
    if cp.returncode != 0:
        raise RuntimeError(f"mongosh failed rc={cp.returncode}")
    return cp.stdout


def parse_marker(text: str, prefix: str) -> str:
    vals = [line[len(prefix):] for line in text.splitlines() if line.startswith(prefix)]
    if len(vals) != 1:
        raise RuntimeError(f"marker {prefix} count={len(vals)}")
    return vals[0]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_class(rel: str) -> str:
    wrapped = f"/{rel}/"
    for tier in ("daily", "weekly", "monthly", "database"):
        if f"/{tier}/" in wrapped:
            return tier
    return "other"


def backup_stamp(path: Path) -> str:
    m = re.search(r"(20\d{6}T\d{6}Z)", path.name)
    if m:
        t = m.group(1)
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}T{t[9:11]}:{t[11:13]}:{t[13:15]}Z"
    m = re.search(r"(20\d{6})", path.name)
    if m:
        t = m.group(1)
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}T00:00:00Z"
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime))


def inventory_latest(mongo_name: str, mongo_image: str) -> dict:
    if not BACKUP_ROOT.is_dir():
        fail(31, "DEP_REC_BACKUP_ROOT_MISSING")
    timer = run(["systemctl", "is-active", "--quiet", "sigesc-mongo-backup.timer"], check=False)
    if timer.returncode != 0:
        fail(32, "DEP_REC_BACKUP_TIMER_NOT_ACTIVE")

    found = run(["find", str(BACKUP_ROOT), "-xdev", "-maxdepth", "6", "-type", "f", "-name", "*.archive.gz", "-print0"]).stdout
    paths = [Path(p) for p in found.split("\0") if p]
    by_inode: dict[tuple[int, int], dict] = {}
    for path in paths:
        rel = str(path.relative_to(BACKUP_ROOT))
        tier = source_class(rel)
        if tier == "other":
            continue
        st = path.stat()
        key = (st.st_dev, st.st_ino)
        if key in by_inode:
            by_inode[key]["classes"].add(tier)
            continue
        gz = run(["gzip", "-t", str(path)], check=False)
        if gz.returncode != 0:
            fail(37, f"DEP_REC_GZIP_FAIL:{tier}")
        actual = sha256_file(path)
        if actual == BASELINE_SHA:
            classes = {"documented_baseline"}
        else:
            sha_sidecar = Path(str(path) + ".sha256")
            meta_sidecar = Path(str(path) + ".metadata.txt")
            if not sha_sidecar.is_file() or sha_sidecar.stat().st_size == 0:
                fail(39, f"DEP_REC_SHA_SIDECAR_MISSING:{tier}")
            if not meta_sidecar.is_file() or meta_sidecar.stat().st_size == 0:
                fail(40, f"DEP_REC_METADATA_MISSING:{tier}")
            expected = sha_sidecar.read_text(encoding="utf-8", errors="replace").split()[0].lower()
            if expected != actual:
                fail(41, f"DEP_REC_SHA_FAIL:{tier}")
            meta = meta_sidecar.read_text(encoding="utf-8", errors="replace")
            if mongo_name not in meta:
                fail(42, f"DEP_REC_PROVENANCE_CONTAINER_FAIL:{tier}")
            if mongo_image not in meta:
                fail(43, f"DEP_REC_PROVENANCE_IMAGE_FAIL:{tier}")
            classes = {tier}
        by_inode[key] = {
            "path": path,
            "rel": rel,
            "epoch": int(st.st_mtime),
            "classes": classes,
            "sha": actual,
            "stamp": backup_stamp(path),
        }
    if not by_inode or len(by_inode) > 40:
        fail(44, f"DEP_REC_BACKUP_COUNT_INVALID:{len(by_inode)}")
    latest = max(by_inode.values(), key=lambda x: (x["epoch"], x["rel"]))
    emit(f"DEP_REC_VALIDATED_BACKUP_POINTS={len(by_inode)}")
    emit(f"DEP_REC_SOURCE_BACKUP_STAMP={latest['stamp']}")
    emit(f"DEP_REC_SOURCE_BACKUP_SHA12={latest['sha'][:12]}")
    return latest


def live_seed(mongo_container: str) -> dict:
    js = r'''
const d=db.getSiblingDB("sigesc");
const year=2026, expectedMissing=4;
const anchorName="E M E I E F Monsenhor Augusto Dias de Brito";
const norm=v=>(v===undefined||v===null)?"":String(v);
const yearEq=v=>norm(v)===String(year);
const anchors=d.schools.find({name:anchorName},{_id:0,id:1,mantenedora_id:1}).toArray();
if(anchors.length!==1||!anchors[0].mantenedora_id){print("DEP_REC_SEED_ERROR=ANCHOR_TENANT_NOT_UNIQUE");quit(41);}
const tenant=anchors[0].mantenedora_id;
const schools=d.schools.find({mantenedora_id:tenant},{_id:0,id:1}).toArray();
const schoolIds=new Set(schools.map(x=>x.id).filter(Boolean));
const users=d.users.find({mantenedora_id:tenant},{_id:0,id:1}).toArray();
const userIds=new Set(users.map(x=>x.id).filter(Boolean));
const tenantLog=log=>{
  if(norm(log.mantenedora_id)===norm(tenant)) return true;
  if(log.mantenedora_id!==undefined&&log.mantenedora_id!==null&&norm(log.mantenedora_id)!=="") return false;
  return !!((log.school_id&&schoolIds.has(log.school_id))||(log.user_id&&userIds.has(log.user_id)));
};
const current=d.student_dependencies.find({mantenedora_id:tenant,academic_year:{$in:[year,String(year)]}},{_id:0,id:1}).toArray();
const currentIds=new Set(current.map(x=>x.id).filter(Boolean));
const depLogs=d.audit_logs.find({collection:"student_dependencies"},{_id:0,action:1,document_id:1,mantenedora_id:1,user_id:1,school_id:1,old_value:1,new_value:1}).toArray().filter(tenantLog).filter(x=>yearEq((x.new_value||{}).academic_year)||yearEq((x.old_value||{}).academic_year));
const creates=depLogs.filter(x=>x.action==="create"&&x.document_id&&yearEq((x.new_value||{}).academic_year));
const missingIds=[...new Set(creates.map(x=>x.document_id).filter(id=>!currentIds.has(id)))];
if(missingIds.length!==expectedMissing){print("DEP_REC_SEED_ERROR=MISSING_COUNT_CHANGED:"+missingIds.length);quit(42);}
const baseById={};
for(const x of creates) if(missingIds.includes(x.document_id)&&!baseById[x.document_id]) baseById[x.document_id]=x.new_value||{};
const studentIds=[...new Set(missingIds.map(id=>(baseById[id]||{}).student_id).filter(Boolean))];
const students=d.students.find({mantenedora_id:tenant,id:{$in:studentIds}},{_id:0,id:1,status:1,dependency_mode:1,school_id:1,class_id:1}).toArray();
print("DEP_REC_PRIVATE_SEED="+EJSON.stringify({tenant,dependency_ids:missingIds,student_ids:studentIds,students}));
print("DEP_REC_SEED_COUNT="+missingIds.length);
'''
    out = docker_mongosh(mongo_container, js)
    err = [x for x in out.splitlines() if x.startswith("DEP_REC_SEED_ERROR=")]
    if err:
        fail(35, err[-1])
    try:
        seed = json.loads(parse_marker(out, "DEP_REC_PRIVATE_SEED="))
        count = int(parse_marker(out, "DEP_REC_SEED_COUNT="))
    except Exception:
        fail(36, "DEP_REC_LIVE_SEED_MARKER_MISSING")
    if count != EXPECTED_MISSING or len(seed.get("dependency_ids") or []) != EXPECTED_MISSING:
        fail(36, "DEP_REC_LIVE_SEED_COUNT_INVALID")
    emit(f"DEP_REC_SEED_COUNT={count}")
    return seed


def wait_mongo(container: str) -> None:
    for _ in range(30):
        cp = run(["docker", "exec", container, "mongosh", "--quiet", "--eval", "quit(db.adminCommand({ping:1}).ok?0:1)"], check=False)
        if cp.returncode == 0:
            return
        time.sleep(1)
    fail(46, "DEP_REC_TEMP_MONGO_START_FAIL")


def restore_source(mongo_image: str, latest: dict, seed: dict, run_id: str) -> tuple[str, dict]:
    drill = f"sigesc-dep-recovery-{run_id}"
    run(["docker", "rm", "-f", drill], check=False)
    try:
        cp = run([
            "docker", "run", "-d", "--name", drill, "--network", "none",
            "--mount", f"type=bind,src={BACKUP_ROOT},dst=/backup,readonly",
            mongo_image, "mongod", "--bind_ip", "127.0.0.1",
        ], check=False)
        if cp.returncode != 0:
            fail(46, "DEP_REC_TEMP_MONGO_START_FAIL")
        wait_mongo(drill)
        net = run(["docker", "inspect", "-f", "{{.HostConfig.NetworkMode}}", drill]).stdout.strip()
        ports = run(["docker", "port", drill], check=False).stdout.strip()
        if net != "none":
            fail(47, "DEP_REC_NETWORK_ISOLATION_FAIL")
        if ports:
            fail(48, "DEP_REC_PORT_ISOLATION_FAIL")
        rel = latest["rel"]
        cp = run([
            "docker", "exec", drill, "mongorestore", "--quiet", "--gzip",
            f"--archive=/backup/{rel}", "--stopOnError",
            "--nsInclude=sigesc.student_dependencies",
            "--nsInclude=sigesc.dependency_completions",
            "--nsInclude=sigesc.grades",
            "--nsInclude=sigesc.attendance",
        ], check=False)
        if cp.returncode != 0:
            fail(49, "DEP_REC_RESTORE_FAILED")
        ids_json = json.dumps(seed["dependency_ids"], ensure_ascii=False)
        js = f'''
const d=db.getSiblingDB("sigesc");
const ids={ids_json};
const deps=d.student_dependencies.find({{id:{{$in:ids}}}}).toArray();
if(deps.length!==4){{print("DEP_REC_SOURCE_ERROR=DEPENDENCY_COUNT:"+deps.length);quit(51);}}
if(deps.some(x=>String(x.academic_year)!=="2026"||x.status!=="active")){{print("DEP_REC_SOURCE_ERROR=DEPENDENCY_STATE");quit(52);}}
const grades=d.grades.find({{dependency_id:{{$in:ids}}}}).toArray();
const attendance=d.attendance.find({{"records.dependency_id":{{$in:ids}}}}).toArray().map(doc=>({{
  _id:doc._id,id:doc.id||null,class_id:doc.class_id||null,course_id:doc.course_id||null,date:doc.date||null,
  attendance_type:doc.attendance_type||null,academic_year:doc.academic_year||null,
  records:(doc.records||[]).filter(r=>r&&ids.includes(r.dependency_id))
}}));
const completions=d.dependency_completions.find({{dependency_id:{{$in:ids}}}}).toArray();
print("DEP_REC_PRIVATE_SOURCE="+EJSON.stringify({{deps,grades,attendance,completions}}));
'''
        out = docker_mongosh(drill, js)
        src_err = [x for x in out.splitlines() if x.startswith("DEP_REC_SOURCE_ERROR=")]
        if src_err:
            fail(50, src_err[-1])
        try:
            source_text = parse_marker(out, "DEP_REC_PRIVATE_SOURCE=")
            source = json.loads(source_text)
        except Exception:
            fail(50, "DEP_REC_SOURCE_MARKER_MISSING")
        if len(source.get("deps") or []) != EXPECTED_MISSING:
            fail(50, "DEP_REC_SOURCE_DEPENDENCY_COUNT_INVALID")
        if source.get("completions"):
            fail(50, "DEP_REC_SOURCE_TERMINAL_SNAPSHOT_UNEXPECTED")
        emit(f"DEP_REC_SOURCE_GRADES={len(source.get('grades') or [])}")
        att_records = sum(len(x.get("records") or []) for x in source.get("attendance") or [])
        emit(f"DEP_REC_SOURCE_ATTENDANCE_RECORDS={att_records}")
        return source_text, source
    finally:
        run(["docker", "rm", "-f", drill], check=False)


def encode_source(source_text: str) -> str:
    return base64.b64encode(source_text.encode("utf-8")).decode("ascii")


def preflight_js(source_b64: str, expected_tenant: str) -> str:
    return f'''
const d=db.getSiblingDB("sigesc");
const source=EJSON.parse(Buffer.from("{source_b64}","base64").toString("utf8"));
const tenant={json.dumps(expected_tenant)};
const ids=source.deps.map(x=>x.id);
const plan={{dependency_insert:0,dependency_existing:0,grade_insert:0,grade_existing:0,grade_patch_dependency_id:0,attendance_patch_dependency_id:0,attendance_append_record:0,attendance_existing:0,conflicts:[]}};
const coreDep=x=>[x.student_id,x.school_id,x.class_id,x.course_id,String(x.academic_year),String(x.origin_academic_year),x.status].join("|");
for(const dep of source.deps){{
  if(String(dep.mantenedora_id||"")!==String(tenant)) plan.conflicts.push("DEP_TENANT");
  const live=d.student_dependencies.findOne({{id:dep.id}});
  if(!live) plan.dependency_insert++;
  else if(coreDep(live)!==coreDep(dep)) plan.conflicts.push("DEP_MISMATCH"); else plan.dependency_existing++;
  const dup=d.student_dependencies.findOne({{student_id:dep.student_id,course_id:dep.course_id,origin_academic_year:dep.origin_academic_year,status:"active",id:{{$ne:dep.id}}}});
  if(dup) plan.conflicts.push("DEP_ACTIVE_DUPLICATE");
  const stu=d.students.findOne({{id:dep.student_id,mantenedora_id:tenant}},{{_id:0,status:1,dependency_mode:1}});
  if(!stu) plan.conflicts.push("STUDENT_MISSING");
  else {{
    const st=String(stu.status||"active").toLowerCase();
    if(!["active","ativo"].includes(st)) plan.conflicts.push("STUDENT_NOT_ACTIVE");
    if(!["with_dependency","dependency_only"].includes(String(stu.dependency_mode||"none"))) plan.conflicts.push("STUDENT_MODE_INVALID");
  }}
}}
function sameGradeKey(a,b){{return ["student_id","class_id","course_id","academic_year"].every(k=>String(a[k]??"")===String(b[k]??""));}}
for(const g of source.grades){{
  let live=null;
  if(g.id) live=d.grades.findOne({{id:g.id}});
  if(!live&&g._id) live=d.grades.findOne({{_id:g._id}});
  if(!live){{plan.grade_insert++;continue;}}
  if(String(live.dependency_id||"")===String(g.dependency_id||"")){{plan.grade_existing++;continue;}}
  if(!live.dependency_id&&sameGradeKey(live,g)){{plan.grade_patch_dependency_id++;continue;}}
  plan.conflicts.push("GRADE_CONFLICT");
}}
for(const a of source.attendance){{
  let live=null;
  if(a.id) live=d.attendance.findOne({{id:a.id}});
  if(!live&&a._id) live=d.attendance.findOne({{_id:a._id}});
  if(!live){{plan.conflicts.push("ATTENDANCE_DOCUMENT_MISSING");continue;}}
  const records=live.records||[];
  for(const sr of (a.records||[])){{
    const exact=records.filter(r=>r&&r.student_id===sr.student_id&&r.dependency_id===sr.dependency_id);
    if(exact.length===1){{plan.attendance_existing++;continue;}}
    if(exact.length>1){{plan.conflicts.push("ATTENDANCE_DUPLICATE_EXACT");continue;}}
    const same=records.filter(r=>r&&r.student_id===sr.student_id);
    if(same.length===0){{plan.attendance_append_record++;continue;}}
    if(same.length===1&&!same[0].dependency_id){{plan.attendance_patch_dependency_id++;continue;}}
    plan.conflicts.push("ATTENDANCE_STUDENT_CONFLICT");
  }}
}}
if((source.completions||[]).length) plan.conflicts.push("SOURCE_COMPLETION_UNEXPECTED");
print("DEP_REC_PRIVATE_PLAN="+EJSON.stringify(plan));
'''


def apply_js(source_b64: str, expected_tenant: str, run_id: str, backup_stamp_value: str, backup_sha: str) -> str:
    return f'''
const d=db.getSiblingDB("sigesc");
const source=EJSON.parse(Buffer.from("{source_b64}","base64").toString("utf8"));
const tenant={json.dumps(expected_tenant)};
const runId={json.dumps(run_id)};
const backupStamp={json.dumps(backup_stamp_value)};
const backupSha={json.dumps(backup_sha)};
const now=new Date().toISOString();
const counts={{dependency_inserted:0,dependency_existing:0,grade_inserted:0,grade_patched:0,grade_existing:0,attendance_patched:0,attendance_appended:0,attendance_existing:0,audit_events:0}};
const conflicts=[];
const coreDep=x=>[x.student_id,x.school_id,x.class_id,x.course_id,String(x.academic_year),String(x.origin_academic_year),x.status].join("|");
for(const dep of source.deps){{
  if(String(dep.mantenedora_id||"")!==String(tenant)) conflicts.push("DEP_TENANT");
  const live=d.student_dependencies.findOne({{id:dep.id}});
  if(live&&coreDep(live)!==coreDep(dep)) conflicts.push("DEP_MISMATCH");
  const dup=d.student_dependencies.findOne({{student_id:dep.student_id,course_id:dep.course_id,origin_academic_year:dep.origin_academic_year,status:"active",id:{{$ne:dep.id}}}});
  if(dup) conflicts.push("DEP_ACTIVE_DUPLICATE");
  const stu=d.students.findOne({{id:dep.student_id,mantenedora_id:tenant}},{{_id:0,status:1,dependency_mode:1}});
  if(!stu) conflicts.push("STUDENT_MISSING");
  else {{const st=String(stu.status||"active").toLowerCase();if(!["active","ativo"].includes(st))conflicts.push("STUDENT_NOT_ACTIVE");if(!["with_dependency","dependency_only"].includes(String(stu.dependency_mode||"none")))conflicts.push("STUDENT_MODE_INVALID");}}
}}
function sameGradeKey(a,b){{return ["student_id","class_id","course_id","academic_year"].every(k=>String(a[k]??"")===String(b[k]??""));}}
for(const g of source.grades){{let live=null;if(g.id)live=d.grades.findOne({{id:g.id}});if(!live&&g._id)live=d.grades.findOne({{_id:g._id}});if(live&&String(live.dependency_id||"")!==String(g.dependency_id||"")&&!(!live.dependency_id&&sameGradeKey(live,g)))conflicts.push("GRADE_CONFLICT");}}
for(const a of source.attendance){{let live=null;if(a.id)live=d.attendance.findOne({{id:a.id}});if(!live&&a._id)live=d.attendance.findOne({{_id:a._id}});if(!live){{conflicts.push("ATTENDANCE_DOCUMENT_MISSING");continue;}}const records=live.records||[];for(const sr of (a.records||[])){{const exact=records.filter(r=>r&&r.student_id===sr.student_id&&r.dependency_id===sr.dependency_id);if(exact.length>1)conflicts.push("ATTENDANCE_DUPLICATE_EXACT");else if(exact.length===0){{const same=records.filter(r=>r&&r.student_id===sr.student_id);if(!(same.length===0||(same.length===1&&!same[0].dependency_id)))conflicts.push("ATTENDANCE_STUDENT_CONFLICT");}}}}}}
if((source.completions||[]).length)conflicts.push("SOURCE_COMPLETION_UNEXPECTED");
if(conflicts.length){{print("DEP_REC_APPLY_ERROR=PRECONDITION_CONFLICT:"+[...new Set(conflicts)].join(","));quit(71);}}
function audit(collection,documentId,oldValue,newValue,description){{d.audit_logs.insertOne({{action:"restore",collection,document_id:String(documentId),mantenedora_id:tenant,user_id:"system:dependency-forensic-recovery",school_id:(newValue||oldValue||{{}}).school_id||null,academic_year:2026,old_value:oldValue||null,new_value:newValue||null,description,timestamp_utc:now,timestamp_local:now,restoration_run_id:runId,restoration_source_backup:backupStamp,restoration_source_sha256:backupSha}});counts.audit_events++;}}
for(const dep of source.deps){{
  const live=d.student_dependencies.findOne({{id:dep.id}});
  if(!live){{d.student_dependencies.insertOne(dep);counts.dependency_inserted++;audit("student_dependencies",dep.id,null,dep,"Restauração forense de vínculo de Dependência 2026");}}
  else counts.dependency_existing++;
}}
for(const g of source.grades){{
  let live=null;if(g.id)live=d.grades.findOne({{id:g.id}});if(!live&&g._id)live=d.grades.findOne({{_id:g._id}});
  if(!live){{d.grades.insertOne(g);counts.grade_inserted++;audit("grades",g.id||g._id,null,g,"Restauração forense de nota vinculada à Dependência 2026");continue;}}
  if(String(live.dependency_id||"")===String(g.dependency_id||"")){{counts.grade_existing++;continue;}}
  const filter=g.id?{{id:g.id}}:{{_id:g._id}};d.grades.updateOne(filter,{{$set:{{dependency_id:g.dependency_id}}}});counts.grade_patched++;audit("grades",g.id||g._id,{{dependency_id:live.dependency_id||null}},{{dependency_id:g.dependency_id}},"Restauração forense do dependency_id em nota 2026");
}}
for(const a of source.attendance){{
  let live=null;if(a.id)live=d.attendance.findOne({{id:a.id}});if(!live&&a._id)live=d.attendance.findOne({{_id:a._id}});const before=EJSON.parse(EJSON.stringify(live));let changed=false;
  for(const sr of (a.records||[])){{
    const exact=(live.records||[]).filter(r=>r&&r.student_id===sr.student_id&&r.dependency_id===sr.dependency_id);
    if(exact.length===1){{counts.attendance_existing++;continue;}}
    const sameIdx=(live.records||[]).map((r,i)=>({{r,i}})).filter(x=>x.r&&x.r.student_id===sr.student_id);
    if(sameIdx.length===1&&!sameIdx[0].r.dependency_id){{live.records[sameIdx[0].i].dependency_id=sr.dependency_id;counts.attendance_patched++;changed=true;}}
    else if(sameIdx.length===0){{live.records.push(sr);counts.attendance_appended++;changed=true;}}
  }}
  if(changed){{const filter=a.id?{{id:a.id}}:{{_id:a._id}};d.attendance.updateOne(filter,{{$set:{{records:live.records}}}});audit("attendance",a.id||a._id,{{records:before.records}},{{records:live.records}},"Restauração forense de registros de frequência de Dependência 2026");}}
}}
for(const dep of source.deps){{const live=d.student_dependencies.findOne({{id:dep.id}});if(!live||live.status!=="active"||coreDep(live)!==coreDep(dep)){{print("DEP_REC_APPLY_ERROR=POST_DEPENDENCY_VERIFY");quit(72);}}}}
for(const g of source.grades){{let live=null;if(g.id)live=d.grades.findOne({{id:g.id}});if(!live&&g._id)live=d.grades.findOne({{_id:g._id}});if(!live||String(live.dependency_id||"")!==String(g.dependency_id||"")){{print("DEP_REC_APPLY_ERROR=POST_GRADE_VERIFY");quit(73);}}}}
for(const a of source.attendance){{let live=null;if(a.id)live=d.attendance.findOne({{id:a.id}});if(!live&&a._id)live=d.attendance.findOne({{_id:a._id}});for(const sr of (a.records||[])){{const exact=(live.records||[]).filter(r=>r&&r.student_id===sr.student_id&&r.dependency_id===sr.dependency_id);if(exact.length!==1){{print("DEP_REC_APPLY_ERROR=POST_ATTENDANCE_VERIFY");quit(74);}}}}}}
print("DEP_REC_PRIVATE_APPLY="+EJSON.stringify(counts));
'''


def main() -> int:
    if len(sys.argv) != 4:
        emit("DEP_REC_USAGE_ERROR")
        return 2
    mongo_container, run_id, mode = sys.argv[1:]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", mongo_container):
        fail(2, "DEP_REC_MONGO_CONTAINER_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        fail(2, "DEP_REC_RUN_ID_INVALID")
    if mode not in {"preview", "apply"}:
        fail(2, "DEP_REC_MODE_INVALID")

    image_cp = run(["docker", "inspect", "-f", "{{.Config.Image}}", mongo_container], check=False)
    name_cp = run(["docker", "inspect", "-f", "{{.Name}}", mongo_container], check=False)
    if image_cp.returncode != 0 or name_cp.returncode != 0:
        fail(33, "DEP_REC_PROD_MONGO_UNRESOLVED")
    mongo_image = image_cp.stdout.strip()
    mongo_name = name_cp.stdout.strip().lstrip("/")
    if mongo_image != EXPECTED_IMAGE:
        fail(34, "DEP_REC_MONGO_IMAGE_MISMATCH")

    seed = live_seed(mongo_container)
    latest = inventory_latest(mongo_name, mongo_image)
    source_text, source = restore_source(mongo_image, latest, seed, run_id)
    src_b64 = encode_source(source_text)

    try:
        preflight_out = docker_mongosh(mongo_container, preflight_js(src_b64, seed["tenant"]))
        plan_text = parse_marker(preflight_out, "DEP_REC_PRIVATE_PLAN=")
        plan = json.loads(plan_text)
    except Exception:
        fail(60, "DEP_REC_PREFLIGHT_FAILED")
    conflicts = sorted(set(plan.get("conflicts") or []))
    emit(f"DEP_REC_PREFLIGHT_CONFLICTS={len(conflicts)}")
    for key in (
        "dependency_insert", "dependency_existing", "grade_insert", "grade_existing",
        "grade_patch_dependency_id", "attendance_patch_dependency_id",
        "attendance_append_record", "attendance_existing",
    ):
        emit(f"DEP_REC_PLAN_{key.upper()}={int(plan.get(key, 0))}")
    if conflicts:
        emit("DEP_REC_PREFLIGHT_CONFLICT_TYPES=" + ",".join(conflicts))
        fail(61, "DEP_REC_PREFLIGHT_CONFLICT")

    emit("DEP_REC_PRIVATE_EVIDENCE=" + json.dumps({"seed": seed, "source": source, "plan": plan, "source_backup": {"stamp": latest["stamp"], "sha256": latest["sha"]}}, ensure_ascii=False, separators=(",", ":")))

    if mode == "preview":
        emit("DEP_REC_MODE=PREVIEW")
        emit("PRODUCTION_DATABASE_TOUCHED=NO")
        emit("TEMP_RESTORE_NETWORK=none")
        emit("TEMP_RESTORE_PORTS=none")
        emit("BACKUP_MOUNT=READ_ONLY")
        emit("TEMP_CONTAINERS_CLEANED=YES")
        return 0

    try:
        apply_out = docker_mongosh(mongo_container, apply_js(src_b64, seed["tenant"], run_id, latest["stamp"], latest["sha"]))
    except Exception:
        emit("DEP_REC_APPLY_ERROR=LIVE_MONGOSH_FAILURE")
        emit("PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY")
        return 70
    err = [x for x in apply_out.splitlines() if x.startswith("DEP_REC_APPLY_ERROR=")]
    if err:
        emit(err[-1])
        emit("PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY")
        return 71
    try:
        counts_text = parse_marker(apply_out, "DEP_REC_PRIVATE_APPLY=")
        counts = json.loads(counts_text)
    except Exception:
        emit("DEP_REC_APPLY_ERROR=RESULT_MARKER_MISSING")
        emit("PRODUCTION_DATABASE_TOUCHED=POSSIBLE_PARTIAL_APPLY")
        return 75
    emit("DEP_REC_PRIVATE_APPLY=" + counts_text)
    for k, v in counts.items():
        emit(f"DEP_REC_APPLY_{k.upper()}={int(v)}")
    emit("DEP_REC_MODE=APPLY")
    emit("PRODUCTION_DATABASE_TOUCHED=YES_AUTHORIZED_RESTORE_ONLY")
    emit("TEMP_RESTORE_NETWORK=none")
    emit("TEMP_RESTORE_PORTS=none")
    emit("BACKUP_MOUNT=READ_ONLY")
    emit("TEMP_CONTAINERS_CLEANED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
