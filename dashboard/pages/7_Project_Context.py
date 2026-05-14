import os
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")

st.title("Project Context")


def get(path):
    try:
        response = requests.get(f"{API_BASE}{path}", timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return []


principles = get("/principles")
rules = get("/rules")
validation = get("/validation")

c1, c2, c3 = st.columns(3)
c1.metric("Principles", len(principles))
c2.metric("Rules", len(rules))
c3.metric("Validation Cases", len(validation))

st.subheader("Veda System")
st.write(
    "Veda Trading AI is a recoverable, author-aligned trading intelligence system. "
    "It preserves raw source context, converts trading knowledge into durable principles, "
    "maps those principles into rules, and validates expected behavior before any live trading."
)

st.subheader("Extracted Source")
st.markdown(
    """
- Source: Practical Guide to Trading and Investing by VanIlango / JustNifty
- Pages extracted: 154
- ChatGPT project: Veda trading system
- Visible project chat: Nifty Trading Analysis
- Project sources tab: empty during extraction
"""
)

st.subheader("Implementation Status")
left, right = st.columns(2)
with left:
    st.markdown(
        """
**Completed**
- Azure VM deployment
- Nginx front door with Basic Auth
- NIFTY and BANKNIFTY profiles
- Rule evaluator
- Setup evaluator
- Scenario lab
- Live PostgreSQL backup checkpoint
"""
    )

with right:
    st.markdown(
        """
**Pending**
- GitHub push from laptop passphrase session
- Market data integration
- Paper-trading loop
- Backtesting/replay
- Telegram/blog scheduled ingestion
- Off-VM automated backups
"""
    )

st.subheader("Core Trading Context")
st.markdown(
    """
- Price action is primary: HH/HL for bullish structure, LH/LL for bearish structure.
- Retracement is used to avoid chasing and locate LRHR entries.
- 200 EMA acts as the major intraday bias filter.
- Trendlines and channels define support, resistance, extremes, and re-entry zones.
- Elliott Wave is optional context, not a mandatory gate.
- Part booking and trailing are required at extremes or target zones.
- Small, consistent, plan-based execution is preferred over oversized trades.
"""
)

st.subheader("Live JustNifty-Derived Principles")
justnifty_principles = [p for p in principles if p.get("code", "") >= "AP-006"]
for item in justnifty_principles:
    st.markdown(f"**{item['code']} - {item['title']}**")
    st.write(item["description"])

st.subheader("Live Validation Themes")
for item in validation:
    code = item.get("case_code", "")
    if code.startswith("VAL-JN"):
        st.markdown(f"**{code} - {item['title']}**")
        st.json(item.get("expected_json", {}))
