#!/usr/bin/env bash
set -euo pipefail
mongo_container="${1:?mongo container required}"
run_id="${2:?run id required}"
live_seed_host="${3:?live seed path required}"
probe_template_host="${4:?probe template path required}"
canonical_root='/root/sigesc-backups'
roots=(/root /opt /srv /var/backups)
expected_image='mongo:7'
drill=''
seed_raw="/tmp/sigesc-r1b1-seed-${run_id}.log"
probe_materialized="/tmp/sigesc-r1b1-materialized-${run_id}.js"
probe_raw="/tmp/sigesc-r1b1-probe-${run_id}.log"
cleanup(){
  [[ -z "$drill" ]] || docker rm -f "$drill" >/dev/null 2>&1 || true
  rm -f "$seed_raw" "$probe_materialized" "$probe_raw" "$live_seed_host" "$probe_template_host" >/dev/null 2>&1 || true
}
trap cleanup EXIT
emit_boundary(){
  echo 'PRODUCTION_LIVE_METADATA_READS=YES'
  echo 'PRODUCTION_LIVE_COLLECTIONS=schools,classes,courses'
  echo 'PRODUCTION_WRITES=NO'
  echo 'PRODUCTION_BACKEND_PYTHON_EXECUTIONS=0'
  echo 'LIVE_TECHNICAL_IDS_EXPOSED=NO'
  echo 'R1B1_MONGOSH_MODE=file_dev_stdin'
  echo 'TEMP_RESTORE_NETWORK=none'
  echo 'TEMP_RESTORE_PORTS=none'
  echo 'SOURCE_MOUNT=read_only'
  echo 'TEMP_CONTAINERS_CLEANED=YES'
  echo 'PEDAGOGICAL_PLAINTEXT_EMITTED=NO'
  echo 'RAW_PROBE_OUTPUT_EMITTED=NO'
  echo 'EPHEMERAL_TECHNICAL_ID_FILES_CLEANED=YES'
}
emit_safe_seed_diagnostic(){
  local line="${1:-}"
  [[ -n "$line" ]] || return 0
  if printf '%s\n' "$line" | grep -Eq '^LUIZ_GOMES_R1_0B1_LIVE_SEED_DIAGNOSTIC_JSON=\{"schema":"LUIZ_GOMES_R1_0B1_SEED_DIAGNOSTIC_V1","reason":"[A-Za-z0-9_.$-]{1,64}","diagnostic_stage":"[A-Za-z0-9_.$-]{1,64}","error_name":"[A-Za-z0-9_.$-]{1,64}"\}$'; then
    printf '%s\n' "$line"
  fi
}
# Distinct exit codes are intentionally non-semantic and contain no data.
# The workflow already emits R1B1_REMOTE_SCAN_RC=<code>, so these values
# identify only the controlled failure stage without exposing raw logs.
# 10 staged input; 11 live seed execution; 12 live seed not ready;
# 13 dump selection; 14 canonical tree; 15 Mongo image; 16 temp Mongo start;
# 17 network isolation; 18 published port; 19 restore; 20 probe marker;
# 21 live seed marker missing.

[[ -s "$live_seed_host" && -s "$probe_template_host" ]] || { echo 'R1B1_STAGED_INPUT_MISSING'; emit_boundary; exit 10; }
umask 077
set +e
docker exec -i "$mongo_container" mongosh --quiet --file /dev/stdin < "$live_seed_host" > "$seed_raw" 2>&1
seed_rc=$?
set -e
diag_line="$(grep '^LUIZ_GOMES_R1_0B1_LIVE_SEED_DIAGNOSTIC_JSON=' "$seed_raw" | tail -n 1 || true)"
seed_line="$(grep '^LUIZ_GOMES_R1_0B1_LIVE_SEED_JSON=' "$seed_raw" | tail -n 1 || true)"
if [[ "$seed_rc" -ne 0 ]]; then
  rm -f "$seed_raw"
  echo 'R1B1_LIVE_SEED_EXEC_FAILED'
  emit_boundary
  exit 11
fi
if [[ -z "$seed_line" ]]; then
  emit_safe_seed_diagnostic "$diag_line"
  rm -f "$seed_raw"
  echo 'R1B1_LIVE_SEED_MARKER_MISSING'
  emit_boundary
  exit 21
fi
seed_json="${seed_line#LUIZ_GOMES_R1_0B1_LIVE_SEED_JSON=}"
if [[ "$seed_json" != *'"status":"READY"'* ]]; then
  emit_safe_seed_diagnostic "$diag_line"
  rm -f "$seed_raw"
  echo 'R1B1_LIVE_SEED_NOT_READY'
  emit_boundary
  exit 12
fi
{ printf 'const LIVE_SEED = %s;\n' "$seed_json"; cat "$probe_template_host"; } > "$probe_materialized"
chmod 600 "$probe_materialized"
rm -f "$seed_raw"

declare -A file_by_group_collection count_by_group min_epoch_by_group max_epoch_by_group
for root in "${roots[@]}"; do
  [[ -d "$root" ]] || continue
  while IFS= read -r -d '' bson; do
    mtime="$(stat -Lc '%Y' "$bson")"
    [[ "$(date -u -d "@$mtime" '+%Y-%m-%d')" == '2026-08-18' ]] || continue
    group="$(dirname "$bson")"; collection="$(basename "$bson" .bson)"
    [[ "$collection" =~ ^[A-Za-z0-9_]+$ ]] || continue
    count_by_group[$group]=$(( ${count_by_group[$group]:-0}+1 ))
    file_by_group_collection["$group|$collection"]="$bson"
    [[ -n "${min_epoch_by_group[$group]:-}" && "$mtime" -ge "${min_epoch_by_group[$group]}" ]] || min_epoch_by_group[$group]="$mtime"
    [[ -n "${max_epoch_by_group[$group]:-}" && "$mtime" -le "${max_epoch_by_group[$group]}" ]] || max_epoch_by_group[$group]="$mtime"
  done < <(find "$root" -xdev -maxdepth 8 \( -path "$canonical_root" -o -path "$canonical_root/*" \) -prune -o -type f -name '*.bson' -print0 2>/dev/null)
done
selection_required=(users schools classes courses learning_objects)
eligible=()
for group in "${!count_by_group[@]}"; do
  ok=true
  for c in "${selection_required[@]}"; do [[ -s "${file_by_group_collection["$group|$c"]:-}" ]] || { ok=false; break; }; done
  [[ "$ok" == true ]] || continue
  spread=$(( ${max_epoch_by_group[$group]}-${min_epoch_by_group[$group]} ))
  (( spread<=600 )) || continue
  eligible+=("$group")
done
[[ "${#eligible[@]}" -eq 1 ]] || { echo "R1B1_ELIGIBLE_GROUP_COUNT:${#eligible[@]}"; emit_boundary; exit 13; }
group="${eligible[0]}"
[[ "$group" != "$canonical_root" && "$group" != "$canonical_root/"* ]] || { echo 'R1B1_CANONICAL_TREE_SELECTION_BLOCKED'; emit_boundary; exit 14; }
spread=$(( ${max_epoch_by_group[$group]}-${min_epoch_by_group[$group]} ))
group_fp="$(printf '%s' "$group" | sha256sum | awk '{print substr($1,1,16)}')"
printf 'R1B1_SOURCE_META_JSON={"snapshot_date":"2026-08-18","group_fingerprint":"%s","bson_files":%d,"mtime_spread_seconds":%d,"provenance":"structural_only_ad_hoc_bson_dump"}\n' "$group_fp" "${count_by_group[$group]}" "$spread"

mongo_image="$(docker inspect -f '{{.Config.Image}}' "$mongo_container")"
[[ "$mongo_image" == "$expected_image" ]] || { echo 'R1B1_MONGO_IMAGE_MISMATCH'; emit_boundary; exit 15; }
drill="sigesc-r1b1-${run_id}"
docker run -d --name "$drill" --network none --mount "type=bind,src=$group,dst=/dump,readonly" --mount "type=bind,src=$probe_materialized,dst=/forensic/probe.js,readonly" "$mongo_image" mongod --bind_ip 127.0.0.1 >/dev/null
for attempt in $(seq 1 30); do
  docker exec "$drill" mongosh --quiet --eval 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)' >/dev/null 2>&1 && break
  sleep 1
  if [[ "$attempt" == 30 ]]; then echo 'R1B1_TEMP_MONGO_START_FAIL'; emit_boundary; exit 16; fi
done
[[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$drill")" == 'none' ]] || { echo 'R1B1_NETWORK_ISOLATION_FAIL'; emit_boundary; exit 17; }
test -z "$(docker port "$drill" 2>/dev/null || true)" || { echo 'R1B1_PUBLISHED_PORT_FAIL'; emit_boundary; exit 18; }
restore=(schools classes courses learning_objects)
for c in "${restore[@]}"; do
  f="${file_by_group_collection["$group|$c"]:-}"
  [[ -s "$f" ]] || { echo "R1B1_RESTORE_COLLECTION_MISSING:$c"; emit_boundary; exit 19; }
  set +e
  docker exec "$drill" mongorestore --quiet --stopOnError --db sigesc --collection "$c" "/dump/$c.bson" >/dev/null 2>&1
  restore_rc=$?
  set -e
  [[ "$restore_rc" -eq 0 ]] || { echo "R1B1_RESTORE_FAILED:$c"; emit_boundary; exit 19; }
  echo "R1B1_RESTORED_COLLECTION:$c"
done
set +e
docker exec "$drill" mongosh --quiet --file /forensic/probe.js > "$probe_raw" 2>&1
probe_rc=$?
set -e
point="$(grep '^LUIZ_GOMES_R1_0B1_RESULT_JSON=' "$probe_raw" | tail -n 1 || true)"
if [[ -z "$point" ]]; then
  rm -f "$probe_raw" "$probe_materialized"
  echo "R1B1_PROBE_EXIT_CODE=$probe_rc"
  docker rm -f "$drill" >/dev/null 2>&1 || true; drill=''
  emit_boundary
  exit 20
fi
printf '%s\n' "$point"
rm -f "$probe_raw" "$probe_materialized"
docker rm -f "$drill" >/dev/null 2>&1; drill=''
emit_boundary
