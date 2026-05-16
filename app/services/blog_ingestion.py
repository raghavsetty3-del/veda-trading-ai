from app.config import settings
from app.ingestion.blog import fetch_rss_entries, fetch_wordpress_posts
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


def _archive_blog_items(db, entries: list[dict], source_label: str) -> dict:
    created = 0
    existing = 0
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
                payload={"psychology_preview": psychology, "source": source_label},
            )
        else:
            existing += 1
    return {"seen": len(entries), "created": created, "existing": existing}


def backfill_wordpress_site(db, site: str, max_pages: int = 10, per_page: int = 100) -> dict:
    safe_pages = max(1, min(max_pages, 200))
    safe_per_page = max(1, min(per_page, 100))
    results = []
    total_pages = None
    for page in range(1, safe_pages + 1):
        entries, total_pages = fetch_wordpress_posts(site, page=page, per_page=safe_per_page)
        if not entries:
            break
        result = _archive_blog_items(db, entries, f"wordpress:{site}:page:{page}")
        result["page"] = page
        results.append(result)
        if total_pages and page >= total_pages:
            break
    summary = {
        "site": site,
        "pages_requested": safe_pages,
        "per_page": safe_per_page,
        "total_pages": total_pages,
        "pages_seen": len(results),
        "seen": sum(item["seen"] for item in results),
        "created": sum(item["created"] for item in results),
        "existing": sum(item["existing"] for item in results),
        "results": results,
    }
    audit(db, "blog.wordpress_backfill", f"Backfilled WordPress site {site}", payload=summary)
    return summary


def backfill_feed_pages(db, feed_url: str, max_pages: int = 10, page_size: int = 25) -> dict:
    safe_pages = max(1, min(max_pages, 500))
    safe_page_size = max(1, min(page_size, 100))
    results = []
    for page in range(1, safe_pages + 1):
        if "blogspot.com" in feed_url:
            separator = "&" if "?" in feed_url else "?"
            page_url = f"{feed_url}{separator}max-results={safe_page_size}&start-index={((page - 1) * safe_page_size) + 1}"
        else:
            separator = "&" if "?" in feed_url else "?"
            page_url = f"{feed_url}{separator}paged={page}"
        entries = fetch_rss_entries(page_url)
        if not entries:
            break
        result = _archive_blog_items(db, entries, f"feed:{page_url}")
        result["page"] = page
        result["feed_url"] = page_url
        results.append(result)
    summary = {
        "feed_url": feed_url,
        "pages_requested": safe_pages,
        "page_size": safe_page_size,
        "pages_seen": len(results),
        "seen": sum(item["seen"] for item in results),
        "created": sum(item["created"] for item in results),
        "existing": sum(item["existing"] for item in results),
        "results": results,
    }
    audit(db, "blog.feed_backfill", f"Backfilled feed {feed_url}", payload=summary)
    return summary


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
