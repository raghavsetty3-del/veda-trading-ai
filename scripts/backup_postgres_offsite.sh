#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
CONTAINER="${AZURE_BACKUP_CONTAINER:-veda-postgres-backups}"

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI is required for offsite backup upload." >&2
  exit 1
fi

if [ -z "${AZURE_STORAGE_ACCOUNT:-}" ]; then
  echo "AZURE_STORAGE_ACCOUNT is required." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP=$(date +"%Y%m%d_%H%M%S")
FILE="$BACKUP_DIR/postgres_$STAMP.sql.gz"
BLOB_NAME="postgres/$STAMP/postgres.sql.gz"

echo "Creating PostgreSQL backup: $FILE"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-veda}" "${POSTGRES_DB:-veda}" | gzip > "$FILE"

echo "Uploading backup to Azure Blob: $AZURE_STORAGE_ACCOUNT/$CONTAINER/$BLOB_NAME"
az storage blob upload \
  --account-name "$AZURE_STORAGE_ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$BLOB_NAME" \
  --file "$FILE" \
  --auth-mode login \
  --overwrite false \
  --only-show-errors

echo "Offsite backup complete: $BLOB_NAME"
