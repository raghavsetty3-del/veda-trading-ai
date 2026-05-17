import time
from app.config import settings
from app.db import SessionLocal
from app.services.audit import audit
from app.services.blog_ingestion import configured_blog_feeds, ingest_configured_blog_feeds
from app.services.knowledge_extraction import process_pending_sources, process_source
from app.services.market_provider import has_configured_market_sources, ingest_configured_market_sources
from app.services.paper_scheduler import configured_paper_symbols, run_scheduled_paper_trading
from app.services.source_media_enrichment import enrich_sources_media
from app.services.telegram_bot_ingestion import ingest_bot_telegram, telegram_bot_status
from app.services.telegram_public_ingestion import ingest_configured_public_telegram
from app.ingestion.telegram_public import configured_public_channels
from app.services.x_ingestion import configured_x_usernames, ingest_configured_x_usernames


def process_created_sources(db, ingest_result: dict, label: str) -> None:
    source_ids = list(dict.fromkeys(ingest_result.get("created_source_ids") or []))
    if not source_ids:
        return
    processed = []
    failed = []
    for source_id in source_ids[: settings.source_immediate_extraction_limit]:
        try:
            result = process_source(db, int(source_id))
            if result:
                processed.append(source_id)
        except Exception as exc:
            failed.append({"source_id": source_id, "error": str(exc)[:300]})
    audit(
        db,
        "extraction.ingest_immediate",
        f"Immediately processed newly ingested {label} sources",
        payload={
            "label": label,
            "created": len(source_ids),
            "processed": len(processed),
            "failed": failed,
            "limit": settings.source_immediate_extraction_limit,
        },
        severity="WARN" if failed else "INFO",
    )


def main():
    last_heartbeat = 0.0
    last_blog_ingest = 0.0 if settings.blog_ingest_on_start else time.time()
    last_telegram_bot_ingest = 0.0 if settings.telegram_bot_ingest_on_start else time.time()
    last_telegram_public_ingest = 0.0 if settings.telegram_public_ingest_on_start else time.time()
    last_x_ingest = 0.0 if settings.x_ingest_on_start else time.time()
    last_source_media_enrichment = 0.0 if settings.source_media_enrichment_on_start else time.time()
    last_source_extraction = 0.0 if settings.source_extraction_on_start else time.time()
    last_market_ingest = 0.0 if settings.market_data_ingest_on_start else time.time()
    last_paper_run = 0.0 if settings.paper_trading_on_start else time.time()
    while True:
        db = SessionLocal()
        try:
            now = time.time()
            if now - last_heartbeat >= 600:
                audit(db, "scheduler.heartbeat", "Scheduler heartbeat")
                last_heartbeat = now
            if configured_blog_feeds() and now - last_blog_ingest >= settings.blog_ingest_interval_seconds:
                result = ingest_configured_blog_feeds(db)
                process_created_sources(db, result, "blog")
                last_blog_ingest = now
            if telegram_bot_status()["configured"] and now - last_telegram_bot_ingest >= settings.telegram_bot_ingest_interval_seconds:
                ingest_bot_telegram(db, limit=settings.telegram_bot_ingest_limit)
                last_telegram_bot_ingest = now
            if configured_public_channels() and now - last_telegram_public_ingest >= settings.telegram_public_ingest_interval_seconds:
                ingest_configured_public_telegram(db)
                last_telegram_public_ingest = now
            if configured_x_usernames() and settings.x_bearer_token and now - last_x_ingest >= settings.x_ingest_interval_seconds:
                result = ingest_configured_x_usernames(db)
                process_created_sources(db, result, "x")
                last_x_ingest = now
            if now - last_source_media_enrichment >= settings.source_media_enrichment_interval_seconds:
                result = enrich_sources_media(db, source_type="blog", limit=settings.source_media_enrichment_limit)
                if result["seen"] or result["changed"]:
                    audit(
                        db,
                        "extraction.scheduled_media_enrichment",
                        "Scanned source documents for chart/media links",
                        payload={
                            "seen": result["seen"],
                            "changed": result["changed"],
                            "media_added": result["media_added"],
                        },
                    )
                last_source_media_enrichment = now
            if now - last_source_extraction >= settings.source_extraction_interval_seconds:
                result = process_pending_sources(db, limit=settings.source_extraction_limit)
                if result["seen"] or result["processed"]:
                    audit(
                        db,
                        "extraction.scheduled_process_pending",
                        "Processed pending source documents from scheduler",
                        payload={"processed": result["processed"], "seen": result["seen"]},
                    )
                last_source_extraction = now
            if has_configured_market_sources() and now - last_market_ingest >= settings.market_data_ingest_interval_seconds:
                ingest_configured_market_sources(db)
                last_market_ingest = now
            if configured_paper_symbols() and now - last_paper_run >= settings.paper_trading_interval_seconds:
                run_scheduled_paper_trading(db)
                last_paper_run = now
        finally:
            db.close()
        time.sleep(60)


if __name__ == "__main__":
    main()
