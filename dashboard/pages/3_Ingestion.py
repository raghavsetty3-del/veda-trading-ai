import json
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

st.subheader("Configured Blog Feeds")
if st.button("Run Configured Blog Ingestion"):
    r = requests.post(f"{API_BASE}/ingest/blog/configured", timeout=120)
    st.write(r.json())

st.subheader("Blog Backfill")
backfill_kind = st.selectbox("Backfill Type", ["WordPress site", "RSS/Atom feed"])
backfill_target = st.text_input("Backfill Target", value="jusnifty.wordpress.com")
backfill_pages = st.number_input("Backfill Pages", min_value=1, max_value=200, value=10)
backfill_page_size = st.number_input("Backfill Page Size", min_value=1, max_value=100, value=25)
if st.button("Run Blog Backfill"):
    payload = {
        "max_pages": int(backfill_pages),
        "page_size": int(backfill_page_size),
    }
    if backfill_kind == "WordPress site":
        payload["wordpress_site"] = backfill_target
    else:
        payload["feed_url"] = backfill_target
    r = requests.post(f"{API_BASE}/ingest/blog/backfill", json=payload, timeout=300)
    st.write(r.json())

st.subheader("Telegram")
telegram_status = requests.get(f"{API_BASE}/ingest/telegram/status", timeout=8).json()
st.write(telegram_status)
live_limit = st.number_input("Live Telegram Limit", min_value=1, max_value=500, value=int(telegram_status.get("ingest_limit", 50)))
live_channels = st.text_input("Live Channel Override", value="")
if st.button("Run Live Telegram Ingestion"):
    payload = {
        "limit": int(live_limit),
        "channels": [item.strip() for item in live_channels.split(",") if item.strip()] or None,
    }
    r = requests.post(f"{API_BASE}/ingest/telegram/live", json=payload, timeout=120)
    st.write(r.json())

st.subheader("Telegram Bot API")
bot_status = telegram_status.get("bot_api", {})
st.write(bot_status)
bot_limit = st.number_input("Bot API Telegram Limit", min_value=1, max_value=100, value=int(bot_status.get("ingest_limit", 100)))
if st.button("Run Telegram Bot Ingestion"):
    r = requests.post(f"{API_BASE}/ingest/telegram/bot", json={"limit": int(bot_limit)}, timeout=120)
    st.write(r.json())

st.subheader("Public Telegram")
public_status = telegram_status.get("public_web", {})
st.write(public_status)
public_limit = st.number_input("Public Telegram Limit", min_value=1, max_value=100, value=int(public_status.get("ingest_limit", 50)))
public_channels = st.text_input("Public Channel Override", value="")
if st.button("Run Public Telegram Ingestion"):
    payload = {
        "limit": int(public_limit),
        "channels": [item.strip() for item in public_channels.split(",") if item.strip()] or None,
    }
    r = requests.post(f"{API_BASE}/ingest/telegram/public", json=payload, timeout=120)
    st.write(r.json())

st.subheader("X/Twitter")
x_status = requests.get(f"{API_BASE}/ingest/x/status", timeout=8).json()
st.write(x_status)
x_limit = st.number_input("X Ingest Limit", min_value=5, max_value=100, value=int(x_status.get("ingest_limit", 20)))
x_usernames = st.text_input("X Username Override", value="")
if st.button("Run X Ingestion"):
    payload = {
        "limit": int(x_limit),
        "usernames": [item.strip().lstrip("@") for item in x_usernames.split(",") if item.strip()] or None,
    }
    r = requests.post(f"{API_BASE}/ingest/x/configured", json=payload, timeout=120)
    st.write(r.json())

st.subheader("Manual X/Twitter Posts")
x_export_username = st.text_input("X Export Username", value="")
x_sample = [
    {
        "post_id": "1",
        "text": "Sample X post text",
        "created_at": "2026-05-16T09:15:00",
        "author": "manual",
        "url": "",
    }
]
x_raw_posts = st.text_area("X posts JSON", value=json.dumps(x_sample, indent=2), height=180)
if st.button("Ingest Manual X Posts"):
    try:
        posts = json.loads(x_raw_posts)
        r = requests.post(
            f"{API_BASE}/ingest/x/export",
            json={"username": x_export_username.strip().lstrip("@") or "manual-x", "posts": posts},
            timeout=60,
        )
        st.write(r.json())
    except Exception as exc:
        st.error(f"Manual X ingestion failed: {exc}")

channel = st.text_input("Telegram channel/export name", value="manual-export")
sample = [
    {
        "message_id": "1",
        "text": "Sample message text",
        "date": "2026-05-14T09:15:00",
        "author": "manual",
    }
]
raw_messages = st.text_area("Telegram messages JSON", value=json.dumps(sample, indent=2), height=180)
if st.button("Ingest Telegram Export"):
    try:
        messages = json.loads(raw_messages)
        r = requests.post(
            f"{API_BASE}/ingest/telegram/export",
            json={"channel": channel, "messages": messages},
            timeout=60,
        )
        st.write(r.json())
    except Exception as exc:
        st.error(f"Telegram export ingestion failed: {exc}")

st.subheader("Recent Sources")
sources = requests.get(f"{API_BASE}/sources?limit=100", timeout=8).json()
if sources:
    st.dataframe(pd.DataFrame(sources), use_container_width=True)
