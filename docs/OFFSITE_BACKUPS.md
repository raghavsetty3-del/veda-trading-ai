# Offsite Backups

PostgreSQL backups should be copied away from the VM after creation. The local VM backup protects against application mistakes; an offsite copy protects against VM or disk loss.

## Script

Use either Azure CLI login or a SAS-token env file:

```bash
AZURE_STORAGE_ACCOUNT=<dedicated-storage-account> \
AZURE_BACKUP_CONTAINER=veda-postgres-backups \
BACKUP_DIR=/home/traderadmin/veda-backups \
bash scripts/backup_postgres_offsite.sh
```

```bash
OFFSITE_BACKUP_ENV_FILE=/home/traderadmin/veda-trading-ai/.offsite-backup.env \
bash scripts/backup_postgres_offsite.sh
```

The script:

- Creates a compressed PostgreSQL dump.
- Stores the local copy under `BACKUP_DIR`.
- Uploads the dump to Azure Blob Storage under `postgres/<timestamp>/postgres.sql.gz`.
- Uses `AZURE_STORAGE_SAS_TOKEN` with `curl` when available.
- Falls back to `az storage blob upload --auth-mode login`, so the shell can also use Azure CLI authentication.

Example private env file, not committed to Git:

```bash
AZURE_STORAGE_ACCOUNT=<dedicated-storage-account>
AZURE_BACKUP_CONTAINER=veda-postgres-backups
AZURE_STORAGE_SAS_TOKEN='<sas-token>'
BACKUP_DIR=/home/traderadmin/veda-backups
```

## Azure Setup

Create a dedicated storage account and container instead of using unrelated infrastructure state storage:

```bash
az storage account create \
  --name <dedicated-storage-account> \
  --resource-group rg-ai-trading-india \
  --location centralindia \
  --sku Standard_LRS \
  --kind StorageV2

az storage container create \
  --account-name <dedicated-storage-account> \
  --name veda-postgres-backups \
  --auth-mode login
```

## Schedule

After the storage account and private env file are ready, schedule a daily run from `/home/traderadmin/veda-trading-ai`. The VM uses UTC, so `18:45 UTC` runs at `00:15 IST`:

```cron
45 18 * * * OFFSITE_BACKUP_ENV_FILE=/home/traderadmin/veda-trading-ai/.offsite-backup.env bash /home/traderadmin/veda-trading-ai/scripts/backup_postgres_offsite.sh >> /home/traderadmin/veda-backups/offsite.log 2>&1
```

The script resolves the project directory from its own path, so cron does not need to `cd` before invoking it.

## Retention

The Azure lifecycle policy in `infra/azure/backup-lifecycle-policy.json` deletes PostgreSQL backup blobs after 90 days:

```bash
az storage account management-policy create \
  --resource-group rg-ai-trading-india \
  --account-name vedabkp260514rs \
  --policy @infra/azure/backup-lifecycle-policy.json
```

## Restore

Download the selected blob, then restore with:

```bash
bash scripts/restore_postgres.sh /path/to/postgres.sql.gz
```

For a non-destructive restore drill, restore into a temporary PostgreSQL container instead:

```bash
bash scripts/verify_postgres_backup.sh /path/to/postgres.sql.gz
```

The drill removes the temporary container after verification.

The VM also includes a scheduled wrapper that selects the newest local PostgreSQL backup and runs the same non-destructive drill weekly:

```bash
sudo systemctl status veda-restore-drill.timer
sudo journalctl -u veda-restore-drill.service -n 100 --no-pager
```

Manual run:

```bash
PROJECT_DIR=/home/traderadmin/veda-trading-ai BACKUP_DIR=/home/traderadmin/veda-backups bash scripts/run_restore_drill.sh
```
