from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SystemState
from app.services.audit import audit
from app.services.source_archive import archive_source_document


OFFSET_KEY = "telegram_bot_update_offset"


def configured_bot_allowed_chats() -> list[str]:
    raw = settings.telegram_bot_allowed_chats or settings.telegram_channels or ""
    return [item.strip() for item in raw.replace("\n", ",").split(",") if item.strip()]


def telegram_bot_status() -> dict:
    allowed_chats = configured_bot_allowed_chats()
    return {
        "configured": bool(settings.telegram_bot_token),
        "missing": [] if settings.telegram_bot_token else ["TELEGRAM_BOT_TOKEN"],
        "allowed_chats": allowed_chats,
        "ingest_limit": settings.telegram_bot_ingest_limit,
        "interval_seconds": settings.telegram_bot_ingest_interval_seconds,
        "run_on_start": settings.telegram_bot_ingest_on_start,
        "requires_api_credentials": False,
        "history": "new messages only after bot is added to the channel",
    }


def _state_offset(db: Session) -> int | None:
    row = db.get(SystemState, OFFSET_KEY)
    if not row or not isinstance(row.value, dict):
        return None
    offset = row.value.get("offset")
    return int(offset) if offset is not None else None


def _save_offset(db: Session, offset: int) -> None:
    row = db.get(SystemState, OFFSET_KEY)
    value = {"offset": offset, "updated_at": datetime.utcnow().isoformat()}
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        row = SystemState(key=OFFSET_KEY, value=value)
        db.add(row)
    db.commit()


def _chat_keys(chat: dict) -> set[str]:
    values = {str(chat.get("id", ""))}
    if chat.get("username"):
        values.add(str(chat["username"]))
        values.add(f"@{chat['username']}")
    if chat.get("title"):
        values.add(str(chat["title"]))
    return {item.lower() for item in values if item}


def _allowed(chat: dict, allowed_chats: list[str]) -> bool:
    if not allowed_chats:
        return True
    keys = _chat_keys(chat)
    allowed = {item.lower().strip() for item in allowed_chats}
    return bool(keys & allowed)


def _message_from_update(update: dict, allowed_chats: list[str]) -> dict | None:
    message = update.get("channel_post") or update.get("message")
    if not message:
        return None
    chat = message.get("chat") or {}
    if not _allowed(chat, allowed_chats):
        return None
    text = message.get("text") or message.get("caption") or ""
    if not text.strip():
        return None
    chat_id = str(chat.get("id") or "unknown")
    message_id = str(message.get("message_id"))
    title = chat.get("title") or chat.get("username") or chat_id
    return {
        "update_id": update.get("update_id"),
        "message_id": message_id,
        "chat_id": chat_id,
        "channel": title,
        "author": title,
        "date": datetime.utcfromtimestamp(message["date"]).isoformat() if message.get("date") else None,
        "text": text,
        "source_url": f"telegram://bot/{chat_id}/{message_id}",
    }


def fetch_bot_updates(db: Session, limit: int | None = None) -> dict:
    if not settings.telegram_bot_token:
        raise RuntimeError("Telegram Bot API is not configured. Missing: TELEGRAM_BOT_TOKEN")
    safe_limit = max(1, min(limit or settings.telegram_bot_ingest_limit, 100))
    params = {
        "timeout": 0,
        "limit": safe_limit,
        "allowed_updates": '["message","channel_post"]',
    }
    offset = _state_offset(db)
    if offset is not None:
        params["offset"] = offset

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates"
    with httpx.Client(timeout=30) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or "Telegram Bot API getUpdates failed")

    updates = payload.get("result") or []
    allowed_chats = configured_bot_allowed_chats()
    messages = [item for update in updates if (item := _message_from_update(update, allowed_chats))]
    if updates:
        max_update_id = max(int(update["update_id"]) for update in updates if update.get("update_id") is not None)
        _save_offset(db, max_update_id + 1)
    return {
        "configured": True,
        "limit": safe_limit,
        "updates_seen": len(updates),
        "seen": len(messages),
        "allowed_chats": allowed_chats,
        "messages": messages,
    }


def ingest_bot_telegram(db: Session, limit: int | None = None) -> dict:
    fetched = fetch_bot_updates(db, limit=limit)
    created = 0
    existing = 0
    rows = []
    for message in fetched["messages"]:
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
                f"Ingested Telegram bot message {message['message_id']} from {message['channel']}",
                entity_type="source_document",
                entity_id=str(row.id),
                payload={"psychology_preview": psychology, "channel": message["channel"]},
            )
        else:
            existing += 1

    summary = {
        "configured": fetched["configured"],
        "limit": fetched["limit"],
        "updates_seen": fetched["updates_seen"],
        "seen": fetched["seen"],
        "created": created,
        "existing": existing,
        "allowed_chats": fetched["allowed_chats"],
        "items": rows,
    }
    audit(db, "telegram.bot_ingested", "Ingested Telegram Bot API messages", payload=summary)
    return summary
