import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Extraction Workbench")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


def post(path, params=None):
    try:
        response = requests.post(f"{API_BASE}{path}", params=params, timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


limit = st.number_input("Pending source limit", min_value=1, max_value=500, value=50)
if st.button("Process Pending Sources"):
    result = post("/extraction/process-pending", {"limit": int(limit)})
    if result:
        st.json({"seen": result["seen"], "processed": result["processed"]})

st.subheader("Recent Insights")
insights = get("/insights", {"limit": 100}) or []
if insights:
    st.dataframe(pd.DataFrame(insights), use_container_width=True)
else:
    st.info("No insights yet.")

st.subheader("Recent Sources")
sources = get("/sources", {"limit": 100}) or []
if sources:
    st.dataframe(pd.DataFrame(sources), use_container_width=True)
