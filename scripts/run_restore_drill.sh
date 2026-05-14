#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-/home/traderadmin/veda-backups}"
LOG_FILE="${RESTORE_DRILL_LOG_FILE:-$BACKUP_DIR/restore-drill.log}"
API_AUDIT_URL="${API_AUDIT_URL:-http://localhost:8000/audit}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE" >/dev/null
}

json_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  printf '%s' "$value"
}

post_audit() {
  local severity="$1"
  local message="$2"
  local backup_file="${3:-}"
  local escaped_message escaped_backup

  escaped_message="$(json_escape "$message")"
  escaped_backup="$(json_escape "$backup_file")"
  curl -fsS -X POST "$API_AUDIT_URL" \
    -H "Content-Type: application/json" \
    -d "{\"event_type\":\"ops.restore_drill\",\"severity\":\"$severity\",\"message\":\"$escaped_message\",\"payload\":{\"backup_file\":\"$escaped_backup\",\"time\":\"$(date -Is)\"}}" \
    >/dev/null 2>&1 || true
}

latest_backup() {
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'postgres_*.sql.gz' -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr \
    | awk 'NR == 1 {sub(/^[^ ]+ /, ""); print}'
}

main() {
  cd "$PROJECT_DIR"

  local backup_file
  backup_file="$(latest_backup)"
  if [[ -z "$backup_file" ]]; then
    log "restore_drill_failed reason=no_backup backup_dir=$BACKUP_DIR"
    post_audit "ERROR" "Restore drill could not find a local PostgreSQL backup." ""
    return 1
  fi

  log "restore_drill_started backup_file=$backup_file"
  if bash "$PROJECT_DIR/scripts/verify_postgres_backup.sh" "$backup_file" >>"$LOG_FILE" 2>&1; then
    log "restore_drill_completed backup_file=$backup_file"
    post_audit "INFO" "Restore drill completed successfully." "$backup_file"
  else
    log "restore_drill_failed backup_file=$backup_file"
    post_audit "ERROR" "Restore drill failed." "$backup_file"
    return 1
  fi
}

main "$@"
