import time
from app.config import settings
from app.db import SessionLocal
from app.services.audit import audit
from app.services.blog_ingestion import configured_blog_feeds, ingest_configured_blog_feeds
from app.services.market_provider import has_configured_market_sources, ingest_configured_market_sources
from app.services.paper_scheduler import configured_paper_symbols, run_scheduled_paper_trading


def main():
    last_heartbeat = 0.0
    last_blog_ingest = 0.0 if settings.blog_ingest_on_start else time.time()
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
                ingest_configured_blog_feeds(db)
                last_blog_ingest = now
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
