from sqlalchemy.orm import Session
from app.models import AuditLog


def audit(db: Session, event_type: str, message: str, severity: str = "INFO", entity_type: str | None = None, entity_id: str | None = None, payload: dict | None = None):
    row = AuditLog(event_type=event_type, severity=severity, entity_type=entity_type, entity_id=entity_id, message=message, payload=payload)
    db.add(row)
    db.commit()
    return row
