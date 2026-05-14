import time
from app.config import settings
from app.db import SessionLocal
from app.services.audit import audit
from app.services.blog_ingestion import configured_blog_feeds, ingest_configured_blog_feeds


def main():
    last_heartbeat = 0.0
    last_blog_ingest = 0.0 if settings.blog_ingest_on_start else time.time()
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
        finally:
            db.close()
        time.sleep(60)


if __name__ == "__main__":
    main()
