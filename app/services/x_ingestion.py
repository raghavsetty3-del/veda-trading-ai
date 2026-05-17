import httpx

from app.config import settings
from app.ingestion.media import allowed_chart_page_url, extract_media_urls_from_html, unique_urls
from app.models import FailedJob
from app.schemas import XExportIngestRequest
from app.services.audit import audit
from app.services.source_archive import archive_source_document

X_API_BASE = "https://api.x.com/2"


def configured_x_usernames() -> list[str]:
    raw = settings.x_usernames or ""
    parts = raw.replace("\n", ",").split(",")
    return [item.strip().lstrip("@") for item in parts if item.strip()]


def x_status() -> dict:
    usernames = configured_x_usernames()
    missing = []
    if not settings.x_bearer_token:
        missing.append("X_BEARER_TOKEN")
    if not usernames:
        missing.append("X_USERNAMES")
    return {
        "configured": not missing,
        "missing": missing,
        "usernames": usernames,
        "ingest_limit": settings.x_ingest_limit,
        "source": "official_x_api_v2",
        "endpoints": [
            "/2/users/by/username/:username",
            "/2/users/:id/tweets",
            "/ingest/x/backfill",
        ],
    }


def _headers() -> dict:
    if not settings.x_bearer_token:
        raise ValueError("X_BEARER_TOKEN is not configured")
    return {"Authorization": f"Bearer {settings.x_bearer_token}"}


def _raise_for_x_error(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        raise ValueError(f"X API request failed with {exc.response.status_code}: {detail}") from exc


def _lookup_user(client: httpx.Client, username: str) -> dict:
    response = client.get(
        f"{X_API_BASE}/users/by/username/{username}",
        params={"user.fields": "id,name,username"},
    )
    _raise_for_x_error(response)
    data = response.json().get("data")
    if not data:
        raise ValueError(f"X username not found: {username}")
    return data


def _fetch_user_posts(client: httpx.Client, user_id: str, limit: int, pagination_token: str | None = None) -> dict:
    max_results = max(5, min(limit, 100))
    params = {
        "max_results": max_results,
        "exclude": "retweets",
        "tweet.fields": "attachments,created_at,author_id,conversation_id,entities,lang,public_metrics,referenced_tweets,text",
        "expansions": "attachments.media_keys",
        "media.fields": "alt_text,duration_ms,height,media_key,preview_image_url,type,url,width",
    }
    if pagination_token:
        params["pagination_token"] = pagination_token
    response = client.get(
        f"{X_API_BASE}/users/{user_id}/tweets",
        params=params,
    )
    _raise_for_x_error(response)
    return response.json()


def _media_by_key(payload: dict) -> dict:
    return {
        item.get("media_key"): item
        for item in (payload.get("includes") or {}).get("media", [])
        if item.get("media_key")
    }


def _post_entity_urls(post: dict) -> list[str]:
    urls = []
    for item in (post.get("entities") or {}).get("urls", []):
        urls.append(item.get("expanded_url") or item.get("unwound_url") or item.get("url"))
    return unique_urls(urls)


def _post_media_urls(post: dict, media_lookup: dict) -> list[str]:
    urls = []
    for key in (post.get("attachments") or {}).get("media_keys", []):
        media = media_lookup.get(key) or {}
        urls.append(media.get("url") or media.get("preview_image_url"))
    return unique_urls(urls)


def _linked_page_media_urls(urls: list[str], limit: int = 6) -> list[str]:
    media = []
    headers = {"User-Agent": "VedaTradingAI/0.2 chart-media-resolver"}
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        for url in urls:
            if not allowed_chart_page_url(url):
                continue
            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception:
                continue
            media.extend(extract_media_urls_from_html(response.text, str(response.url), limit=limit))
            if len(media) >= limit:
                break
    return unique_urls(media, limit=limit)


def _source_text_with_links(text: str, links: list[str], media_urls: list[str]) -> str:
    parts = [text]
    if links:
        parts.append("Linked author URLs:\n" + "\n".join(links[:8]))
    if media_urls:
        parts.append("Chart/media URLs:\n" + "\n".join(media_urls[:8]))
    return "\n\n".join(part for part in parts if part)


def ingest_x_username(db, username: str, limit: int | None = None, pages: int = 1) -> dict:
    clean_username = username.strip().lstrip("@")
    if not clean_username:
        raise ValueError("X username is required")

    max_items = max(5, min(limit or settings.x_ingest_limit, 100))
    max_pages = max(1, min(pages, 25))
    created = 0
    existing = 0
    created_source_ids = []
    seen = 0
    pages_fetched = 0
    next_token = None
    seen_post_ids = set()
    with httpx.Client(headers=_headers(), timeout=30.0) as client:
        user = _lookup_user(client, clean_username)
        while pages_fetched < max_pages:
            payload = _fetch_user_posts(client, user["id"], max_items, pagination_token=next_token)
            pages_fetched += 1
            posts = payload.get("data") or []
            media_lookup = _media_by_key(payload)
            for post in posts:
                post_id = post.get("id")
                if not post_id or post_id in seen_post_ids:
                    continue
                seen_post_ids.add(post_id)
                seen += 1
                text = post.get("text") or ""
                source_url = f"https://x.com/{user['username']}/status/{post_id}"
                links = _post_entity_urls(post)
                media_urls = unique_urls([*_post_media_urls(post, media_lookup), *_linked_page_media_urls(links)], limit=8)
                row, was_created, psychology = archive_source_document(
                    db,
                    {
                        "source_type": "x",
                        "source_url": source_url,
                        "source_external_id": post_id,
                        "title": text[:120],
                        "author": user.get("username"),
                        "raw_text": _source_text_with_links(text, links, media_urls),
                        "raw_html": None,
                        "media_paths": media_urls,
                        "published_at": post.get("created_at"),
                    },
                )
                if was_created:
                    created += 1
                    created_source_ids.append(row.id)
                    audit(
                        db,
                        "source.ingested",
                        f"Ingested X post: {row.title}",
                        entity_type="source_document",
                        entity_id=str(row.id),
                        payload={"psychology_preview": psychology, "username": user.get("username"), "media_count": len(media_urls)},
                    )
                else:
                    existing += 1
            next_token = (payload.get("meta") or {}).get("next_token")
            if not posts or not next_token:
                break

    return {
        "username": user.get("username", clean_username),
        "seen": seen,
        "created": created,
        "existing": existing,
        "created_source_ids": created_source_ids,
        "pages_fetched": pages_fetched,
        "has_more": bool(next_token),
    }


def ingest_configured_x_usernames(
    db,
    usernames: list[str] | None = None,
    limit: int | None = None,
    pages: int = 1,
) -> dict:
    target_usernames = usernames or configured_x_usernames()
    results = []
    errors = []
    safe_pages = max(1, min(pages, 25))
    for username in target_usernames:
        try:
            results.append(ingest_x_username(db, username, limit=limit, pages=safe_pages))
        except Exception as exc:
            errors.append({"username": username, "error": str(exc)})
            db.add(FailedJob(job_type="x.ingest", payload={"username": username, "pages": safe_pages}, error=str(exc)))
            db.commit()

    summary = {
        "usernames": len(target_usernames),
        "created": sum(item["created"] for item in results),
        "existing": sum(item["existing"] for item in results),
        "seen": sum(item["seen"] for item in results),
        "created_source_ids": [source_id for item in results for source_id in item.get("created_source_ids", [])],
        "pages": safe_pages,
        "pages_fetched": sum(item.get("pages_fetched", 0) for item in results),
        "has_more": any(item.get("has_more") for item in results),
        "results": results,
        "errors": errors,
    }
    audit(
        db,
        "x.backfill_ingest" if safe_pages > 1 else "x.configured_ingest",
        "Ran X backfill ingestion" if safe_pages > 1 else "Ran configured X ingestion",
        payload=summary,
    )
    return summary


def ingest_x_export(db, payload: XExportIngestRequest) -> dict:
    clean_username = payload.username.strip().lstrip("@")
    if not clean_username:
        raise ValueError("X username is required")

    created = 0
    existing = 0
    items = []
    for post in payload.posts:
        post_id = str(post.post_id)
        source_url = post.url or f"https://x.com/{clean_username}/status/{post_id}"
        links = post.expanded_urls or []
        media_urls = unique_urls([*(post.media_urls or []), *_linked_page_media_urls(links)], limit=8)
        row, was_created, psychology = archive_source_document(
            db,
            {
                "source_type": "x",
                "source_url": source_url,
                "source_external_id": post_id,
                "title": post.text[:120],
                "author": post.author or clean_username,
                "raw_text": _source_text_with_links(post.text, links, media_urls),
                "raw_html": None,
                "media_paths": media_urls,
            },
        )
        items.append({"id": row.id, "source_url": row.source_url, "created": was_created})
        if was_created:
            created += 1
            audit(
                db,
                "source.ingested",
                f"Ingested manual X post: {row.title}",
                entity_type="source_document",
                entity_id=str(row.id),
                payload={"psychology_preview": psychology, "username": clean_username, "media_count": len(media_urls)},
            )
        else:
            existing += 1

    summary = {
        "username": clean_username,
        "seen": len(payload.posts),
        "created": created,
        "existing": existing,
        "items": items,
    }
    audit(db, "x.export_ingested", f"Ingested manual X posts for {clean_username}", payload=summary)
    return summary
