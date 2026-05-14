import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Rule Mappings")

rules = requests.get(f"{API_BASE}/rules", timeout=8).json()
st.dataframe(pd.DataFrame(rules), use_container_width=True)
