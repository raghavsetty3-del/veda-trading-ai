# Operations Monitoring

The VM includes a lightweight healthwatch script and systemd timer for self-healing the Docker Compose stack.

## Healthwatch

`scripts/healthwatch.sh` checks:

- expected Compose services are present and running;
- Docker healthchecks are not `unhealthy`;
- direct API health responds at `http://localhost:8000/health`;
- the Nginx gateway returns either `200` or `401`.

When a problem is detected, it runs `docker compose up -d --remove-orphans`, waits, and restarts app-facing services if the API is still unhealthy.

Logs are written to:

```text
/home/traderadmin/veda-trading-ai/logs/healthwatch.log
```

Healthwatch also writes audit events to the API when auto-heal starts, succeeds, or leaves remaining issues.

## systemd Timer

The timer runs every 2 minutes:

```bash
sudo systemctl status veda-healthwatch.timer
sudo journalctl -u veda-healthwatch.service -n 100 --no-pager
```

Manual run:

```bash
PROJECT_DIR=/home/traderadmin/veda-trading-ai bash scripts/healthwatch.sh
```
