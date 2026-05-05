#!/usr/bin/env bash
# ============================================================
# SIGESC — Runner de Migração de Nomes (CAPS → Title Case)
# ------------------------------------------------------------
# Executa o script normalize_names_back.py em 3 fases
# supervisionadas, com logging, healthcheck e dual-gate
# (dry-run obrigatório antes de qualquer --apply).
#
# Uso:
#   ./run_migration.sh dry-run         # apenas inspeção
#   ./run_migration.sh apply           # 3 fases com prompts Y/n
#   ./run_migration.sh apply --yes     # 3 fases sem prompts (CI/cron)
#   ./run_migration.sh status          # mostra backups existentes
#   ./run_migration.sh rollback TS     # reverte TUDO usando timestamp
#
# Variáveis de ambiente opcionais:
#   LOG_DIR    diretório de log (default: /var/log/sigesc)
#   BATCH      tamanho de batch do bulkWrite (default: 1000)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY_SCRIPT="$SCRIPT_DIR/normalize_names_back.py"

LOG_DIR="${LOG_DIR:-/var/log/sigesc}"
BATCH="${BATCH:-1000}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/migracao_nomes_$TIMESTAMP.log"

PHASE_1="courses,users"
PHASE_2="students,staff"
PHASE_3="schools,classes,mantenedoras"

# --- cores (desativa se TTY não disponível) -----------------
if [[ -t 1 ]]; then
  C_RESET="$(printf '\033[0m')"
  C_BOLD="$(printf '\033[1m')"
  C_BLUE="$(printf '\033[34m')"
  C_GREEN="$(printf '\033[32m')"
  C_YELLOW="$(printf '\033[33m')"
  C_RED="$(printf '\033[31m')"
else
  C_RESET="" C_BOLD="" C_BLUE="" C_GREEN="" C_YELLOW="" C_RED=""
fi

log_info()  { printf '%s[INFO]%s  %s\n' "$C_BLUE" "$C_RESET" "$*"; }
log_ok()    { printf '%s[ OK ]%s  %s\n' "$C_GREEN" "$C_RESET" "$*"; }
log_warn()  { printf '%s[WARN]%s  %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
log_err()   { printf '%s[ERR ]%s  %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
section()   { printf '\n%s%s==> %s%s\n' "$C_BOLD" "$C_BLUE" "$*" "$C_RESET"; }

ensure_env() {
  if [[ ! -f "$PY_SCRIPT" ]]; then
    log_err "Script não encontrado: $PY_SCRIPT"
    exit 2
  fi
  if ! command -v python >/dev/null 2>&1; then
    log_err "python não encontrado no PATH."
    exit 2
  fi
  mkdir -p "$LOG_DIR" 2>/dev/null || {
    log_warn "Sem permissão para criar $LOG_DIR — logando apenas no stdout."
    LOG_FILE=""
  }
}

run_py() {
  local args=("$@")
  if [[ -n "$LOG_FILE" ]]; then
    args+=("--log-file" "$LOG_FILE")
  fi
  (cd "$BACKEND_DIR" && python "$PY_SCRIPT" "${args[@]}")
}

confirm() {
  local prompt="$1"
  if [[ "${AUTO_YES:-0}" == "1" ]]; then
    log_info "$prompt [auto-yes]"
    return 0
  fi
  read -r -p "$(printf '%s%s%s [y/N] ' "$C_BOLD" "$prompt" "$C_RESET")" ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

cmd_dry_run() {
  section "DRY-RUN (nenhum dado será alterado)"
  run_py --dry-run --batch-size "$BATCH"
}

cmd_apply_phase() {
  local phase_num="$1" cols="$2"
  section "FASE $phase_num — coleções: $cols"
  if ! confirm "Aplicar Fase $phase_num ($cols)?"; then
    log_warn "Fase $phase_num pulada pelo usuário."
    return 1
  fi
  run_py --apply --confirm --collections "$cols" --batch-size "$BATCH" --no-progress
  log_ok "Fase $phase_num concluída."
}

cmd_apply_all() {
  section "PRÉ-CHECK (dry-run obrigatório)"
  run_py --dry-run --batch-size "$BATCH"

  printf '\n'
  if ! confirm "Prosseguir para APPLY em 3 fases?"; then
    log_warn "Cancelado pelo usuário. Nenhum dado foi alterado."
    exit 0
  fi

  local total_ok=0
  cmd_apply_phase 1 "$PHASE_1" && ((total_ok++)) || true
  cmd_apply_phase 2 "$PHASE_2" && ((total_ok++)) || true
  cmd_apply_phase 3 "$PHASE_3" && ((total_ok++)) || true

  section "HEALTHCHECK PÓS-MIGRAÇÃO"
  run_py --dry-run --batch-size "$BATCH"

  section "RESUMO"
  log_ok "Fases aplicadas: $total_ok / 3"
  if [[ -n "$LOG_FILE" ]]; then
    log_info "Log completo: $LOG_FILE"
  fi
}

cmd_status() {
  section "Backups e contagens no banco"
  (cd "$BACKEND_DIR" && python - <<'PY'
import asyncio, os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path.cwd() / ".env")

async def main():
    url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not url or not db_name:
        print("ERRO: MONGO_URL/DB_NAME ausentes."); return
    c = AsyncIOMotorClient(url); db = c[db_name]
    names = sorted(await db.list_collection_names())
    print(f"DB: {db_name}\n")
    print(f"{'Coleção':<42} {'Docs':>8}")
    print("-" * 52)
    for n in names:
        if n.startswith("backup_") or n in {
            "students","staff","schools","classes","courses","users","mantenedoras"
        }:
            cnt = await db[n].count_documents({})
            marker = "  (backup)" if n.startswith("backup_") else ""
            print(f"{n:<42} {cnt:>8}{marker}")
    c.close()
asyncio.run(main())
PY
  )
}

cmd_rollback() {
  local ts="${1:-}"
  if [[ -z "$ts" ]]; then
    log_err "Uso: $0 rollback <timestamp>  (ex: 20260505T105357Z)"
    exit 2
  fi
  section "ROLLBACK GLOBAL — timestamp $ts"
  log_warn "Isso vai SOBRESCREVER todas as coleções com o conteúdo dos backups."
  if ! confirm "Confirmar rollback de TODAS as 7 coleções?"; then
    log_warn "Cancelado."; exit 0
  fi
  run_py --rollback "$ts" --confirm --collections "$PHASE_1,$PHASE_2,$PHASE_3"
  log_ok "Rollback concluído."
}

main() {
  ensure_env
  local action="${1:-dry-run}"
  shift || true

  # flag opcional --yes (em qualquer posição dos extras)
  for arg in "$@"; do
    [[ "$arg" == "--yes" || "$arg" == "-y" ]] && export AUTO_YES=1
  done

  case "$action" in
    dry-run|dry)    cmd_dry_run ;;
    apply|migrate)  cmd_apply_all ;;
    status)         cmd_status ;;
    rollback)       cmd_rollback "${1:-}" ;;
    -h|--help|help)
      sed -n '1,30p' "$0"
      ;;
    *)
      log_err "Ação desconhecida: $action"
      sed -n '1,30p' "$0"
      exit 2
      ;;
  esac
}

main "$@"
