#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/traderadmin/veda-trading-ai}"
COMPOSE="${COMPOSE:-docker compose}"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/healthwatch.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/veda-healthwatch.lock}"
API_HEALTH_URL="${API_HEALTH_URL:-http://localhost:8000/health}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost/}"
HEAL_WAIT_SECONDS="${HEAL_WAIT_SECONDS:-20}"

services=(postgres redis chroma api worker scheduler dashboard nginx)

mkdir -p "$(dirname "$LOG_FILE")"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG_FILE" >/dev/null
}

post_audit() {
  local severity="$1"
  local message="$2"
  curl -fsS -X POST "http://localhost:8000/audit" \
    -H "Content-Type: application/json" \
    -d "{\"event_type\":\"ops.healthwatch\",\"severity\":\"$severity\",\"message\":\"$message\",\"payload\":{\"host\":\"$(hostname)\",\"project_dir\":\"$PROJECT_DIR\",\"time\":\"$(date -Is)\"}}" \
    >/dev/null 2>&1 || true
}

container_issue() {
  local service="$1"
  local cid state running health

  cid="$($COMPOSE ps -q "$service" 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    printf '%s missing' "$service"
    return 0
  fi

  state="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null || true)"
  running="${state%% *}"
  health="${state#* }"

  if [[ "$running" != "running" ]]; then
    printf '%s not_running:%s' "$service" "$running"
    return 0
  fi

  if [[ "$health" == "unhealthy" ]]; then
    printf '%s unhealthy' "$service"
    return 0
  fi

  return 1
}

collect_issues() {
  local issue
  issues=()

  for service in "${services[@]}"; do
    if issue="$(container_issue "$service")"; then
      issues+=("$issue")
    fi
  done

  if ! curl -fsS --max-time 5 "$API_HEALTH_URL" >/dev/null; then
    issues+=("api_health_failed")
  fi

  local gateway_code
  gateway_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$GATEWAY_URL" || true)"
  if [[ "$gateway_code" != "200" && "$gateway_code" != "401" ]]; then
    issues+=("gateway_unexpected_status:$gateway_code")
  fi
}

heal_stack() {
  local reason="$1"

  log "healing_started reason=$reason"
  post_audit "WARNING" "Healthwatch detected an unhealthy stack and started auto-heal."

  if docker ps --format '{{.Names}}' | grep -qx 'ai-trading-bot'; then
    log "stopping_legacy_port_conflict container=ai-trading-bot"
    docker stop ai-trading-bot >>"$LOG_FILE" 2>&1 || true
  fi

  $COMPOSE up -d --remove-orphans >>"$LOG_FILE" 2>&1 || true
  sleep "$HEAL_WAIT_SECONDS"

  if ! curl -fsS --max-time 5 "$API_HEALTH_URL" >/dev/null; then
    log "api_still_unhealthy restarting app services"
    $COMPOSE restart api worker scheduler dashboard nginx >>"$LOG_FILE" 2>&1 || true
    sleep 10
  fi

  collect_issues
  if ((${#issues[@]} == 0)); then
    log "healing_completed status=healthy"
    post_audit "INFO" "Healthwatch auto-heal completed and stack is healthy."
  else
    log "healing_incomplete remaining=${issues[*]}"
    post_audit "ERROR" "Healthwatch auto-heal completed with remaining issues."
    return 1
  fi
}

main() {
  if [[ ! -d "$PROJECT_DIR" ]]; then
    log "project_dir_missing path=$PROJECT_DIR"
    return 1
  fi

  cd "$PROJECT_DIR"

  collect_issues
  if ((${#issues[@]} == 0)); then
    log "status=healthy"
    return 0
  fi

  heal_stack "${issues[*]}"
}

main "$@"
