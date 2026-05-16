from sqlalchemy.orm import Session

from app.ingestion.telegram_public import configured_public_channels, fetch_public_channels, public_telegram_status
from app.services.audit import audit
from app.services.source_archive import archive_source_document


def ingest_public_telegram(db: Session, limit: int | None = None, channels: list[str] | None = None) -> dict:
    fetched = fetch_public_channels(limit=limit, channels=channels)
    results = []
    created_total = 0
    existing_total = 0
    seen_total = 0
    for item in fetched["channels"]:
        created = 0
        existing = 0
        rows = []
        for message in item["messages"]:
            row, was_created, psychology = archive_source_document(
                db,
                {
                    "source_type": "telegram",
                    "source_url": message["source_url"],
                    "source_external_id": str(message["message_id"]),
                    "title": f"{message['channel']} message {message['message_id']}",
                    "author": message["author"],
                    "raw_text": message["text"],
                    "raw_html": None,
                    "media_paths": None,
                },
            )
            rows.append({"id": row.id, "source_url": row.source_url, "created": was_created})
            if was_created:
                created += 1
                audit(
                    db,
                    "source.ingested",
                    f"Ingested public Telegram message {message['message_id']} from {message['channel']}",
                    entity_type="source_document",
                    entity_id=str(row.id),
                    payload={"psychology_preview": psychology, "channel": message["channel"]},
                )
            else:
                existing += 1
        seen_total += item["seen"]
        created_total += created
        existing_total += existing
        results.append(
            {
                "channel": item["normalized_channel"],
                "source_url": item["source_url"],
                "seen": item["seen"],
                "created": created,
                "existing": existing,
                "items": rows,
            }
        )

    summary = {
        "configured": fetched["configured"],
        "limit": fetched["limit"],
        "channels": len(results),
        "seen": seen_total,
        "created": created_total,
        "existing": existing_total,
        "results": results,
    }
    audit(db, "telegram.public_ingested", "Ingested public Telegram web messages", payload=summary)
    return summary


def ingest_configured_public_telegram(db: Session) -> dict:
    return ingest_public_telegram(db, limit=public_telegram_status()["ingest_limit"], channels=configured_public_channels())
