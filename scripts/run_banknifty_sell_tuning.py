#!/usr/bin/env python3
"""Run replay-only index sell-side tuning sweeps.

This script does not change live or paper-trading settings. It sweeps exit
management parameters over historical candles and writes an evidence report.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_replay_risk_report import _run_replay  # noqa: E402


@dataclass
class ReplayArgs:
    timeframe: str
    limit: int
    min_window: int
    max_trades: int
    cooldown_candles: int
    exit_mode: str
    part_book_r_multiple: float
    part_book_fraction: float
    trail_lookback_candles: int
    output_dir: str


def _side_row(report: dict[str, Any], side: str) -> dict[str, Any]:
    for row in report.get("by_side") or []:
        if row.get("side") == side:
            return row
    return {}


def _score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    pf = float(row.get("profit_factor") or 0)
    drawdown = float(row.get("max_drawdown_points") or 0)
    net_points = float(row.get("net_points") or 0)
    baseline_drawdown = float(baseline.get("max_drawdown_points") or drawdown or 1)
    drawdown_improvement = max(0.0, baseline_drawdown - drawdown)
    return round((pf * 1000) + (drawdown_improvement * 2) + (net_points * 0.05), 3)


def _result_row(args: ReplayArgs, replay: dict[str, Any], baseline_sell: dict[str, Any]) -> dict[str, Any]:
    sell = _side_row(replay, "sell")
    metrics = replay.get("metrics") or {}
    baseline_drawdown = float(baseline_sell.get("max_drawdown_points") or 0)
    sell_drawdown = float(sell.get("max_drawdown_points") or 0)
    return {
        "config": {
            "part_book_r_multiple": args.part_book_r_multiple,
            "part_book_fraction": args.part_book_fraction,
            "trail_lookback_candles": args.trail_lookback_candles,
            "cooldown_candles": args.cooldown_candles,
        },
        "sell": sell,
        "overall": metrics,
        "drawdown_improvement_points": round(baseline_drawdown - sell_drawdown, 2),
        "score": _score(sell, baseline_sell),
    }


def _write_report(output_dir: Path, symbol: str, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{symbol.lower()}_sell_tuning_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BANKNIFTY", help="Index symbol to tune, such as NIFTY or BANKNIFTY.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--min-window", type=int, default=200)
    parser.add_argument("--max-trades", type=int, default=100)
    parser.add_argument("--output-dir", default="data/reports")
    parser.add_argument("--full-grid", action="store_true", help="Run the larger exploratory grid instead of the quick first pass.")
    args = parser.parse_args()
    symbol = args.symbol.strip().upper()

    base = {
        "timeframe": args.timeframe,
        "limit": args.limit,
        "min_window": args.min_window,
        "max_trades": args.max_trades,
        "exit_mode": "author_part_book_trail",
        "output_dir": args.output_dir,
    }
    if args.full_grid:
        sweep_configs = [
            ReplayArgs(**base, cooldown_candles=5, part_book_r_multiple=part_r, part_book_fraction=fraction, trail_lookback_candles=lookback)
            for part_r in [0.75, 1.0, 1.25]
            for fraction in [0.4, 0.5, 0.6]
            for lookback in [2, 3, 4]
        ]
        sweep_configs.extend([
            ReplayArgs(**base, cooldown_candles=8, part_book_r_multiple=1.0, part_book_fraction=0.5, trail_lookback_candles=3),
            ReplayArgs(**base, cooldown_candles=8, part_book_r_multiple=0.75, part_book_fraction=0.5, trail_lookback_candles=3),
            ReplayArgs(**base, cooldown_candles=8, part_book_r_multiple=1.0, part_book_fraction=0.6, trail_lookback_candles=3),
        ])
    else:
        sweep_configs = [
            ReplayArgs(**base, cooldown_candles=5, part_book_r_multiple=1.0, part_book_fraction=0.5, trail_lookback_candles=3),
            ReplayArgs(**base, cooldown_candles=5, part_book_r_multiple=0.75, part_book_fraction=0.5, trail_lookback_candles=3),
            ReplayArgs(**base, cooldown_candles=5, part_book_r_multiple=0.75, part_book_fraction=0.6, trail_lookback_candles=3),
            ReplayArgs(**base, cooldown_candles=5, part_book_r_multiple=1.0, part_book_fraction=0.6, trail_lookback_candles=2),
        ]

    from app.db import SessionLocal

    rows = []
    baseline_sell: dict[str, Any] = {}
    with SessionLocal() as db:
        for index, replay_args in enumerate(sweep_configs, start=1):
            print(
                f"Running {index}/{len(sweep_configs)}: "
                f"part_r={replay_args.part_book_r_multiple}, "
                f"fraction={replay_args.part_book_fraction}, "
                f"trail={replay_args.trail_lookback_candles}, "
                f"cooldown={replay_args.cooldown_candles}",
                file=sys.stderr,
                flush=True,
            )
            replay = _run_replay(db, replay_args, symbol)
            sell = _side_row(replay, "sell")
            if (
                replay_args.part_book_r_multiple == 1.0
                and replay_args.part_book_fraction == 0.5
                and replay_args.trail_lookback_candles == 3
                and replay_args.cooldown_candles == 5
            ):
                baseline_sell = sell
            rows.append({
                "index": index,
                **_result_row(replay_args, replay, baseline_sell or sell),
            })

    baseline_sell = baseline_sell or rows[0]["sell"]
    for row in rows:
        row["drawdown_improvement_points"] = round(
            float(baseline_sell.get("max_drawdown_points") or 0)
            - float((row.get("sell") or {}).get("max_drawdown_points") or 0),
            2,
        )
        row["score"] = _score(row.get("sell") or {}, baseline_sell)

    min_sell_trades = max(20, int((baseline_sell.get("trades") or 0) * 0.8))
    viable = [
        row for row in rows
        if (row.get("sell") or {}).get("trades", 0) >= min_sell_trades
        and float((row.get("sell") or {}).get("net_points") or 0) > 0
        and float((row.get("sell") or {}).get("profit_factor") or 0) >= 1.5
    ]
    ranked = sorted(
        viable,
        key=lambda row: (
            row["score"],
            row["drawdown_improvement_points"],
            float((row.get("sell") or {}).get("profit_factor") or 0),
            float((row.get("sell") or {}).get("net_points") or 0),
        ),
        reverse=True,
    )
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "purpose": f"Replay-only {symbol} sell-side drawdown tuning. No live or paper settings were changed.",
        "mode": "full_grid" if args.full_grid else "quick_first_pass",
        "baseline_sell": baseline_sell,
        "baseline_config": {
            "part_book_r_multiple": 1.0,
            "part_book_fraction": 0.5,
            "trail_lookback_candles": 3,
            "cooldown_candles": 5,
        },
        "selection_criteria": {
            "min_sell_trades": min_sell_trades,
            "min_sell_profit_factor": 1.5,
            "require_positive_sell_net_points": True,
        },
        "search_space": [asdict(item) for item in sweep_configs],
        "top_candidates": ranked[:10],
        "results": sorted(rows, key=lambda row: row["score"], reverse=True),
    }
    output_path = _write_report(ROOT / args.output_dir, symbol, payload)
    print(json.dumps({
        "output_path": str(output_path),
        "baseline_sell": baseline_sell,
        "top_candidates": ranked[:5],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
