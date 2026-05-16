from sqlalchemy.orm import Session

from app.models import SourceDocument
from app.services.psychology import extract_psychology


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
        return existing, False, extract_psychology(existing.raw_text)

    row = SourceDocument(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    psychology = extract_psychology(row.raw_text)
    return row, True, psychology
