import os

import pandas as pd
import requests
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://api:8000")

LOT_SIZES = {
    "NIFTY": 65,
    "BANKNIFTY": 30,
}


st.title("Replay Risk Report")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


def metric_value(metrics: dict, key: str, default=None):
    value = metrics.get(key, default)
    return value if value is not None else default


def as_frame(rows: list[dict], preferred: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    ordered = [column for column in preferred if column in frame.columns]
    ordered.extend([column for column in frame.columns if column not in ordered and column != "equity_curve_tail"])
    return frame[ordered]


reports_payload = get("/reports/replay-risk") or {}
report_items = reports_payload.get("items") or []
selected_name = None
if report_items:
    labels = {
        item["name"]: (
            f"{item['name']} | "
            f"{item.get('generated_at', 'unknown')[:19]} | "
            f"{', '.join(symbol.get('symbol', '') for symbol in item.get('symbols') or [])}"
        )
        for item in report_items
    }
    selected_name = st.selectbox("Report", list(labels), format_func=lambda value: labels[value])

payload = get("/reports/replay-risk/latest", {"name": selected_name} if selected_name else None) or {}
if not payload.get("available"):
    st.info("No replay risk report found yet. Run scripts/run_replay_risk_report.py to generate one.")
    if payload.get("searched_paths"):
        st.caption("Searched: " + ", ".join(payload["searched_paths"]))
    st.stop()

report = payload.get("report") or {}
config = report.get("config") or {}
symbols = report.get("symbols") or []

meta_cols = st.columns(5)
meta_cols[0].metric("Generated", str(report.get("generated_at") or "unknown")[:19])
meta_cols[1].metric("Updated", str(payload.get("updated_at") or "unknown")[:19])
meta_cols[2].metric("Timeframe", config.get("timeframe", "unknown"))
meta_cols[3].metric("Max Trades", config.get("max_trades", "unknown"))
meta_cols[4].metric("Exit Mode", config.get("exit_mode", "unknown"))

summary_rows = []
for item in symbols:
    metrics = item.get("metrics") or {}
    symbol = item.get("symbol")
    lot_size = LOT_SIZES.get(symbol, 1)
    net_points = float(metrics.get("net_points") or metrics.get("final_equity_points") or 0)
    summary_rows.append({
        "Symbol": symbol,
        "Source Candles": item.get("source_candles"),
        "Trades": metrics.get("trades"),
        "Realized": metrics.get("realized_trades"),
        "Net Points": round(net_points, 2),
        "Approx 1-Lot P&L": round(net_points * lot_size, 2),
        "Profit Factor": metrics.get("profit_factor_label"),
        "Win Rate": metrics.get("win_rate"),
        "Max Drawdown Points": metrics.get("max_drawdown_points"),
        "Max Losing Streak": metrics.get("max_losing_streak"),
    })

st.subheader("Overall")
st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
st.caption("Approx 1-lot P&L is points multiplied by the configured lot size; it excludes brokerage, taxes, slippage, and option premium behavior.")

if not symbols:
    st.stop()

selected_symbol = st.selectbox("Symbol Detail", [item.get("symbol") for item in symbols])
selected = next(item for item in symbols if item.get("symbol") == selected_symbol)
metrics = selected.get("metrics") or {}

cols = st.columns(6)
cols[0].metric("Trades", metric_value(metrics, "trades", 0))
cols[1].metric("Net Points", metric_value(metrics, "net_points", metric_value(metrics, "final_equity_points", 0)))
cols[2].metric("Profit Factor", metric_value(metrics, "profit_factor_label", "N/A"))
cols[3].metric("Win Rate", metric_value(metrics, "win_rate", "N/A"))
cols[4].metric("Max Drawdown", metric_value(metrics, "max_drawdown_points", 0))
cols[5].metric("Losing Streak", metric_value(metrics, "max_losing_streak", 0))

tab_side, tab_month, tab_regime, tab_structure = st.tabs(["Side", "Monthly", "Regime", "Structure"])

with tab_side:
    side_frame = as_frame(
        selected.get("by_side") or [],
        [
            "side",
            "trades",
            "net_points",
            "profit_factor_label",
            "win_rate",
            "max_drawdown_points",
            "max_losing_streak",
            "max_winning_streak",
        ],
    )
    if side_frame.empty:
        st.info("No side-wise replay rows in the report.")
    else:
        st.dataframe(side_frame, use_container_width=True, hide_index=True)

with tab_month:
    monthly_frame = as_frame(
        selected.get("monthly") or [],
        [
            "month",
            "trades",
            "net_points",
            "profit_factor_label",
            "win_rate",
            "max_drawdown_points",
            "max_losing_streak",
            "max_winning_streak",
        ],
    )
    if monthly_frame.empty:
        st.info("No monthly replay rows in the report.")
    else:
        worst_months = monthly_frame.sort_values("max_drawdown_points", ascending=False).head(10)
        st.dataframe(worst_months, use_container_width=True, hide_index=True)
        chart_frame = monthly_frame[["month", "net_points", "max_drawdown_points"]].copy()
        chart_frame = chart_frame.set_index("month")
        st.line_chart(chart_frame)

with tab_regime:
    regime_frame = as_frame(
        selected.get("by_regime") or [],
        [
            "regime",
            "trades",
            "net_points",
            "profit_factor_label",
            "win_rate",
            "max_drawdown_points",
            "max_losing_streak",
            "max_winning_streak",
        ],
    )
    if regime_frame.empty:
        st.info("No regime replay rows in the report.")
    else:
        st.dataframe(regime_frame, use_container_width=True, hide_index=True)

with tab_structure:
    structure_frame = as_frame(
        selected.get("by_structure") or [],
        [
            "market_structure",
            "trades",
            "net_points",
            "profit_factor_label",
            "win_rate",
            "max_drawdown_points",
            "max_losing_streak",
            "max_winning_streak",
        ],
    )
    if structure_frame.empty:
        st.info("No structure replay rows in the report.")
    else:
        st.dataframe(structure_frame, use_container_width=True, hide_index=True)
