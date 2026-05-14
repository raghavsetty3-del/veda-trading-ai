# Telegram Ingestion

Telegram ingestion has two stages.

## Current Stage: Export Ingestion

The safe path is available now: paste/export message JSON and archive it as source documents.

API:

```bash
curl -X POST http://localhost:8000/ingest/telegram/export \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "manual-export",
    "messages": [
      {
        "message_id": "1",
        "text": "Message text",
        "date": "2026-05-14T09:15:00",
        "author": "manual"
      }
    ]
  }'
```

Each message becomes a `SourceDocument` with a stable URL:

```text
telegram://<channel>/<message_id>
```

Duplicate message IDs for the same channel are skipped.

## Future Stage: Live Listener

Live Telegram listening still requires:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_CHANNELS`

Check readiness:

```bash
curl http://localhost:8000/ingest/telegram/status
```

Live listening remains disabled until credentials are configured and the listener is explicitly enabled.
