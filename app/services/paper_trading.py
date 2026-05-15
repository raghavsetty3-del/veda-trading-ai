from datetime import datetime

from sqlalchemy.orm import Session

from app.models import PaperTrade, RuleMapping
from app.services.instrument_profiles import apply_instrument_profile
from app.services.recovery import get_kill_switch
from app.services.rules import evaluate_rule, evaluate_setup


def list_paper_trades(db: Session, limit: int = 100) -> list[PaperTrade]:
    safe_limit = max(1, min(limit, 500))
    return db.query(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(safe_limit).all()


def serialize_paper_trade(row: PaperTrade) -> dict:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "timeframe": row.timeframe,
        "side": row.side,
        "stance": row.stance,
        "entry_price": row.entry_price,
        "stop_loss": row.stop_loss,
        "target": row.target,
        "quantity": row.quantity,
        "status": row.status,
        "exit_price": row.exit_price,
        "exit_reason": row.exit_reason,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "realized_pnl": row.realized_pnl,
        "r_multiple": row.r_multiple,
        "reason": row.reason,
        "context": row.context,
        "created_at": row.created_at.isoformat(),
    }


def build_paper_trade_plan(db: Session, payload) -> dict:
    market_context = apply_instrument_profile({"symbol": payload.symbol, **payload.market_context})
    rules = db.query(RuleMapping).filter_by(active=True).order_by(RuleMapping.rule_code).all()
    rule_results = []
    for row in rules:
        evaluation = evaluate_rule(row.logic_json, market_context)
        rule_results.append({
            "rule_code": row.rule_code,
            "rule_name": row.rule_name,
            "matched": evaluation["matched"],
            "passed": evaluation["passed"],
            "failed": evaluation["failed"],
            "expected_behavior": row.expected_behavior,
        })
    setup = evaluate_setup(market_context, rule_results)
    side = "none"
    if setup["stance"] in {"long", "long_bias"}:
        side = "buy"
    elif setup["stance"] in {"short", "short_bias"}:
        side = "sell"

    entry_price = float(market_context.get("last_price") or market_context.get("close") or 0)
    risk_points = float(market_context.get("risk_points") or max(entry_price * 0.003, 1))
    stop_loss = None
    target = None
    if side == "buy":
        stop_loss = entry_price - risk_points
        target = entry_price + (risk_points * 2)
    elif side == "sell":
        stop_loss = entry_price + risk_points
        target = entry_price - (risk_points * 2)

    return {
        "market_context": market_context,
        "setup": setup,
        "rules": rule_results,
        "side": side,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "quantity": max(1, payload.quantity),
    }


def create_paper_trade(db: Session, payload) -> dict:
    kill_switch_on = get_kill_switch(db)
    plan = build_paper_trade_plan(db, payload)
    if kill_switch_on and not payload.allow_when_kill_switch_on:
        return {
            "created": False,
            "blocked": True,
            "reason": "Kill switch is enabled",
            **plan,
        }
    if plan["side"] == "none":
        return {
            "created": False,
            "blocked": True,
            "reason": f"Setup stance is {plan['setup']['stance']}",
            **plan,
        }
    row = PaperTrade(
        symbol=plan["market_context"]["symbol"],
        timeframe=payload.timeframe,
        side=plan["side"],
        stance=plan["setup"]["stance"],
        entry_price=plan["entry_price"],
        stop_loss=plan["stop_loss"],
        target=plan["target"],
        quantity=plan["quantity"],
        reason="; ".join(plan["setup"].get("reasons", [])) or plan["setup"]["stance"],
        context={"market_context": plan["market_context"], "setup": plan["setup"], "rules": plan["rules"]},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "created": True,
        "blocked": False,
        "trade": serialize_paper_trade(row),
        **plan,
    }


def _realized_pnl(row: PaperTrade, exit_price: float) -> float | None:
    if row.side == "buy":
        return round((exit_price - row.entry_price) * row.quantity, 2)
    if row.side == "sell":
        return round((row.entry_price - exit_price) * row.quantity, 2)
    return None


def _r_multiple(row: PaperTrade, realized_pnl: float | None) -> float | None:
    if realized_pnl is None or row.stop_loss is None:
        return None
    risk = abs(row.entry_price - row.stop_loss) * row.quantity
    if risk <= 0:
        return None
    return round(realized_pnl / risk, 3)


def update_paper_trade_status(db: Session, trade_id: int, payload) -> PaperTrade | None:
    row = db.get(PaperTrade, trade_id)
    if not row:
        return None
    row.status = payload.status
    if payload.exit_price is not None:
        row.exit_price = payload.exit_price
        row.realized_pnl = _realized_pnl(row, payload.exit_price)
        row.r_multiple = _r_multiple(row, row.realized_pnl)
    if payload.exit_reason is not None:
        row.exit_reason = payload.exit_reason
    if payload.closed_at is not None:
        row.closed_at = payload.closed_at
    elif row.status in {"closed", "exited", "stopped", "target_hit", "cancelled"} or payload.exit_price is not None:
        row.closed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row
