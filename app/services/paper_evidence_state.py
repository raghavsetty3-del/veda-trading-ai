from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AuditLog, SystemState
from app.services.audit import audit
from app.services.paper_trading import paper_performance_metrics

STATE_KEY = "paper_evidence_snapshot"
TRACKED_FIELDS = [
    "realized_closed_trades",
    "remaining_review_trades",
    "sample_ready",
    "net_realized_pnl",
    "pnl_positive",
    "profit_factor",
    "profit_factor_label",
    "average_r_multiple",
    "forward_review_ready",
]


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


def _review_gate(gate: str, ready: bool, detail: str) -> dict:
    return {
        "gate": gate,
        "ready": ready,
        "detail": detail,
    }


def _build_symbol_review(item: dict) -> dict:
    symbol = item.get("symbol")
    realized = item.get("realized_closed_trades") or 0
    minimum = item.get("minimum_review_trades") or 20
    remaining = item.get("remaining_review_trades") or max(0, minimum - realized)
    net_pnl = item.get("net_realized_pnl") or 0
    average_r = item.get("average_r_multiple")
    gross_loss = item.get("gross_loss") or 0
    profit_factor_label = item.get("profit_factor_label")
    open_trades = item.get("open_trades") or 0
    open_risk = item.get("open_risk_points") or 0
    managed_open_risk = open_trades == 0 or open_risk > 0
    profit_factor_reviewable = realized >= minimum and gross_loss > 0
    average_r_positive = average_r is not None and average_r > 0

    gates = [
        _review_gate(
            "minimum_realized_sample",
            realized >= minimum,
            f"{realized}/{minimum} realized closed trades; {remaining} remaining.",
        ),
        _review_gate(
            "positive_realized_pnl",
            net_pnl > 0,
            f"Net realized P&L: {net_pnl}.",
        ),
        _review_gate(
            "positive_average_r",
            average_r_positive,
            f"Average R-multiple: {average_r if average_r is not None else 'N/A'}.",
        ),
        _review_gate(
            "profit_factor_reviewable",
            profit_factor_reviewable,
            f"Profit factor: {profit_factor_label}; gross loss sample: {gross_loss}.",
        ),
        _review_gate(
            "managed_open_risk",
            managed_open_risk,
            f"Open trades: {open_trades}; open risk points: {open_risk}.",
        ),
    ]
    return {
        "symbol": symbol,
        "author_review_ready": all(gate["ready"] for gate in gates),
        "gates": gates,
        "metrics": item,
    }


def build_paper_evidence_review(db: Session, symbols: list[str] | None = None) -> dict:
    performance = paper_performance_metrics(db, symbols=symbols, limit=500)
    items = [_build_symbol_review(item) for item in performance.get("items") or []]
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "symbols": performance.get("symbols") or [item["symbol"] for item in items],
        "items": items,
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


def _filter_compact(compact: dict | None, symbols: list[str] | None) -> dict:
    if not isinstance(compact, dict):
        return {}
    if not symbols:
        return compact
    selected = {item.upper() for item in symbols}
    return {symbol: values for symbol, values in compact.items() if symbol.upper() in selected}


def _compact_deltas(previous: dict, current: dict) -> dict:
    deltas = {}
    for symbol in sorted(set(previous) | set(current)):
        previous_values = previous.get(symbol) or {}
        current_values = current.get(symbol) or {}
        symbol_deltas = {}
        for field in TRACKED_FIELDS:
            before = previous_values.get(field)
            after = current_values.get(field)
            if before != after:
                symbol_deltas[field] = {
                    "previous": before,
                    "current": after,
                }
        if symbol_deltas:
            deltas[symbol] = symbol_deltas
    return deltas


def list_paper_evidence_history(db: Session, symbols: list[str] | None = None, limit: int = 25) -> dict:
    safe_limit = max(1, min(limit, 200))
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.event_type == "paper.evidence_snapshot")
        .order_by(AuditLog.created_at.desc())
        .limit(safe_limit * 5)
        .all()
    )

    items = []
    for row in rows:
        payload = row.payload or {}
        previous = _filter_compact(payload.get("previous"), symbols)
        current = _filter_compact(payload.get("current"), symbols)
        if symbols and not previous and not current:
            continue
        items.append({
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "trigger": payload.get("trigger"),
            "previous": previous,
            "current": current,
            "deltas": _compact_deltas(previous, current),
        })
        if len(items) >= safe_limit:
            break

    return {
        "limit": safe_limit,
        "symbols": [item.upper() for item in symbols] if symbols else None,
        "items": items,
    }
