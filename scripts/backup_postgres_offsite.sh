#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
CONTAINER="${AZURE_BACKUP_CONTAINER:-veda-postgres-backups}"
cd "$PROJECT_DIR"

if [ -n "${OFFSITE_BACKUP_ENV_FILE:-}" ] && [ -f "$OFFSITE_BACKUP_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$OFFSITE_BACKUP_ENV_FILE"
  set +a
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
if [ -n "${AZURE_STORAGE_SAS_TOKEN:-}" ]; then
  SAS_TOKEN="${AZURE_STORAGE_SAS_TOKEN#\?}"
  curl -fsS \
    -X PUT \
    -H "x-ms-blob-type: BlockBlob" \
    -H "Content-Type: application/gzip" \
    --data-binary "@$FILE" \
    "https://${AZURE_STORAGE_ACCOUNT}.blob.core.windows.net/${CONTAINER}/${BLOB_NAME}?${SAS_TOKEN}" \
    >/dev/null
elif command -v az >/dev/null 2>&1; then
  az storage blob upload \
    --account-name "$AZURE_STORAGE_ACCOUNT" \
    --container-name "$CONTAINER" \
    --name "$BLOB_NAME" \
    --file "$FILE" \
    --auth-mode login \
    --overwrite false \
    --only-show-errors
else
  echo "Azure CLI or AZURE_STORAGE_SAS_TOKEN is required for offsite backup upload." >&2
  exit 1
fi

echo "Offsite backup complete: $BLOB_NAME"
