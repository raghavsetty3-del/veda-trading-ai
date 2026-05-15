import base64
import csv
import hashlib
import hmac
import struct
import time
from datetime import datetime, timedelta
from io import StringIO
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

ROOT_URL = "https://apiconnect.angelone.in"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
CANDLE_PATH = "/rest/secure/angelbroking/historical/v1/getCandleData"

INTERVAL_MAP = {
    "1m": "ONE_MINUTE",
    "3m": "THREE_MINUTE",
    "5m": "FIVE_MINUTE",
    "10m": "TEN_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "1d": "ONE_DAY",
}


def angelone_status() -> dict:
    missing = []
    for name, value in {
        "ANGELONE_API_KEY": settings.angelone_api_key,
        "ANGELONE_CLIENT_CODE": settings.angelone_client_code,
        "ANGELONE_PIN": settings.angelone_pin,
        "ANGELONE_TOTP_SECRET": settings.angelone_totp_secret,
    }.items():
        if not value:
            missing.append(name)
    return {
        "configured": not missing,
        "missing": missing,
        "history_days": settings.angelone_history_days,
        "supported_intervals": sorted(INTERVAL_MAP),
        "source_format": "angelone://EXCHANGE/SYMBOLTOKEN?interval=FIVE_MINUTE",
        "examples": [
            "NIFTY|5m|angelone://NSE/99926000",
            "BANKNIFTY|5m|angelone://NSE/99926009",
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


def _headers(jwt_token: str | None = None) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-ClientLocalIP": settings.angelone_client_local_ip,
        "X-ClientPublicIP": settings.angelone_client_public_ip,
        "X-MACAddress": settings.angelone_client_mac,
        "X-PrivateKey": settings.angelone_api_key or "",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
    }
    if jwt_token:
        headers["Authorization"] = f"Bearer {jwt_token}"
    return headers


def _require_configured() -> None:
    status = angelone_status()
    if not status["configured"]:
        raise RuntimeError(f"Angel One SmartAPI is not configured. Missing: {', '.join(status['missing'])}")


def _login() -> str:
    _require_configured()
    payload = {
        "clientcode": settings.angelone_client_code,
        "password": settings.angelone_pin,
        "totp": _totp(settings.angelone_totp_secret or ""),
    }
    response = httpx.post(f"{ROOT_URL}{LOGIN_PATH}", json=payload, headers=_headers(), timeout=15)
    response.raise_for_status()
    data = response.json()
    if not data.get("status"):
        raise RuntimeError(f"Angel One login failed: {data.get('message') or data}")
    token = (data.get("data") or {}).get("jwtToken")
    if not token:
        raise RuntimeError("Angel One login did not return a JWT token.")
    return token.removeprefix("Bearer ").strip()


def _default_window() -> tuple[str, str]:
    now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(second=0, microsecond=0)
    start = now - timedelta(days=max(1, settings.angelone_history_days))
    return start.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M")


def _parse_source(source_url: str, default_timeframe: str) -> dict:
    parsed = urlparse(source_url)
    params = parse_qs(parsed.query)
    exchange = (params.get("exchange", [parsed.netloc or "NSE"])[0] or "NSE").upper()
    symboltoken = params.get("symboltoken", [parsed.path.strip("/")])[0]
    if "/" in symboltoken:
        symboltoken = symboltoken.rsplit("/", 1)[-1]
    if not symboltoken:
        raise RuntimeError("Angel One source URL must include a symbol token.")

    default_from, default_to = _default_window()
    interval = params.get("interval", [INTERVAL_MAP.get(default_timeframe.lower(), default_timeframe.upper())])[0]
    return {
        "exchange": exchange,
        "symboltoken": symboltoken,
        "interval": interval,
        "fromdate": params.get("fromdate", [default_from])[0],
        "todate": params.get("todate", [default_to])[0],
    }


def fetch_angelone_candles_as_csv(
    source_url: str,
    default_symbol: str,
    default_timeframe: str,
    source_name: str,
) -> str:
    params = _parse_source(source_url, default_timeframe)
    jwt_token = _login()
    response = httpx.post(f"{ROOT_URL}{CANDLE_PATH}", json=params, headers=_headers(jwt_token), timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get("status"):
        raise RuntimeError(f"Angel One candle request failed: {data.get('message') or data}")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ts", "open", "high", "low", "close", "volume", "symbol", "timeframe", "source"])
    for row in data.get("data") or []:
        if len(row) < 5:
            continue
        ts, open_value, high, low, close, *rest = row
        volume = rest[0] if rest else None
        writer.writerow([
            ts,
            open_value,
            high,
            low,
            close,
            volume,
            default_symbol.upper(),
            default_timeframe.lower(),
            source_name or f"provider:angelone:{default_symbol.upper()}:{default_timeframe.lower()}",
        ])
    return output.getvalue()
