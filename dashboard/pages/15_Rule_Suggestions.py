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


def post(path, payload):
    try:
        response = requests.post(f"{API_BASE}{path}", json=payload, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


condition_tab, mechanism_tab = st.tabs(["Condition Rules", "Author Mechanisms"])

with condition_tab:
    limit = st.number_input("Insight limit", min_value=1, max_value=500, value=200)
    result = get("/suggestions/rules", {"limit": int(limit)}) or {"items": []}

    st.metric("Suggestions", result.get("count", 0))
    items = result.get("items", [])
    if items:
        st.dataframe(pd.DataFrame(items), use_container_width=True)
        selected = st.selectbox("Suggestion", [item["rule_code"] for item in items])
        selected_item = next(item for item in items if item["rule_code"] == selected)
        st.json(selected_item)
        review_note = st.text_area("Review note", value="")
        if st.button("Promote To Draft Rule"):
            promoted = post(f"/suggestions/rules/{selected}/promote", {"review_note": review_note or None})
            if promoted:
                st.success("Draft rule promotion complete.")
                st.json(promoted)
    else:
        st.info("No rule suggestions yet. Process sources in the Extraction Workbench first.")

with mechanism_tab:
    mechanism_limit = st.number_input("Mechanism insight limit", min_value=1, max_value=1000, value=300)
    min_hits = st.number_input("Minimum repeats", min_value=1, max_value=25, value=2)
    mechanisms = get(
        "/suggestions/mechanisms",
        {"limit": int(mechanism_limit), "min_hits": int(min_hits)},
    ) or {"items": []}
    st.metric("Repeated Mechanisms", mechanisms.get("count", 0))
    st.caption(f"Insights scanned: {mechanisms.get('insights_scanned', 0)}")
    mechanism_items = mechanisms.get("items", [])
    if mechanism_items:
        df = pd.DataFrame(mechanism_items)
        st.dataframe(
            df[[
                "field",
                "mechanism",
                "supporting_insights",
                "average_confidence",
                "symbols",
                "timeframes",
                "chart_insights",
                "chart_images",
                "review_status",
            ]],
            use_container_width=True,
        )
        selected_mechanism = st.selectbox(
            "Mechanism",
            [f"{item['field']} | {item['mechanism']}" for item in mechanism_items],
        )
        selected_item = mechanism_items[
            [f"{item['field']} | {item['mechanism']}" for item in mechanism_items].index(selected_mechanism)
        ]
        st.json(selected_item)
    else:
        st.info("No repeated author mechanisms at this threshold yet.")
