from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.models import MarketCandle, PaperTrade, RuleMapping
from app.services.instrument_profiles import apply_instrument_profile
from app.services.recovery import get_kill_switch
from app.services.rules import evaluate_rule, evaluate_setup


def list_paper_trades(db: Session, limit: int = 100) -> list[PaperTrade]:
    safe_limit = max(1, min(limit, 500))
    return db.query(PaperTrade).order_by(PaperTrade.created_at.desc()).limit(safe_limit).all()


def paper_performance_metrics(db: Session, symbols: list[str] | None = None, limit: int = 500) -> dict:
    safe_limit = max(1, min(limit, 500))
    query = db.query(PaperTrade)
    if symbols:
        query = query.filter(PaperTrade.symbol.in_([item.upper() for item in symbols]))
    rows = query.order_by(PaperTrade.created_at.desc()).limit(safe_limit).all()

    grouped: dict[str, list[PaperTrade]] = {}
    for row in rows:
        grouped.setdefault(row.symbol, []).append(row)

    items = []
    for symbol in sorted(grouped):
        symbol_rows = grouped[symbol]
        realized_values = [row.realized_pnl for row in symbol_rows if row.realized_pnl is not None]
        open_rows = [row for row in symbol_rows if row.status == "planned"]
        open_risk_points = 0.0
        open_reward_points = 0.0
        for row in open_rows:
            if row.stop_loss is not None:
                open_risk_points += abs(row.entry_price - row.stop_loss) * row.quantity
            if row.target is not None:
                open_reward_points += abs(row.target - row.entry_price) * row.quantity
        gross_profit = round(sum(value for value in realized_values if value > 0), 2)
        gross_loss = round(abs(sum(value for value in realized_values if value < 0)), 2)
        net_pnl = round(sum(realized_values), 2)
        if not realized_values:
            profit_factor = None
            profit_factor_label = "N/A"
        elif gross_loss == 0 and gross_profit > 0:
            profit_factor = None
            profit_factor_label = "Infinite (no realized losses yet)"
        elif gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 3)
            profit_factor_label = str(profit_factor)
        else:
            profit_factor = 0.0
            profit_factor_label = "0.0"

        closed_wins = [value for value in realized_values if value > 0]
        r_values = [row.r_multiple for row in symbol_rows if row.r_multiple is not None]
        minimum_review_trades = 20
        realized_count = len(realized_values)
        items.append({
            "symbol": symbol,
            "total_trades": len(symbol_rows),
            "open_trades": len(open_rows),
            "open_trade_ids": [row.id for row in open_rows],
            "open_sides": sorted({row.side for row in open_rows}),
            "open_risk_points": round(open_risk_points, 2),
            "open_reward_points": round(open_reward_points, 2),
            "open_reward_risk_ratio": round(open_reward_points / open_risk_points, 3) if open_risk_points > 0 else None,
            "cancelled_trades": sum(1 for row in symbol_rows if row.status == "cancelled"),
            "realized_closed_trades": realized_count,
            "minimum_review_trades": minimum_review_trades,
            "remaining_review_trades": max(0, minimum_review_trades - realized_count),
            "sample_ready": realized_count >= minimum_review_trades,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_realized_pnl": net_pnl,
            "pnl_positive": net_pnl > 0,
            "forward_review_ready": realized_count >= minimum_review_trades and net_pnl > 0,
            "profit_factor": profit_factor,
            "profit_factor_label": profit_factor_label,
            "win_rate": round(len(closed_wins) / realized_count, 4) if realized_values else None,
            "average_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
        })

    return {
        "limit": safe_limit,
        "symbols": sorted(grouped),
        "items": items,
    }


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
    fallback_risk_points = max(entry_price * 0.003, 1)
    recent_high = float(market_context.get("recent_high") or 0)
    recent_low = float(market_context.get("recent_low") or 0)
    risk_points = float(market_context.get("risk_points") or fallback_risk_points)
    stop_loss = None
    target = None
    if side == "buy":
        stop_loss = recent_low if recent_low and recent_low < entry_price else entry_price - risk_points
        risk_points = abs(entry_price - stop_loss) or fallback_risk_points
        target = entry_price + (risk_points * 2)
    elif side == "sell":
        stop_loss = recent_high if recent_high and recent_high > entry_price else entry_price + risk_points
        risk_points = abs(entry_price - stop_loss) or fallback_risk_points
        target = entry_price - (risk_points * 2)
    market_context["risk_points"] = risk_points
    market_context["stop_basis"] = "price_action_structure"

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
    exit_plan = None
    if settings.paper_exit_mode == "author_part_book_trail" and plan["side"] in {"buy", "sell"}:
        exit_plan = {
            "mode": "author_part_book_trail",
            "part_book_r_multiple": settings.paper_part_book_r_multiple,
            "part_book_fraction": settings.paper_part_book_fraction,
            "trail_lookback_candles": settings.paper_trail_lookback_candles,
            "trailing_stop": plan["stop_loss"],
            "trail_window": [],
            "partial_exit": None,
            "partial_realized_pnl": 0.0,
            "last_reconciled_candle_at": plan["market_context"].get("last_candle_at"),
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
        context={
            "market_context": plan["market_context"],
            "setup": plan["setup"],
            "rules": plan["rules"],
            "exit_plan": exit_plan,
        },
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


def _entry_candle_at(row: PaperTrade) -> datetime | None:
    raw_value = ((row.context or {}).get("market_context") or {}).get("last_candle_at")
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_context_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _open_paper_trade_query(db: Session, symbols: list[str] | None = None, timeframe: str | None = None):
    closed_statuses = {"cancelled", "closed", "exited", "stopped", "target_hit", "trailed"}
    query = db.query(PaperTrade).filter(PaperTrade.closed_at.is_(None))
    query = query.filter(~PaperTrade.status.in_(closed_statuses))
    if symbols:
        query = query.filter(PaperTrade.symbol.in_([item.upper() for item in symbols]))
    if timeframe:
        query = query.filter(PaperTrade.timeframe == timeframe.lower())
    return query.order_by(PaperTrade.created_at.asc())


def _exit_from_candle(row: PaperTrade, candle: MarketCandle) -> tuple[str, float, str] | None:
    if row.side == "buy":
        stop_hit = row.stop_loss is not None and candle.low <= row.stop_loss
        target_hit = row.target is not None and candle.high >= row.target
        if stop_hit:
            return "stopped", float(row.stop_loss), f"Auto paper reconciliation: stop hit on {candle.ts.isoformat()}"
        if target_hit:
            return "target_hit", float(row.target), f"Auto paper reconciliation: target hit on {candle.ts.isoformat()}"
    if row.side == "sell":
        stop_hit = row.stop_loss is not None and candle.high >= row.stop_loss
        target_hit = row.target is not None and candle.low <= row.target
        if stop_hit:
            return "stopped", float(row.stop_loss), f"Auto paper reconciliation: stop hit on {candle.ts.isoformat()}"
        if target_hit:
            return "target_hit", float(row.target), f"Auto paper reconciliation: target hit on {candle.ts.isoformat()}"
    return None


def _author_exit_from_candle(row: PaperTrade, candle: MarketCandle) -> tuple[str, float, str] | None:
    context = row.context or {}
    exit_plan = context.get("exit_plan") or {}
    if exit_plan.get("mode") != "author_part_book_trail":
        return _exit_from_candle(row, candle)

    entry = float(row.entry_price)
    stop = float(row.stop_loss) if row.stop_loss is not None else None
    if stop is None:
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    part_r = max(float(exit_plan.get("part_book_r_multiple") or 1.0), 0.25)
    part_fraction = min(max(float(exit_plan.get("part_book_fraction") or 0.5), 0.1), 0.9)
    remaining_fraction = 1 - part_fraction
    lookback = max(int(exit_plan.get("trail_lookback_candles") or 3), 1)
    partial_exit = exit_plan.get("partial_exit")
    partial_realized = float(exit_plan.get("partial_realized_pnl") or 0.0)
    trailing_stop = float(exit_plan.get("trailing_stop") or stop)
    trail_window = list(exit_plan.get("trail_window") or [])
    part_target = entry + (risk * part_r) if row.side == "buy" else entry - (risk * part_r)

    if row.side == "buy":
        if candle.low <= trailing_stop:
            active_remaining_fraction = remaining_fraction if partial_exit else 1.0
            active_partial_realized = partial_realized if partial_exit else 0.0
            pnl = ((trailing_stop - entry) * row.quantity * active_remaining_fraction) + active_partial_realized
            status = "trailed" if partial_exit else "stopped"
            exit_plan["final_realized_pnl"] = round(pnl, 2)
            context["exit_plan"] = exit_plan
            row.context = context
            flag_modified(row, "context")
            return status, trailing_stop, f"Auto paper reconciliation: author exit {status} on {candle.ts.isoformat()}"
        if not partial_exit and candle.high >= part_target:
            partial_realized = (part_target - entry) * row.quantity * part_fraction
            partial_exit = {"price": part_target, "at": candle.ts.isoformat(), "fraction": part_fraction, "r_multiple": part_r}
            trailing_stop = max(trailing_stop, entry)
    elif row.side == "sell":
        if candle.high >= trailing_stop:
            active_remaining_fraction = remaining_fraction if partial_exit else 1.0
            active_partial_realized = partial_realized if partial_exit else 0.0
            pnl = ((entry - trailing_stop) * row.quantity * active_remaining_fraction) + active_partial_realized
            status = "trailed" if partial_exit else "stopped"
            exit_plan["final_realized_pnl"] = round(pnl, 2)
            context["exit_plan"] = exit_plan
            row.context = context
            flag_modified(row, "context")
            return status, trailing_stop, f"Auto paper reconciliation: author exit {status} on {candle.ts.isoformat()}"
        if not partial_exit and candle.low <= part_target:
            partial_realized = (entry - part_target) * row.quantity * part_fraction
            partial_exit = {"price": part_target, "at": candle.ts.isoformat(), "fraction": part_fraction, "r_multiple": part_r}
            trailing_stop = min(trailing_stop, entry)

    if partial_exit:
        trail_value = candle.low if row.side == "buy" else candle.high
        trail_window.append(trail_value)
        trail_window = trail_window[-lookback:]
        if row.side == "buy":
            trailing_stop = max(trailing_stop, min(trail_window))
        else:
            trailing_stop = min(trailing_stop, max(trail_window))

    exit_plan.update({
        "partial_exit": partial_exit,
        "partial_realized_pnl": round(partial_realized, 2),
        "trailing_stop": trailing_stop,
        "trail_window": trail_window,
        "last_reconciled_candle_at": candle.ts.isoformat(),
    })
    context["exit_plan"] = exit_plan
    row.context = context
    flag_modified(row, "context")
    return None


def reconcile_open_paper_trades(
    db: Session,
    symbols: list[str] | None = None,
    timeframe: str | None = None,
    limit: int = 200,
) -> dict:
    safe_limit = max(1, min(limit, 500))
    rows = _open_paper_trade_query(db, symbols=symbols, timeframe=timeframe).limit(safe_limit).all()
    reconciled = []
    skipped = []

    for row in rows:
        entry_candle_at = _entry_candle_at(row)
        if not entry_candle_at:
            skipped.append({"id": row.id, "symbol": row.symbol, "reason": "missing entry candle timestamp"})
            continue
        exit_plan = (row.context or {}).get("exit_plan") or {}
        last_reconciled_at = _parse_context_time(exit_plan.get("last_reconciled_candle_at"))
        scan_after = last_reconciled_at or entry_candle_at
        candles = (
            db.query(MarketCandle)
            .filter(
                MarketCandle.symbol == row.symbol,
                MarketCandle.timeframe == row.timeframe,
                MarketCandle.ts > scan_after,
            )
            .order_by(MarketCandle.ts.asc())
            .limit(500)
            .all()
        )
        if not candles:
            skipped.append({"id": row.id, "symbol": row.symbol, "reason": "no later candles"})
            continue

        for candle in candles:
            exit_result = _author_exit_from_candle(row, candle)
            if not exit_result:
                continue
            status, exit_price, exit_reason = exit_result
            row.status = status
            row.exit_price = exit_price
            row.exit_reason = exit_reason
            row.closed_at = candle.ts
            final_realized_pnl = ((row.context or {}).get("exit_plan") or {}).get("final_realized_pnl")
            row.realized_pnl = round(float(final_realized_pnl), 2) if final_realized_pnl is not None else _realized_pnl(row, exit_price)
            row.r_multiple = _r_multiple(row, row.realized_pnl)
            reconciled.append(serialize_paper_trade(row))
            break
        else:
            skipped.append({"id": row.id, "symbol": row.symbol, "reason": "target/stop not reached"})

    db.commit()
    return {
        "checked": len(rows),
        "closed": len(reconciled),
        "skipped": len(skipped),
        "items": reconciled,
        "skipped_items": skipped[:50],
    }


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
