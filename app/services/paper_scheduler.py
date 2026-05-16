from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.config import settings
from app.models import MarketCandle, PaperTrade
from app.services.audit import audit
from app.services.market_data import market_snapshot
from app.services.paper_evidence_state import record_paper_evidence_snapshot
from app.services.paper_exit_config import global_paper_exit_config, paper_exit_config_for_symbol, paper_symbol_exit_overrides
from app.services.paper_trading import create_paper_trade, reconcile_open_paper_trades
from app.services.trading_calendar import is_intraday_timeframe, is_nse_index_symbol, is_regular_nse_session_now


def configured_paper_symbols() -> list[str]:
    return [
        item.strip().upper()
        for item in (settings.paper_trading_symbols or "").split(",")
        if item.strip()
    ]


def paper_scheduler_config() -> dict:
    symbols = configured_paper_symbols()
    global_exit = global_paper_exit_config()
    return {
        "enabled": settings.enable_paper_trading,
        "symbols": symbols,
        "timeframe": settings.paper_trading_timeframe,
        "interval_seconds": settings.paper_trading_interval_seconds,
        "candle_limit": settings.paper_trading_candle_limit,
        "quantity": settings.paper_trading_quantity,
        "max_open_trades_per_symbol": settings.paper_max_open_trades_per_symbol,
        "cooldown_candles": global_exit["cooldown_candles"],
        "exit_mode": global_exit["exit_mode"],
        "part_book_r_multiple": global_exit["part_book_r_multiple"],
        "part_book_fraction": global_exit["part_book_fraction"],
        "trail_lookback_candles": global_exit["trail_lookback_candles"],
        "symbol_exit_overrides": paper_symbol_exit_overrides(),
        "effective_exit_by_symbol": {
            symbol: paper_exit_config_for_symbol(symbol)
            for symbol in symbols
        },
        "run_on_start": settings.paper_trading_on_start,
    }


def _has_existing_trade_for_candle(db: Session, symbol: str, timeframe: str, last_candle_at: str | None) -> bool:
    if not last_candle_at:
        return False

    rows = (
        db.query(PaperTrade)
        .filter(PaperTrade.symbol == symbol.upper(), PaperTrade.timeframe == timeframe.lower())
        .order_by(PaperTrade.created_at.desc())
        .limit(20)
        .all()
    )
    return any(
        (row.context or {}).get("market_context", {}).get("last_candle_at") == last_candle_at
        for row in rows
    )


def _open_trade_count_for_symbol(db: Session, symbol: str, timeframe: str) -> int:
    closed_statuses = {"cancelled", "closed", "exited", "stopped", "target_hit", "trailed"}
    return (
        db.query(PaperTrade)
        .filter(PaperTrade.symbol == symbol.upper(), PaperTrade.timeframe == timeframe.lower())
        .filter(PaperTrade.closed_at.is_(None))
        .filter(~PaperTrade.status.in_(closed_statuses))
        .count()
    )


def _has_recent_trade_in_cooldown(db: Session, symbol: str, timeframe: str, cooldown_candles: int) -> bool:
    if cooldown_candles <= 0:
        return False
    recent_rows = (
        db.query(MarketCandle.ts)
        .filter(MarketCandle.symbol == symbol.upper(), MarketCandle.timeframe == timeframe.lower())
        .order_by(MarketCandle.ts.desc())
        .limit(cooldown_candles + 1)
        .all()
    )
    recent_candle_labels = {row[0].isoformat() for row in recent_rows}
    if not recent_candle_labels:
        return False
    rows = (
        db.query(PaperTrade)
        .filter(PaperTrade.symbol == symbol.upper(), PaperTrade.timeframe == timeframe.lower())
        .order_by(PaperTrade.created_at.desc())
        .limit(50)
        .all()
    )
    return any(
        (row.context or {}).get("market_context", {}).get("last_candle_at") in recent_candle_labels
        for row in rows
    )


def run_scheduled_paper_trading(
    db: Session,
    symbols: list[str] | None = None,
    timeframe: str | None = None,
    limit: int | None = None,
    quantity: int | None = None,
) -> dict:
    timeframe = (timeframe or settings.paper_trading_timeframe).lower()
    safe_limit = max(20, min(limit or settings.paper_trading_candle_limit, 500))
    safe_quantity = max(1, quantity or settings.paper_trading_quantity)
    target_symbols = [item.upper() for item in (symbols or configured_paper_symbols())]

    if not settings.enable_paper_trading:
        result = {"enabled": False, "created": 0, "blocked": 0, "skipped": len(target_symbols), "items": []}
        audit(db, "paper.scheduler_run", "Paper scheduler skipped because paper trading is disabled", payload=result)
        return result

    reconciliation = reconcile_open_paper_trades(db, symbols=target_symbols, timeframe=timeframe)
    items = []
    for symbol in target_symbols:
        snapshot = market_snapshot(db, symbol=symbol, timeframe=timeframe, limit=safe_limit)
        item = {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": snapshot["candles"],
            "ready": snapshot["ready"],
            "created": False,
            "blocked": False,
            "skipped": False,
            "reason": snapshot["reason"],
        }

        if not snapshot["ready"]:
            item["skipped"] = True
            items.append(item)
            continue

        session_label = ((snapshot["market_context"].get("session_context") or {}).get("label") or "unknown")
        if (
            is_intraday_timeframe(timeframe)
            and is_nse_index_symbol(symbol)
            and not is_regular_nse_session_now()
            and session_label != "inferred_special_session"
        ):
            item["skipped"] = True
            item["reason"] = "Outside NSE regular session and latest candle is not an inferred special-session candle."
            items.append(item)
            continue

        open_trade_count = _open_trade_count_for_symbol(db, symbol, timeframe)
        max_open_trades = max(1, settings.paper_max_open_trades_per_symbol)
        if open_trade_count >= max_open_trades:
            item["skipped"] = True
            item["reason"] = f"Open paper trade limit reached for symbol/timeframe ({open_trade_count}/{max_open_trades})"
            items.append(item)
            continue

        last_candle_at = snapshot["market_context"].get("last_candle_at")
        if _has_existing_trade_for_candle(db, symbol, timeframe, last_candle_at):
            item["skipped"] = True
            item["reason"] = "Trade already evaluated for latest candle"
            items.append(item)
            continue

        cooldown_candles = max(0, int(paper_exit_config_for_symbol(symbol).get("cooldown_candles") or 0))
        if _has_recent_trade_in_cooldown(db, symbol, timeframe, cooldown_candles):
            item["skipped"] = True
            item["reason"] = f"Paper trade cooldown active ({cooldown_candles} candles)"
            items.append(item)
            continue

        payload = SimpleNamespace(
            symbol=symbol,
            timeframe=timeframe,
            market_context=snapshot["market_context"],
            quantity=safe_quantity,
            allow_when_kill_switch_on=False,
        )
        trade_result = create_paper_trade(db, payload)
        item.update({
            "created": trade_result["created"],
            "blocked": trade_result["blocked"],
            "reason": trade_result.get("reason", "created" if trade_result["created"] else "blocked"),
            "stance": trade_result["setup"]["stance"],
            "side": trade_result["side"],
            "trade": trade_result.get("trade"),
        })
        items.append(item)

    result = {
        "enabled": True,
        "reconciliation": reconciliation,
        "created": sum(1 for item in items if item["created"]),
        "blocked": sum(1 for item in items if item["blocked"]),
        "skipped": sum(1 for item in items if item["skipped"]),
        "items": items,
    }
    audit(db, "paper.scheduler_run", "Scheduled paper trade evaluation completed", payload=result)
    result["evidence_snapshot"] = record_paper_evidence_snapshot(db, trigger="scheduler", symbols=target_symbols)
    return result
