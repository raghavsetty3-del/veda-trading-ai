import json
import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Rule Evaluator")

default_context = {
    "market_structure": "HH_HL",
    "price_above_ema200": True,
    "retracement_pct": 61.8,
    "distance_from_ema_pct": 0.8,
    "higher_timeframe_bias": "bullish",
    "at_channel_or_envelope_extreme": False,
    "core_tools_aligned": True,
    "emotional_state": "calm",
    "adx": 22,
}

raw = st.text_area("Market Context JSON", value=json.dumps(default_context, indent=2), height=280)

if st.button("Evaluate Rules"):
    try:
        market_context = json.loads(raw)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
    else:
        response = requests.post(
            f"{API_BASE}/rules/evaluate",
            json={"market_context": market_context},
            timeout=10,
        )
        if not response.ok:
            st.error(response.text)
        else:
            payload = response.json()
            results = payload["results"]
            rows = [
                {
                    "rule_code": item["rule_code"],
                    "matched": item["matched"],
                    "rule_name": item["rule_name"],
                    "expected_behavior": item["expected_behavior"],
                }
                for item in results
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            st.subheader("Details")
            for item in results:
                with st.expander(f"{item['rule_code']} - {item['rule_name']}"):
                    st.write(item["expected_behavior"])
                    st.json({"passed": item["passed"], "failed": item["failed"]})
