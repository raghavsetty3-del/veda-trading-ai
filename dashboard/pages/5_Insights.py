import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Extracted Insights")

insights = requests.get(f"{API_BASE}/insights?limit=100", timeout=8).json()
if insights:
    st.dataframe(pd.DataFrame(insights), use_container_width=True)
else:
    st.info("No insights yet.")
