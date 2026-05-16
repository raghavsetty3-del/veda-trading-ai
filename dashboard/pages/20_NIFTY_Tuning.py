import os

import pandas as pd
import requests
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://api:8000")

PROMOTION_KEYS = [
    ("Exit Mode", "exit_mode", "PAPER_EXIT_MODE"),
    ("Part Book R", "part_book_r_multiple", "PAPER_PART_BOOK_R_MULTIPLE"),
    ("Part Book Fraction", "part_book_fraction", "PAPER_PART_BOOK_FRACTION"),
    ("Trail Lookback Candles", "trail_lookback_candles", "PAPER_TRAIL_LOOKBACK_CANDLES"),
    ("Cooldown Candles", "cooldown_candles", "PAPER_TRADE_COOLDOWN_CANDLES"),
]

st.title("NIFTY Tuning")


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


def candidate_config(item: dict) -> dict:
    config = dict(item.get("config") or {})
    config.setdefault("exit_mode", "author_part_book_trail")
    return config


def values_match(left, right) -> bool:
    if left is None or right is None:
        return left == right
    try:
        return abs(float(left) - float(right)) < 0.000001
    except (TypeError, ValueError):
        return str(left) == str(right)


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


def comparison_rows(current: dict, candidate: dict) -> list[dict]:
    rows = []
    for label, key, env_key in PROMOTION_KEYS:
        current_value = current.get(key)
        candidate_value = candidate.get(key)
        rows.append({
            "Setting": label,
            "Env Key": env_key,
            "Current Paper Value": current_value,
            "Candidate Value": candidate_value,
            "Matches": "Yes" if values_match(current_value, candidate_value) else "No",
        })
    return rows


def env_block(config: dict) -> str:
    lines = []
    for _, key, env_key in PROMOTION_KEYS:
        value = config.get(key)
        if value is not None:
            lines.append(f"{env_key}={value}")
    return "\n".join(lines)


reports_payload = get("/reports/nifty-tuning") or {}
report_items = reports_payload.get("items") or []
if not report_items:
    st.info("No NIFTY tuning report found.")
    st.stop()

labels = {
    item["name"]: (
        f"{item['name']} | {item.get('mode') or 'unknown'} | "
        f"{item.get('generated_at', 'unknown')[:19]}"
    )
    for item in report_items
}
selected_name = st.selectbox("Report", list(labels), format_func=lambda value: labels[value])

payload = get("/reports/nifty-tuning/latest", {"name": selected_name}) or {}
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
    st.dataframe(pd.DataFrame([candidate_row(item) for item in top_candidates[:10]]), use_container_width=True, hide_index=True)
else:
    st.info("No top candidates in this report.")

st.subheader("Review Candidate")
if top_candidates:
    best_candidate = top_candidates[0]
    best_config = candidate_config(best_candidate)
    scheduler_config = get("/paper/scheduler") or {}
    effective_scheduler = (scheduler_config.get("effective_exit_by_symbol") or {}).get("NIFTY") or scheduler_config
    validation_payload = get("/reports/replay-risk/latest", {"symbol": "NIFTY"}) or {}
    validation_report = validation_payload.get("report") or {}
    validation_config = validation_report.get("config") or {}
    validation_symbol = next(
        (item for item in validation_report.get("symbols", []) if item.get("symbol") == "NIFTY"),
        {},
    )
    validation_metrics = validation_symbol.get("metrics") or {}
    validation_sell = next(
        (item for item in validation_symbol.get("by_side", []) if item.get("side") == "sell"),
        {},
    )

    st.caption("Review only. NIFTY candidate settings are not applied because paper settings are currently global.")
    cols = st.columns(5)
    cols[0].metric("Candidate Sell PF", (best_candidate.get("sell") or {}).get("profit_factor_label", "N/A"))
    cols[1].metric("Candidate Sell DD", (best_candidate.get("sell") or {}).get("max_drawdown_points", "N/A"))
    cols[2].metric("Validation Trades", validation_metrics.get("trades", "N/A"))
    cols[3].metric("Validation PF", validation_metrics.get("profit_factor_label", "N/A"))
    cols[4].metric("Validation Sell PF", validation_sell.get("profit_factor_label", "N/A"))

    config_matches = all(values_match(best_config.get(key), validation_config.get(key)) for _, key, _ in PROMOTION_KEYS)
    if validation_payload.get("available") and config_matches:
        st.success("Latest NIFTY replay validation matches this candidate configuration.")
    elif validation_payload.get("available"):
        st.warning("Latest NIFTY replay validation uses different settings than this candidate.")
    else:
        st.info("No NIFTY replay validation is available yet.")

    st.dataframe(pd.DataFrame(comparison_rows(effective_scheduler, best_config)), use_container_width=True, hide_index=True)
    st.text("NIFTY candidate env values for later per-symbol promotion")
    st.code(env_block(best_config), language="dotenv")

    validation_rows = []
    if validation_metrics:
        validation_rows.append({
            "Scope": "NIFTY Overall",
            "Trades": validation_metrics.get("trades"),
            "PF": validation_metrics.get("profit_factor_label"),
            "Net Points": validation_metrics.get("net_points"),
            "Max DD": validation_metrics.get("max_drawdown_points"),
            "Win Rate": validation_metrics.get("win_rate"),
        })
    if validation_sell:
        validation_rows.append({
            "Scope": "NIFTY Sell",
            "Trades": validation_sell.get("trades"),
            "PF": validation_sell.get("profit_factor_label"),
            "Net Points": validation_sell.get("net_points"),
            "Max DD": validation_sell.get("max_drawdown_points"),
            "Win Rate": validation_sell.get("win_rate"),
        })
    if validation_rows:
        st.dataframe(pd.DataFrame(validation_rows), use_container_width=True, hide_index=True)

st.subheader("All Results")
if results:
    st.dataframe(pd.DataFrame([candidate_row(item) for item in results]), use_container_width=True, hide_index=True)
else:
    st.info("No result rows in this report.")
