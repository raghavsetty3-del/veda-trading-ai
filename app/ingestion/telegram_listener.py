import importlib.util
from pathlib import Path

from app.config import settings


def configured_channels() -> list[str]:
    return [
        item.strip()
        for item in (settings.telegram_channels or "").replace("\n", ",").split(",")
        if item.strip()
    ]


def telethon_available() -> bool:
    return importlib.util.find_spec("telethon") is not None


def telegram_status() -> dict:
    missing = []
    if not settings.telegram_api_id:
        missing.append("TELEGRAM_API_ID")
    if not settings.telegram_api_hash:
        missing.append("TELEGRAM_API_HASH")
    if not settings.telegram_channels:
        missing.append("TELEGRAM_CHANNELS")
    if not telethon_available():
        missing.append("telethon package")
    channels = configured_channels()
    return {
        "configured": not missing,
        "missing": missing,
        "session_name": settings.telegram_session_name,
        "session_dir": settings.telegram_session_dir,
        "auth_mode": "bot" if settings.telegram_bot_token else "user_session",
        "bot_token_present": bool(settings.telegram_bot_token),
        "telethon_available": telethon_available(),
        "channels": channels,
        "ingest_limit": settings.telegram_ingest_limit,
    }


async def fetch_recent_messages(limit: int | None = None, channels: list[str] | None = None) -> dict:
    status = telegram_status()
    if not status["configured"]:
        raise RuntimeError(f"Telegram listener is not configured. Missing: {', '.join(status['missing'])}")

    from telethon import TelegramClient

    safe_limit = max(1, min(limit or settings.telegram_ingest_limit, 500))
    target_channels = [item.strip() for item in (channels or configured_channels()) if item.strip()]
    session_dir = Path(settings.telegram_session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / settings.telegram_session_name

    client = TelegramClient(str(session_path), int(settings.telegram_api_id), settings.telegram_api_hash)
    if settings.telegram_bot_token:
        await client.start(bot_token=settings.telegram_bot_token)
    else:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError(
                "Telegram user session is not authorized. Configure TELEGRAM_BOT_TOKEN or run a one-time "
                "interactive Telethon login on the VM to create the session file."
            )

    try:
        channel_results = []
        for channel in target_channels:
            messages = []
            async for message in client.iter_messages(channel, limit=safe_limit):
                text = message.message or ""
                if not text.strip():
                    continue
                messages.append({
                    "message_id": str(message.id),
                    "text": text,
                    "date": message.date.isoformat() if message.date else None,
                    "author": str(message.sender_id or channel),
                    "media_paths": None,
                })
            channel_results.append({"channel": channel, "seen": len(messages), "messages": messages})
        return {
            "configured": True,
            "limit": safe_limit,
            "channels": channel_results,
        }
    finally:
        await client.disconnect()


async def start_telegram_listener(limit: int | None = None, channels: list[str] | None = None) -> dict:
    return await fetch_recent_messages(limit=limit, channels=channels)
