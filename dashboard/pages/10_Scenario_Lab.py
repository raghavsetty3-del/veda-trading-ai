import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Scenario Lab")


def get(path):
    response = requests.get(f"{API_BASE}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def post(path):
    response = requests.post(f"{API_BASE}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


try:
    scenarios = get("/strategy/scenarios")
except Exception as exc:
    st.error(f"API error: {exc}")
    scenarios = []

if scenarios:
    rows = [
        {
            "id": item["id"],
            "title": item["title"],
            "symbol": item["market_context"].get("symbol"),
            "expected_stance": item["expected_stance"],
        }
        for item in scenarios
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    labels = {f"{item['title']} ({item['id']})": item["id"] for item in scenarios}
    selected = st.selectbox("Scenario", list(labels.keys()))

    if st.button("Evaluate Scenario"):
        try:
            result = post(f"/strategy/scenarios/{labels[selected]}/evaluate")
        except Exception as exc:
            st.error(f"API error: {exc}")
        else:
            scenario = result["scenario"]
            setup = result["setup"]
            if result["passed"]:
                st.success("Scenario passed")
            else:
                st.error("Scenario failed")

            c1, c2, c3 = st.columns(3)
            c1.metric("Expected", scenario["expected_stance"])
            c2.metric("Actual", setup["stance"])
            c3.metric("Symbol", scenario["market_context"].get("symbol", ""))

            st.subheader("Description")
            st.write(scenario["description"])

            st.subheader("Risk Flags")
            if setup["risk_flags"]:
                for flag in setup["risk_flags"]:
                    st.warning(flag)
            else:
                st.success("No blocking risk flags.")

            st.subheader("Market Context")
            st.json(setup["market_context"])
