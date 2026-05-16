#!/usr/bin/env python3
"""Run paper replay validation with a larger candle window."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="NIFTY,BANKNIFTY")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--limit", type=int, default=200000)
    parser.add_argument("--max-trades", type=int, default=500)
    parser.add_argument("--expected-min-profit-factor", type=float, default=1.5)
    args = parser.parse_args()

    from app.db import SessionLocal
    from app.schemas import PaperReplayValidationRequest
    from app.services import market_data
    from app.services.paper_replay_validation import create_paper_replay_validation

    market_data.MAX_CANDLE_QUERY_LIMIT = max(market_data.MAX_CANDLE_QUERY_LIMIT, args.limit)
    notes = (
        "Expanded Dhan replay after multi-year intraday backfill and regime coverage check. "
        "NIFTY includes 2019/COVID intraday; BANKNIFTY 5m starts where Dhan returns "
        "spot-index intraday, with 2019+ daily regime coverage separately verified."
    )
    base = {
        "timeframe": args.timeframe,
        "limit": args.limit,
        "min_window": 200,
        "quantity": 1,
        "max_trades": args.max_trades,
        "cooldown_candles": 5,
        "exit_mode": "author_part_book_trail",
        "part_book_r_multiple": 1.0,
        "part_book_fraction": 0.5,
        "trail_lookback_candles": 3,
        "include_trades": False,
        "expected_min_realized_trades": 20,
        "expected_min_net_pnl": 0.0,
        "expected_min_profit_factor": args.expected_min_profit_factor,
        "notes": notes,
    }
    with SessionLocal() as db:
        for symbol in [item.strip().upper() for item in args.symbols.split(",") if item.strip()]:
            payload = PaperReplayValidationRequest(
                **dict(base, symbol=symbol, name=f"dhan-expanded-regime-replay-{symbol}")
            )
            result = create_paper_replay_validation(db, payload)
            delivered = result.get("delivered_json") or {}
            metrics = delivered.get("metrics") or {}
            print(json.dumps({
                "symbol": symbol,
                "case_code": result.get("case_code"),
                "status": result.get("status"),
                "score": result.get("score"),
                "source_candles": delivered.get("source_candles"),
                "realized_trades": metrics.get("realized_trades"),
                "net_realized_pnl": metrics.get("net_realized_pnl"),
                "profit_factor": metrics.get("profit_factor"),
                "profit_factor_label": metrics.get("profit_factor_label"),
                "win_rate": metrics.get("win_rate"),
                "average_r_multiple": metrics.get("average_r_multiple"),
            }), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
