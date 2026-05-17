from datetime import datetime
from email.utils import parsedate_to_datetime

from sqlalchemy.orm import Session

from app.models import SourceDocument
from app.services.psychology import extract_psychology
from app.ingestion.media import unique_urls


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).replace(tzinfo=None)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def archive_source_document(db: Session, data: dict) -> tuple[SourceDocument, bool, dict]:
    allowed = {
        "source_type",
        "source_url",
        "source_external_id",
        "title",
        "author",
        "raw_text",
        "raw_html",
        "media_paths",
        "published_at",
        "published_at_raw",
    }
    values = {key: value for key, value in data.items() if key in allowed}
    published_at = _parse_datetime(values.pop("published_at", None) or values.pop("published_at_raw", None))
    if published_at:
        values["published_at"] = published_at
    existing = None
    if values.get("source_url"):
        existing = (
            db.query(SourceDocument)
            .filter_by(source_type=values["source_type"], source_url=values["source_url"])
            .first()
        )
    if existing:
        changed = False
        incoming_media = unique_urls(values.get("media_paths") or [])
        if incoming_media:
            merged_media = unique_urls([*(existing.media_paths or []), *incoming_media])
            if merged_media != (existing.media_paths or []):
                existing.media_paths = merged_media
                existing.processed = False
                changed = True
        incoming_text = values.get("raw_text")
        if incoming_text and len(incoming_text) > len(existing.raw_text or ""):
            existing.raw_text = incoming_text
            existing.processed = False
            changed = True
        if values.get("published_at") and not existing.published_at:
            existing.published_at = values["published_at"]
            changed = True
        if changed:
            db.commit()
            db.refresh(existing)
        return existing, False, extract_psychology(existing.raw_text)

    row = SourceDocument(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    psychology = extract_psychology(row.raw_text)
    return row, True, psychology
