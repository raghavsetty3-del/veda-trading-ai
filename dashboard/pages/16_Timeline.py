import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Timeline")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


health = get("/health") or {}
readiness = get("/readiness") or {}
system_state = get("/system/state") or {}
validations = get("/validation") or []
recent_audit = get("/audit", {"limit": 20}) or []

cols = st.columns(4)
cols[0].metric("API", health.get("status", "unknown"))
cols[1].metric("Kill Switch", str(health.get("kill_switch", "unknown")))
cols[2].metric("Validation Cases", len(validations))
restore_ok = any(item.get("event_type") == "ops.restore_drill" and item.get("severity") == "INFO" for item in recent_audit)
cols[3].metric("Live Review", "ready" if readiness.get("ready_for_live_review") else "not ready")

timeline = [
    {
        "Phase": "GitHub sync",
        "Target": "2026-05-15",
        "Estimate": "10 min",
        "Owner": "User",
        "Status": "Blocked by SSH passphrase in laptop shell",
    },
    {
        "Phase": "Real market data provider",
        "Target": "2026-05-15 to 2026-05-16",
        "Estimate": "0.5-1 day after URL/API credentials",
        "Owner": "Shared",
        "Status": "Waiting for provider details",
    },
    {
        "Phase": "Historical NIFTY/BANKNIFTY candles",
        "Target": "2026-05-16 to 2026-05-17",
        "Estimate": "0.5-1 day after files/source",
        "Owner": "Shared",
        "Status": "Waiting for OHLC data source",
    },
    {
        "Phase": "Paper-trade evidence run",
        "Target": "2026-05-18 to 2026-05-24",
        "Estimate": "5 trading sessions minimum",
        "Owner": "System",
        "Status": "Needs live/provider candles",
    },
    {
        "Phase": "Rule tuning from evidence",
        "Target": "2026-05-25 to 2026-05-29",
        "Estimate": "3-5 days",
        "Owner": "Codex + user review",
        "Status": "Depends on paper evidence",
    },
    {
        "Phase": "External alerts",
        "Target": "2026-05-15",
        "Estimate": "30-60 min after webhook URL",
        "Owner": "Shared",
        "Status": "Hook built, URL needed",
    },
    {
        "Phase": "Telegram/blog production ingestion",
        "Target": "2026-05-16 to 2026-05-17",
        "Estimate": "0.5-1 day after credentials",
        "Owner": "Shared",
        "Status": "Waiting for Telegram/RSS details",
    },
    {
        "Phase": "OpenAI extraction enrichment",
        "Target": "2026-05-16",
        "Estimate": "30-60 min after API key",
        "Owner": "Shared",
        "Status": "Optional, disabled until configured",
    },
    {
        "Phase": "Live-readiness review",
        "Target": "2026-06-01 or later",
        "Estimate": "1 review session after evidence gates pass",
        "Owner": "User",
        "Status": "Not ready yet",
    },
]

st.dataframe(pd.DataFrame(timeline), use_container_width=True, hide_index=True)

st.subheader("Live Readiness Gates")
gates = [
    {"Gate": item.get("gate"), "Ready": item.get("ready"), "Detail": item.get("detail")}
    for item in readiness.get("gates", [])
]
st.dataframe(pd.DataFrame(gates), use_container_width=True, hide_index=True)

st.subheader("Missing Inputs")
missing_inputs = readiness.get("missing_inputs", [])
if missing_inputs:
    st.dataframe(pd.DataFrame({"Missing": missing_inputs}), use_container_width=True, hide_index=True)
else:
    st.success("No missing external inputs reported.")

st.subheader("Recent Evidence")
if validations:
    rows = [
        {
            "Case": item.get("case_code"),
            "Status": item.get("status"),
            "Score": item.get("score"),
            "Created": item.get("created_at"),
        }
        for item in validations[:10]
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No validation cases found.")

with st.expander("System State"):
    st.json(system_state)

with st.expander("Readiness JSON"):
    st.json(readiness)
