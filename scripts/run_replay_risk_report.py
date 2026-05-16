#!/usr/bin/env python3
"""Generate replay risk and consistency reports from stored candles."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _profit_factor(values: list[float]) -> tuple[float | None, str]:
    gross_profit = round(sum(value for value in values if value > 0), 2)
    gross_loss = round(abs(sum(value for value in values if value < 0)), 2)
    if not values:
        return None, "N/A"
    if gross_loss == 0 and gross_profit > 0:
        return None, "Infinite (no realized losses)"
    if gross_loss > 0:
        value = round(gross_profit / gross_loss, 3)
        return value, str(value)
    return 0.0, "0.0"


def _max_drawdown(values: list[float]) -> dict:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    max_dd_trade = 0
    curve = []
    for index, value in enumerate(values, start=1):
        equity += value
        peak = max(peak, equity)
        drawdown = peak - equity
        if drawdown > max_dd:
            max_dd = drawdown
            max_dd_trade = index
        curve.append(round(equity, 2))
    return {
        "max_drawdown_points": round(max_dd, 2),
        "max_drawdown_trade": max_dd_trade,
        "final_equity_points": round(equity, 2),
        "equity_curve_tail": curve[-10:],
    }


def _streaks(values: list[float]) -> dict:
    losing = 0
    winning = 0
    max_losing = 0
    max_winning = 0
    for value in values:
        if value < 0:
            losing += 1
            winning = 0
        elif value > 0:
            winning += 1
            losing = 0
        else:
            losing = 0
            winning = 0
        max_losing = max(max_losing, losing)
        max_winning = max(max_winning, winning)
    return {"max_losing_streak": max_losing, "max_winning_streak": max_winning}


def _group_summary(trades: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        groups[str(trade.get(key) or "unknown")].append(trade)
    rows = []
    for group_key, items in sorted(groups.items()):
        pnl_values = [float(item.get("realized_pnl") or 0) for item in items]
        wins = [value for value in pnl_values if value > 0]
        pf, pf_label = _profit_factor(pnl_values)
        rows.append({
            key: group_key,
            "trades": len(items),
            "net_points": round(sum(pnl_values), 2),
            "profit_factor": pf,
            "profit_factor_label": pf_label,
            "win_rate": round(len(wins) / len(items), 4) if items else None,
            **_max_drawdown(pnl_values),
            **_streaks(pnl_values),
        })
    return rows


def _monthly_summary(trades: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for trade in trades:
        exit_at = trade.get("exit_at") or trade.get("entry_at")
        month = str(exit_at)[:7] if exit_at else "unknown"
        groups[month].append(trade)
    rows = []
    for month, items in sorted(groups.items()):
        pnl_values = [float(item.get("realized_pnl") or 0) for item in items]
        wins = [value for value in pnl_values if value > 0]
        pf, pf_label = _profit_factor(pnl_values)
        rows.append({
            "month": month,
            "trades": len(items),
            "net_points": round(sum(pnl_values), 2),
            "profit_factor": pf,
            "profit_factor_label": pf_label,
            "win_rate": round(len(wins) / len(items), 4) if items else None,
            **_max_drawdown(pnl_values),
            **_streaks(pnl_values),
        })
    return rows


def _trade_regime(context: dict) -> str:
    structure = str(context.get("market_structure") or "unknown").lower()
    bias = str(context.get("higher_timeframe_bias") or "unknown").lower()
    if structure in {"hh_hl", "lh_ll"} and bias in {"bullish", "bearish"}:
        return "trend_aligned"
    if structure == "sideways" or bias in {"mixed", "unknown"}:
        return "sideways_or_mixed"
    return "transition"


def _run_replay(db, args, symbol: str) -> dict:
    from app.services import market_data
    from app.services.market_data import apply_higher_timeframe_context, candle_market_context, latest_candles
    from app.services.paper_replay import _author_part_book_trail_exit, _exit_from_future, _r_multiple
    from app.services.paper_trading import build_paper_trade_plan

    market_data.MAX_CANDLE_QUERY_LIMIT = max(market_data.MAX_CANDLE_QUERY_LIMIT, args.limit)
    candles = list(reversed(latest_candles(db, symbol, args.timeframe, args.limit)))
    min_window = max(20, args.min_window)
    max_trades = max(1, args.max_trades)
    cooldown = max(0, args.cooldown_candles)

    class ReplayPayload:
        def __init__(self, market_context: dict):
            self.symbol = symbol
            self.timeframe = args.timeframe
            self.market_context = market_context
            self.quantity = 1
            self.allow_when_kill_switch_on = False

    trades = []
    blocked_counts: Counter[str] = Counter()
    index = min_window
    while index < len(candles) - 1 and len(trades) < max_trades:
        window = candles[index - min_window:index]
        entry_at = window[-1].ts
        context = apply_higher_timeframe_context(
            db,
            symbol,
            args.timeframe,
            candle_market_context(symbol, args.timeframe, window),
            anchor_ts=entry_at,
        )
        plan = build_paper_trade_plan(db, ReplayPayload(context))
        if plan["side"] == "none":
            blocked_counts[plan["setup"]["stance"]] += 1
            index += 1
            continue

        future_candles = candles[index:]
        if args.exit_mode == "author_part_book_trail":
            exit_result = _author_part_book_trail_exit(
                plan,
                future_candles,
                args.part_book_r_multiple,
                args.part_book_fraction,
                args.trail_lookback_candles,
            )
        else:
            exit_result = _exit_from_future(plan, future_candles)

        trade = {
            "symbol": symbol,
            "timeframe": args.timeframe,
            "entry_at": entry_at.isoformat(),
            "side": plan["side"],
            "stance": plan["setup"]["stance"],
            "entry_price": plan["entry_price"],
            "stop_loss": plan["stop_loss"],
            "target": plan["target"],
            "market_structure": context.get("market_structure"),
            "higher_timeframe_bias": context.get("higher_timeframe_bias"),
            "higher_timeframe_agreement": context.get("higher_timeframe_agreement"),
            "regime": _trade_regime(context),
        }
        if exit_result:
            realized_pnl = float(exit_result["realized_pnl"])
            trade.update({
                "status": exit_result["status"],
                "exit_at": exit_result["exit_at"].isoformat() if exit_result.get("exit_at") else None,
                "exit_price": exit_result.get("exit_price"),
                "bars_held": exit_result["bars_held"],
                "realized_pnl": realized_pnl,
                "r_multiple": _r_multiple(plan, realized_pnl),
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
    wins = [value for value in pnl_values if value > 0]
    pf, pf_label = _profit_factor(pnl_values)
    return {
        "symbol": symbol,
        "timeframe": args.timeframe,
        "source_candles": len(candles),
        "blocked_counts": dict(blocked_counts),
        "metrics": {
            "trades": len(trades),
            "realized_trades": len(realized),
            "open_at_end": sum(1 for trade in trades if trade.get("status") == "open_at_end"),
            "net_points": round(sum(pnl_values), 2),
            "gross_profit": round(sum(value for value in pnl_values if value > 0), 2),
            "gross_loss": round(abs(sum(value for value in pnl_values if value < 0)), 2),
            "profit_factor": pf,
            "profit_factor_label": pf_label,
            "win_rate": round(len(wins) / len(realized), 4) if realized else None,
            **_max_drawdown(pnl_values),
            **_streaks(pnl_values),
        },
        "monthly": _monthly_summary(realized),
        "by_side": _group_summary(realized, "side"),
        "by_regime": _group_summary(realized, "regime"),
        "by_structure": _group_summary(realized, "market_structure"),
        "trades": realized,
    }


def _write_outputs(output_dir: Path, report: dict) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"replay_risk_report_{stamp}.json"
    summary_payload = {
        **report,
        "symbols": [
            {key: value for key, value in item.items() if key != "trades"}
            for item in report["symbols"]
        ],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2, sort_keys=True), encoding="utf-8")

    trade_path = output_dir / f"replay_risk_trades_{stamp}.csv"
    trades = [trade for item in report["symbols"] for trade in item.get("trades", [])]
    if trades:
        fieldnames = sorted({key for trade in trades for key in trade})
        with trade_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(trades)
    return {"summary_path": str(summary_path), "trades_path": str(trade_path), "trade_rows": len(trades)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="NIFTY,BANKNIFTY")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--min-window", type=int, default=200)
    parser.add_argument("--max-trades", type=int, default=500)
    parser.add_argument("--cooldown-candles", type=int, default=5)
    parser.add_argument("--exit-mode", default="author_part_book_trail")
    parser.add_argument("--part-book-r-multiple", type=float, default=1.0)
    parser.add_argument("--part-book-fraction", type=float, default=0.5)
    parser.add_argument("--trail-lookback-candles", type=int, default=3)
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    from app.db import SessionLocal

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "config": vars(args),
        "symbols": [],
    }
    with SessionLocal() as db:
        for symbol in [item.strip().upper() for item in args.symbols.split(",") if item.strip()]:
            report["symbols"].append(_run_replay(db, args, symbol))

    outputs = _write_outputs(ROOT / args.output_dir, report)
    compact = {
        "generated_at": report["generated_at"],
        "outputs": outputs,
        "symbols": [
            {
                "symbol": item["symbol"],
                "source_candles": item["source_candles"],
                "metrics": item["metrics"],
                "by_side": item["by_side"],
                "by_regime": item["by_regime"],
            }
            for item in report["symbols"]
        ],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
