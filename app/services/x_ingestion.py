import httpx

from app.config import settings
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


def _fetch_user_posts(client: httpx.Client, user_id: str, limit: int) -> list[dict]:
    max_results = max(5, min(limit, 100))
    response = client.get(
        f"{X_API_BASE}/users/{user_id}/tweets",
        params={
            "max_results": max_results,
            "exclude": "retweets",
            "tweet.fields": "created_at,author_id,conversation_id,entities,lang,public_metrics,referenced_tweets,text",
        },
    )
    _raise_for_x_error(response)
    return response.json().get("data") or []


def ingest_x_username(db, username: str, limit: int | None = None) -> dict:
    clean_username = username.strip().lstrip("@")
    if not clean_username:
        raise ValueError("X username is required")

    max_items = max(5, min(limit or settings.x_ingest_limit, 100))
    created = 0
    existing = 0
    with httpx.Client(headers=_headers(), timeout=30.0) as client:
        user = _lookup_user(client, clean_username)
        posts = _fetch_user_posts(client, user["id"], max_items)

    for post in posts:
        post_id = post.get("id")
        text = post.get("text") or ""
        source_url = f"https://x.com/{user['username']}/status/{post_id}"
        row, was_created, psychology = archive_source_document(
            db,
            {
                "source_type": "x",
                "source_url": source_url,
                "source_external_id": post_id,
                "title": text[:120],
                "author": user.get("username"),
                "raw_text": text,
                "raw_html": None,
                "media_paths": [],
            },
        )
        if was_created:
            created += 1
            audit(
                db,
                "source.ingested",
                f"Ingested X post: {row.title}",
                entity_type="source_document",
                entity_id=str(row.id),
                payload={"psychology_preview": psychology, "username": user.get("username")},
            )
        else:
            existing += 1

    return {
        "username": user.get("username", clean_username),
        "seen": len(posts),
        "created": created,
        "existing": existing,
    }


def ingest_configured_x_usernames(db, usernames: list[str] | None = None, limit: int | None = None) -> dict:
    target_usernames = usernames or configured_x_usernames()
    results = []
    errors = []
    for username in target_usernames:
        try:
            results.append(ingest_x_username(db, username, limit=limit))
        except Exception as exc:
            errors.append({"username": username, "error": str(exc)})
            db.add(FailedJob(job_type="x.ingest", payload={"username": username}, error=str(exc)))
            db.commit()

    summary = {
        "usernames": len(target_usernames),
        "created": sum(item["created"] for item in results),
        "existing": sum(item["existing"] for item in results),
        "seen": sum(item["seen"] for item in results),
        "results": results,
        "errors": errors,
    }
    audit(db, "x.configured_ingest", "Ran configured X ingestion", payload=summary)
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
        row, was_created, psychology = archive_source_document(
            db,
            {
                "source_type": "x",
                "source_url": source_url,
                "source_external_id": post_id,
                "title": post.text[:120],
                "author": post.author or clean_username,
                "raw_text": post.text,
                "raw_html": None,
                "media_paths": [],
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
                payload={"psychology_preview": psychology, "username": clean_username},
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
