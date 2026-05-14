import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Market Data")


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


symbols = [item["symbol"] for item in (get("/instruments") or [])]
symbol = st.selectbox("Symbol", symbols or ["NIFTY", "BANKNIFTY"])
timeframe = st.selectbox("Timeframe", ["5m", "15m", "1h", "1d"], index=0)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Latest Candles")
    candles = get("/market/candles", {"symbol": symbol, "timeframe": timeframe, "limit": 50}) or []
    if candles:
        st.dataframe(pd.DataFrame(candles), use_container_width=True)
    else:
        st.info("No candles loaded yet.")

with c2:
    st.subheader("Snapshot")
    if st.button("Create Snapshot"):
        snapshot = post("/market/snapshot", {"symbol": symbol, "timeframe": timeframe, "limit": 50})
        if snapshot:
            st.json(snapshot)

st.subheader("Manual Candle Ingestion")
with st.form("manual_candle"):
    ts_value = st.text_input("Timestamp", value=datetime.utcnow().replace(microsecond=0).isoformat())
    open_value = st.number_input("Open", min_value=0.0, step=1.0)
    high_value = st.number_input("High", min_value=0.0, step=1.0)
    low_value = st.number_input("Low", min_value=0.0, step=1.0)
    close_value = st.number_input("Close", min_value=0.0, step=1.0)
    volume_value = st.number_input("Volume", min_value=0.0, step=1.0)
    source = st.text_input("Source", value="manual")
    submitted = st.form_submit_button("Save Candle")

if submitted:
    payload = {
        "symbol": symbol,
        "timeframe": timeframe,
        "ts": ts_value,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume_value,
        "source": source,
    }
    result = post("/market/candles", payload)
    if result:
        st.success("Candle saved.")
        st.json(result)
