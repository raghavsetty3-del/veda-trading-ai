import os

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Rule Suggestions")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


limit = st.number_input("Insight limit", min_value=1, max_value=500, value=200)
result = get("/suggestions/rules", {"limit": int(limit)}) or {"items": []}

st.metric("Suggestions", result.get("count", 0))
items = result.get("items", [])
if items:
    st.dataframe(pd.DataFrame(items), use_container_width=True)
    selected = st.selectbox("Suggestion", [item["rule_code"] for item in items])
    st.json(next(item for item in items if item["rule_code"] == selected))
else:
    st.info("No rule suggestions yet. Process sources in the Extraction Workbench first.")
