import json
import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Backtest Replay")


def post(path, payload):
    try:
        response = requests.post(f"{API_BASE}{path}", json=payload, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


default_steps = [
    {
        "label": "bullish-lrhr",
        "market_context": {
            "market_structure": "HH_HL",
            "price_above_ema200": True,
            "retracement_pct": 50.0,
            "distance_from_ema_pct": 0.7,
            "higher_timeframe_bias": "bullish",
            "at_channel_or_envelope_extreme": False,
            "core_tools_aligned": True,
            "emotional_state": "calm",
            "adx": 24,
        },
    },
    {
        "label": "extended-wait",
        "market_context": {
            "market_structure": "HH_HL",
            "price_above_ema200": True,
            "retracement_pct": 38.2,
            "distance_from_ema_pct": 2.1,
            "higher_timeframe_bias": "bullish",
            "at_channel_or_envelope_extreme": False,
            "core_tools_aligned": True,
            "emotional_state": "calm",
            "adx": 25,
        },
    },
]

symbol = st.selectbox("Symbol", ["NIFTY", "BANKNIFTY"])
timeframe = st.selectbox("Timeframe", ["5m", "15m", "1h", "1d"], index=0)
raw_steps = st.text_area("Replay Steps JSON", value=json.dumps(default_steps, indent=2), height=360)

if st.button("Run Replay"):
    try:
        steps = json.loads(raw_steps)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
        steps = None
    if steps:
        result = post(
            "/backtests/evaluate",
            {"name": "dashboard-replay", "symbol": symbol, "timeframe": timeframe, "steps": steps},
        )
        if result:
            st.json({"counts": result["counts"], "steps": result["steps"]})
            rows = [
                {
                    "index": item["index"],
                    "label": item["label"],
                    "stance": item["setup"]["stance"],
                    "long_score": item["setup"]["long_score"],
                    "short_score": item["setup"]["short_score"],
                    "risk_flags": len(item["setup"]["risk_flags"]),
                    "htf_bias": item["setup"]["market_context"].get("higher_timeframe_bias"),
                    "htf_source": item["setup"]["market_context"].get("higher_timeframe_bias_source"),
                }
                for item in result["results"]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

st.subheader("Replay Stored Candles")
limit = st.number_input("Candle Limit", min_value=20, max_value=500, value=200, step=10)
min_window = st.number_input("Minimum Window", min_value=2, max_value=200, value=20, step=1)
rule_code = st.text_input("Validation Rule Code", value="")
expected_min_matches = st.number_input("Expected Min Rule Matches", min_value=0, max_value=500, value=1, step=1)
if st.button("Run Stored Candle Replay"):
    result = post(
        "/backtests/candles",
        {
            "name": "stored-candle-replay",
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "min_window": min_window,
        },
    )
    if result:
        st.json({"ready": result["ready"], "counts": result["counts"], "steps": result["steps"], "reason": result.get("reason")})
        if result["results"]:
            rows = [
                {
                    "index": item["index"],
                    "label": item["label"],
                    "stance": item["setup"]["stance"],
                    "long_score": item["setup"]["long_score"],
                    "short_score": item["setup"]["short_score"],
                    "risk_flags": len(item["setup"]["risk_flags"]),
                }
                for item in result["results"]
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

if st.button("Save Stored Candle Replay as Validation"):
    payload = {
        "name": "stored-candle-validation",
        "symbol": symbol,
        "timeframe": timeframe,
        "limit": limit,
        "min_window": min_window,
        "rule_code": rule_code or None,
        "expected_min_matches": expected_min_matches,
        "notes": "Saved from Backtest Replay dashboard.",
    }
    result = post("/validation/from-candle-replay", payload)
    if result:
        st.json(result)

st.subheader("Historical Paper Replay")
paper_limit = st.number_input("Paper Replay Candle Limit", min_value=250, max_value=10000, value=1500, step=250)
paper_min_window = st.number_input("Paper Replay Minimum Window", min_value=20, max_value=500, value=200, step=10)
paper_max_trades = st.number_input("Paper Replay Max Trades", min_value=1, max_value=500, value=100, step=10)
paper_cooldown = st.number_input("Paper Replay Cooldown Candles", min_value=0, max_value=50, value=5, step=1)
paper_include_trades = st.checkbox("Include Trade Rows", value=False)
if st.button("Run Historical Paper Replay"):
    result = post(
        "/backtests/paper-replay",
        {
            "name": "dashboard-historical-paper-replay",
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": int(paper_limit),
            "min_window": int(paper_min_window),
            "max_trades": int(paper_max_trades),
            "cooldown_candles": int(paper_cooldown),
            "exit_mode": "author_part_book_trail",
            "part_book_r_multiple": 1.0,
            "part_book_fraction": 0.5,
            "trail_lookback_candles": 3,
            "include_trades": paper_include_trades,
        },
    )
    if result:
        metrics = result.get("metrics", {})
        cols = st.columns(5)
        cols[0].metric("Trades", metrics.get("trades"))
        cols[1].metric("Realized", metrics.get("realized_trades"))
        cols[2].metric("Net P&L", metrics.get("net_realized_pnl"))
        cols[3].metric("Profit Factor", metrics.get("profit_factor_label"))
        cols[4].metric("Avg R", metrics.get("average_r_multiple"))
        st.json({
            "ready": result.get("ready"),
            "source_candles": result.get("source_candles"),
            "blocked_counts": result.get("blocked_counts"),
            "metrics": metrics,
        })
        if result.get("trades"):
            st.dataframe(pd.DataFrame(result["trades"]), use_container_width=True)
