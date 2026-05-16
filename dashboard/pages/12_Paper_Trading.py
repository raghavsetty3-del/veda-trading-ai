import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Paper Trading")


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


def patch(path, payload):
    try:
        response = requests.patch(f"{API_BASE}{path}", json=payload, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


health = get("/health") or {}
st.metric("Kill Switch", str(health.get("kill_switch", "unknown")))

symbols = [item["symbol"] for item in (get("/instruments") or [])]
symbol = st.selectbox("Symbol", symbols or ["NIFTY", "BANKNIFTY"])
timeframe = st.selectbox("Timeframe", ["5m", "15m", "1h", "1d"], index=0)

st.subheader("Performance")
performance = get("/paper/performance", {"limit": 500}) or {}
performance_items = performance.get("items", [])
selected_performance = next((item for item in performance_items if item.get("symbol") == symbol), None)
if selected_performance:
    cols = st.columns(5)
    cols[0].metric("Realized", selected_performance.get("realized_closed_trades"))
    cols[1].metric("Open", selected_performance.get("open_trades"))
    cols[2].metric("Net P&L", selected_performance.get("net_realized_pnl"))
    cols[3].metric("Profit Factor", selected_performance.get("profit_factor_label"))
    cols[4].metric("Sample Ready", str(selected_performance.get("sample_ready")))
    risk_cols = st.columns(3)
    risk_cols[0].metric("Open Risk", selected_performance.get("open_risk_points"))
    risk_cols[1].metric("Open Reward", selected_performance.get("open_reward_points"))
    risk_cols[2].metric("Open R:R", selected_performance.get("open_reward_risk_ratio"))
if performance_items:
    st.dataframe(pd.DataFrame(performance_items), use_container_width=True)
else:
    st.info("No paper performance metrics yet.")

st.subheader("Author Context")
context_limit = st.number_input("Context Candle Limit", min_value=20, max_value=500, value=250, step=10)
if st.button("Refresh Author Context"):
    snapshot = post(
        "/market/snapshot",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "limit": int(context_limit),
        },
    )
    if snapshot:
        context = snapshot.get("market_context", {})
        setup_payload = post("/strategy/evaluate-setup", {"market_context": context}) or {}
        setup = setup_payload.get("setup", {})

        cols = st.columns(5)
        cols[0].metric("Ready", str(snapshot.get("ready")))
        cols[1].metric("Entry Structure", context.get("market_structure"))
        cols[2].metric("LRHR %", context.get("retracement_pct"))
        cols[3].metric("EMA200", "Above" if context.get("price_above_ema200") else "Below")
        cols[4].metric("Stance", setup.get("stance", "unknown"))

        htf_cols = st.columns(4)
        htf_cols[0].metric("HTF Bias", context.get("higher_timeframe_bias"))
        htf_cols[1].metric("HTF Agreement", context.get("higher_timeframe_agreement", "fallback"))
        htf_cols[2].metric("HTF Source", context.get("higher_timeframe_bias_source"))
        htf_cols[3].metric("ADX", context.get("adx"))

        higher_timeframe_context = context.get("higher_timeframe_context") or []
        if higher_timeframe_context:
            st.dataframe(pd.DataFrame(higher_timeframe_context), use_container_width=True)

        if setup.get("risk_flags"):
            for flag in setup["risk_flags"]:
                st.warning(flag)
        elif setup:
            st.success("No blocking risk flags for this context.")

        with st.expander("Full snapshot context"):
            st.json(snapshot)
        if setup_payload:
            with st.expander("Full setup evaluation"):
                st.json(setup_payload)

st.subheader("Create Simulated Trade")
with st.form("paper_trade"):
    last_price = st.number_input("Last Price", min_value=0.0, step=1.0)
    trend = st.selectbox("Trend", ["up", "down", "range"])
    price_action = st.selectbox("Price Action", ["HH_HL", "LH_LL", "sideways"])
    ema_bias = st.selectbox("EMA Bias", ["above_200", "below_200", "mixed"])
    risk_points = st.number_input("Risk Points", min_value=1.0, value=50.0, step=1.0)
    quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
    allow_kill_switch = st.checkbox("Allow while kill switch is on", value=False)
    submitted = st.form_submit_button("Evaluate Paper Trade")

if submitted:
    result = post(
        "/paper/trades",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "quantity": quantity,
            "allow_when_kill_switch_on": allow_kill_switch,
            "market_context": {
                "last_price": last_price,
                "trend": trend,
                "price_action": price_action,
                "ema_bias": ema_bias,
                "risk_points": risk_points,
            },
        },
    )
    if result:
        st.json(result)

st.subheader("Scheduled Evaluation")
scheduler = get("/paper/scheduler") or {}
if scheduler:
    cols = st.columns(5)
    cols[0].metric("Enabled", str(scheduler.get("enabled")))
    cols[1].metric("Symbols", ", ".join(scheduler.get("symbols", [])))
    cols[2].metric("Interval", f"{scheduler.get('interval_seconds')}s")
    cols[3].metric("Candle Limit", scheduler.get("candle_limit"))
    cols[4].metric("Max Open/Symbol", scheduler.get("max_open_trades_per_symbol"))
    if st.button("Run Scheduled Evaluation Now"):
        result = post(
            "/paper/scheduler/run",
            {
                "symbols": [symbol],
                "timeframe": timeframe,
                "limit": scheduler.get("candle_limit"),
                "quantity": scheduler.get("quantity"),
            },
        )
        if result:
            st.json(result)

    if st.button("Reconcile Open Trades"):
        result = post(
            "/paper/trades/reconcile",
            {
                "symbols": [symbol],
                "timeframe": timeframe,
                "limit": 200,
            },
        )
        if result:
            st.json(result)

st.subheader("Save Paper Evidence")
validation_rule_code = st.text_input("Evidence Rule Code", value="")
validation_status = st.selectbox("Evidence Status Filter", ["", "planned", "open", "closed", "cancelled"], index=0)
validation_limit = st.number_input("Evidence Trade Limit", min_value=1, max_value=500, value=100, step=10)
expected_min_trades = st.number_input("Expected Min Evidence Trades", min_value=1, max_value=500, value=1, step=1)
expected_min_closed_trades = st.number_input("Expected Min Closed Trades", min_value=0, max_value=500, value=0, step=1)
expected_min_realized_pnl = st.number_input("Expected Min Realized P&L", value=0.0, step=50.0)
if st.button("Save Paper Trades as Validation"):
    result = post(
        "/validation/from-paper-trades",
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "status": validation_status or None,
            "rule_code": validation_rule_code or None,
            "limit": validation_limit,
            "expected_min_trades": expected_min_trades,
            "expected_min_closed_trades": expected_min_closed_trades,
            "expected_min_realized_pnl": expected_min_realized_pnl,
            "notes": "Saved from Paper Trading dashboard.",
        },
    )
    if result:
        st.json(result)

st.subheader("Update Paper Trade Exit")
with st.form("paper_trade_exit"):
    trade_id = st.number_input("Trade ID", min_value=1, value=1, step=1)
    exit_status = st.selectbox("Exit Status", ["closed", "target_hit", "stopped", "cancelled"], index=0)
    exit_price = st.number_input("Exit Price", min_value=0.0, step=1.0)
    exit_reason = st.text_area("Exit Reason", value="")
    submitted_exit = st.form_submit_button("Save Exit")
    if submitted_exit:
        result = patch(
            f"/paper/trades/{trade_id}",
            {
                "status": exit_status,
                "exit_price": exit_price,
                "exit_reason": exit_reason or None,
            },
        )
        if result:
            st.json(result)

st.subheader("Recent Paper Trades")
trades = get("/paper/trades", {"limit": 100}) or []
if trades:
    st.dataframe(pd.DataFrame(trades), use_container_width=True)
else:
    st.info("No paper trades yet.")
