from datetime import datetime
from sqlalchemy.orm import Session
from app.models import SystemState


def get_kill_switch(db: Session) -> bool:
    row = db.get(SystemState, "global_kill_switch")
    return bool(row and row.value.get("enabled", False))


def set_kill_switch(db: Session, enabled: bool, reason: str):
    row = db.get(SystemState, "global_kill_switch")
    payload = {"enabled": enabled, "reason": reason, "updated_at": datetime.utcnow().isoformat()}
    if row:
        row.value = payload
        row.updated_at = datetime.utcnow()
    else:
        row = SystemState(key="global_kill_switch", value=payload)
        db.add(row)
    db.commit()
    return row
