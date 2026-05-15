import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Expected vs Delivered Validation")

cases = requests.get(f"{API_BASE}/validation", timeout=8).json()
if cases:
    st.dataframe(pd.DataFrame(cases), use_container_width=True)
else:
    st.info("No validation cases yet.")

st.subheader("Create Validation Case")
with st.form("validation"):
    code = st.text_input("Case Code")
    title = st.text_input("Title")
    expected = st.text_area("Expected JSON", value='{"system_should": "avoid_or_reduce_trades"}')
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Create")
    if submitted:
        import json
        payload = {"case_code": code, "title": title, "expected_json": json.loads(expected), "notes": notes}
        r = requests.post(f"{API_BASE}/validation", json=payload, timeout=8)
        st.write(r.json())

st.subheader("Create Trade Export Validation")
with st.form("trade_export_validation"):
    symbol = st.selectbox("Trade Export Symbol", ["NIFTY", "BANKNIFTY"], index=1)
    timeframe = st.text_input("Trade Export Timeframe", value="")
    strategy_name = st.text_input("Strategy Name", value="ADX Supertrend Pivot")
    source_path = st.text_input("API Source Path", value="/app/data/trade_exports/banknifty_strategy_export.csv")
    rule_code = st.text_input("Linked Rule Code", value="")
    expected_min_trades = st.number_input("Minimum Trades", min_value=1, max_value=10000, value=20, step=10)
    expected_min_net_pnl = st.number_input("Minimum Net P&L", value=0.0, step=100.0)
    expected_min_win_rate = st.number_input("Minimum Win Rate", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
    notes = st.text_area("Trade Export Notes", value="")
    submitted = st.form_submit_button("Create Trade Export Validation")
    if submitted:
        payload = {
            "symbol": symbol,
            "timeframe": timeframe or None,
            "strategy_name": strategy_name,
            "source_path": source_path,
            "rule_code": rule_code or None,
            "expected_min_trades": expected_min_trades,
            "expected_min_net_pnl": expected_min_net_pnl,
            "expected_min_win_rate": expected_min_win_rate,
            "notes": notes or None,
        }
        r = requests.post(f"{API_BASE}/validation/from-trade-export", json=payload, timeout=20)
        st.write(r.json())
