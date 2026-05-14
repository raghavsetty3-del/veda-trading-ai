from datetime import datetime

from sqlalchemy.orm import Session

from app.models import RuleMapping


def serialize_rule(row: RuleMapping) -> dict:
    return {
        "id": row.id,
        "principle_id": row.principle_id,
        "rule_code": row.rule_code,
        "rule_name": row.rule_name,
        "logic_json": row.logic_json,
        "expected_behavior": row.expected_behavior,
        "status": row.status,
        "version": row.version,
        "active": row.active,
    }


def set_rule_activation(db: Session, rule_code: str, active: bool, validation_note: str) -> dict | None:
    row = db.query(RuleMapping).filter_by(rule_code=rule_code).first()
    if not row:
        return None

    row.active = active
    row.status = "active_reviewed" if active else "draft"
    marker = "Activated" if active else "Deactivated"
    row.expected_behavior = (
        f"{row.expected_behavior}\n\n"
        f"{marker} review {datetime.utcnow().isoformat()}: {validation_note}"
    )
    db.commit()
    db.refresh(row)
    return serialize_rule(row)
