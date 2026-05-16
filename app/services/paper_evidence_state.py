from datetime import datetime

from sqlalchemy.orm import Session

from app.models import SystemState
from app.services.audit import audit
from app.services.paper_trading import paper_performance_metrics

STATE_KEY = "paper_evidence_snapshot"


def _compact_items(items: list[dict]) -> dict:
    compact = {}
    for item in items:
        symbol = item.get("symbol")
        if not symbol:
            continue
        compact[symbol] = {
            "realized_closed_trades": item.get("realized_closed_trades"),
            "remaining_review_trades": item.get("remaining_review_trades"),
            "sample_ready": item.get("sample_ready"),
            "net_realized_pnl": item.get("net_realized_pnl"),
            "pnl_positive": item.get("pnl_positive"),
            "profit_factor": item.get("profit_factor"),
            "profit_factor_label": item.get("profit_factor_label"),
            "average_r_multiple": item.get("average_r_multiple"),
            "forward_review_ready": item.get("forward_review_ready"),
        }
    return compact


def build_paper_evidence_snapshot(db: Session, symbols: list[str] | None = None) -> dict:
    performance = paper_performance_metrics(db, symbols=symbols, limit=500)
    compact = _compact_items(performance.get("items") or [])
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "symbols": performance.get("symbols") or sorted(compact),
        "compact": compact,
        "items": performance.get("items") or [],
    }


def record_paper_evidence_snapshot(db: Session, trigger: str = "manual", symbols: list[str] | None = None) -> dict:
    snapshot = build_paper_evidence_snapshot(db)
    row = db.get(SystemState, STATE_KEY)
    previous = row.value if row else None
    previous_compact = (previous or {}).get("compact") if isinstance(previous, dict) else None
    changed = previous_compact != snapshot["compact"]

    if not row:
        row = SystemState(key=STATE_KEY, value=snapshot, updated_at=datetime.utcnow())
        db.add(row)
    elif changed:
        row.value = snapshot
        row.updated_at = datetime.utcnow()

    if previous is None or changed:
        db.commit()

    if changed or previous is None:
        audit(
            db,
            "paper.evidence_snapshot",
            "Paper evidence snapshot changed",
            payload={
                "trigger": trigger,
                "previous": previous_compact,
                "current": snapshot["compact"],
            },
        )

    return {
        "changed": changed or previous is None,
        "trigger": trigger,
        "snapshot": snapshot,
    }
