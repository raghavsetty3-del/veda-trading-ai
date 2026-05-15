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


def post(path, payload=None):
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

st.subheader("Provider Ingestion")
provider_status = get("/market/provider/status") or {}
if provider_status:
    cols = st.columns(4)
    cols[0].metric("Configured", str(provider_status.get("configured")))
    cols[1].metric("Sources", provider_status.get("source_count", 0))
    cols[2].metric("Interval", f"{provider_status.get('interval_seconds')}s")
    cols[3].metric("Limit", provider_status.get("limit"))
    with st.expander("Configured sources"):
        st.json(provider_status.get("sources", []))
    with st.expander("Angel One SmartAPI"):
        st.json(provider_status.get("angelone", {}))
    if st.button("Run Configured Provider Ingestion"):
        result = post("/market/provider/ingest-configured")
        if result:
            st.json(result)

with st.form("provider_ingest"):
    source_url = st.text_input("Provider CSV URL or path")
    source_name = st.text_input("Source Name", value=f"provider:{symbol}:{timeframe}")
    max_rows = st.number_input("Max Rows", min_value=1, max_value=5000, value=5000, step=100)
    provider_submitted = st.form_submit_button("Ingest Provider Source")

if provider_submitted:
    result = post(
        "/market/provider/ingest",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "source_url": source_url,
            "source_name": source_name,
            "max_rows": int(max_rows),
        },
    )
    if result:
        st.json(result)

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

st.subheader("CSV Candle Import")
csv_source = st.text_input(
    "CSV Source",
    value=f"manual-csv-upload:{symbol}:{timeframe}",
    help="Use a provider:... label for real provider data. Manual, smoke, test, demo, and sample labels are excluded from live readiness.",
)
uploaded = st.file_uploader("CSV file", type=["csv"])
if uploaded is not None:
    df = pd.read_csv(uploaded)
    st.dataframe(df.head(20), use_container_width=True)
    required = {"ts", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        st.error(f"Missing columns: {', '.join(sorted(missing))}")
    elif st.button("Import CSV Candles"):
        rows = []
        for _, row in df.iterrows():
            source_value = row.get("source", csv_source)
            if pd.isna(source_value):
                source_value = csv_source
            rows.append({
                "symbol": str(row.get("symbol", symbol)).upper(),
                "timeframe": str(row.get("timeframe", timeframe)).lower(),
                "ts": pd.to_datetime(row["ts"]).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": None if pd.isna(row.get("volume")) else float(row.get("volume", 0)),
                "source": str(source_value),
            })
        result = post("/market/candles/bulk", {"candles": rows})
        if result:
            st.success("CSV candles imported.")
            st.json(result)
