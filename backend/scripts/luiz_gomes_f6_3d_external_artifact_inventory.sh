#!/usr/bin/env bash
# LUIZ-GOMES-F6.3d — inventário metadata-only de possíveis artefatos históricos
# fora da árvore canônica /root/sigesc-backups. Não abre arquivos nem acessa Mongo.
set -euo pipefail

canonical_root='/root/sigesc-backups'
roots=(/root /opt /srv /var/backups)

declare -A mtime_by_inode size_by_inode root_by_inode kind_by_inode namedate_by_inode pathfp_by_inode sha_sidecar_by_inode meta_sidecar_by_inode

root_class() {
  case "$1" in
    /root) echo 'root' ;;
    /opt) echo 'opt' ;;
    /srv) echo 'srv' ;;
    /var/backups) echo 'var_backups' ;;
    *) echo 'other' ;;
  esac
}

artifact_kind() {
  local base lower
  base="$(basename "$1")"
  lower="${base,,}"
  case "$lower" in
    *.archive.gz) echo 'mongo_archive_gzip' ;;
    *.bson.gz) echo 'bson_gzip' ;;
    *.bson) echo 'bson' ;;
    *.dump.gz) echo 'dump_gzip' ;;
    *.dump) echo 'dump' ;;
    *.tar.gz|*.tgz) echo 'named_tar_gzip' ;;
    *.zip) echo 'named_zip' ;;
    *) echo 'other_candidate' ;;
  esac
}

filename_date() {
  local base dashed compact
  base="$(basename "$1")"
  dashed="$(printf '%s' "$base" | grep -oE '20[0-9]{2}-[01][0-9]-[0-3][0-9]' | head -n1 || true)"
  if [[ -n "$dashed" ]]; then
    printf '%s\n' "$dashed"
    return
  fi
  compact="$(printf '%s' "$base" | grep -oE '20[0-9]{6}' | head -n1 || true)"
  if [[ "$compact" =~ ^20[0-9]{6}$ ]]; then
    printf '%s-%s-%s\n' "${compact:0:4}" "${compact:4:2}" "${compact:6:2}"
  else
    printf 'unknown\n'
  fi
}

existing_roots=0
for root in "${roots[@]}"; do
  if [[ ! -d "$root" ]]; then
    echo "F63D_ROOT_MISSING:$(root_class "$root")"
    continue
  fi
  existing_roots=$((existing_roots + 1))
  src="$(root_class "$root")"
  while IFS= read -r -d '' candidate; do
    inode="$(stat -Lc '%d:%i' "$candidate")"
    if [[ -z "${mtime_by_inode[$inode]:-}" ]]; then
      mtime_by_inode[$inode]="$(stat -Lc '%Y' "$candidate")"
      size_by_inode[$inode]="$(stat -Lc '%s' "$candidate")"
      root_by_inode[$inode]="$src"
      kind_by_inode[$inode]="$(artifact_kind "$candidate")"
      namedate_by_inode[$inode]="$(filename_date "$candidate")"
      pathfp_by_inode[$inode]="$(printf '%s' "$candidate" | sha256sum | awk '{print substr($1,1,16)}')"
      [[ -s "${candidate}.sha256" ]] && sha_sidecar_by_inode[$inode]='true' || sha_sidecar_by_inode[$inode]='false'
      [[ -s "${candidate}.metadata.txt" ]] && meta_sidecar_by_inode[$inode]='true' || meta_sidecar_by_inode[$inode]='false'
    else
      case "+${root_by_inode[$inode]}+" in
        *"+$src+"*) ;;
        *) root_by_inode[$inode]="${root_by_inode[$inode]}+$src" ;;
      esac
    fi
  done < <(
    find "$root" -xdev -maxdepth 8 \
      \( -path "$canonical_root" -o -path "$canonical_root/*" \) -prune -o \
      -type f \( \
        -name '*.archive.gz' -o -name '*.bson' -o -name '*.bson.gz' -o \
        -name '*.dump' -o -name '*.dump.gz' -o \
        -iname '*sigesc*.tar.gz' -o -iname '*mongo*.tar.gz' -o -iname '*backup*.tar.gz' -o \
        -iname '*sigesc*.tgz' -o -iname '*mongo*.tgz' -o -iname '*backup*.tgz' -o \
        -iname '*sigesc*.zip' -o -iname '*mongo*.zip' -o -iname '*backup*.zip' \
      \) -print0 2>/dev/null
  )
done

(( existing_roots > 0 )) || { echo 'F63D_NO_SEARCH_ROOTS_AVAILABLE'; exit 1; }
count="${#mtime_by_inode[@]}"
(( count <= 200 )) || { echo "F63D_ARTIFACT_COUNT_SAFETY_LIMIT:$count"; exit 1; }
echo "F63D_SEARCH_ROOTS_PRESENT=$existing_roots"
echo "F63D_PHYSICAL_ARTIFACT_COUNT=$count"

if (( count > 0 )); then
  mapfile -t ordered < <(
    for inode in "${!mtime_by_inode[@]}"; do
      printf '%s|%s\n' "${mtime_by_inode[$inode]}" "$inode"
    done | sort -n -t'|' -k1,1 | cut -d'|' -f2-
  )

  ordinal=0
  for inode in "${ordered[@]}"; do
    ordinal=$((ordinal + 1))
    epoch="${mtime_by_inode[$inode]}"
    mtime_date="$(date -u -d "@$epoch" '+%Y-%m-%d')"
    printf 'F63D_POINT_JSON={"ordinal":%d,"path_fingerprint":"%s","filename_date":"%s","mtime_date":"%s","size_bytes":%s,"source_root":"%s","artifact_kind":"%s","sha_sidecar":%s,"metadata_sidecar":%s}\n' \
      "$ordinal" "${pathfp_by_inode[$inode]}" "${namedate_by_inode[$inode]}" "$mtime_date" \
      "${size_by_inode[$inode]}" "${root_by_inode[$inode]}" "${kind_by_inode[$inode]}" \
      "${sha_sidecar_by_inode[$inode]}" "${meta_sidecar_by_inode[$inode]}"
  done
fi

echo 'F63D_FILESYSTEM_READ_ONLY=YES'
echo 'F63D_FILE_CONTENT_READ=NO'
echo 'F63D_MONGO_ACCESSED=NO'
echo 'F63D_RESTORE_EXECUTED=NO'
echo 'F63D_CANONICAL_BACKUP_TREE_EXCLUDED=YES'
echo 'F63D_PATHS_EMITTED=NO'
