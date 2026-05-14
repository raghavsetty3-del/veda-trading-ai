#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
STAMP=$(date +"%Y%m%d_%H%M%S")
FILE="$BACKUP_DIR/postgres_$STAMP.sql.gz"
echo "Creating PostgreSQL backup: $FILE"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-veda}" "${POSTGRES_DB:-veda}" | gzip > "$FILE"
echo "Backup complete: $FILE"
