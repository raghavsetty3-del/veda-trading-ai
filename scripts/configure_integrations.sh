#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/traderadmin/veda-trading-ai}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
HEALTHWATCH_ENV_FILE="${HEALTHWATCH_ENV_FILE:-$PROJECT_DIR/.healthwatch.env}"

usage() {
  cat <<'USAGE'
Usage:
  PROJECT_DIR=/home/traderadmin/veda-trading-ai bash scripts/configure_integrations.sh

This script updates deployment-only integration settings:
  - TELEGRAM_API_ID
  - TELEGRAM_API_HASH
  - TELEGRAM_CHANNELS
  - TELEGRAM_PUBLIC_CHANNELS
  - BLOG_FEEDS
  - X_BEARER_TOKEN
  - X_USERNAMES
  - HEALTHWATCH_WEBHOOK_URL

Secrets are written only to the VM .env / .healthwatch.env files.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Project directory not found: $PROJECT_DIR" >&2
  exit 1
fi

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

prompt_value() {
  local label="$1"
  local current="${2:-}"
  local value
  if [[ -n "$current" ]]; then
    read -r -p "$label [$current] (leave blank to keep): " value
    printf '%s' "${value:-$current}"
  else
    read -r -p "$label (leave blank to skip): " value
    printf '%s' "$value"
  fi
}

current_value() {
  local key="$1"
  if [[ -f "$ENV_FILE" ]]; then
    grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"
  [[ -z "$value" ]] && return 0
  touch "$file"
  chmod 600 "$file"
  if grep -qE "^${key}=" "$file"; then
    local tmp
    tmp="$(mktemp)"
    awk -v k="$key" -v v="$value" 'BEGIN{done=0} $0 ~ "^" k "=" {$0=k "=" v; done=1} {print} END{if(!done) print k "=" v}' "$file" > "$tmp"
    cat "$tmp" > "$file"
    rm -f "$tmp"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$file"
  fi
}

echo "Veda integration setup"
echo "Project: $PROJECT_DIR"
echo

telegram_api_id="$(prompt_value "Telegram API ID" "$(current_value TELEGRAM_API_ID)")"
telegram_api_hash="$(prompt_value "Telegram API hash" "$(current_value TELEGRAM_API_HASH)")"
telegram_channels="$(prompt_value "Telegram channels, comma-separated" "$(current_value TELEGRAM_CHANNELS)")"
telegram_public_channels="$(prompt_value "Public Telegram channels, comma-separated" "$(current_value TELEGRAM_PUBLIC_CHANNELS)")"
blog_feeds="$(prompt_value "Blog/RSS feeds, comma-separated" "$(current_value BLOG_FEEDS)")"
x_bearer_token="$(prompt_value "X API bearer token" "$(current_value X_BEARER_TOKEN)")"
x_usernames="$(prompt_value "X usernames, comma-separated" "$(current_value X_USERNAMES)")"
healthwatch_webhook="$(prompt_value "Healthwatch webhook URL" "")"

set_env_value TELEGRAM_API_ID "$telegram_api_id" "$ENV_FILE"
set_env_value TELEGRAM_API_HASH "$telegram_api_hash" "$ENV_FILE"
set_env_value TELEGRAM_CHANNELS "$telegram_channels" "$ENV_FILE"
set_env_value TELEGRAM_PUBLIC_CHANNELS "$telegram_public_channels" "$ENV_FILE"
set_env_value TELEGRAM_PUBLIC_INGEST_ON_START "true" "$ENV_FILE"
set_env_value BLOG_FEEDS "$blog_feeds" "$ENV_FILE"
set_env_value BLOG_INGEST_ON_START "true" "$ENV_FILE"
set_env_value X_BEARER_TOKEN "$x_bearer_token" "$ENV_FILE"
set_env_value X_USERNAMES "$x_usernames" "$ENV_FILE"
set_env_value X_INGEST_ON_START "true" "$ENV_FILE"

if [[ -n "$healthwatch_webhook" ]]; then
  set_env_value HEALTHWATCH_WEBHOOK_URL "$healthwatch_webhook" "$HEALTHWATCH_ENV_FILE"
  set_env_value HEALTHWATCH_WEBHOOK_NAME "veda-healthwatch" "$HEALTHWATCH_ENV_FILE"
fi

echo
echo "Restarting Veda services with updated integration settings..."
cd "$PROJECT_DIR"
docker compose up -d api scheduler dashboard

if [[ -n "$healthwatch_webhook" ]] && command -v systemctl >/dev/null 2>&1; then
  sudo systemctl daemon-reload || true
  sudo systemctl restart veda-healthwatch.timer || true
fi

echo
echo "Integration status:"
curl -fsS http://localhost:8000/readiness || true
echo
