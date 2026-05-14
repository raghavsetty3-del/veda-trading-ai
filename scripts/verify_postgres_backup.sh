#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup.sql.gz>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKUP_FILE="$1"
DB_NAME="${POSTGRES_DB:-veda}"
DB_USER="${POSTGRES_USER:-veda}"
DB_PASSWORD="${RESTORE_DRILL_PASSWORD:-restore_drill_password}"
CONTAINER="${RESTORE_DRILL_CONTAINER:-veda-restore-drill-$(date +%s)}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

cd "$PROJECT_DIR"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting restore drill container: $CONTAINER"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER" \
  -e POSTGRES_DB="$DB_NAME" \
  -e POSTGRES_USER="$DB_USER" \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" \
  postgres:16 >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec "$CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null

echo "Restoring backup into temporary database"
gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$DB_USER" "$DB_NAME" >/dev/null

echo "Verifying restored public tables"
TABLES="$(docker exec "$CONTAINER" psql -At -U "$DB_USER" "$DB_NAME" -c "select table_name from information_schema.tables where table_schema='public' order by table_name;")"
if [ -z "$TABLES" ]; then
  echo "No public tables found after restore" >&2
  exit 1
fi

printf '%s\n' "$TABLES"
echo "Restore drill complete: $BACKUP_FILE"
