# Offsite Backups

PostgreSQL backups should be copied away from the VM after creation. The local VM backup protects against application mistakes; an offsite copy protects against VM or disk loss.

## Script

Use:

```bash
AZURE_STORAGE_ACCOUNT=<dedicated-storage-account> \
AZURE_BACKUP_CONTAINER=veda-postgres-backups \
BACKUP_DIR=/home/traderadmin/veda-backups \
bash scripts/backup_postgres_offsite.sh
```

The script:

- Creates a compressed PostgreSQL dump.
- Stores the local copy under `BACKUP_DIR`.
- Uploads the dump to Azure Blob Storage under `postgres/<timestamp>/postgres.sql.gz`.
- Uses `az storage blob upload --auth-mode login`, so the VM or shell must already be authenticated.

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

After the storage account is created and the VM is authenticated, schedule a daily run from `/home/traderadmin/veda-trading-ai`:

```cron
15 0 * * * AZURE_STORAGE_ACCOUNT=<dedicated-storage-account> AZURE_BACKUP_CONTAINER=veda-postgres-backups BACKUP_DIR=/home/traderadmin/veda-backups bash /home/traderadmin/veda-trading-ai/scripts/backup_postgres_offsite.sh >> /home/traderadmin/veda-backups/offsite.log 2>&1
```

## Restore

Download the selected blob, then restore with:

```bash
bash scripts/restore_postgres.sh /path/to/postgres.sql.gz
```
