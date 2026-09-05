#!/usr/bin/env bash
# LUIZ-GOMES-F6.3c — executa exclusivamente no host de produção, mas restaura
# backups SOMENTE em containers Mongo temporários isolados. Nenhum mongorestore
# é executado contra o Mongo de produção.
set -euo pipefail

mongo_container="${1:?mongo container required}"
run_id="${2:?run id required}"
probe_host="${3:?probe path required}"
backup_root='/root/sigesc-backups'

cleanup_probe() {
  rm -f "$probe_host" >/dev/null 2>&1 || true
}
cleanup_drill() {
  if [[ -n "${drill:-}" ]]; then
    docker rm -f "$drill" >/dev/null 2>&1 || true
  fi
}
cleanup_all() {
  cleanup_drill
  cleanup_probe
}
trap cleanup_all EXIT

test -s "$probe_host" || { echo 'F63C_PROBE_STAGE_MISSING'; exit 1; }
test -d "$backup_root" || { echo 'F63C_BACKUP_ROOT_MISSING'; exit 1; }
for tier in daily weekly monthly; do
  test -d "$backup_root/$tier" || { echo "F63C_TIER_MISSING:$tier"; exit 1; }
done

systemctl is-active --quiet sigesc-mongo-backup.timer || {
  echo 'F63C_BACKUP_TIMER_NOT_ACTIVE'
  exit 1
}

project="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$mongo_container")"
mongo_image="$(docker inspect -f '{{.Config.Image}}' "$mongo_container")"
mongo_name="$(docker inspect -f '{{.Name}}' "$mongo_container" | sed 's#^/##')"
test -n "$project" && test -n "$mongo_image" && test -n "$mongo_name" || {
  echo 'F63C_PRODUCTION_MONGO_IDENTITY_UNRESOLVED'
  exit 1
}

# A promoção daily -> weekly/monthly usa hard link. A identidade física correta
# é device:inode. SHA continua sendo validado e exposto somente como fingerprint.
declare -A path_by_inode epoch_by_inode tier_by_inode sha_by_inode
for tier in daily weekly monthly; do
  while IFS= read -r -d '' archive; do
    sha_sidecar="${archive}.sha256"
    meta_sidecar="${archive}.metadata.txt"
    test -s "$sha_sidecar" || { echo "F63C_SHA_SIDECAR_MISSING:$tier"; exit 1; }
    test -s "$meta_sidecar" || { echo "F63C_METADATA_MISSING:$tier"; exit 1; }
    gzip -t "$archive" || { echo "F63C_GZIP_FAIL:$tier"; exit 1; }

    expected="$(awk 'NR==1 {print tolower($1)}' "$sha_sidecar")"
    actual="$(sha256sum "$archive" | awk '{print tolower($1)}')"
    test -n "$expected" && test "$expected" = "$actual" || {
      echo "F63C_SHA_FAIL:$tier"
      exit 1
    }

    # Proveniência: o metadata homologado identifica container e imagem do Mongo
    # de origem. Divergência aborta fail-closed antes de qualquer restore.
    grep -Fq "$mongo_name" "$meta_sidecar" || {
      echo "F63C_PROVENANCE_CONTAINER_FAIL:$tier"
      exit 1
    }
    grep -Fq "$mongo_image" "$meta_sidecar" || {
      echo "F63C_PROVENANCE_IMAGE_FAIL:$tier"
      exit 1
    }

    inode_key="$(stat -Lc '%d:%i' "$archive")"
    test -n "$inode_key" || { echo "F63C_INODE_FAIL:$tier"; exit 1; }
    if [[ -z "${path_by_inode[$inode_key]:-}" ]]; then
      path_by_inode[$inode_key]="$archive"
      epoch_by_inode[$inode_key]="$(stat -Lc '%Y' "$archive")"
      tier_by_inode[$inode_key]="$tier"
      sha_by_inode[$inode_key]="$actual"
    else
      tier_by_inode[$inode_key]="${tier_by_inode[$inode_key]}+$tier"
      test "${sha_by_inode[$inode_key]}" = "$actual" || {
        echo 'F63C_HARDLINK_SHA_INCONSISTENT'
        exit 1
      }
    fi
  done < <(find "$backup_root/$tier" -maxdepth 1 -type f -name '*.archive.gz' -print0)
done

count="${#path_by_inode[@]}"
(( count > 0 )) || { echo 'F63C_NO_RETAINED_BACKUPS'; exit 1; }
# 14 daily + 8 weekly + 12 monthly = 34 máximos; folga pequena para detectar
# drift de retenção sem criar uma varredura ilimitada acidental.
(( count <= 40 )) || { echo "F63C_TOO_MANY_UNIQUE_BACKUPS:$count"; exit 1; }
echo "F63C_INVENTORY_COUNT=$count"

mapfile -t ordered < <(
  for inode_key in "${!path_by_inode[@]}"; do
    printf '%s|%s\n' "${epoch_by_inode[$inode_key]}" "$inode_key"
  done | sort -n -t'|' -k1,1 | cut -d'|' -f2-
)

idx=0
for inode_key in "${ordered[@]}"; do
  idx=$((idx + 1))
  archive="${path_by_inode[$inode_key]}"
  rel="${archive#${backup_root}/}"
  epoch="${epoch_by_inode[$inode_key]}"
  backup_date="$(date -u -d "@$epoch" '+%Y-%m-%d')"
  tiers="${tier_by_inode[$inode_key]}"
  sha="${sha_by_inode[$inode_key]}"
  sha_fp="${sha:0:12}"
  drill="sigesc-f63c-${run_id}-${idx}"

  cleanup_drill
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
    if [[ "$attempt" == 30 ]]; then
      echo 'F63C_TEMP_MONGO_START_FAIL'
      exit 1
    fi
  done

  [[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$drill")" == 'none' ]] || {
    echo 'F63C_NETWORK_ISOLATION_FAIL'
    exit 1
  }
  test -z "$(docker port "$drill" 2>/dev/null || true)" || {
    echo 'F63C_PUBLISHED_PORT_FAIL'
    exit 1
  }

  # Namespace allowlist. Nenhuma coleção de estudantes, matrícula, frequência
  # ou notas é restaurada no ambiente forense.
  docker exec "$drill" mongorestore --quiet --gzip \
    --archive="/backup/$rel" --stopOnError \
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
  test -n "$point_line" || { echo 'F63C_POINT_PROBE_NO_JSON'; exit 1; }

  printf 'F63C_POINT_META_JSON={"backup_date":"%s","tier":"%s","sha_fingerprint":"%s","ordinal":%d}\n' \
    "$backup_date" "$tiers" "$sha_fp" "$idx"
  printf '%s\n' "$point_line"

  cleanup_drill
  drill=''
done

echo 'PRODUCTION_DATABASE_TOUCHED=NO'
echo 'TEMP_RESTORE_NETWORK=none'
echo 'TEMP_RESTORE_PORTS=none'
echo 'BACKUP_MOUNT=read_only'
echo 'TEMP_CONTAINERS_CLEANED=YES'
