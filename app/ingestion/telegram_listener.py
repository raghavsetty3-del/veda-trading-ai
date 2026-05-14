from app.config import settings


def telegram_status() -> dict:
    missing = []
    if not settings.telegram_api_id:
        missing.append("TELEGRAM_API_ID")
    if not settings.telegram_api_hash:
        missing.append("TELEGRAM_API_HASH")
    if not settings.telegram_channels:
        missing.append("TELEGRAM_CHANNELS")
    return {
        "configured": not missing,
        "missing": missing,
        "session_name": settings.telegram_session_name,
        "channels": [
            item.strip()
            for item in (settings.telegram_channels or "").replace("\n", ",").split(",")
            if item.strip()
        ],
    }


def start_telegram_listener():
    status = telegram_status()
    if not status["configured"]:
        raise RuntimeError(f"Telegram listener is not configured. Missing: {', '.join(status['missing'])}")
    raise NotImplementedError("Live Telethon listener is not enabled in this safe build yet.")
