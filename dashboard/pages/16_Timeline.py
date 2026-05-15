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
        "Estimate": "Done",
        "Owner": "User + Codex",
        "Status": "Current commits pushed",
    },
    {
        "Phase": "Real market data provider",
        "Target": "2026-05-15",
        "Estimate": "Done",
        "Owner": "Shared",
        "Status": "DhanHQ active for NIFTY and BANKNIFTY",
    },
    {
        "Phase": "Historical NIFTY/BANKNIFTY candles",
        "Target": "2026-05-15",
        "Estimate": "Done",
        "Owner": "Shared",
        "Status": "Dhan provider-backed candles loaded",
    },
    {
        "Phase": "Paper-trade evidence run",
        "Target": "2026-05-15 to 2026-05-24",
        "Estimate": "5 trading sessions minimum",
        "Owner": "System",
        "Status": "Strict LRHR scheduler active; collecting realized exits",
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

provider_candle_counts = readiness.get("provider_candle_counts", {})
total_candle_counts = readiness.get("candle_counts", {})
if provider_candle_counts or total_candle_counts:
    st.subheader("Candle Evidence")
    symbols = sorted(set(provider_candle_counts) | set(total_candle_counts))
    st.dataframe(
        pd.DataFrame([
            {
                "Symbol": symbol,
                "Provider-backed": provider_candle_counts.get(symbol, 0),
                "Total": total_candle_counts.get(symbol, 0),
            }
            for symbol in symbols
        ]),
        use_container_width=True,
        hide_index=True,
    )

paper = readiness.get("paper", [])
if paper:
    st.subheader("Paper Performance")
    st.dataframe(
        pd.DataFrame([
            {
                "Symbol": item.get("symbol"),
                "Closed": item.get("closed_paper_trades"),
                "Minimum": item.get("minimum_review_trades"),
                "Sample Ready": item.get("sample_ready"),
                "Gross Profit": item.get("gross_profit"),
                "Gross Loss": item.get("gross_loss"),
                "Net P&L": item.get("net_realized_pnl"),
                "Profit Factor": item.get("profit_factor_label"),
                "Avg R": item.get("average_r_multiple"),
            }
            for item in paper
        ]),
        use_container_width=True,
        hide_index=True,
    )

non_production = readiness.get("non_production_source_counts", {})
if non_production:
    with st.expander("Non-production candle sources"):
        st.dataframe(
            pd.DataFrame([
                {"Source": source, "Candles": candles}
                for source, candles in sorted(non_production.items())
            ]),
            use_container_width=True,
            hide_index=True,
        )

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
