#!/usr/bin/env bash
# LUIZ-GOMES-F6.3d.1 — identifica um único dump BSON coerente de 18/08/2026
# fora da árvore canônica e o restaura SOMENTE em Mongo temporário isolado.
set -euo pipefail

mongo_container="${1:?mongo container required}"
run_id="${2:?run id required}"
probe_host="${3:?probe path required}"
canonical_root='/root/sigesc-backups'
roots=(/root /opt /srv /var/backups)
expected_image='mongo:7'
drill=''

cleanup() {
  if [[ -n "$drill" ]]; then
    docker rm -f "$drill" >/dev/null 2>&1 || true
  fi
  rm -f "$probe_host" >/dev/null 2>&1 || true
}
trap cleanup EXIT

test -s "$probe_host" || { echo 'F63D1_PROBE_STAGE_MISSING'; exit 1; }

# Descobre grupos por diretório-pai, sem emitir caminho ou basename.
declare -A file_by_group_collection count_by_group min_epoch_by_group max_epoch_by_group
for root in "${roots[@]}"; do
  [[ -d "$root" ]] || continue
  while IFS= read -r -d '' bson; do
    mtime="$(stat -Lc '%Y' "$bson")"
    [[ "$(date -u -d "@$mtime" '+%Y-%m-%d')" == '2026-08-18' ]] || continue
    group="$(dirname "$bson")"
    base="$(basename "$bson")"
    collection="${base%.bson}"
    [[ "$collection" =~ ^[A-Za-z0-9_]+$ ]] || continue
    key="$group"
    count_by_group[$key]=$(( ${count_by_group[$key]:-0} + 1 ))
    file_by_group_collection["$key|$collection"]="$bson"
    if [[ -z "${min_epoch_by_group[$key]:-}" || "$mtime" -lt "${min_epoch_by_group[$key]}" ]]; then min_epoch_by_group[$key]="$mtime"; fi
    if [[ -z "${max_epoch_by_group[$key]:-}" || "$mtime" -gt "${max_epoch_by_group[$key]}" ]]; then max_epoch_by_group[$key]="$mtime"; fi
  done < <(
    find "$root" -xdev -maxdepth 8 \
      \( -path "$canonical_root" -o -path "$canonical_root/*" \) -prune -o \
      -type f -name '*.bson' -print0 2>/dev/null
  )
done

required=(users schools classes courses learning_objects)
optional=(staff teacher_assignments teacher_class_assignments content_entries audit_logs)
eligible=()
for group in "${!count_by_group[@]}"; do
  ok=true
  for col in "${required[@]}"; do
    file="${file_by_group_collection["$group|$col"]:-}"
    if [[ -z "$file" || ! -s "$file" ]]; then ok=false; break; fi
  done
  [[ "$ok" == true ]] || continue
  spread=$(( ${max_epoch_by_group[$group]} - ${min_epoch_by_group[$group]} ))
  (( spread <= 600 )) || continue
  eligible+=("$group")
done

[[ "${#eligible[@]}" -eq 1 ]] || {
  echo "F63D1_ELIGIBLE_GROUP_COUNT:${#eligible[@]}"
  exit 1
}
group="${eligible[0]}"
[[ "$group" != "$canonical_root" && "$group" != "$canonical_root/"* ]] || {
  echo 'F63D1_CANONICAL_TREE_SELECTION_BLOCKED'
  exit 1
}

bson_count="${count_by_group[$group]}"
(( bson_count >= 5 && bson_count <= 100 )) || { echo "F63D1_GROUP_BSON_COUNT_INVALID:$bson_count"; exit 1; }
spread=$(( ${max_epoch_by_group[$group]} - ${min_epoch_by_group[$group]} ))
group_fp="$(printf '%s' "$group" | sha256sum | awk '{print substr($1,1,16)}')"

present=()
for col in "${required[@]}" "${optional[@]}"; do
  [[ -s "${file_by_group_collection["$group|$col"]:-}" ]] && present+=("$col")
done
collections_csv="$(IFS=,; echo "${present[*]}")"
printf 'F63D1_GROUP_META_JSON={"snapshot_date":"2026-08-18","group_fingerprint":"%s","bson_files":%d,"mtime_spread_seconds":%d,"provenance":"structural_only_ad_hoc_bson_dump","collections":"%s"}\n' \
  "$group_fp" "$bson_count" "$spread" "$collections_csv"

echo 'F63D1_GROUP_SELECTION=PASS'
echo 'F63D1_CANONICAL_BACKUP_TREE_EXCLUDED=YES'
echo 'F63D1_SOURCE_FILES_MUTATED=NO'

mongo_image="$(docker inspect -f '{{.Config.Image}}' "$mongo_container")"
test -n "$mongo_image" || { echo 'F63D1_PRODUCTION_MONGO_IMAGE_UNRESOLVED'; exit 1; }
[[ "$mongo_image" == "$expected_image" ]] || { echo 'F63D1_MONGO_IMAGE_MISMATCH'; exit 1; }

drill="sigesc-f63d1-${run_id}"
docker run -d --name "$drill" --network none \
  --mount "type=bind,src=$group,dst=/dump,readonly" \
  --mount "type=bind,src=$probe_host,dst=/forensic/probe.js,readonly" \
  "$mongo_image" mongod --bind_ip 127.0.0.1 >/dev/null

for attempt in $(seq 1 30); do
  if docker exec "$drill" mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)' >/dev/null 2>&1; then
    break
  fi
  sleep 1
  [[ "$attempt" != 30 ]] || { echo 'F63D1_TEMP_MONGO_START_FAIL'; exit 1; }
done

[[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$drill")" == 'none' ]] || { echo 'F63D1_NETWORK_ISOLATION_FAIL'; exit 1; }
test -z "$(docker port "$drill" 2>/dev/null || true)" || { echo 'F63D1_PUBLISHED_PORT_FAIL'; exit 1; }

# Restore explícito e limitado por coleção. Nunca usa namespace de estudantes,
# matrículas, frequência ou notas.
for col in "${required[@]}" "${optional[@]}"; do
  source_file="${file_by_group_collection["$group|$col"]:-}"
  [[ -s "$source_file" ]] || continue
  docker exec "$drill" mongorestore --quiet --stopOnError --db sigesc --collection "$col" "/dump/$col.bson" >/dev/null 2>&1
  echo "F63D1_RESTORED_COLLECTION:$col"
done

point_line="$(docker exec "$drill" mongosh --quiet --file /forensic/probe.js \
  | grep '^LUIZ_GOMES_F6_3C_POINT_JSON=' | tail -n 1 || true)"
test -n "$point_line" || { echo 'F63D1_POINT_PROBE_NO_JSON'; exit 1; }
printf '%s\n' "$point_line"

docker rm -f "$drill" >/dev/null 2>&1
drill=''

echo 'PRODUCTION_DATABASE_TOUCHED=NO'
echo 'TEMP_RESTORE_NETWORK=none'
echo 'TEMP_RESTORE_PORTS=none'
echo 'SOURCE_MOUNT=read_only'
echo 'TEMP_CONTAINERS_CLEANED=YES'
echo 'PEDAGOGICAL_PLAINTEXT_EMITTED=NO'
