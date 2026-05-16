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


def config_matches(left: dict, right: dict) -> bool:
    return all(values_match(left.get(key), right.get(key)) for _, key, _ in PROMOTION_KEYS)


def env_block(config: dict) -> str:
    lines = []
    for _, key, env_key in PROMOTION_KEYS:
        value = config.get(key)
        if value is not None:
            lines.append(f"{env_key}={value}")
    return "\n".join(lines)


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


def gate_rows(gates: list[dict], area: str) -> list[dict]:
    return [
        {
            "Area": area,
            "Gate": item.get("gate"),
            "Required": "Yes" if item.get("required", True) else "No",
            "Ready": "Yes" if item.get("ready") else "No",
            "Detail": item.get("detail"),
        }
        for item in gates
    ]


def banknifty_validation_summary(config: dict) -> tuple[dict | None, bool, str | None]:
    payload = get("/reports/replay-risk/latest", {"symbol": "BANKNIFTY"}) or {}
    if not payload.get("available"):
        return None, False, payload.get("error") or "No replay risk report available."

    validation_report = payload.get("report") or {}
    validation_config = validation_report.get("config") or {}
    matches = config_matches(config, validation_config)
    symbols = validation_report.get("symbols") or []
    banknifty = next((item for item in symbols if item.get("symbol") == "BANKNIFTY"), None)
    return banknifty, matches, None


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

st.subheader("Review Candidate")
if top_candidates:
    best_candidate = top_candidates[0]
    best_config = candidate_config(best_candidate)
    scheduler_config = get("/paper/scheduler") or {}
    validation_symbol, validation_matches, validation_error = banknifty_validation_summary(best_config)

    st.caption("Review only. This page does not update paper settings, live settings, .env, or the running scheduler.")

    sell_metrics = best_candidate.get("sell") or {}
    validation_metrics = (validation_symbol or {}).get("metrics") or {}
    validation_sell = next(
        (item for item in (validation_symbol or {}).get("by_side", []) if item.get("side") == "sell"),
        {},
    )

    candidate_cols = st.columns(5)
    candidate_cols[0].metric("Candidate Sell PF", sell_metrics.get("profit_factor_label", "N/A"))
    candidate_cols[1].metric("Candidate Sell DD", sell_metrics.get("max_drawdown_points", "N/A"))
    candidate_cols[2].metric("Validation Trades", validation_metrics.get("trades", "N/A"))
    candidate_cols[3].metric("Validation PF", validation_metrics.get("profit_factor_label", "N/A"))
    candidate_cols[4].metric("Validation Sell PF", validation_sell.get("profit_factor_label", "N/A"))

    compare_frame = pd.DataFrame(comparison_rows(scheduler_config, best_config))
    st.dataframe(compare_frame, use_container_width=True, hide_index=True)

    st.text("Candidate env values for later manual promotion")
    st.code(env_block(best_config), language="dotenv")

    if validation_error:
        st.info(validation_error)
    elif not validation_matches:
        st.warning("Latest replay risk report uses different settings than this candidate.")
    else:
        st.success("Latest replay risk report matches this candidate configuration.")

    validation_rows = []
    if validation_metrics:
        validation_rows.append({
            "Scope": "BANKNIFTY Overall",
            "Trades": validation_metrics.get("trades"),
            "PF": validation_metrics.get("profit_factor_label"),
            "Net Points": validation_metrics.get("net_points"),
            "Max DD": validation_metrics.get("max_drawdown_points"),
            "Win Rate": validation_metrics.get("win_rate"),
        })
    if validation_sell:
        validation_rows.append({
            "Scope": "BANKNIFTY Sell",
            "Trades": validation_sell.get("trades"),
            "PF": validation_sell.get("profit_factor_label"),
            "Net Points": validation_sell.get("net_points"),
            "Max DD": validation_sell.get("max_drawdown_points"),
            "Win Rate": validation_sell.get("win_rate"),
        })
    if validation_rows:
        st.dataframe(pd.DataFrame(validation_rows), use_container_width=True, hide_index=True)
else:
    st.info("No candidate is available to review.")

st.subheader("Promotion Readiness")
promotion = get("/reports/banknifty-promotion-readiness") or {}
if promotion:
    readiness_cols = st.columns(4)
    readiness_cols[0].metric(
        "Paper Candidate Review",
        "Ready" if promotion.get("ready_for_paper_candidate_review") else "Blocked",
    )
    readiness_cols[1].metric(
        "Live Candidate Review",
        "Ready" if promotion.get("ready_for_live_candidate_review") else "Blocked",
    )
    readiness_cols[2].metric(
        "Paper Blocking Gates",
        len(promotion.get("paper_candidate_blocking_gates") or []),
    )
    readiness_cols[3].metric(
        "Live Blocking Gates",
        len(promotion.get("live_candidate_blocking_gates") or []),
    )

    blocking = promotion.get("live_candidate_blocking_gates") or []
    if blocking:
        st.warning("Live candidate review remains blocked by: " + ", ".join(blocking))
    else:
        st.success("Live candidate review gates are clear. Keep live trading disabled until explicit manual approval.")

    gates = []
    gates.extend(gate_rows(promotion.get("replay_gates") or [], "Replay"))
    gates.extend(gate_rows(promotion.get("paper_gates") or [], "Forward Paper"))
    if gates:
        st.dataframe(pd.DataFrame(gates), use_container_width=True, hide_index=True)

    candidate_env = promotion.get("candidate_env") or {}
    if candidate_env:
        st.text("Review-only candidate env values")
        st.code("\n".join(f"{key}={value}" for key, value in candidate_env.items()), language="dotenv")
else:
    st.info("Promotion readiness is not available yet.")

st.subheader("All Results")
if results:
    result_frame = pd.DataFrame([candidate_row(item) for item in results])
    st.dataframe(result_frame, use_container_width=True, hide_index=True)
else:
    st.info("No result rows in this report.")
