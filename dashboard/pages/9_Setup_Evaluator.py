import json
import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Setup Evaluator")

default_context = {
    "symbol": "BANKNIFTY",
    "timeframe": "5m",
    "market_structure": "HH_HL",
    "price_above_ema200": True,
    "retracement_pct": 50.0,
    "distance_from_ema_pct": 1.2,
    "higher_timeframe_bias": "bullish",
    "at_channel_or_envelope_extreme": False,
    "core_tools_aligned": True,
    "emotional_state": "calm",
    "adx": 24,
}

raw = st.text_area("Market Context JSON", value=json.dumps(default_context, indent=2), height=300)

if st.button("Evaluate Setup"):
    try:
        market_context = json.loads(raw)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
    else:
        response = requests.post(
            f"{API_BASE}/strategy/evaluate-setup",
            json={"market_context": market_context},
            timeout=10,
        )
        if not response.ok:
            st.error(response.text)
        else:
            payload = response.json()
            setup = payload["setup"]
            profile = setup["market_context"].get("instrument_profile", {})

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Stance", setup["stance"])
            c2.metric("Long Score", setup["long_score"])
            c3.metric("Short Score", setup["short_score"])
            c4.metric("Profile", profile.get("symbol", "DEFAULT"))

            if profile:
                st.info(profile.get("risk_note", ""))

            st.subheader("Reasons")
            for reason in setup["reasons"]:
                st.write(f"- {reason}")

            st.subheader("Risk Flags")
            if setup["risk_flags"]:
                for flag in setup["risk_flags"]:
                    st.warning(flag)
            else:
                st.success("No blocking risk flags.")

            st.subheader("Matched Rules")
            st.json(setup["matched_rules"])

            st.subheader("Failed Rules")
            st.json(setup["failed_rules"])
