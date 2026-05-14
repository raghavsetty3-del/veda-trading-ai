from app.config import settings
from app.ingestion.blog import fetch_rss_entries
from app.models import FailedJob
from app.services.audit import audit
from app.services.source_archive import archive_source_document


def configured_blog_feeds() -> list[str]:
    raw = settings.blog_feeds or ""
    parts = raw.replace("\n", ",").split(",")
    return [item.strip() for item in parts if item.strip()]


def ingest_blog_feed(db, feed_url: str, limit: int | None = None) -> dict:
    max_items = limit or settings.blog_ingest_limit
    created = 0
    existing = 0
    entries = fetch_rss_entries(feed_url)[:max_items]
    for item in entries:
        row, was_created, psychology = archive_source_document(db, item)
        if was_created:
            created += 1
            audit(
                db,
                "source.ingested",
                f"Ingested source {row.source_type}: {row.title}",
                entity_type="source_document",
                entity_id=str(row.id),
                payload={"psychology_preview": psychology, "feed_url": feed_url},
            )
        else:
            existing += 1
    return {"feed_url": feed_url, "seen": len(entries), "created": created, "existing": existing}


def ingest_configured_blog_feeds(db) -> dict:
    feeds = configured_blog_feeds()
    results = []
    errors = []
    for feed_url in feeds:
        try:
            results.append(ingest_blog_feed(db, feed_url, settings.blog_ingest_limit))
        except Exception as exc:
            errors.append({"feed_url": feed_url, "error": str(exc)})
            db.add(FailedJob(job_type="blog.rss_ingest", payload={"feed_url": feed_url}, error=str(exc)))
            db.commit()

    summary = {
        "feeds": len(feeds),
        "created": sum(item["created"] for item in results),
        "existing": sum(item["existing"] for item in results),
        "seen": sum(item["seen"] for item in results),
        "results": results,
        "errors": errors,
    }
    audit(db, "blog.configured_ingest", "Ran configured blog feed ingestion", payload=summary)
    return summary
