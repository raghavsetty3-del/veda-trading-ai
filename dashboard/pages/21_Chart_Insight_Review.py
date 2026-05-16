import os

import pandas as pd
import requests
import streamlit as st


API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Chart Insight Review")


def get(path, params=None):
    try:
        response = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None


def joined(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item not in (None, ""))
    if value in (None, ""):
        return ""
    return str(value)


payload = get(
    "/insights/chart-samples",
    {"limit": 50, "chart_only": True, "actionable_only": True, "visual_only": True},
) or {}
items = payload.get("items") or []
if not items:
    payload = get("/insights/chart-samples", {"limit": 50, "chart_only": True, "actionable_only": False}) or {}
    items = payload.get("items") or []

cols = st.columns(4)
cols[0].metric("Samples", len(items))
cols[1].metric("Scanned", payload.get("scanned", 0))
cols[2].metric("Limit", payload.get("limit", 0))
cols[3].metric("Visual Only", str(payload.get("visual_only", False)))

quality_counts = payload.get("quality_counts") or {}
if quality_counts:
    st.dataframe(
        pd.DataFrame([
            {"Quality": key, "Count In Scan": value}
            for key, value in sorted(quality_counts.items())
        ]),
        use_container_width=True,
        hide_index=True,
    )

if not items:
    st.info("No chart-backed insights are available yet.")
    st.stop()

rows = []
for item in items:
    source = item.get("source") or {}
    summary = item.get("table_summary") or {}
    rows.append({
        "Insight": item.get("insight_id"),
        "Created": item.get("created_at"),
        "Source": source.get("source_type"),
        "Title": source.get("title"),
        "Author": source.get("author"),
        "Quality": item.get("review_quality"),
        "Image Attempted": item.get("image_analysis_attempted"),
        "Prepared": item.get("image_inputs_prepared"),
        "Chart Score": item.get("chart_detail_score"),
        "Mechanism Score": item.get("mechanism_detail_score"),
        "Symbols": summary.get("symbols"),
        "Timeframe": item.get("timeframe"),
        "Bias": item.get("bias"),
        "Confidence": item.get("confidence"),
        "Images": item.get("image_count"),
        "Visible TF": summary.get("visible_timeframes"),
        "Indicators": summary.get("visible_indicators"),
        "Levels": summary.get("price_levels"),
        "Patterns": summary.get("pattern_notes"),
        "Mindset": summary.get("mindset"),
        "Entry": summary.get("entry"),
        "Exit": summary.get("exit"),
        "Risk": summary.get("risk"),
        "URL": source.get("source_url"),
    })

frame = pd.DataFrame(rows)
st.dataframe(frame, use_container_width=True, hide_index=True)

labels = {
    str(item.get("insight_id")): f"{item.get('insight_id')} | {(item.get('source') or {}).get('title') or 'Untitled'}"
    for item in items
}
selected_id = st.selectbox("Insight", list(labels), format_func=lambda value: labels[value])
selected = next(item for item in items if str(item.get("insight_id")) == selected_id)
source = selected.get("source") or {}

detail_cols = st.columns(4)
detail_cols[0].metric("Images", selected.get("image_count"))
detail_cols[1].metric("Prepared", selected.get("image_inputs_prepared"))
detail_cols[2].metric("Chart Score", selected.get("chart_detail_score"))
detail_cols[3].metric("Mechanism Score", selected.get("mechanism_detail_score"))

st.subheader("Chart Evidence")
chart_rows = [
    {"Field": "Visible Timeframes", "Value": joined(selected.get("visible_timeframes"))},
    {"Field": "Visible Indicators", "Value": joined(selected.get("visible_indicators"))},
    {"Field": "Price Levels", "Value": joined(selected.get("price_levels"))},
    {"Field": "Pattern Notes", "Value": joined(selected.get("pattern_notes"))},
    {"Field": "Trade Context", "Value": selected.get("trade_context")},
    {"Field": "Caveats", "Value": joined(selected.get("chart_caveats"))},
]
st.dataframe(pd.DataFrame(chart_rows), use_container_width=True, hide_index=True)

st.subheader("Author Mechanism")
mechanism_rows = [
    {"Field": "Mindset", "Value": joined(selected.get("mindset"))},
    {"Field": "Decision Process", "Value": joined(selected.get("decision_process"))},
    {"Field": "Entry", "Value": joined(selected.get("entry_mechanisms"))},
    {"Field": "Exit", "Value": joined(selected.get("exit_mechanisms"))},
    {"Field": "Risk", "Value": joined(selected.get("risk_mechanisms"))},
    {"Field": "Timeframe Alignment", "Value": joined(selected.get("timeframe_alignment"))},
    {"Field": "Market Regime Filter", "Value": joined(selected.get("market_regime_filter"))},
    {"Field": "Automation Candidates", "Value": joined(selected.get("automation_candidates"))},
    {"Field": "Human Judgment", "Value": joined(selected.get("non_automatable_judgment"))},
]
st.dataframe(pd.DataFrame(mechanism_rows), use_container_width=True, hide_index=True)

st.subheader("Source")
source_rows = [
    {"Field": "Title", "Value": source.get("title")},
    {"Field": "Author", "Value": source.get("author")},
    {"Field": "Type", "Value": source.get("source_type")},
    {"Field": "Published", "Value": source.get("published_at")},
    {"Field": "Media Count", "Value": source.get("media_count")},
    {"Field": "URL", "Value": source.get("source_url")},
    {"Field": "Preview", "Value": source.get("text_preview")},
]
st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)
