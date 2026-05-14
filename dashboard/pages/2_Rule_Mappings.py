import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Rule Mappings")

rules = requests.get(f"{API_BASE}/rules", timeout=8).json()
st.dataframe(pd.DataFrame(rules), use_container_width=True)

st.subheader("Draft Rule Activation")
drafts = [item for item in rules if item.get("status") in {"draft", "active_reviewed"}]
if drafts:
    selected = st.selectbox("Rule", [item["rule_code"] for item in drafts])
    active = st.checkbox("Active", value=bool(next(item for item in drafts if item["rule_code"] == selected).get("active")))
    validation_note = st.text_area("Validation note")
    if st.button("Update Activation"):
        response = requests.patch(
            f"{API_BASE}/rules/{selected}/activation",
            json={"active": active, "validation_note": validation_note},
            timeout=12,
        )
        st.write(response.json())
