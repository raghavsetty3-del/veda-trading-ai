import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Author Principles")

principles = requests.get(f"{API_BASE}/principles", timeout=8).json()
st.dataframe(pd.DataFrame(principles), use_container_width=True)

st.subheader("Add Principle")
with st.form("principle"):
    code = st.text_input("Code")
    title = st.text_input("Title")
    description = st.text_area("Description")
    submitted = st.form_submit_button("Create")
    if submitted:
        r = requests.post(f"{API_BASE}/principles", json={"code": code, "title": title, "description": description}, timeout=8)
        st.write(r.json())
