#!/usr/bin/env bash
# LUIZ-GOMES-F6.3c.2 — inventário estritamente read-only dos archives Mongo.
# Não restaura, não abre documentos e não emite caminhos/nomes de arquivos.
set -euo pipefail

backup_root='/root/sigesc-backups'
test -d "$backup_root" || { echo 'F63C2_BACKUP_ROOT_MISSING'; exit 1; }

declare -A mtime_by_inode size_by_inode source_by_inode namedate_by_inode sha_sidecar_by_inode meta_sidecar_by_inode

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

filename_date() {
  local base="$1" token digits
  token="$(printf '%s' "$base" | grep -oE '20[0-9]{6}(T[0-9]{6}Z)?' | head -n1 || true)"
  digits="${token:0:8}"
  if [[ "$digits" =~ ^20[0-9]{6}$ ]]; then
    printf '%s-%s-%s\n' "${digits:0:4}" "${digits:4:2}" "${digits:6:2}"
  else
    printf 'unknown\n'
  fi
}

while IFS= read -r -d '' archive; do
  inode="$(stat -Lc '%d:%i' "$archive")"
  rel="${archive#${backup_root}/}"
  src="$(source_class "$rel")"
  if [[ -z "${mtime_by_inode[$inode]:-}" ]]; then
    mtime_by_inode[$inode]="$(stat -Lc '%Y' "$archive")"
    size_by_inode[$inode]="$(stat -Lc '%s' "$archive")"
    source_by_inode[$inode]="$src"
    namedate_by_inode[$inode]="$(filename_date "$(basename "$archive")")"
    [[ -s "${archive}.sha256" ]] && sha_sidecar_by_inode[$inode]='true' || sha_sidecar_by_inode[$inode]='false'
    [[ -s "${archive}.metadata.txt" ]] && meta_sidecar_by_inode[$inode]='true' || meta_sidecar_by_inode[$inode]='false'
  else
    case "+${source_by_inode[$inode]}+" in
      *"+$src+"*) ;;
      *) source_by_inode[$inode]="${source_by_inode[$inode]}+$src" ;;
    esac
  fi
done < <(find "$backup_root" -xdev -maxdepth 6 -type f -name '*.archive.gz' -print0)

count="${#mtime_by_inode[@]}"
(( count > 0 )) || { echo 'F63C2_NO_ARCHIVES_FOUND'; exit 1; }
(( count <= 100 )) || { echo "F63C2_ARCHIVE_COUNT_SAFETY_LIMIT:$count"; exit 1; }
echo "F63C2_PHYSICAL_ARCHIVE_COUNT=$count"

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
  printf 'F63C2_POINT_JSON={"ordinal":%d,"filename_date":"%s","mtime_date":"%s","size_bytes":%s,"source_class":"%s","sha_sidecar":%s,"metadata_sidecar":%s}\n' \
    "$ordinal" "${namedate_by_inode[$inode]}" "$mtime_date" "${size_by_inode[$inode]}" "${source_by_inode[$inode]}" \
    "${sha_sidecar_by_inode[$inode]}" "${meta_sidecar_by_inode[$inode]}"
done

echo 'F63C2_FILESYSTEM_READ_ONLY=YES'
echo 'F63C2_MONGO_ACCESSED=NO'
echo 'F63C2_RESTORE_EXECUTED=NO'
echo 'F63C2_PATHS_EMITTED=NO'
