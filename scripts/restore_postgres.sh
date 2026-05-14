#!/usr/bin/env bash
set -euo pipefail
if [ $# -lt 1 ]; then echo "Usage: $0 <backup.sql.gz>"; exit 1; fi
BACKUP_FILE="$1"
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "${POSTGRES_USER:-veda}" "${POSTGRES_DB:-veda}"
echo "Restore complete"
