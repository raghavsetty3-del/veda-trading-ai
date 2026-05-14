import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Expected vs Delivered Validation")

cases = requests.get(f"{API_BASE}/validation", timeout=8).json()
if cases:
    st.dataframe(pd.DataFrame(cases), use_container_width=True)
else:
    st.info("No validation cases yet.")

st.subheader("Create Validation Case")
with st.form("validation"):
    code = st.text_input("Case Code")
    title = st.text_input("Title")
    expected = st.text_area("Expected JSON", value='{"system_should": "avoid_or_reduce_trades"}')
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Create")
    if submitted:
        import json
        payload = {"case_code": code, "title": title, "expected_json": json.loads(expected), "notes": notes}
        r = requests.post(f"{API_BASE}/validation", json=payload, timeout=8)
        st.write(r.json())
