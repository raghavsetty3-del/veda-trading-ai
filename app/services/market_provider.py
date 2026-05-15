import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.schemas import MarketCandleCreate
from app.services.angelone_market_data import angelone_status, fetch_angelone_candles_as_csv
from app.services.market_data import upsert_candles


def configured_market_sources() -> list[dict]:
    sources = []
    raw = settings.market_data_sources or ""
    for item in [part.strip() for part in raw.split(";") if part.strip()]:
        parts = [part.strip() for part in item.split("|", 2)]
        if len(parts) != 3:
            sources.append({"error": "Expected SYMBOL|timeframe|source_url", "raw": item})
            continue
        symbol, timeframe, source_url = parts
        sources.append({
            "symbol": symbol.upper(),
            "timeframe": timeframe.lower(),
            "source_url": source_url,
            "source_name": f"provider:{symbol.upper()}:{timeframe.lower()}",
            "max_rows": settings.market_data_ingest_limit,
        })
    return sources


def has_configured_market_sources() -> bool:
    return any(not source.get("error") for source in configured_market_sources())


def market_provider_status() -> dict:
    sources = configured_market_sources()
    valid_sources = [source for source in sources if not source.get("error")]
    angelone = angelone_status()
    angelone_source_count = sum(
        1
        for source in valid_sources
        if urlparse(source.get("source_url", "")).scheme == "angelone"
    )
    operational_sources = [
        source
        for source in valid_sources
        if urlparse(source.get("source_url", "")).scheme != "angelone" or angelone["configured"]
    ]
    return {
        "configured": bool(operational_sources),
        "source_count": len(valid_sources),
        "operational_source_count": len(operational_sources),
        "sources": sources,
        "interval_seconds": settings.market_data_ingest_interval_seconds,
        "limit": settings.market_data_ingest_limit,
        "run_on_start": settings.market_data_ingest_on_start,
        "supported_sources": ["http", "https", "file", "local_path", "angelone"],
        "required_columns": ["ts", "open", "high", "low", "close"],
        "optional_columns": ["symbol", "timeframe", "volume", "source"],
        "angelone": {
            **angelone,
            "source_count": angelone_source_count,
            "operational": angelone_source_count == 0 or angelone["configured"],
        },
    }


def _fetch_source_text(source_url: str, default_symbol: str, default_timeframe: str, source_name: str) -> str:
    parsed = urlparse(source_url)
    if parsed.scheme == "angelone":
        return fetch_angelone_candles_as_csv(source_url, default_symbol, default_timeframe, source_name)
    if parsed.scheme in {"http", "https"}:
        response = httpx.get(source_url, timeout=30)
        response.raise_for_status()
        return response.text
    if parsed.scheme == "file":
        return Path(parsed.path).read_text(encoding="utf-8-sig")
    return Path(source_url).read_text(encoding="utf-8-sig")


def _value(row: dict, *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in {None, ""}:
            return value
    return None


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _parse_csv_candles(text: str, default_symbol: str, default_timeframe: str, source_name: str, max_rows: int) -> dict:
    reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    candles = []
    errors = []
    for index, raw_row in enumerate(reader, start=2):
        if len(candles) >= max_rows:
            break
        row = {str(key).strip().lower(): value for key, value in raw_row.items() if key}
        try:
            candles.append(MarketCandleCreate(
                symbol=(_value(row, "symbol") or default_symbol).upper(),
                timeframe=(_value(row, "timeframe", "interval") or default_timeframe).lower(),
                ts=_parse_timestamp(_value(row, "ts", "timestamp", "datetime", "date") or ""),
                open=float(_value(row, "open", "o") or 0),
                high=float(_value(row, "high", "h") or 0),
                low=float(_value(row, "low", "l") or 0),
                close=float(_value(row, "close", "c") or 0),
                volume=float(_value(row, "volume", "vol", "v")) if _value(row, "volume", "vol", "v") else None,
                source=_value(row, "source") or source_name,
            ))
        except Exception as exc:
            if len(errors) < 20:
                errors.append({"row": index, "error": str(exc)})
    return {"candles": candles, "errors": errors, "truncated": len(candles) >= max_rows}


def ingest_market_source(db: Session, source: dict) -> dict:
    if source.get("error"):
        return {"created": 0, "updated": 0, "received": 0, "errors": [source], "source": source}

    symbol = source["symbol"].upper()
    timeframe = source.get("timeframe", "5m").lower()
    source_url = source["source_url"]
    source_name = source.get("source_name") or f"provider:{symbol}:{timeframe}"
    max_rows = max(1, min(int(source.get("max_rows") or settings.market_data_ingest_limit), 5000))

    try:
        text = _fetch_source_text(source_url, symbol, timeframe, source_name)
    except Exception as exc:
        return {
            "received": 0,
            "created": 0,
            "updated": 0,
            "symbols": [symbol],
            "timeframes": [timeframe],
            "source": {
                "symbol": symbol,
                "timeframe": timeframe,
                "source_url": source_url,
                "source_name": source_name,
            },
            "parse_errors": [{"source_url": source_url, "error": str(exc)}],
            "truncated": False,
        }

    parsed = _parse_csv_candles(text, symbol, timeframe, source_name, max_rows)
    result = upsert_candles(db, parsed["candles"]) if parsed["candles"] else {
        "received": 0,
        "created": 0,
        "updated": 0,
        "symbols": [symbol],
        "timeframes": [timeframe],
    }
    return {
        **result,
        "source": {
            "symbol": symbol,
            "timeframe": timeframe,
            "source_url": source_url,
            "source_name": source_name,
        },
        "parse_errors": parsed["errors"],
        "truncated": parsed["truncated"],
    }


def ingest_configured_market_sources(db: Session) -> dict:
    sources = configured_market_sources()
    results = []
    for source in sources:
        results.append(ingest_market_source(db, source))
    return {
        "configured_sources": len([source for source in sources if not source.get("error")]),
        "created": sum(item.get("created", 0) for item in results),
        "updated": sum(item.get("updated", 0) for item in results),
        "received": sum(item.get("received", 0) for item in results),
        "results": results,
    }
