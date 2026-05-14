from datetime import datetime
import feedparser
import httpx
from bs4 import BeautifulSoup


def clean_html(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def fetch_rss_entries(feed_url: str) -> list[dict]:
    parsed = feedparser.parse(feed_url)
    entries = []
    for e in parsed.entries:
        html = getattr(e, "summary", "") or getattr(e, "content", [{}])[0].get("value", "")
        entries.append({
            "source_type": "blog",
            "source_url": getattr(e, "link", None),
            "source_external_id": getattr(e, "id", getattr(e, "link", "")),
            "title": getattr(e, "title", None),
            "author": getattr(e, "author", None),
            "raw_html": html,
            "raw_text": clean_html(html),
            "published_at_raw": getattr(e, "published", None),
        })
    return entries


def fetch_blog_page(url: str) -> dict:
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else url
    return {
        "source_type": "blog",
        "source_url": url,
        "source_external_id": url,
        "title": title,
        "author": None,
        "raw_html": html,
        "raw_text": clean_html(html),
    }
