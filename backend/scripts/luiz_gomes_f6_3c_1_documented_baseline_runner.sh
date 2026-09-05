#!/usr/bin/env bash
# LUIZ-GOMES-F6.3c.1 — restaura SOMENTE o baseline documental de 2026-08-19
# em Mongo temporário isolado. Nenhum mongorestore é executado contra produção.
set -euo pipefail

mongo_container="${1:?mongo container required}"
run_id="${2:?run id required}"
probe_host="${3:?probe path required}"
backup_root='/root/sigesc-backups'
baseline_rel='database/sigesc-full-20260819T140519Z.archive.gz'
baseline="$backup_root/$baseline_rel"
expected_sha='f4db1877202e4933335523e197f3ef63706f37bf60b4c3cfd0ef08674568b61a'
expected_image='mongo:7'
drill=""

cleanup() {
  if [[ -n "$drill" ]]; then
    docker rm -f "$drill" >/dev/null 2>&1 || true
  fi
  rm -f "$probe_host" >/dev/null 2>&1 || true
}
trap cleanup EXIT

test -s "$probe_host" || { echo 'F63C1_PROBE_STAGE_MISSING'; exit 1; }
test -f "$baseline" || { echo 'F63C1_DOCUMENTED_BASELINE_MISSING'; exit 1; }
gzip -t "$baseline" || { echo 'F63C1_BASELINE_GZIP_FAIL'; exit 1; }
actual_sha="$(sha256sum "$baseline" | awk '{print tolower($1)}')"
[[ "$actual_sha" == "$expected_sha" ]] || { echo 'F63C1_BASELINE_SHA_FAIL'; exit 1; }

mongo_image="$(docker inspect -f '{{.Config.Image}}' "$mongo_container")"
mongo_name="$(docker inspect -f '{{.Name}}' "$mongo_container" | sed 's#^/##')"
test -n "$mongo_image" && test -n "$mongo_name" || {
  echo 'F63C1_PRODUCTION_MONGO_IDENTITY_UNRESOLVED'
  exit 1
}
[[ "$mongo_image" == "$expected_image" ]] || {
  echo 'F63C1_DOCUMENTED_IMAGE_MISMATCH'
  exit 1
}

echo 'F63C1_BASELINE_IDENTITY=PASS'
echo 'F63C1_BASELINE_GZIP=PASS'
echo 'F63C1_BASELINE_SHA=PASS'
echo 'F63C1_BASELINE_PROVENANCE=DOCUMENTED_PRE_DVD_BASELINE'

drill="sigesc-f63c1-${run_id}"
docker run -d --name "$drill" --network none \
  --mount "type=bind,src=$backup_root,dst=/backup,readonly" \
  --mount "type=bind,src=$probe_host,dst=/forensic/probe.js,readonly" \
  "$mongo_image" mongod --bind_ip 127.0.0.1 >/dev/null

for attempt in $(seq 1 30); do
  if docker exec "$drill" mongosh --quiet --eval \
    'quit(db.adminCommand({ping:1}).ok ? 0 : 1)' >/dev/null 2>&1; then
    break
  fi
  sleep 1
  [[ "$attempt" != 30 ]] || { echo 'F63C1_TEMP_MONGO_START_FAIL'; exit 1; }
done

[[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$drill")" == 'none' ]] || {
  echo 'F63C1_NETWORK_ISOLATION_FAIL'
  exit 1
}
test -z "$(docker port "$drill" 2>/dev/null || true)" || {
  echo 'F63C1_PUBLISHED_PORT_FAIL'
  exit 1
}

# Restore parcial — somente catálogo, identidade/vínculo docente e fontes de conteúdo.
docker exec "$drill" mongorestore --quiet --gzip \
  --archive="/backup/$baseline_rel" --stopOnError \
  --nsInclude=sigesc.users \
  --nsInclude=sigesc.staff \
  --nsInclude=sigesc.schools \
  --nsInclude=sigesc.classes \
  --nsInclude=sigesc.courses \
  --nsInclude=sigesc.teacher_assignments \
  --nsInclude=sigesc.teacher_class_assignments \
  --nsInclude=sigesc.learning_objects \
  --nsInclude=sigesc.content_entries \
  --nsInclude=sigesc.audit_logs >/dev/null 2>&1

point_line="$(docker exec "$drill" mongosh --quiet --file /forensic/probe.js \
  | grep '^LUIZ_GOMES_F6_3C_POINT_JSON=' | tail -n 1 || true)"
test -n "$point_line" || { echo 'F63C1_POINT_PROBE_NO_JSON'; exit 1; }
printf 'F63C1_POINT_META_JSON={"backup_date":"2026-08-19","source":"documented_pre_dvd_baseline","sha_fingerprint":"%s"}\n' "${actual_sha:0:12}"
printf '%s\n' "$point_line"

docker rm -f "$drill" >/dev/null 2>&1
drill=""

echo 'PRODUCTION_DATABASE_TOUCHED=NO'
echo 'TEMP_RESTORE_NETWORK=none'
echo 'TEMP_RESTORE_PORTS=none'
echo 'BACKUP_MOUNT=read_only'
echo 'TEMP_CONTAINERS_CLEANED=YES'
