#!/usr/bin/env bash
# SIGESC Dependency Forensics F2 v2 — timeline over retained canonical backups.
# Production Mongo is READ ONLY. mongorestore runs only in disposable isolated containers.
set -euo pipefail

mongo_container="${1:?mongo container required}"
run_id="${2:?run id required}"
backup_root='/root/sigesc-backups'
anchor='E M E I E F Monsenhor Augusto Dias de Brito'
expected_missing=4
baseline_sha='f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a'
baseline_image='mongo:7'
drill=''

cleanup() {
  if [[ -n "${drill:-}" ]]; then
    docker rm -f "$drill" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

source_class() {
  local rel="$1"
  case "/$rel/" in
    *'/daily/'*) echo 'daily' ;;
    *'/weekly/'*) echo 'weekly' ;;
    *'/monthly/'*) echo 'monthly' ;;
    *'/database/'*) echo 'database' ;;
    *'/restore-drills/'*) echo 'restore_drill' ;;
    *) echo 'other' ;;
  esac
}

add_source_class() {
  local current="$1" candidate="$2"
  case "+$current+" in
    *"+$candidate+"*) printf '%s\n' "$current" ;;
    *) printf '%s+%s\n' "$current" "$candidate" ;;
  esac
}

backup_date() {
  local archive="$1" epoch="$2" token digits
  token="$(basename "$archive" | grep -oE '20[0-9]{6}(T[0-9]{6}Z)?' | head -n1 || true)"
  digits="${token:0:8}"
  if [[ "$digits" =~ ^20[0-9]{6}$ ]]; then
    printf '%s-%s-%s\n' "${digits:0:4}" "${digits:4:2}" "${digits:6:2}"
  else
    date -u -d "@$epoch" '+%Y-%m-%d'
  fi
}

test -d "$backup_root" || { echo 'DEP_F2_BACKUP_ROOT_MISSING'; exit 31; }
systemctl is-active --quiet sigesc-mongo-backup.timer || { echo 'DEP_F2_BACKUP_TIMER_NOT_ACTIVE'; exit 33; }

mongo_image="$(docker inspect -f '{{.Config.Image}}' "$mongo_container")"
mongo_name="$(docker inspect -f '{{.Name}}' "$mongo_container" | sed 's#^/##')"
test -n "$mongo_image" && test -n "$mongo_name" || { echo 'DEP_F2_PROD_MONGO_UNRESOLVED'; exit 34; }

# Re-identify the four disappeared links from tenant-scoped CREATE audit evidence.
# This is the only live Mongo access, and it is read-only.
dep_ids="$(docker exec -i "$mongo_container" mongosh --quiet --eval '
  const d=db.getSiblingDB("sigesc");
  const year=2026; const anchor="E M E I E F Monsenhor Augusto Dias de Brito";
  const norm=v=>(v===undefined||v===null)?"":String(v);
  const yearEq=v=>norm(v)===String(year);
  const a=d.schools.find({name:anchor},{_id:0,id:1,mantenedora_id:1}).toArray();
  if(a.length!==1||!a[0].mantenedora_id) quit(41);
  const tenant=a[0].mantenedora_id;
  const schools=new Set(d.schools.find({mantenedora_id:tenant},{_id:0,id:1}).toArray().map(x=>x.id));
  const users=new Set(d.users.find({mantenedora_id:tenant},{_id:0,id:1}).toArray().map(x=>x.id));
  const tenantLog=x=>norm(x.mantenedora_id)===norm(tenant)||((x.mantenedora_id===undefined||x.mantenedora_id===null||norm(x.mantenedora_id)==="")&&((x.school_id&&schools.has(x.school_id))||(x.user_id&&users.has(x.user_id))));
  const current=new Set(d.student_dependencies.find({mantenedora_id:tenant,academic_year:{$in:[year,String(year)]}},{_id:0,id:1}).toArray().map(x=>x.id));
  const logs=d.audit_logs.find({collection:"student_dependencies",action:"create"},{_id:0,document_id:1,mantenedora_id:1,user_id:1,school_id:1,new_value:1}).toArray().filter(tenantLog).filter(x=>yearEq((x.new_value||{}).academic_year));
  const ids=[...new Set(logs.map(x=>x.document_id).filter(id=>id&&!current.has(id)))].sort();
  print(ids.join(","));
' | tail -n 1)"
IFS=',' read -r -a ids <<< "$dep_ids"
[[ "${#ids[@]}" -eq "$expected_missing" ]] || { echo "DEP_F2_MISSING_COUNT_CHANGED:${#ids[@]}"; exit 35; }

# Proven topology (F6.3c.2): canonical root is recursive; tiers need not be direct children.
# Physical identity is device:inode so hard-link promotion cannot duplicate timeline points.
declare -A path_by_inode epoch_by_inode source_by_inode has_sidecars_by_inode
declare -A sha_by_inode date_by_inode provenance_by_inode

while IFS= read -r -d '' archive; do
  inode="$(stat -Lc '%d:%i' "$archive")"
  rel="${archive#${backup_root}/}"
  src="$(source_class "$rel")"
  has_sidecars=false
  [[ -s "${archive}.sha256" && -s "${archive}.metadata.txt" ]] && has_sidecars=true

  if [[ -z "${path_by_inode[$inode]:-}" ]]; then
    path_by_inode[$inode]="$archive"
    epoch_by_inode[$inode]="$(stat -Lc '%Y' "$archive")"
    source_by_inode[$inode]="$src"
    has_sidecars_by_inode[$inode]="$has_sidecars"
  else
    source_by_inode[$inode]="$(add_source_class "${source_by_inode[$inode]}" "$src")"
    # Prefer an alias with both sidecars for canonical integrity/provenance checks.
    if [[ "${has_sidecars_by_inode[$inode]}" != true && "$has_sidecars" == true ]]; then
      path_by_inode[$inode]="$archive"
      has_sidecars_by_inode[$inode]=true
    fi
  fi
done < <(find "$backup_root" -xdev -maxdepth 6 -type f -name '*.archive.gz' -print0)

physical_count="${#path_by_inode[@]}"
(( physical_count > 0 )) || { echo 'DEP_F2_NO_ARCHIVES_FOUND'; exit 43; }
(( physical_count <= 100 )) || { echo "DEP_F2_ARCHIVE_COUNT_SAFETY_LIMIT:$physical_count"; exit 43; }

validated=0
for inode in "${!path_by_inode[@]}"; do
  archive="${path_by_inode[$inode]}"
  src="${source_by_inode[$inode]}"
  gzip -t "$archive" || { echo "DEP_F2_GZIP_FAIL:$src"; exit 38; }
  actual="$(sha256sum "$archive" | awk '{print tolower($1)}')"

  if [[ "$actual" == "$baseline_sha" ]]; then
    [[ "$mongo_image" == "$baseline_image" ]] || { echo 'DEP_F2_BASELINE_IMAGE_MISMATCH'; exit 42; }
    provenance_by_inode[$inode]='documented_pre_dvd_baseline'
  else
    [[ "${has_sidecars_by_inode[$inode]}" == true ]] || { echo "DEP_F2_SIDECARS_MISSING:$src"; exit 36; }
    sha_sidecar="${archive}.sha256"; meta_sidecar="${archive}.metadata.txt"
    expected="$(awk 'NR==1 {print tolower($1)}' "$sha_sidecar")"
    [[ -n "$expected" && "$expected" == "$actual" ]] || { echo "DEP_F2_SHA_FAIL:$src"; exit 39; }
    grep -Fq "$mongo_name" "$meta_sidecar" || { echo "DEP_F2_PROVENANCE_CONTAINER_FAIL:$src"; exit 40; }
    grep -Fq "$mongo_image" "$meta_sidecar" || { echo "DEP_F2_PROVENANCE_IMAGE_FAIL:$src"; exit 42; }
    provenance_by_inode[$inode]='metadata_sha256'
  fi

  sha_by_inode[$inode]="$actual"
  date_by_inode[$inode]="$(backup_date "$archive" "${epoch_by_inode[$inode]}")"
  validated=$((validated+1))
done

(( validated > 0 && validated <= 40 )) || { echo "DEP_F2_VALIDATED_COUNT_INVALID:$validated"; exit 43; }
echo "DEP_F2_PHYSICAL_ARCHIVES=$physical_count"
echo "DEP_F2_VALIDATED_BACKUP_POINTS=$validated"

mapfile -t ordered < <(
  for inode in "${!path_by_inode[@]}"; do
    printf '%s|%s|%s\n' "${date_by_inode[$inode]}" "${epoch_by_inode[$inode]}" "$inode"
  done | sort -t'|' -k1,1 -k2,2n | cut -d'|' -f3-
)

idx=0
for inode in "${ordered[@]}"; do
  idx=$((idx+1))
  archive="${path_by_inode[$inode]}"
  rel="${archive#${backup_root}/}"
  drill="sigesc-dep-f2v2-${run_id}-${idx}"
  cleanup; drill="sigesc-dep-f2v2-${run_id}-${idx}"

  docker run -d --name "$drill" --network none \
    --mount "type=bind,src=$backup_root,dst=/backup,readonly" \
    "$mongo_image" mongod --bind_ip 127.0.0.1 >/dev/null
  for attempt in $(seq 1 30); do
    if docker exec "$drill" mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok?0:1)' >/dev/null 2>&1; then break; fi
    sleep 1
    [[ "$attempt" != 30 ]] || { echo 'DEP_F2_TEMP_MONGO_START_FAIL'; exit 44; }
  done
  [[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$drill")" == 'none' ]] || { echo 'DEP_F2_NETWORK_ISOLATION_FAIL'; exit 45; }
  test -z "$(docker port "$drill" 2>/dev/null || true)" || { echo 'DEP_F2_PORT_ISOLATION_FAIL'; exit 46; }

  docker exec "$drill" mongorestore --quiet --gzip --archive="/backup/$rel" --stopOnError \
    --nsInclude=sigesc.student_dependencies \
    --nsInclude=sigesc.dependency_completions \
    --nsInclude=sigesc.grades \
    --nsInclude=sigesc.attendance >/dev/null 2>&1

  point="$(docker exec -e DEP_IDS="$dep_ids" "$drill" mongosh --quiet --eval '
    const d=db.getSiblingDB("sigesc");
    const ids=(process.env.DEP_IDS||"").split(",").filter(Boolean);
    const deps=d.student_dependencies.find({id:{$in:ids}},{_id:0,id:1,status:1,student_id:1,school_id:1,class_id:1,course_id:1,academic_year:1,origin_academic_year:1,created_at:1,updated_at:1,updated_by:1,status_reason:1}).toArray();
    const depMap=Object.fromEntries(deps.map(x=>[x.id,x]));
    const details=ids.map((id,n)=>{
      const x=depMap[id]||{};
      return {ordinal:n+1,id,present:!!depMap[id],status:x.status||null,student_id:x.student_id||null,school_id:x.school_id||null,class_id:x.class_id||null,course_id:x.course_id||null,academic_year:x.academic_year||null,origin_academic_year:x.origin_academic_year||null,created_at:x.created_at||null,updated_at:x.updated_at||null,updated_by:x.updated_by||null,status_reason:x.status_reason||null,grade_refs:d.grades.countDocuments({dependency_id:id}),attendance_refs:d.attendance.countDocuments({"records.dependency_id":id}),completion_refs:d.dependency_completions.countDocuments({dependency_id:id})};
    });
    print(EJSON.stringify({present_count:details.filter(x=>x.present).length,active_count:details.filter(x=>x.status==="active").length,inactive_count:details.filter(x=>x.present&&x.status!=="active").length,details}));
  ' | tail -n 1)"

  printf 'DEP_F2_POINT_JSON={"ordinal":%d,"backup_date":"%s","source_class":"%s","provenance":"%s","sha_fingerprint":"%s","probe":%s}\n' \
    "$idx" "${date_by_inode[$inode]}" "${source_by_inode[$inode]}" "${provenance_by_inode[$inode]}" "${sha_by_inode[$inode]:0:12}" "$point"
  cleanup; drill=''
done

echo 'PRODUCTION_DATABASE_TOUCHED=NO'
echo 'PRODUCTION_LIVE_READS=ONLY'
echo 'TEMP_RESTORE_NETWORK=none'
echo 'TEMP_RESTORE_PORTS=none'
echo 'BACKUP_MOUNT=READ_ONLY'
echo 'TEMP_CONTAINERS_CLEANED=YES'
