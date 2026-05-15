import base64
import csv
import hashlib
import hmac
import struct
import time
from datetime import datetime, timedelta
from io import StringIO
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

API_ROOT = "https://api.dhan.co/v2"
AUTH_ROOT = "https://auth.dhan.co"

INTRADAY_INTERVALS = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "25m": "25",
    "1h": "60",
}

_TOKEN_CACHE: dict[str, datetime | str] = {}


def dhan_status() -> dict:
    generation_missing = []
    for name, value in {
        "DHAN_CLIENT_ID": settings.dhan_client_id,
        "DHAN_PIN": settings.dhan_pin,
        "DHAN_TOTP_SECRET": settings.dhan_totp_secret,
    }.items():
        if not value:
            generation_missing.append(name)

    configured = bool(settings.dhan_access_token) or not generation_missing
    missing = [] if configured else ["DHAN_ACCESS_TOKEN"] + generation_missing
    return {
        "configured": configured,
        "missing": sorted(set(missing)),
        "has_access_token": bool(settings.dhan_access_token),
        "can_generate_access_token": not generation_missing,
        "history_days": settings.dhan_history_days,
        "supported_intervals": sorted([*INTRADAY_INTERVALS, "1d"]),
        "source_format": "dhan://EXCHANGE_SEGMENT/SECURITY_ID?instrument=INDEX",
        "examples": [
            "NIFTY|5m|dhan://IDX_I/13?instrument=INDEX",
            "BANKNIFTY|5m|dhan://IDX_I/25?instrument=INDEX",
        ],
    }


def _totp(secret: str) -> str:
    normalized = "".join(secret.split()).upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    counter = int(time.time() // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def _parse_expiry(value: str | None) -> datetime:
    if not value:
        return datetime.now(ZoneInfo("Asia/Kolkata")) + timedelta(hours=23)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _generate_access_token() -> tuple[str, datetime]:
    if not settings.dhan_client_id or not settings.dhan_pin or not settings.dhan_totp_secret:
        raise RuntimeError("Dhan access token is not configured and token-generation credentials are incomplete.")

    query = urlencode({
        "dhanClientId": settings.dhan_client_id,
        "pin": settings.dhan_pin,
        "totp": _totp(settings.dhan_totp_secret),
    })
    response = httpx.post(f"{AUTH_ROOT}/app/generateAccessToken?{query}", timeout=20)
    response.raise_for_status()
    data = response.json()
    token = data.get("accessToken")
    if not token:
        raise RuntimeError(f"Dhan token generation failed: {data}")
    return token, _parse_expiry(data.get("expiryTime"))


def _access_token() -> str:
    if settings.dhan_access_token:
        return settings.dhan_access_token
    cached_token = _TOKEN_CACHE.get("token")
    cached_expiry = _TOKEN_CACHE.get("expiry")
    if isinstance(cached_token, str) and isinstance(cached_expiry, datetime):
        if cached_expiry - datetime.now() > timedelta(minutes=5):
            return cached_token

    token, expiry = _generate_access_token()
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expiry"] = expiry
    return token


def _default_window(timeframe: str) -> tuple[str, str]:
    now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0)
    days = max(1, settings.dhan_history_days)
    start = now - timedelta(days=days)
    if timeframe.lower() == "1d":
        return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")


def _parse_source(source_url: str, default_timeframe: str) -> dict:
    parsed = urlparse(source_url)
    params = parse_qs(parsed.query)
    security_id = params.get("securityId", [parsed.path.strip("/")])[0]
    if "/" in security_id:
        security_id = security_id.rsplit("/", 1)[-1]
    if not security_id:
        raise RuntimeError("Dhan source URL must include a security ID.")

    exchange_segment = (params.get("exchangeSegment", [parsed.netloc or "IDX_I"])[0] or "IDX_I").upper()
    instrument = (params.get("instrument", ["INDEX"])[0] or "INDEX").upper()
    default_from, default_to = _default_window(default_timeframe)
    interval = params.get("interval", [INTRADAY_INTERVALS.get(default_timeframe.lower(), "5")])[0]
    return {
        "securityId": security_id,
        "exchangeSegment": exchange_segment,
        "instrument": instrument,
        "interval": str(interval),
        "fromDate": params.get("fromDate", params.get("fromdate", [default_from]))[0],
        "toDate": params.get("toDate", params.get("todate", [default_to]))[0],
        "oi": (params.get("oi", ["false"])[0] or "false").lower() == "true",
    }


def _response_to_csv(data: dict, default_symbol: str, default_timeframe: str, source_name: str) -> str:
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    volumes = data.get("volume") or []
    timestamps = data.get("timestamp") or []

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ts", "open", "high", "low", "close", "volume", "symbol", "timeframe", "source"])
    for index, ts in enumerate(timestamps):
        if index >= min(len(opens), len(highs), len(lows), len(closes)):
            break
        dt = datetime.fromtimestamp(int(ts), tz=ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        writer.writerow([
            dt.isoformat(),
            opens[index],
            highs[index],
            lows[index],
            closes[index],
            volumes[index] if index < len(volumes) else None,
            default_symbol.upper(),
            default_timeframe.lower(),
            source_name or f"provider:dhan:{default_symbol.upper()}:{default_timeframe.lower()}",
        ])
    return output.getvalue()


def fetch_dhan_candles_as_csv(
    source_url: str,
    default_symbol: str,
    default_timeframe: str,
    source_name: str,
) -> str:
    params = _parse_source(source_url, default_timeframe)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "access-token": _access_token(),
    }

    if default_timeframe.lower() == "1d":
        path = "/charts/historical"
        payload = {
            "securityId": params["securityId"],
            "exchangeSegment": params["exchangeSegment"],
            "instrument": params["instrument"],
            "expiryCode": 0,
            "oi": params["oi"],
            "fromDate": params["fromDate"][:10],
            "toDate": params["toDate"][:10],
        }
    else:
        path = "/charts/intraday"
        payload = params

    response = httpx.post(f"{API_ROOT}{path}", json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and data.get("status") == "failure":
        raise RuntimeError(f"Dhan candle request failed: {data}")
    return _response_to_csv(data, default_symbol, default_timeframe, source_name)
