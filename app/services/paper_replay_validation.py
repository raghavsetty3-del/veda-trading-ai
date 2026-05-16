from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ValidationCase
from app.services.paper_replay import evaluate_historical_paper_replay


def _case_code(symbol: str, timeframe: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"PAPER-REPLAY-{symbol.upper()}-{timeframe.lower()}-{stamp}"


def _profit_factor_pass(metrics: dict, expected_min_profit_factor: float | None) -> bool:
    if expected_min_profit_factor is None:
        return True
    value = metrics.get("profit_factor")
    if value is not None:
        return float(value) >= expected_min_profit_factor
    return str(metrics.get("profit_factor_label") or "").lower().startswith("infinite")


def create_paper_replay_validation(db: Session, payload) -> dict:
    result = evaluate_historical_paper_replay(db, payload)
    metrics = result.get("metrics") or {}
    expected_min_realized_trades = max(0, payload.expected_min_realized_trades)
    expected_min_net_pnl = payload.expected_min_net_pnl
    expected_min_profit_factor = payload.expected_min_profit_factor

    ready = bool(result.get("ready"))
    enough_realized = int(metrics.get("realized_trades") or 0) >= expected_min_realized_trades
    enough_net_pnl = float(metrics.get("net_realized_pnl") or 0.0) >= expected_min_net_pnl
    enough_profit_factor = _profit_factor_pass(metrics, expected_min_profit_factor)
    status = "pass" if ready and enough_realized and enough_net_pnl and enough_profit_factor else "fail"
    checks = [ready, enough_realized, enough_net_pnl, enough_profit_factor]
    score = round(sum(1 for item in checks if item) / len(checks), 3)

    delivered_json = {
        "ready": ready,
        "symbol": result.get("symbol"),
        "timeframe": result.get("timeframe"),
        "source_candles": result.get("source_candles"),
        "min_window": result.get("min_window"),
        "max_trades": result.get("max_trades"),
        "cooldown_candles": result.get("cooldown_candles"),
        "exit_mode": result.get("exit_mode"),
        "part_book_r_multiple": result.get("part_book_r_multiple"),
        "part_book_fraction": result.get("part_book_fraction"),
        "trail_lookback_candles": result.get("trail_lookback_candles"),
        "blocked_counts": result.get("blocked_counts"),
        "metrics": metrics,
        "checks": {
            "ready": ready,
            "enough_realized": enough_realized,
            "enough_net_pnl": enough_net_pnl,
            "enough_profit_factor": enough_profit_factor,
        },
    }

    row = ValidationCase(
        case_code=_case_code(payload.symbol, payload.timeframe),
        title=f"Historical paper replay validation: {payload.symbol.upper()} {payload.timeframe}",
        expected_json={
            "type": "historical_paper_replay",
            "symbol": payload.symbol.upper(),
            "timeframe": payload.timeframe.lower(),
            "expected_min_realized_trades": expected_min_realized_trades,
            "expected_min_net_pnl": expected_min_net_pnl,
            "expected_min_profit_factor": expected_min_profit_factor,
            "requires_timestamped_higher_timeframe_context": True,
            "exit_mode": payload.exit_mode,
        },
        delivered_json=delivered_json,
        status=status,
        score=score,
        notes=payload.notes,
        evaluated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "validation_case_id": row.id,
        "case_code": row.case_code,
        "status": row.status,
        "score": row.score,
        "delivered_json": delivered_json,
    }
