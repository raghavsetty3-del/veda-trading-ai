import os

import pandas as pd
import requests
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("BANKNIFTY Tuning")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


def config_label(config: dict) -> str:
    return (
        f"R {config.get('part_book_r_multiple')} | "
        f"fraction {config.get('part_book_fraction')} | "
        f"trail {config.get('trail_lookback_candles')} | "
        f"cooldown {config.get('cooldown_candles')}"
    )


def candidate_row(item: dict) -> dict:
    sell = item.get("sell") or {}
    overall = item.get("overall") or {}
    config = item.get("config") or {}
    return {
        "Config": config_label(config),
        "Sell Trades": sell.get("trades"),
        "Sell PF": sell.get("profit_factor_label"),
        "Sell Net Points": sell.get("net_points"),
        "Sell Max DD": sell.get("max_drawdown_points"),
        "DD Improvement": item.get("drawdown_improvement_points"),
        "Overall PF": overall.get("profit_factor_label"),
        "Overall Net Points": overall.get("net_points"),
        "Overall Max DD": overall.get("max_drawdown_points"),
        "Score": item.get("score"),
    }


reports_payload = get("/reports/banknifty-tuning") or {}
report_items = reports_payload.get("items") or []
if not report_items:
    st.info("No BANKNIFTY tuning report found.")
    st.stop()

labels = {
    item["name"]: (
        f"{item['name']} | {item.get('mode') or 'unknown'} | "
        f"{item.get('generated_at', 'unknown')[:19]}"
    )
    for item in report_items
}
selected_name = st.selectbox("Report", list(labels), format_func=lambda value: labels[value])

payload = get("/reports/banknifty-tuning/latest", {"name": selected_name}) or {}
if not payload.get("available"):
    st.error(payload.get("error") or "Report unavailable.")
    st.stop()

report = payload.get("report") or {}
baseline = report.get("baseline_sell") or {}
top_candidates = report.get("top_candidates") or []
results = report.get("results") or []

meta_cols = st.columns(5)
meta_cols[0].metric("Mode", report.get("mode", "unknown"))
meta_cols[1].metric("Generated", str(report.get("generated_at") or "unknown")[:19])
meta_cols[2].metric("Candidates", len(results))
meta_cols[3].metric("Baseline Sell PF", baseline.get("profit_factor_label", "N/A"))
meta_cols[4].metric("Baseline Sell DD", baseline.get("max_drawdown_points", "N/A"))

st.subheader("Top Candidates")
if top_candidates:
    top_frame = pd.DataFrame([candidate_row(item) for item in top_candidates[:10]])
    st.dataframe(top_frame, use_container_width=True, hide_index=True)
else:
    st.info("No top candidates in this report.")

st.subheader("All Results")
if results:
    result_frame = pd.DataFrame([candidate_row(item) for item in results])
    st.dataframe(result_frame, use_container_width=True, hide_index=True)
else:
    st.info("No result rows in this report.")
