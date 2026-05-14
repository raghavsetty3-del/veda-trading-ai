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

If `/home/traderadmin/ai-trading-system` exists, healthwatch also verifies the crypto bot container and its local status endpoint:

```text
http://localhost:8001/api/status
```

During healing, it restarts that project with `docker compose up -d --remove-orphans`. It only stops the legacy `ai-trading-bot` container when it is occupying host port `8000`, so the current bot can keep running on port `8001`.

## Crypto Proxy

Nginx exposes the crypto bot behind the existing Basic Auth boundary:

```text
http://20.235.64.162/crypto/
http://20.235.64.162/crypto/api/status
```

The proxy uses Docker `host-gateway` through `host.docker.internal` to reach the bot on host port `8001`.

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
