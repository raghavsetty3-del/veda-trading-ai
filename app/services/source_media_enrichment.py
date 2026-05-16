from sqlalchemy.orm import Session

from app.ingestion.media import extract_media_urls_from_html, unique_urls
from app.models import SourceDocument


def enrich_source_media(db: Session, source: SourceDocument) -> dict:
    media_was_missing = source.media_paths is None
    existing = source.media_paths or []
    extracted = extract_media_urls_from_html(source.raw_html, source.source_url)
    merged = unique_urls([*existing, *extracted])
    added = max(0, len(merged) - len(existing))
    changed = media_was_missing or merged != existing
    if changed:
        source.media_paths = merged
        if added:
            source.processed = False
        db.add(source)
    return {
        "source_id": source.id,
        "source_type": source.source_type,
        "media_count": len(merged),
        "added": added,
        "changed": changed,
    }


def enrich_sources_media(
    db: Session,
    source_type: str | None = None,
    limit: int = 100,
    only_missing: bool = True,
) -> dict:
    safe_limit = max(1, min(limit, 1000))
    query = db.query(SourceDocument).filter(SourceDocument.raw_html.isnot(None))
    if source_type:
        query = query.filter(SourceDocument.source_type == source_type)
    if only_missing:
        query = query.filter(SourceDocument.media_paths.is_(None))
    rows = query.order_by(SourceDocument.id.desc()).limit(safe_limit).all()

    items = [enrich_source_media(db, row) for row in rows]
    db.commit()
    return {
        "seen": len(rows),
        "changed": sum(1 for item in items if item["changed"]),
        "media_added": sum(item["added"] for item in items),
        "items": items,
    }
