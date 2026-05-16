#!/usr/bin/env python3
"""Summarize trend-regime coverage in stored market candles."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Window:
    symbol: str
    timeframe: str
    start: str
    end: str
    candles: int
    return_pct: float
    range_pct: float
    efficiency: float
    avg_atr_pct: float
    regime: str


def _classify(return_pct: float, range_pct: float, efficiency: float, avg_atr_pct: float) -> str:
    if return_pct >= 3.0 and efficiency >= 0.12:
        return "uptrend"
    if return_pct <= -3.0 and efficiency >= 0.12:
        return "downtrend"
    if abs(return_pct) <= 2.0 and (efficiency <= 0.12 or range_pct <= 8.0):
        return "sideways"
    if avg_atr_pct >= 0.45 and abs(return_pct) <= 4.0:
        return "volatile_sideways"
    return "transition"


def _analyze_window(symbol: str, timeframe: str, rows: list) -> Window | None:
    if len(rows) < 20:
        return None
    first = rows[0]
    last = rows[-1]
    if not first.close:
        return None
    closes = [row.close for row in rows]
    highs = [row.high for row in rows]
    lows = [row.low for row in rows]
    return_pct = (last.close - first.close) / first.close * 100
    range_pct = (max(highs) - min(lows)) / last.close * 100 if last.close else 0.0
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
    efficiency = abs(last.close - first.close) / path if path else 0.0
    true_ranges = []
    for previous, current in zip(rows[:-1], rows[1:]):
        true_ranges.append(max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        ))
    avg_atr = mean(true_ranges) if true_ranges else 0.0
    avg_atr_pct = avg_atr / last.close * 100 if last.close else 0.0
    return Window(
        symbol=symbol,
        timeframe=timeframe,
        start=first.ts.isoformat(),
        end=last.ts.isoformat(),
        candles=len(rows),
        return_pct=round(return_pct, 3),
        range_pct=round(range_pct, 3),
        efficiency=round(efficiency, 4),
        avg_atr_pct=round(avg_atr_pct, 4),
        regime=_classify(return_pct, range_pct, efficiency, avg_atr_pct),
    )


def _sample_windows(rows: list, window_candles: int, step_candles: int) -> list[list]:
    samples = []
    cursor = 0
    while cursor + window_candles <= len(rows):
        samples.append(rows[cursor:cursor + window_candles])
        cursor += step_candles
    if rows and (not samples or samples[-1][-1].ts != rows[-1].ts) and len(rows) >= window_candles:
        samples.append(rows[-window_candles:])
    return samples


def _rows(db, market_candle, should_use_candle, symbol: str, timeframe: str) -> list:
    raw_rows = (
        db.query(market_candle)
        .filter_by(symbol=symbol.upper(), timeframe=timeframe.lower())
        .order_by(market_candle.ts.asc())
        .all()
    )
    return [
        row
        for row in raw_rows
        if should_use_candle(row.symbol, row.timeframe, row.ts, row.open, row.high, row.low, row.close, row.volume)
    ]


def _example_payload(window: Window) -> dict:
    return {
        "start": window.start,
        "end": window.end,
        "return_pct": window.return_pct,
        "range_pct": window.range_pct,
        "efficiency": window.efficiency,
        "avg_atr_pct": window.avg_atr_pct,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="NIFTY,BANKNIFTY")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--window-candles", type=int, default=1500)
    parser.add_argument("--step-candles", type=int, default=750)
    args = parser.parse_args()

    from app.db import SessionLocal
    from app.models import MarketCandle
    from app.services.trading_calendar import should_use_candle

    db = SessionLocal()
    try:
        summary = {}
        for symbol in [item.strip().upper() for item in args.symbols.split(",") if item.strip()]:
            rows = _rows(db, MarketCandle, should_use_candle, symbol, args.timeframe)
            windows = [
                analyzed
                for sample in _sample_windows(rows, args.window_candles, args.step_candles)
                if (analyzed := _analyze_window(symbol, args.timeframe, sample))
            ]
            counts = Counter(window.regime for window in windows)
            examples: dict[str, list[dict]] = defaultdict(list)
            for window in windows:
                if len(examples[window.regime]) < 3:
                    examples[window.regime].append(_example_payload(window))
            summary[symbol] = {
                "timeframe": args.timeframe.lower(),
                "candles": len(rows),
                "first_ts": rows[0].ts.isoformat() if rows else None,
                "last_ts": rows[-1].ts.isoformat() if rows else None,
                "window_candles": args.window_candles,
                "step_candles": args.step_candles,
                "regime_counts": dict(sorted(counts.items())),
                "required_regimes_present": {
                    "uptrend": counts["uptrend"] > 0,
                    "downtrend": counts["downtrend"] > 0,
                    "sideways": (counts["sideways"] + counts["volatile_sideways"]) > 0,
                },
                "examples": dict(examples),
            }
        print(json.dumps(summary, indent=2, sort_keys=True))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
