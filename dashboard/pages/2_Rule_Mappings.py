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
    evidence_response = requests.get(f"{API_BASE}/rules/{selected}/evidence", timeout=12)
    if evidence_response.ok:
        evidence = evidence_response.json()
        cols = st.columns(4)
        cols[0].metric("Scenarios", evidence["scenario_count"])
        cols[1].metric("Covered", evidence["fully_covered_scenarios"])
        cols[2].metric("Matched", evidence["matched_scenarios"])
        cols[3].metric("Paper trades", evidence["paper_trade_observations"])
        if evidence["eligible_for_activation"]:
            st.success("Activation evidence is ready.")
        else:
            st.warning("Activation evidence is incomplete.")
            st.write(evidence["blockers"])
        with st.expander("Evidence details"):
            st.json(evidence)
    else:
        st.warning("Unable to load activation evidence.")
    if st.button("Update Activation"):
        response = requests.patch(
            f"{API_BASE}/rules/{selected}/activation",
            json={"active": active, "validation_note": validation_note},
            timeout=12,
        )
        if response.ok:
            st.success("Activation updated.")
        else:
            st.error("Activation was not updated.")
        st.json(response.json())
