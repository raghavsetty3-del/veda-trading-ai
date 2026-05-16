from datetime import datetime
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings


def configured_public_channels() -> list[str]:
    return [
        item.strip()
        for item in (settings.telegram_public_channels or "").replace("\n", ",").split(",")
        if item.strip()
    ]


def normalize_public_channel(value: str) -> str:
    item = value.strip()
    if not item:
        raise ValueError("Telegram channel is required")
    if item.startswith("@"):
        return item[1:]
    parsed = urlparse(item if "://" in item else f"https://{item}")
    if parsed.netloc.lower() in {"t.me", "telegram.me"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] == "s":
            parts = parts[1:]
        if parts:
            return parts[0]
    return item.strip("/")


def public_telegram_status() -> dict:
    channels = configured_public_channels()
    return {
        "configured": bool(channels),
        "channels": channels,
        "normalized_channels": [normalize_public_channel(channel) for channel in channels],
        "ingest_limit": settings.telegram_public_ingest_limit,
        "interval_seconds": settings.telegram_public_ingest_interval_seconds,
        "run_on_start": settings.telegram_public_ingest_on_start,
        "source": "telegram_public_web",
        "requires_api_credentials": False,
    }


def fetch_public_channel_messages(channel: str, limit: int | None = None) -> dict:
    normalized = normalize_public_channel(channel)
    safe_limit = max(1, min(limit or settings.telegram_public_ingest_limit, 100))
    url = f"https://t.me/s/{normalized}"
    headers = {"User-Agent": "Mozilla/5.0 VedaTradingAI/0.2"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    messages = []
    for node in soup.select(".tgme_widget_message"):
        data_post = node.get("data-post") or ""
        if "/" not in data_post:
            continue
        message_channel, message_id = data_post.rsplit("/", 1)
        text_node = node.select_one(".tgme_widget_message_text")
        text = text_node.get_text("\n", strip=True) if text_node else ""
        if not text:
            continue
        time_node = node.select_one("time")
        published_at = time_node.get("datetime") if time_node else None
        messages.append(
            {
                "message_id": message_id,
                "channel": message_channel,
                "text": text,
                "date": published_at,
                "author": message_channel,
                "source_url": f"https://t.me/{message_channel}/{message_id}",
            }
        )

    messages = messages[-safe_limit:]
    return {
        "configured": True,
        "channel": channel,
        "normalized_channel": normalized,
        "source_url": url,
        "seen": len(messages),
        "messages": messages,
        "fetched_at": datetime.utcnow().isoformat(),
    }


def fetch_public_channels(limit: int | None = None, channels: list[str] | None = None) -> dict:
    target_channels = [item.strip() for item in (channels or configured_public_channels()) if item.strip()]
    if not target_channels:
        raise RuntimeError("No public Telegram channels configured. Set TELEGRAM_PUBLIC_CHANNELS or pass channels.")
    results = [fetch_public_channel_messages(channel, limit=limit) for channel in target_channels]
    return {
        "configured": True,
        "limit": max(1, min(limit or settings.telegram_public_ingest_limit, 100)),
        "channels": results,
    }
