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
        "Phase": "Historical paper replay evidence",
        "Target": "2026-05-16",
        "Estimate": "Done",
        "Owner": "Codex",
        "Status": "Timestamp-correct replay validations saved",
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
        "Estimate": "Done",
        "Owner": "Shared",
        "Status": "Configured and active for optional enrichment",
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
required_gates = readiness.get("required_gates") or [
    item for item in readiness.get("gates", []) if item.get("required", True)
]
gates = [
    {"Gate": item.get("gate"), "Ready": item.get("ready"), "Detail": item.get("detail")}
    for item in required_gates
]
st.dataframe(pd.DataFrame(gates), use_container_width=True, hide_index=True)

advisory_gates = readiness.get("advisory_gates") or [
    item for item in readiness.get("gates", []) if item.get("required") is False
]
if advisory_gates:
    st.subheader("Optional Advisories")
    st.dataframe(
        pd.DataFrame([
            {"Advisory": item.get("gate"), "Ready": item.get("ready"), "Detail": item.get("detail")}
            for item in advisory_gates
        ]),
        use_container_width=True,
        hide_index=True,
    )

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

historical_replay = readiness.get("historical_paper_replay") or {}
replay_symbols = sorted(set(historical_replay.get("required_symbols") or []))
if replay_symbols:
    st.subheader("Historical Paper Replay Evidence")
    latest_by_symbol = historical_replay.get("latest_by_symbol") or {}
    passing_by_symbol = historical_replay.get("passing_by_symbol") or {}
    st.dataframe(
        pd.DataFrame([
            {
                "Symbol": symbol,
                "Latest Case": (latest_by_symbol.get(symbol) or {}).get("case_code"),
                "Latest Status": (latest_by_symbol.get(symbol) or {}).get("status"),
                "Passing Case": (passing_by_symbol.get(symbol) or {}).get("case_code"),
                "Realized": (passing_by_symbol.get(symbol) or {}).get("realized_trades"),
                "Net P&L": (passing_by_symbol.get(symbol) or {}).get("net_realized_pnl"),
                "Profit Factor": (passing_by_symbol.get(symbol) or {}).get("profit_factor_label")
                or (passing_by_symbol.get(symbol) or {}).get("profit_factor"),
                "Avg R": (passing_by_symbol.get(symbol) or {}).get("average_r_multiple"),
            }
            for symbol in replay_symbols
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
                "Open": item.get("open_paper_trades"),
                "Open Risk": item.get("open_risk_points"),
                "Open Reward": item.get("open_reward_points"),
                "Open R:R": item.get("open_reward_risk_ratio"),
                "Closed": item.get("closed_paper_trades"),
                "Remaining": item.get("remaining_review_trades"),
                "Minimum": item.get("minimum_review_trades"),
                "Sample Ready": item.get("sample_ready"),
                "P&L Positive": item.get("pnl_positive"),
                "Forward Ready": item.get("forward_review_ready"),
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
missing_required_inputs = readiness.get("missing_required_inputs")
optional_missing_inputs = readiness.get("optional_missing_inputs")
if missing_required_inputs is None and optional_missing_inputs is None:
    missing_required_inputs = readiness.get("missing_inputs", [])
    optional_missing_inputs = []

if missing_required_inputs:
    st.dataframe(pd.DataFrame({"Required": missing_required_inputs}), use_container_width=True, hide_index=True)
else:
    st.success("No missing required inputs reported.")

if optional_missing_inputs:
    st.dataframe(pd.DataFrame({"Optional": optional_missing_inputs}), use_container_width=True, hide_index=True)

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
