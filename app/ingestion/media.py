from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup


SUPPORTED_OPENAI_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
CONVERTIBLE_IMAGE_EXTENSIONS = {".bmp", ".tif", ".tiff"}
IMAGE_EXTENSIONS = SUPPORTED_OPENAI_IMAGE_EXTENSIONS | CONVERTIBLE_IMAGE_EXTENSIONS
DEFAULT_MEDIA_LIMIT = 8


def unique_urls(urls: list[str | None], limit: int | None = None) -> list[str]:
    seen = set()
    items = []
    for url in urls:
        if not url:
            continue
        clean = str(url).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        items.append(clean)
        if limit and len(items) >= limit:
            break
    return items


def normalize_media_url(url: str | None, base_url: str | None = None) -> str | None:
    if not url:
        return None
    clean = str(url).strip()
    if not clean or clean.startswith("data:"):
        return None
    if base_url:
        clean = urljoin(base_url, clean)
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"}:
        return None
    return clean


def image_extension(url: str) -> str | None:
    parsed = urlparse(url)
    path = parsed.path.lower()
    match = re.search(r"\.(png|jpe?g|webp|gif|bmp|tiff?)$", path)
    if match:
        return "." + match.group(1).replace("jpg", "jpeg")
    fmt = parse_qs(parsed.query).get("format", [None])[0]
    if fmt:
        fmt = fmt.lower().strip(".")
        if fmt == "jpg":
            fmt = "jpeg"
        if fmt in {"png", "jpeg", "webp", "gif", "bmp", "tif", "tiff"}:
            return "." + fmt
    return None


def is_probable_image_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if image_extension(url) in IMAGE_EXTENSIONS:
        return True
    if host.endswith("twimg.com") and "/media/" in parsed.path:
        return True
    return False


def is_supported_openai_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "data"}:
        return False
    if parsed.scheme == "data":
        return url.startswith("data:image/png") or url.startswith("data:image/jpeg") or url.startswith("data:image/webp") or url.startswith("data:image/gif")
    if urlparse(url).netloc.lower().endswith("twimg.com") and "/media/" in urlparse(url).path:
        return True
    ext = image_extension(url)
    return ext in SUPPORTED_OPENAI_IMAGE_EXTENSIONS


def is_convertible_image_url(url: str) -> bool:
    return image_extension(url) in CONVERTIBLE_IMAGE_EXTENSIONS


def _srcset_urls(value: str | None, base_url: str | None) -> list[str]:
    urls = []
    if not value:
        return urls
    for candidate in value.split(","):
        url = candidate.strip().split(" ")[0]
        normalized = normalize_media_url(url, base_url)
        if normalized:
            urls.append(normalized)
    return urls


def extract_media_urls_from_html(html: str | None, base_url: str | None = None, limit: int = DEFAULT_MEDIA_LIMIT) -> list[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str | None] = []

    for tag in soup.find_all("img"):
        for attr in ["src", "data-src", "data-original", "data-lazy-src"]:
            urls.append(normalize_media_url(tag.get(attr), base_url))
        urls.extend(_srcset_urls(tag.get("srcset"), base_url))

    for tag in soup.find_all("a"):
        href = normalize_media_url(tag.get("href"), base_url)
        if href and is_probable_image_url(href):
            urls.append(href)

    return unique_urls([url for url in urls if url], limit=limit)


def allowed_chart_page_url(url: str | None) -> bool:
    normalized = normalize_media_url(url)
    if not normalized:
        return False
    host = urlparse(normalized).netloc.lower().removeprefix("www.")
    allowed_hosts = {
        "jusnifty.wordpress.com",
        "tradeinniftyonly.blogspot.com",
    }
    return host in allowed_hosts
