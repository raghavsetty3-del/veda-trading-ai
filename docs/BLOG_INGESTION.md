# Blog Ingestion

Veda supports manual blog page ingestion, manual RSS ingestion, and scheduled RSS ingestion.

## Manual

Use the dashboard Ingestion page or the API:

```bash
curl -X POST "http://localhost:8000/ingest/blog/rss?feed_url=<rss-url>&limit=20"
```

## Scheduled

Set comma-separated RSS feed URLs:

```text
BLOG_FEEDS=https://example.com/feed,https://example.com/rss
BLOG_INGEST_INTERVAL_SECONDS=3600
BLOG_INGEST_LIMIT=20
BLOG_INGEST_ON_START=false
```

The scheduler checks configured feeds every `BLOG_INGEST_INTERVAL_SECONDS`.

Each ingested item is archived as a `SourceDocument`, receives a lightweight psychology extraction, and is logged in the audit trail. Duplicate source URLs are skipped.

## Current Guardrails

- Raw source text and HTML are preserved.
- Duplicate source URLs are not re-created.
- Feed failures are recorded in `failed_jobs`.
- No trading action is triggered by ingestion.
