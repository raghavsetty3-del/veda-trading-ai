import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
}

st.title("System Evidence")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


readiness = get("/readiness") or {}
performance = get("/paper/performance", {"symbols": "NIFTY,BANKNIFTY", "limit": 500}) or {}
health = get("/health") or {}

health_cols = st.columns(5)
health_cols[0].metric("API", health.get("status", "unknown"))
health_cols[1].metric("Kill Switch", str(health.get("kill_switch", "unknown")))
health_cols[2].metric("Live Enabled", str(readiness.get("live_trading_enabled", "unknown")))
health_cols[3].metric("Ready For Live Review", str(readiness.get("ready_for_live_review", "unknown")))
health_cols[4].metric("Blocking Gates", len(readiness.get("blocking_gates") or []))

blocking_gates = readiness.get("blocking_gates") or []
if blocking_gates:
    st.warning("Blocking gates: " + ", ".join(blocking_gates))

st.subheader("Historical Replay Evidence")
historical = readiness.get("historical_paper_replay") or {}
replay_rows = []
for symbol, item in sorted((historical.get("latest_by_symbol") or {}).items()):
    lot_size = LOT_SIZES.get(symbol, 1)
    net_points = float(item.get("net_realized_pnl") or 0)
    realized = int(item.get("realized_trades") or 0)
    replay_rows.append({
        "Symbol": symbol,
        "Case": item.get("case_code"),
        "Source Candles": item.get("source_candles"),
        "Replay Trades": realized,
        "Net Points": round(net_points, 2),
        "Lot Size": lot_size,
        "Approx 1-Lot P&L": round(net_points * lot_size, 2),
        "Profit Factor": item.get("profit_factor_label"),
        "Avg R": item.get("average_r_multiple"),
        "Status": item.get("status"),
    })

if replay_rows:
    st.dataframe(pd.DataFrame(replay_rows), use_container_width=True, hide_index=True)
else:
    st.info("No historical replay evidence found.")

st.caption("Approx 1-lot P&L is index/futures-style points multiplied by current configured lot size; it excludes brokerage, taxes, slippage, and option premium behavior.")

st.subheader("Forward Paper Evidence")
paper_rows = []
for item in performance.get("items") or readiness.get("paper") or []:
    paper_rows.append({
        "Symbol": item.get("symbol"),
        "Closed": item.get("realized_closed_trades", item.get("closed_paper_trades")),
        "Remaining": item.get("remaining_review_trades"),
        "Sample Ready": item.get("sample_ready"),
        "Net P&L": item.get("net_realized_pnl"),
        "Profit Factor": item.get("profit_factor_label"),
        "Forward Ready": item.get("forward_review_ready"),
    })

if paper_rows:
    st.dataframe(pd.DataFrame(paper_rows), use_container_width=True, hide_index=True)
else:
    st.info("No forward paper evidence found.")

st.subheader("BANKNIFTY Promotion Gate")
promotion = readiness.get("banknifty_promotion_readiness") or {}
if promotion:
    promotion_cols = st.columns(4)
    promotion_cols[0].metric(
        "Paper Candidate",
        "Ready" if promotion.get("ready_for_paper_candidate_review") else "Blocked",
    )
    promotion_cols[1].metric(
        "Live Candidate",
        "Ready" if promotion.get("ready_for_live_candidate_review") else "Blocked",
    )
    promotion_cols[2].metric("Paper Blocks", len(promotion.get("paper_candidate_blocking_gates") or []))
    promotion_cols[3].metric("Live Blocks", len(promotion.get("live_candidate_blocking_gates") or []))

    live_blocks = promotion.get("live_candidate_blocking_gates") or []
    if live_blocks:
        st.warning("Live candidate review blocked by: " + ", ".join(live_blocks))

    gate_rows = []
    for item in promotion.get("all_gates") or []:
        gate_rows.append({
            "Gate": item.get("gate"),
            "Required": item.get("required"),
            "Ready": item.get("ready"),
            "Detail": item.get("detail"),
        })
    if gate_rows:
        st.dataframe(pd.DataFrame(gate_rows), use_container_width=True, hide_index=True)
else:
    st.info("BANKNIFTY promotion readiness is not available yet.")

st.subheader("Data Coverage")
coverage_rows = []
for symbol, count in sorted((readiness.get("provider_candle_counts") or {}).items()):
    coverage_rows.append({
        "Symbol": symbol,
        "Provider Candles": count,
        "Total Candles": (readiness.get("candle_counts") or {}).get(symbol),
    })
if coverage_rows:
    st.dataframe(pd.DataFrame(coverage_rows), use_container_width=True, hide_index=True)

historical_gate = next(
    (item for item in readiness.get("required_gates") or [] if item.get("gate") == "historical_candles_loaded"),
    None,
)
if historical_gate:
    st.caption(historical_gate.get("detail", ""))

st.subheader("Source And Chart Extraction")
archive = readiness.get("source_archive") or {}
processed = int(archive.get("processed_sources") or 0)
total = int(archive.get("total_sources") or 0)
pending = int(archive.get("pending_sources") or 0)
chart_pending = int(archive.get("chart_backed_pending_extraction") or 0)

extract_cols = st.columns(6)
extract_cols[0].metric("Sources", total)
extract_cols[1].metric("Processed", processed)
extract_cols[2].metric("Pending", pending)
extract_cols[3].metric("Chart Pending", chart_pending)
extract_cols[4].metric("Chart Images", archive.get("chart_images_analyzed"))
extract_cols[5].metric("Chart Insights", archive.get("chart_insights"))

if total:
    st.progress(min(processed / total, 1.0), text=f"{processed:,} of {total:,} sources processed")
if archive.get("chart_backed_sources"):
    done = int(archive.get("chart_backed_sources") or 0) - chart_pending
    st.progress(
        min(done / int(archive.get("chart_backed_sources") or 1), 1.0),
        text=f"{done:,} of {int(archive.get('chart_backed_sources') or 0):,} chart-backed sources extracted",
    )

by_type = archive.get("by_type") or {}
if by_type:
    st.dataframe(
        pd.DataFrame([{"Source Type": key, "Count": value} for key, value in sorted(by_type.items())]),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Readiness Gates")
gate_rows = []
for gate in readiness.get("gates") or []:
    gate_rows.append({
        "Gate": gate.get("gate"),
        "Required": gate.get("required"),
        "Ready": gate.get("ready"),
        "Detail": gate.get("detail"),
    })

if gate_rows:
    st.dataframe(pd.DataFrame(gate_rows), use_container_width=True, hide_index=True)
