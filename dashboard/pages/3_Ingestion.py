import os, requests, pandas as pd, streamlit as st
API_BASE = os.getenv("API_BASE", "http://api:8000")
st.title("Ingestion")

st.subheader("Ingest Blog Page")
url = st.text_input("Blog post URL")
if st.button("Ingest Blog Page") and url:
    r = requests.post(f"{API_BASE}/ingest/blog/page", params={"url": url}, timeout=30)
    st.write(r.json())

st.subheader("Ingest RSS Feed")
feed_url = st.text_input("RSS feed URL")
limit = st.number_input("Limit", min_value=1, max_value=100, value=20)
if st.button("Ingest RSS") and feed_url:
    r = requests.post(f"{API_BASE}/ingest/blog/rss", params={"feed_url": feed_url, "limit": int(limit)}, timeout=60)
    st.write(r.json())

st.subheader("Recent Sources")
sources = requests.get(f"{API_BASE}/sources?limit=100", timeout=8).json()
if sources:
    st.dataframe(pd.DataFrame(sources), use_container_width=True)
