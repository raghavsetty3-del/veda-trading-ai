import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
}

JOB_LABELS = {
    "paper_scheduler": "Paper Scheduler",
    "market_provider_ingest": "Market Provider Ingest",
    "source_extraction": "Source Extraction",
    "source_media_enrichment": "Chart Media Enrichment",
    "blog_ingest": "Blog Ingest",
    "telegram_bot_ingest": "Telegram Bot Ingest",
    "telegram_public_ingest": "Telegram Public Ingest",
    "x_ingest": "X Ingest",
    "paper_symbol_exit_overrides": "Paper Exit Overrides",
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


def payload_summary(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    fields = []
    for key in [
        "created",
        "updated",
        "received",
        "processed",
        "seen",
        "skipped",
        "blocked",
        "changed",
        "media_added",
        "feeds",
        "configured_sources",
        "worker_index",
        "worker_count",
    ]:
        if key in payload:
            fields.append(f"{key}={payload.get(key)}")
    if payload.get("symbols"):
        fields.append("symbols=" + ",".join(str(item) for item in payload.get("symbols") or []))
    if payload.get("reconciliation"):
        reconciliation = payload.get("reconciliation") or {}
        fields.append(f"reconciled_closed={reconciliation.get('closed')}")
    return "; ".join(fields[:8])


readiness = get("/readiness") or {}
performance = get("/paper/performance", {"symbols": "NIFTY,BANKNIFTY", "limit": 500}) or {}
scheduler = get("/paper/scheduler") or {}
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

st.subheader("Effective Paper Exit Settings")
effective_rows = []
for symbol, config in sorted((scheduler.get("effective_exit_by_symbol") or {}).items()):
    effective_rows.append({
        "Symbol": symbol,
        "Source": config.get("source"),
        "Exit Mode": config.get("exit_mode"),
        "Part Book R": config.get("part_book_r_multiple"),
        "Part Book Fraction": config.get("part_book_fraction"),
        "Trail Lookback Candles": config.get("trail_lookback_candles"),
        "Cooldown Candles": config.get("cooldown_candles"),
    })

if effective_rows:
    st.dataframe(pd.DataFrame(effective_rows), use_container_width=True, hide_index=True)
else:
    st.info("Effective paper exit settings are not available yet.")

st.subheader("Promotion Gates")
promotions = readiness.get("promotion_readiness_by_symbol") or {}
if not promotions and readiness.get("banknifty_promotion_readiness"):
    promotions = {"BANKNIFTY": readiness.get("banknifty_promotion_readiness") or {}}

if promotions:
    summary_rows = []
    gate_rows = []
    for symbol, promotion in sorted(promotions.items()):
        summary_rows.append({
            "Symbol": symbol,
            "Paper Candidate": "Ready" if promotion.get("ready_for_paper_candidate_review") else "Blocked",
            "Live Candidate": "Ready" if promotion.get("ready_for_live_candidate_review") else "Blocked",
            "Paper Blocks": len(promotion.get("paper_candidate_blocking_gates") or []),
            "Live Blocks": len(promotion.get("live_candidate_blocking_gates") or []),
            "Effective Source": (promotion.get("effective_paper_scheduler") or {}).get("source"),
        })
        for item in promotion.get("all_gates") or []:
            gate_rows.append({
                "Symbol": symbol,
                "Gate": item.get("gate"),
                "Required": item.get("required"),
                "Ready": item.get("ready"),
                "Detail": item.get("detail"),
            })

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    live_blocks = {
        symbol: promotion.get("live_candidate_blocking_gates") or []
        for symbol, promotion in promotions.items()
        if promotion.get("live_candidate_blocking_gates")
    }
    if live_blocks:
        st.warning(
            "Live candidate review blocked by: "
            + "; ".join(f"{symbol}: {', '.join(blocks)}" for symbol, blocks in sorted(live_blocks.items()))
        )
    if gate_rows:
        st.dataframe(pd.DataFrame(gate_rows), use_container_width=True, hide_index=True)
else:
    st.info("Promotion readiness is not available yet.")

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

st.subheader("Latest Background Jobs")
latest_jobs = readiness.get("latest_jobs") or {}
job_rows = []
for key, label in JOB_LABELS.items():
    item = latest_jobs.get(key) or {}
    payload = item.get("payload") or {}
    job_rows.append({
        "Job": label,
        "Seen": item.get("created_at"),
        "Severity": item.get("severity"),
        "Message": item.get("message") or "No audit event found",
        "Summary": payload_summary(payload),
    })

if job_rows:
    st.dataframe(pd.DataFrame(job_rows), use_container_width=True, hide_index=True)
else:
    st.info("No background job audit events found.")

paper_scheduler_payload = (latest_jobs.get("paper_scheduler") or {}).get("payload") or {}
scheduler_items = paper_scheduler_payload.get("items") or []
if scheduler_items:
    scheduler_rows = []
    for item in scheduler_items:
        scheduler_rows.append({
            "Symbol": item.get("symbol"),
            "Timeframe": item.get("timeframe"),
            "Candles": item.get("candles"),
            "Ready": item.get("ready"),
            "Created": item.get("created"),
            "Blocked": item.get("blocked"),
            "Skipped": item.get("skipped"),
            "Reason": item.get("reason"),
        })
    st.subheader("Latest Scheduler Symbols")
    st.dataframe(pd.DataFrame(scheduler_rows), use_container_width=True, hide_index=True)

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
