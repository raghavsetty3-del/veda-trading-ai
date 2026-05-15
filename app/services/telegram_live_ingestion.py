from sqlalchemy.orm import Session

from app.ingestion.telegram_listener import fetch_recent_messages
from app.schemas import TelegramExportIngestRequest, TelegramExportMessage
from app.services.audit import audit
from app.services.telegram_ingestion import ingest_telegram_export


async def ingest_live_telegram(db: Session, limit: int | None = None, channels: list[str] | None = None) -> dict:
    fetched = await fetch_recent_messages(limit=limit, channels=channels)
    results = []
    for item in fetched["channels"]:
        payload = TelegramExportIngestRequest(
            channel=item["channel"],
            messages=[TelegramExportMessage(**message) for message in item["messages"]],
        )
        result = ingest_telegram_export(db, payload)
        results.append(result)

    summary = {
        "configured": fetched["configured"],
        "limit": fetched["limit"],
        "channels": len(results),
        "seen": sum(item["seen"] for item in results),
        "created": sum(item["created"] for item in results),
        "existing": sum(item["existing"] for item in results),
        "results": results,
    }
    audit(db, "telegram.live_ingested", "Ingested configured Telegram live messages", payload=summary)
    return summary
