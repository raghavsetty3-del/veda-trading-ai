import os, requests, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Recovery Controls")

health = requests.get(f"{API_BASE}/health", timeout=8).json()
st.write(health)

enabled = st.checkbox("Enable kill switch", value=bool(health.get("kill_switch")))
reason = st.text_input("Reason", value="dashboard update")
if st.button("Update Kill Switch"):
    r = requests.post(f"{API_BASE}/system/kill-switch", params={"enabled": enabled, "reason": reason}, timeout=8)
    st.write(r.json())

st.warning("Live trading is disabled by default. Keep it disabled until paper trading is validated.")
