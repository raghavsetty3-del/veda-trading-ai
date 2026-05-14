from app.services.audit import audit
from app.services.source_archive import archive_source_document


def ingest_telegram_export(db, payload) -> dict:
    created = 0
    existing = 0
    items = []
    channel = payload.channel.strip()

    for message in payload.messages:
        source_url = f"telegram://{channel}/{message.message_id}"
        row, was_created, psychology = archive_source_document(
            db,
            {
                "source_type": "telegram",
                "source_url": source_url,
                "source_external_id": str(message.message_id),
                "title": f"{channel} message {message.message_id}",
                "author": message.author or channel,
                "raw_text": message.text,
                "raw_html": None,
                "media_paths": message.media_paths,
            },
        )
        items.append({"id": row.id, "source_url": row.source_url, "created": was_created})
        if was_created:
            created += 1
            audit(
                db,
                "source.ingested",
                f"Ingested Telegram message {message.message_id} from {channel}",
                entity_type="source_document",
                entity_id=str(row.id),
                payload={"psychology_preview": psychology, "channel": channel},
            )
        else:
            existing += 1

    summary = {"channel": channel, "seen": len(payload.messages), "created": created, "existing": existing, "items": items}
    audit(db, "telegram.export_ingested", f"Ingested Telegram export for {channel}", payload=summary)
    return summary
