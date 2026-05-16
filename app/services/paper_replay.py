from sqlalchemy.orm import Session

from app.services.market_data import candle_market_context, latest_candles
from app.services.paper_trading import build_paper_trade_plan


def _exit_from_future(plan: dict, future_candles: list) -> dict | None:
    side = plan["side"]
    entry = float(plan["entry_price"])
    stop = plan["stop_loss"]
    target = plan["target"]
    quantity = int(plan["quantity"])
    if side not in {"buy", "sell"} or stop is None or target is None:
        return None

    for offset, candle in enumerate(future_candles, start=1):
        if side == "buy":
            stop_hit = candle.low <= stop
            target_hit = candle.high >= target
            if stop_hit:
                pnl = (stop - entry) * quantity
                return {"status": "stopped", "exit_price": stop, "exit_at": candle.ts, "bars_held": offset, "realized_pnl": round(pnl, 2)}
            if target_hit:
                pnl = (target - entry) * quantity
                return {"status": "target_hit", "exit_price": target, "exit_at": candle.ts, "bars_held": offset, "realized_pnl": round(pnl, 2)}
        if side == "sell":
            stop_hit = candle.high >= stop
            target_hit = candle.low <= target
            if stop_hit:
                pnl = (entry - stop) * quantity
                return {"status": "stopped", "exit_price": stop, "exit_at": candle.ts, "bars_held": offset, "realized_pnl": round(pnl, 2)}
            if target_hit:
                pnl = (entry - target) * quantity
                return {"status": "target_hit", "exit_price": target, "exit_at": candle.ts, "bars_held": offset, "realized_pnl": round(pnl, 2)}
    return None


def _author_part_book_trail_exit(
    plan: dict,
    future_candles: list,
    part_book_r_multiple: float,
    part_book_fraction: float,
    trail_lookback_candles: int,
) -> dict | None:
    side = plan["side"]
    entry = float(plan["entry_price"])
    stop = plan["stop_loss"]
    quantity = int(plan["quantity"])
    if side not in {"buy", "sell"} or stop is None:
        return None

    risk = abs(entry - float(stop))
    if risk <= 0:
        return None

    fraction = min(max(part_book_fraction, 0.1), 0.9)
    remaining_fraction = 1 - fraction
    part_r = max(part_book_r_multiple, 0.25)
    lookback = max(1, trail_lookback_candles)
    part_target = entry + (risk * part_r) if side == "buy" else entry - (risk * part_r)
    trailing_stop = float(stop)
    partial_realized = 0.0
    partial_exit = None
    completed_candles = []

    for offset, candle in enumerate(future_candles, start=1):
        if side == "buy":
            if candle.low <= trailing_stop:
                pnl = ((trailing_stop - entry) * quantity * remaining_fraction) + partial_realized
                return {
                    "status": "trailed" if partial_exit else "stopped",
                    "exit_price": trailing_stop,
                    "exit_at": candle.ts,
                    "bars_held": offset,
                    "realized_pnl": round(pnl, 2),
                    "partial_exit": partial_exit,
                    "trailing_stop": trailing_stop,
                }
            if not partial_exit and candle.high >= part_target:
                partial_realized = (part_target - entry) * quantity * fraction
                partial_exit = {
                    "price": part_target,
                    "at": candle.ts.isoformat(),
                    "fraction": fraction,
                    "r_multiple": part_r,
                }
                trailing_stop = max(trailing_stop, entry)
        else:
            if candle.high >= trailing_stop:
                pnl = ((entry - trailing_stop) * quantity * remaining_fraction) + partial_realized
                return {
                    "status": "trailed" if partial_exit else "stopped",
                    "exit_price": trailing_stop,
                    "exit_at": candle.ts,
                    "bars_held": offset,
                    "realized_pnl": round(pnl, 2),
                    "partial_exit": partial_exit,
                    "trailing_stop": trailing_stop,
                }
            if not partial_exit and candle.low <= part_target:
                partial_realized = (entry - part_target) * quantity * fraction
                partial_exit = {
                    "price": part_target,
                    "at": candle.ts.isoformat(),
                    "fraction": fraction,
                    "r_multiple": part_r,
                }
                trailing_stop = min(trailing_stop, entry)

        if partial_exit:
            completed_candles.append(candle)
            window = completed_candles[-lookback:]
            if side == "buy":
                trailing_stop = max(trailing_stop, min(item.low for item in window))
            else:
                trailing_stop = min(trailing_stop, max(item.high for item in window))

    if partial_exit:
        return {
            "status": "open_at_end",
            "exit_price": None,
            "exit_at": None,
            "bars_held": len(future_candles),
            "realized_pnl": round(partial_realized, 2),
            "partial_exit": partial_exit,
            "trailing_stop": trailing_stop,
        }
    return None


def _r_multiple(plan: dict, realized_pnl: float) -> float | None:
    risk = abs(float(plan["entry_price"]) - float(plan["stop_loss"])) * int(plan["quantity"])
    if risk <= 0:
        return None
    return round(realized_pnl / risk, 3)


def _profit_factor(gross_profit: float, gross_loss: float, realized_count: int) -> tuple[float | None, str]:
    if realized_count == 0:
        return None, "N/A"
    if gross_loss == 0 and gross_profit > 0:
        return None, "Infinite (no realized losses)"
    if gross_loss > 0:
        value = round(gross_profit / gross_loss, 3)
        return value, str(value)
    return 0.0, "0.0"


def evaluate_historical_paper_replay(db: Session, payload) -> dict:
    candles = list(reversed(latest_candles(db, payload.symbol, payload.timeframe, payload.limit)))
    min_window = max(20, payload.min_window)
    max_trades = max(1, payload.max_trades)
    cooldown = max(0, payload.cooldown_candles)
    quantity = max(1, payload.quantity)
    exit_mode = payload.exit_mode
    part_book_r_multiple = payload.part_book_r_multiple
    part_book_fraction = payload.part_book_fraction
    trail_lookback_candles = payload.trail_lookback_candles
    if len(candles) <= min_window:
        return {
            "name": payload.name,
            "symbol": payload.symbol.upper(),
            "timeframe": payload.timeframe.lower(),
            "ready": False,
            "reason": f"Need more than {min_window} candles; found {len(candles)}",
            "source_candles": len(candles),
            "trades": [],
            "metrics": {},
        }

    class ReplayPayload:
        def __init__(
            self,
            symbol: str,
            timeframe: str,
            market_context: dict,
            quantity: int,
        ):
            self.symbol = symbol
            self.timeframe = timeframe
            self.market_context = market_context
            self.quantity = quantity
            self.allow_when_kill_switch_on = False

    trades = []
    blocked_counts: dict[str, int] = {}
    index = min_window
    while index < len(candles) - 1 and len(trades) < max_trades:
        window = candles[index - min_window:index]
        context = candle_market_context(payload.symbol, payload.timeframe, window)
        plan = build_paper_trade_plan(db, ReplayPayload(payload.symbol, payload.timeframe, context, quantity))
        if plan["side"] == "none":
            stance = plan["setup"]["stance"]
            blocked_counts[stance] = blocked_counts.get(stance, 0) + 1
            index += 1
            continue

        future_candles = candles[index:]
        if exit_mode == "author_part_book_trail":
            exit_result = _author_part_book_trail_exit(
                plan,
                future_candles,
                part_book_r_multiple,
                part_book_fraction,
                trail_lookback_candles,
            )
        else:
            exit_result = _exit_from_future(plan, future_candles)
        entry_at = window[-1].ts
        trade = {
            "symbol": plan["market_context"]["symbol"],
            "timeframe": payload.timeframe.lower(),
            "entry_at": entry_at.isoformat(),
            "side": plan["side"],
            "stance": plan["setup"]["stance"],
            "entry_price": plan["entry_price"],
            "stop_loss": plan["stop_loss"],
            "target": plan["target"],
            "matched_rules": plan["setup"].get("matched_rules", []),
            "failed_rules": plan["setup"].get("failed_rules", []),
        }
        if exit_result:
            realized_pnl = exit_result["realized_pnl"]
            trade.update({
                "status": exit_result["status"],
                "exit_at": exit_result["exit_at"].isoformat(),
                "exit_price": exit_result["exit_price"],
                "bars_held": exit_result["bars_held"],
                "realized_pnl": realized_pnl,
                "r_multiple": _r_multiple(plan, realized_pnl),
                "partial_exit": exit_result.get("partial_exit"),
                "trailing_stop": exit_result.get("trailing_stop"),
            })
            index += exit_result["bars_held"] + cooldown
        else:
            trade.update({
                "status": "open_at_end",
                "exit_at": None,
                "exit_price": None,
                "bars_held": len(future_candles),
                "realized_pnl": None,
                "r_multiple": None,
            })
            index += 1 + cooldown
        trades.append(trade)

    realized = [trade for trade in trades if trade.get("realized_pnl") is not None]
    pnl_values = [float(trade["realized_pnl"]) for trade in realized]
    gross_profit = round(sum(value for value in pnl_values if value > 0), 2)
    gross_loss = round(abs(sum(value for value in pnl_values if value < 0)), 2)
    profit_factor, profit_factor_label = _profit_factor(gross_profit, gross_loss, len(realized))
    wins = [value for value in pnl_values if value > 0]
    r_values = [trade["r_multiple"] for trade in realized if trade.get("r_multiple") is not None]

    return {
        "name": payload.name,
        "symbol": payload.symbol.upper(),
        "timeframe": payload.timeframe.lower(),
        "ready": True,
        "source_candles": len(candles),
        "min_window": min_window,
        "max_trades": max_trades,
        "cooldown_candles": cooldown,
        "exit_mode": exit_mode,
        "part_book_r_multiple": part_book_r_multiple,
        "part_book_fraction": part_book_fraction,
        "trail_lookback_candles": trail_lookback_candles,
        "blocked_counts": blocked_counts,
        "metrics": {
            "trades": len(trades),
            "realized_trades": len(realized),
            "open_at_end": sum(1 for trade in trades if trade["status"] == "open_at_end"),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_realized_pnl": round(sum(pnl_values), 2),
            "profit_factor": profit_factor,
            "profit_factor_label": profit_factor_label,
            "win_rate": round(len(wins) / len(realized), 4) if realized else None,
            "average_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
        },
        "trades": trades[:100] if payload.include_trades else [],
    }
