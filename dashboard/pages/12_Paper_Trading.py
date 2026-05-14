import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Paper Trading")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


def post(path, payload):
    try:
        response = requests.post(f"{API_BASE}{path}", json=payload, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


health = get("/health") or {}
st.metric("Kill Switch", str(health.get("kill_switch", "unknown")))

symbols = [item["symbol"] for item in (get("/instruments") or [])]
symbol = st.selectbox("Symbol", symbols or ["NIFTY", "BANKNIFTY"])
timeframe = st.selectbox("Timeframe", ["5m", "15m", "1h", "1d"], index=0)

st.subheader("Create Simulated Trade")
with st.form("paper_trade"):
    last_price = st.number_input("Last Price", min_value=0.0, step=1.0)
    trend = st.selectbox("Trend", ["up", "down", "range"])
    price_action = st.selectbox("Price Action", ["HH_HL", "LH_LL", "sideways"])
    ema_bias = st.selectbox("EMA Bias", ["above_200", "below_200", "mixed"])
    risk_points = st.number_input("Risk Points", min_value=1.0, value=50.0, step=1.0)
    quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
    allow_kill_switch = st.checkbox("Allow while kill switch is on", value=False)
    submitted = st.form_submit_button("Evaluate Paper Trade")

if submitted:
    result = post(
        "/paper/trades",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "quantity": quantity,
            "allow_when_kill_switch_on": allow_kill_switch,
            "market_context": {
                "last_price": last_price,
                "trend": trend,
                "price_action": price_action,
                "ema_bias": ema_bias,
                "risk_points": risk_points,
            },
        },
    )
    if result:
        st.json(result)

st.subheader("Scheduled Evaluation")
scheduler = get("/paper/scheduler") or {}
if scheduler:
    cols = st.columns(4)
    cols[0].metric("Enabled", str(scheduler.get("enabled")))
    cols[1].metric("Symbols", ", ".join(scheduler.get("symbols", [])))
    cols[2].metric("Interval", f"{scheduler.get('interval_seconds')}s")
    cols[3].metric("Candle Limit", scheduler.get("candle_limit"))
    if st.button("Run Scheduled Evaluation Now"):
        result = post(
            "/paper/scheduler/run",
            {
                "symbols": [symbol],
                "timeframe": timeframe,
                "limit": scheduler.get("candle_limit"),
                "quantity": scheduler.get("quantity"),
            },
        )
        if result:
            st.json(result)

st.subheader("Recent Paper Trades")
trades = get("/paper/trades", {"limit": 100}) or []
if trades:
    st.dataframe(pd.DataFrame(trades), use_container_width=True)
else:
    st.info("No paper trades yet.")
