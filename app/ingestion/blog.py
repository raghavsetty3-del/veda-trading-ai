import feedparser
import httpx
from bs4 import BeautifulSoup

from app.ingestion.media import extract_media_urls_from_html


def clean_html(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def clean_author(author: str | None) -> str | None:
    if not author:
        return None
    value = " ".join(str(author).split())
    if value.lower().startswith("ilango"):
        return "Ilango"
    return value


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
            "author": clean_author(getattr(e, "author", None)),
            "raw_html": html,
            "raw_text": clean_html(html),
            "media_paths": extract_media_urls_from_html(html, getattr(e, "link", None)),
            "published_at_raw": getattr(e, "published", None),
        })
    return entries


def fetch_wordpress_posts(site: str, page: int = 1, per_page: int = 100) -> tuple[list[dict], int | None]:
    safe_per_page = max(1, min(per_page, 100))
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(
            f"https://public-api.wordpress.com/wp/v2/sites/{site}/posts",
            params={"per_page": safe_per_page, "page": max(1, page)},
        )
        if response.status_code == 400 and page > 1:
            return [], None
        response.raise_for_status()
    total_pages = response.headers.get("X-WP-TotalPages")
    entries = []
    for item in response.json():
        content = (item.get("content") or {}).get("rendered") or ""
        title = clean_html((item.get("title") or {}).get("rendered") or "")
        author = "Ilango" if site.lower() == "jusnifty.wordpress.com" else str(item.get("author") or "")
        entries.append({
            "source_type": "blog",
            "source_url": item.get("link"),
            "source_external_id": str(item.get("id")),
            "title": title,
            "author": clean_author(author),
            "raw_html": content,
            "raw_text": clean_html(content),
            "media_paths": extract_media_urls_from_html(content, item.get("link")),
            "published_at_raw": item.get("date_gmt") or item.get("date"),
        })
    return entries, int(total_pages) if total_pages else None


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
        "media_paths": extract_media_urls_from_html(html, url),
    }
