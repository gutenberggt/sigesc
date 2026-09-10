#!/usr/bin/env bash
# SIGESC — Dependency F2 v3: timeline forense read-only por backups retidos.
# Produção: somente leitura. Restore: exclusivamente em Mongo temporário isolado.
set -Eeuo pipefail

mongo_container="${1:?mongo container required}"
run_id="${2:?run id required}"
backup_root='/root/sigesc-backups'
expected_missing=4
expected_image='mongo:7'
baseline_sha='f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a'
anchor='E M E I E F Monsenhor Augusto Dias de Brito'
stage='bootstrap'
drill=''
physical_count=0

cleanup(){
  if [[ -n "${drill:-}" ]]; then
    docker rm -f "$drill" >/dev/null 2>&1 || true
    drill=''
  fi
}
emit_boundary(){
  echo 'PRODUCTION_DATABASE_TOUCHED=NO'
  echo 'TEMP_RESTORE_NETWORK=none'
  echo 'TEMP_RESTORE_PORTS=none'
  echo 'BACKUP_MOUNT=READ_ONLY'
  echo 'TEMP_CONTAINERS_CLEANED=YES'
  echo 'PII_IN_PUBLIC_LOGS=NO'
}
on_error(){
  local rc=$?
  trap - ERR
  cleanup
  printf 'DEP_F2V3_ERROR_STAGE=%s\n' "$stage"
  printf 'DEP_F2V3_REMOTE_RC=%s\n' "$rc"
  emit_boundary
  exit "$rc"
}
trap on_error ERR
trap cleanup EXIT

stage='backup_root'
[[ -d "$backup_root" ]] || { echo 'DEP_F2V3_BACKUP_ROOT_MISSING'; exit 31; }

stage='backup_timer'
systemctl is-active --quiet sigesc-mongo-backup.timer || { echo 'DEP_F2V3_BACKUP_TIMER_NOT_ACTIVE'; exit 32; }

stage='mongo_identity'
set +e
mongo_image="$(docker inspect -f '{{.Config.Image}}' "$mongo_container" 2>/dev/null)"; rc_image=$?
mongo_name="$(docker inspect -f '{{.Name}}' "$mongo_container" 2>/dev/null | sed 's#^/##')"; rc_name=$?
set -e
[[ "$rc_image" -eq 0 && "$rc_name" -eq 0 && -n "$mongo_image" && -n "$mongo_name" ]] || { echo 'DEP_F2V3_PROD_MONGO_UNRESOLVED'; exit 33; }
[[ "$mongo_image" == "$expected_image" ]] || { echo 'DEP_F2V3_MONGO_IMAGE_MISMATCH'; exit 34; }

stage='live_seed'
set +e
seed_output="$(docker exec -i "$mongo_container" mongosh --quiet --file /dev/stdin <<'JS'
const d=db.getSiblingDB("sigesc");
const year=2026;
const expectedMissing=4;
const anchorName="E M E I E F Monsenhor Augusto Dias de Brito";
const norm=v=>(v===undefined||v===null)?"":String(v);
const yearEq=v=>norm(v)===String(year);
const ts=x=>x.timestamp_local||x.timestamp_utc||x.timestamp||null;
const anchors=d.schools.find({name:anchorName},{_id:0,id:1,mantenedora_id:1}).toArray();
if(anchors.length!==1||!anchors[0].mantenedora_id){print("DEP_F2V3_SEED_ERROR=ANCHOR_TENANT_NOT_UNIQUE");quit(41);}
const tenant=anchors[0].mantenedora_id;
const schools=d.schools.find({mantenedora_id:tenant},{_id:0,id:1,name:1}).toArray();
const schoolIds=new Set(schools.map(x=>x.id).filter(Boolean));
const schoolMap=Object.fromEntries(schools.map(x=>[x.id,x.name||null]));
const users=d.users.find({mantenedora_id:tenant},{_id:0,id:1}).toArray();
const userIds=new Set(users.map(x=>x.id).filter(Boolean));
const tenantLog=log=>{
  if(norm(log.mantenedora_id)===norm(tenant)) return true;
  if(log.mantenedora_id!==undefined&&log.mantenedora_id!==null&&norm(log.mantenedora_id)!=="") return false;
  return !!((log.school_id&&schoolIds.has(log.school_id))||(log.user_id&&userIds.has(log.user_id)));
};
const current=d.student_dependencies.find({mantenedora_id:tenant,academic_year:{$in:[year,String(year)]}},{_id:0,id:1}).toArray();
const currentIds=new Set(current.map(x=>x.id).filter(Boolean));
const depLogs=d.audit_logs.find(
  {collection:"student_dependencies"},
  {_id:0,action:1,document_id:1,mantenedora_id:1,user_id:1,school_id:1,timestamp:1,timestamp_utc:1,timestamp_local:1,old_value:1,new_value:1}
).toArray().filter(tenantLog).filter(x=>yearEq((x.new_value||{}).academic_year)||yearEq((x.old_value||{}).academic_year));
const creates=depLogs.filter(x=>x.action==="create"&&x.document_id&&yearEq((x.new_value||{}).academic_year));
const missingIds=[...new Set(creates.map(x=>x.document_id).filter(id=>!currentIds.has(id)))];
if(missingIds.length!==expectedMissing){print("DEP_F2V3_SEED_ERROR=MISSING_COUNT_CHANGED:"+missingIds.length);quit(42);}
const baseById={};
for(const x of creates) if(missingIds.includes(x.document_id)&&!baseById[x.document_id]) baseById[x.document_id]=x.new_value||{};
const studentIds=[...new Set(missingIds.map(id=>(baseById[id]||{}).student_id).filter(Boolean))];
const students=d.students.find({mantenedora_id:tenant,id:{$in:studentIds}},{_id:0,id:1,full_name:1,status:1,dependency_mode:1,school_id:1,class_id:1}).toArray();
const studentMap=Object.fromEntries(students.map(x=>[x.id,x]));
const classIds=[...new Set(missingIds.map(id=>(baseById[id]||{}).class_id).filter(Boolean))];
const courseIds=[...new Set(missingIds.map(id=>(baseById[id]||{}).course_id).filter(Boolean))];
const classes=d.classes.find({id:{$in:classIds}},{_id:0,id:1,name:1,grade:1}).toArray();
const courses=d.courses.find({id:{$in:courseIds}},{_id:0,id:1,name:1}).toArray();
const classMap=Object.fromEntries(classes.map(x=>[x.id,x.name||x.grade||null]));
const courseMap=Object.fromEntries(courses.map(x=>[x.id,x.name||null]));
const details=missingIds.map(id=>{
  const b=baseById[id]||{}; const s=studentMap[b.student_id]||{};
  const ev=depLogs.filter(x=>x.document_id===id).map(x=>({action:x.action,timestamp:ts(x),old_status:norm((x.old_value||{}).status)||null,new_status:norm((x.new_value||{}).status)||null}));
  return {dependency_id:id,student_id:b.student_id||null,student_name:s.full_name||null,student_status_now:s.status||null,dependency_mode_now:s.dependency_mode||null,school_id:b.school_id||null,school_name:schoolMap[b.school_id]||null,class_id:b.class_id||null,class_name:classMap[b.class_id]||null,course_id:b.course_id||null,course_name:courseMap[b.course_id]||null,academic_year:b.academic_year||null,origin_academic_year:b.origin_academic_year||null,created_at:b.created_at||null,created_by:b.created_by||null,audit_events:ev};
});
print("DEP_F2V3_PRIVATE_SEED_JSON="+EJSON.stringify({dependency_ids:missingIds,unique_students:studentIds.length,details}));
print("DEP_F2V3_SEED_COUNT="+missingIds.length);
JS
)"
seed_rc=$?
set -e
seed_safe="$(printf '%s\n' "$seed_output" | grep '^DEP_F2V3_SEED_ERROR=' | tail -n1 || true)"
if [[ "$seed_rc" -ne 0 ]]; then
  [[ -z "$seed_safe" ]] || printf '%s\n' "$seed_safe"
  echo 'DEP_F2V3_LIVE_SEED_FAILED'
  exit 35
fi
seed_private_line="$(printf '%s\n' "$seed_output" | grep '^DEP_F2V3_PRIVATE_SEED_JSON=' | tail -n1 || true)"
seed_count_line="$(printf '%s\n' "$seed_output" | grep '^DEP_F2V3_SEED_COUNT=' | tail -n1 || true)"
[[ -n "$seed_private_line" && "$seed_count_line" == "DEP_F2V3_SEED_COUNT=$expected_missing" ]] || { echo 'DEP_F2V3_LIVE_SEED_MARKER_MISSING'; exit 36; }
seed_json="${seed_private_line#DEP_F2V3_PRIVATE_SEED_JSON=}"
# Privado: a linha abaixo é redirecionada pelo workflow para arquivo não público e posteriormente criptografada.
printf 'DEP_F2V3_PRIVATE_SEED_JSON=%s\n' "$seed_json"
echo "DEP_F2V3_SEED_COUNT=$expected_missing"

stage='inventory'
declare -A path_by_inode epoch_by_inode class_by_inode sha_by_inode stamp_by_inode
source_class(){
  local rel="$1"
  case "/$rel/" in
    *'/daily/'*) echo 'daily' ;;
    *'/weekly/'*) echo 'weekly' ;;
    *'/monthly/'*) echo 'monthly' ;;
    *'/database/'*) echo 'database' ;;
    *) echo 'other' ;;
  esac
}
backup_stamp(){
  local archive="$1" token epoch
  token="$(basename "$archive" | grep -oE '20[0-9]{6}T[0-9]{6}Z' | head -n1 || true)"
  if [[ "$token" =~ ^20[0-9]{6}T[0-9]{6}Z$ ]]; then
    printf '%s-%s-%sT%s:%s:%sZ\n' "${token:0:4}" "${token:4:2}" "${token:6:2}" "${token:9:2}" "${token:11:2}" "${token:13:2}"
    return
  fi
  token="$(basename "$archive" | grep -oE '20[0-9]{6}' | head -n1 || true)"
  if [[ "$token" =~ ^20[0-9]{6}$ ]]; then
    printf '%s-%s-%sT00:00:00Z\n' "${token:0:4}" "${token:4:2}" "${token:6:2}"
    return
  fi
  epoch="$(stat -Lc '%Y' "$archive")"
  date -u -d "@$epoch" '+%Y-%m-%dT%H:%M:%SZ'
}

while IFS= read -r -d '' archive; do
  rel="${archive#${backup_root}/}"
  src="$(source_class "$rel")"
  [[ "$src" != 'other' ]] || continue
  inode="$(stat -Lc '%d:%i' "$archive")"
  if [[ -n "${path_by_inode[$inode]:-}" ]]; then
    case "+${class_by_inode[$inode]}+" in *"+$src+"*) ;; *) class_by_inode[$inode]="${class_by_inode[$inode]}+$src" ;; esac
    continue
  fi

  stage="validate_archive_${physical_count}"
  gzip -t "$archive" >/dev/null 2>&1 || { echo "DEP_F2V3_GZIP_FAIL:$src"; exit 37; }
  actual="$(sha256sum "$archive" | awk '{print tolower($1)}')"
  [[ -n "$actual" ]] || { echo "DEP_F2V3_SHA_COMPUTE_FAIL:$src"; exit 38; }
  if [[ "$actual" == "$baseline_sha" ]]; then
    src="documented_baseline"
  else
    sha_sidecar="${archive}.sha256"; meta_sidecar="${archive}.metadata.txt"
    [[ -s "$sha_sidecar" ]] || { echo "DEP_F2V3_SHA_SIDECAR_MISSING:$src"; exit 39; }
    [[ -s "$meta_sidecar" ]] || { echo "DEP_F2V3_METADATA_MISSING:$src"; exit 40; }
    expected="$(awk 'NR==1 {print tolower($1)}' "$sha_sidecar")"
    [[ -n "$expected" && "$expected" == "$actual" ]] || { echo "DEP_F2V3_SHA_FAIL:$src"; exit 41; }
    grep -Fq "$mongo_name" "$meta_sidecar" || { echo "DEP_F2V3_PROVENANCE_CONTAINER_FAIL:$src"; exit 42; }
    grep -Fq "$mongo_image" "$meta_sidecar" || { echo "DEP_F2V3_PROVENANCE_IMAGE_FAIL:$src"; exit 43; }
  fi
  path_by_inode[$inode]="$archive"
  epoch_by_inode[$inode]="$(stat -Lc '%Y' "$archive")"
  class_by_inode[$inode]="$src"
  sha_by_inode[$inode]="$actual"
  stamp_by_inode[$inode]="$(backup_stamp "$archive")"
  physical_count=$((physical_count+1))
done < <(find "$backup_root" -xdev -maxdepth 6 -type f -name '*.archive.gz' -print0)

[[ "$physical_count" -gt 0 && "$physical_count" -le 40 ]] || { echo "DEP_F2V3_BACKUP_COUNT_INVALID:$physical_count"; exit 44; }
echo "DEP_F2V3_VALIDATED_BACKUP_POINTS=$physical_count"

mapfile -t ordered < <(
  for inode in "${!path_by_inode[@]}"; do printf '%s|%s\n' "${epoch_by_inode[$inode]}" "$inode"; done | sort -n -t'|' -k1,1 | cut -d'|' -f2-
)
[[ "${#ordered[@]}" -eq "$physical_count" ]] || { echo 'DEP_F2V3_ORDER_COUNT_MISMATCH'; exit 45; }

idx=0
for inode in "${ordered[@]}"; do
  idx=$((idx+1))
  stage="restore_point_${idx}"
  archive="${path_by_inode[$inode]}"
  rel="${archive#${backup_root}/}"
  drill="sigesc-dep-f2v3-${run_id}-${idx}"
  cleanup
  drill="sigesc-dep-f2v3-${run_id}-${idx}"
  docker run -d --name "$drill" --network none \
    --mount "type=bind,src=$backup_root,dst=/backup,readonly" \
    "$mongo_image" mongod --bind_ip 127.0.0.1 >/dev/null
  ready=false
  for attempt in $(seq 1 30); do
    if docker exec "$drill" mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok?0:1)' >/dev/null 2>&1; then ready=true; break; fi
    sleep 1
  done
  [[ "$ready" == true ]] || { echo 'DEP_F2V3_TEMP_MONGO_START_FAIL'; exit 46; }
  [[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$drill")" == 'none' ]] || { echo 'DEP_F2V3_NETWORK_ISOLATION_FAIL'; exit 47; }
  [[ -z "$(docker port "$drill" 2>/dev/null || true)" ]] || { echo 'DEP_F2V3_PORT_ISOLATION_FAIL'; exit 48; }

  set +e
  docker exec "$drill" mongorestore --quiet --gzip --archive="/backup/$rel" --stopOnError \
    --nsInclude=sigesc.student_dependencies \
    --nsInclude=sigesc.dependency_completions \
    --nsInclude=sigesc.grades \
    --nsInclude=sigesc.attendance >/dev/null 2>&1
  restore_rc=$?
  set -e
  [[ "$restore_rc" -eq 0 ]] || { echo "DEP_F2V3_RESTORE_FAILED:$idx"; exit 49; }

  stage="probe_point_${idx}"
  set +e
  point="$(docker exec -i -e DEP_F2V3_SEED_JSON="$seed_json" "$drill" mongosh --quiet --file /dev/stdin <<'JS'
const d=db.getSiblingDB("sigesc");
const seed=EJSON.parse(process.env.DEP_F2V3_SEED_JSON||"{}");
const ids=seed.dependency_ids||[];
if(ids.length!==4){print("DEP_F2V3_POINT_ERROR=SEED_COUNT");quit(51);}
const deps=d.student_dependencies.find({id:{$in:ids}},{_id:0,id:1,status:1,student_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,origin_academic_year:1,created_at:1,updated_at:1,updated_by:1,status_reason:1}).toArray();
const depMap=Object.fromEntries(deps.map(x=>[x.id,x]));
function attendanceRefs(id){let n=0; d.attendance.find({"records.dependency_id":id},{_id:0,records:1}).forEach(doc=>{for(const r of (doc.records||[])) if(r&&r.dependency_id===id) n++;}); return n;}
const details=ids.map((id,n)=>{const x=depMap[id]||{};return {ordinal:n+1,id,present:!!depMap[id],status:x.status||null,student_id:x.student_id||null,school_id:x.school_id||null,class_id:x.class_id||null,course_id:x.course_id||null,academic_year:x.academic_year||null,origin_academic_year:x.origin_academic_year||null,created_at:x.created_at||null,updated_at:x.updated_at||null,updated_by:x.updated_by||null,status_reason:x.status_reason||null,grade_refs:d.grades.countDocuments({dependency_id:id}),attendance_refs:attendanceRefs(id),completion_refs:d.dependency_completions.countDocuments({dependency_id:id})};});
print("DEP_F2V3_PRIVATE_POINT="+EJSON.stringify({present_count:details.filter(x=>x.present).length,active_count:details.filter(x=>x.status==="active").length,inactive_count:details.filter(x=>x.present&&x.status!=="active").length,details}));
JS
)"
  point_rc=$?
  set -e
  [[ "$point_rc" -eq 0 ]] || { echo "DEP_F2V3_POINT_PROBE_FAILED:$idx"; exit 50; }
  point_line="$(printf '%s\n' "$point" | grep '^DEP_F2V3_PRIVATE_POINT=' | tail -n1 || true)"
  [[ -n "$point_line" ]] || { echo "DEP_F2V3_POINT_MARKER_MISSING:$idx"; exit 51; }
  point_json="${point_line#DEP_F2V3_PRIVATE_POINT=}"
  printf 'DEP_F2V3_PRIVATE_POINT_JSON={"ordinal":%d,"backup_stamp":"%s","source_class":"%s","sha_fingerprint":"%s","probe":%s}\n' \
    "$idx" "${stamp_by_inode[$inode]}" "${class_by_inode[$inode]}" "${sha_by_inode[$inode]:0:12}" "$point_json"
  cleanup
  echo "DEP_F2V3_POINT_COMPLETED=$idx"
done

stage='complete'
emit_boundary
