#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/traderadmin/veda-trading-ai}"
COMPOSE="${COMPOSE:-docker compose}"
LOG_FILE="${LOG_FILE:-$PROJECT_DIR/logs/healthwatch.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/veda-healthwatch.lock}"
API_HEALTH_URL="${API_HEALTH_URL:-http://localhost:8000/health}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost/}"
CRYPTO_PROJECT_DIR="${CRYPTO_PROJECT_DIR:-/home/traderadmin/ai-trading-system}"
CRYPTO_HEALTH_URL="${CRYPTO_HEALTH_URL:-http://localhost:8101/api/status}"
HEAL_WAIT_SECONDS="${HEAL_WAIT_SECONDS:-20}"
HEALTHWATCH_WEBHOOK_URL="${HEALTHWATCH_WEBHOOK_URL:-}"
HEALTHWATCH_WEBHOOK_NAME="${HEALTHWATCH_WEBHOOK_NAME:-veda-healthwatch}"

services=(postgres redis chroma api worker scheduler dashboard nginx)

mkdir -p "$(dirname "$LOG_FILE")"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

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
  curl -fsS -X POST "http://localhost:8000/audit" \
    -H "Content-Type: application/json" \
    -d "{\"event_type\":\"ops.healthwatch\",\"severity\":\"$severity\",\"message\":\"$message\",\"payload\":{\"host\":\"$(hostname)\",\"project_dir\":\"$PROJECT_DIR\",\"time\":\"$(date -Is)\"}}" \
    >/dev/null 2>&1 || true
}

post_external_alert() {
  local severity="$1"
  local message="$2"

  if [[ -z "$HEALTHWATCH_WEBHOOK_URL" ]]; then
    return 0
  fi

  local escaped_name escaped_message escaped_host escaped_project
  escaped_name="$(json_escape "$HEALTHWATCH_WEBHOOK_NAME")"
  escaped_message="$(json_escape "$message")"
  escaped_host="$(json_escape "$(hostname)")"
  escaped_project="$(json_escape "$PROJECT_DIR")"

  if ! curl -fsS -X POST "$HEALTHWATCH_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"source\":\"$escaped_name\",\"severity\":\"$severity\",\"message\":\"$escaped_message\",\"host\":\"$escaped_host\",\"project_dir\":\"$escaped_project\",\"time\":\"$(date -Is)\"}" \
    >/dev/null 2>&1; then
    log "external_alert_failed severity=$severity"
  fi
}

notify() {
  local severity="$1"
  local message="$2"
  post_audit "$severity" "$message"
  post_external_alert "$severity" "$message"
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

  if [[ -d "$CRYPTO_PROJECT_DIR" ]]; then
    if ! docker ps --format '{{.Names}}' | grep -qx 'ai-trading-bot'; then
      issues+=("crypto_bot_missing")
    elif ! curl -fsS --max-time 5 "$CRYPTO_HEALTH_URL" >/dev/null; then
      issues+=("crypto_bot_health_failed")
    fi
  fi
}

heal_stack() {
  local reason="$1"

  log "healing_started reason=$reason"
  notify "WARNING" "Healthwatch detected an unhealthy stack and started auto-heal: $reason"

  if docker ps --format '{{.Names}}' | grep -qx 'ai-trading-bot'; then
    legacy_ports="$(docker port ai-trading-bot 8000/tcp 2>/dev/null || true)"
    if printf '%s\n' "$legacy_ports" | grep -Eq '(^|:)8000$'; then
      log "stopping_legacy_port_conflict container=ai-trading-bot ports=$legacy_ports"
      docker stop ai-trading-bot >>"$LOG_FILE" 2>&1 || true
    fi
  fi

  if [[ -d "$CRYPTO_PROJECT_DIR" ]]; then
    log "ensuring_crypto_bot project_dir=$CRYPTO_PROJECT_DIR"
    (cd "$CRYPTO_PROJECT_DIR" && docker compose up -d --remove-orphans) >>"$LOG_FILE" 2>&1 || true
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
    notify "INFO" "Healthwatch auto-heal completed and stack is healthy."
  else
    log "healing_incomplete remaining=${issues[*]}"
    notify "ERROR" "Healthwatch auto-heal completed with remaining issues: ${issues[*]}"
    return 1
  fi
}

main() {
  if [[ ! -d "$PROJECT_DIR" ]]; then
    log "project_dir_missing path=$PROJECT_DIR"
    post_external_alert "ERROR" "Healthwatch project directory is missing: $PROJECT_DIR"
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
