# X Ingestion

Date: 2026-05-16

X/Twitter ingestion is optional. Veda uses the official X API v2 read endpoints when `X_BEARER_TOKEN` and `X_USERNAMES` are configured.

## Configuration

```text
X_BEARER_TOKEN=
X_USERNAMES=JustNifty,example_user
X_INGEST_INTERVAL_SECONDS=3600
X_INGEST_LIMIT=20
X_INGEST_ON_START=false
```

Do not commit the bearer token. Store it only in the deployment `.env` file.

## Manual Run

Use the dashboard Ingestion page or the API:

```bash
curl -X POST "http://localhost:8000/ingest/x/configured" \
  -H "Content-Type: application/json" \
  -d '{"usernames":["JustNifty"],"limit":20}'
```

Each post is archived as a `SourceDocument` with `source_type=x`, then scheduled source extraction can convert it into structured insights.

## Guardrails

- X ingestion is read-only.
- No trading action is triggered by ingestion.
- Failed X API calls are recorded in `failed_jobs`.
- Use only accounts explicitly selected by the user.
