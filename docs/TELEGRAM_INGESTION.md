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

## Live Listener

Live Telegram ingestion is implemented and remains inactive until credentials are configured. It requires:

- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_CHANNELS`

Optional:

- `TELEGRAM_BOT_TOKEN`

Without a bot token, the VM must already have an authorized Telethon user session file under `TELEGRAM_SESSION_DIR`.

## Public Channel Web Ingestion

If `my.telegram.org` is rate-limited or failing, public Telegram channels can be ingested without API credentials through Telegram's public web view.

Configure:

- `TELEGRAM_PUBLIC_CHANNELS`
- `TELEGRAM_PUBLIC_INGEST_INTERVAL_SECONDS`
- `TELEGRAM_PUBLIC_INGEST_LIMIT`
- `TELEGRAM_PUBLIC_INGEST_ON_START`

Accepted channel formats:

```text
@channelname
https://t.me/channelname
https://t.me/s/channelname
```

Run once:

```bash
curl -X POST http://localhost:8000/ingest/telegram/public \
  -H "Content-Type: application/json" \
  -d '{"channels": ["https://t.me/s/channelname"], "limit": 50}'
```

Run configured channels:

```bash
curl -X POST http://localhost:8000/ingest/telegram/public-configured
```

This path only works for public channels whose posts are visible at `https://t.me/s/<channel>`. Private groups or channels still need the API/session path or a manual export.

From the laptop, use the integration helper after the Telegram rate limit clears:

```powershell
Set-Location C:\Users\LENOVO\Downloads\veda-trading-ai-v0.2
powershell -ExecutionPolicy Bypass -File scripts\configure_integrations.ps1
```

It writes Telegram values to the VM `.env` file only; it does not commit secrets.

Check readiness:

```bash
curl http://localhost:8000/ingest/telegram/status
```

Ingest the latest configured messages:

```bash
curl -X POST http://localhost:8000/ingest/telegram/live \
  -H "Content-Type: application/json" \
  -d '{"limit": 50}'
```

Override channels for one run:

```bash
curl -X POST http://localhost:8000/ingest/telegram/live \
  -H "Content-Type: application/json" \
  -d '{"channels": ["channel_a", "channel_b"], "limit": 20}'
```

Each live message is archived through the same `SourceDocument` path as export ingestion.
