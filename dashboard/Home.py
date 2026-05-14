import os, requests, pandas as pd, streamlit as st

API_BASE = os.getenv("API_BASE", "http://api:8000")
st.set_page_config(page_title="Veda Trading AI", layout="wide")
st.title("Veda Trading AI — Project Health")

def get(path):
    try:
        return requests.get(f"{API_BASE}{path}", timeout=8).json()
    except Exception as exc:
        st.error(f"API error: {exc}")
        return None

health = get("/health") or {}
c1, c2, c3 = st.columns(3)
c1.metric("API", health.get("status", "unknown"))
c2.metric("Version", health.get("version", "unknown"))
c3.metric("Kill Switch", str(health.get("kill_switch", "unknown")))

audit = get("/audit?limit=20") or []
st.subheader("Recent Audit Events")
if audit:
    st.dataframe(pd.DataFrame(audit), use_container_width=True)
else:
    st.info("No audit events yet.")
