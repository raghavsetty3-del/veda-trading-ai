#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
cd "$PROJECT_DIR"
mkdir -p "$BACKUP_DIR"
STAMP=$(date +"%Y%m%d_%H%M%S")
FILE="$BACKUP_DIR/postgres_$STAMP.sql.gz"
echo "Creating PostgreSQL backup: $FILE"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-veda}" "${POSTGRES_DB:-veda}" | gzip > "$FILE"
echo "Backup complete: $FILE"
