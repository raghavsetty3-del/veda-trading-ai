from sqlalchemy.orm import Session

from app.models import SourceDocument
from app.services.psychology import extract_psychology
from app.ingestion.media import unique_urls


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
    }
    values = {key: value for key, value in data.items() if key in allowed}
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
