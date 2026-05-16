#!/usr/bin/env python3
"""Backfill Dhan historical candles through the running Veda API."""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta
from urllib import error, parse, request


DEFAULT_SYMBOLS = "NIFTY:13,BANKNIFTY:25"
DEFAULT_TIMEFRAMES = "5m,15m,1h"


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _format_intraday(value: date, time_text: str) -> str:
    return f"{value.isoformat()} {time_text}"


def _chunks(start: date, end: date, chunk_days: int) -> list[tuple[date, date]]:
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _symbols(raw: str) -> list[tuple[str, str]]:
    pairs = []
    for item in raw.split(","):
        if not item.strip():
            continue
        symbol, security_id = item.split(":", 1)
        pairs.append((symbol.strip().upper(), security_id.strip()))
    return pairs


def _post_json(api_url: str, payload: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    api_request = request.Request(
        f"{api_url.rstrip('/')}/market/provider/ingest",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(api_request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _has_rate_limit(result: dict) -> bool:
    for item in result.get("parse_errors") or []:
        if "429" in str(item.get("error", "")) or "Rate_Limit" in str(item.get("error", "")):
            return True
    return False


def _ingest_with_retry(args, payload: dict, label: str) -> dict:
    for attempt in range(args.retries + 1):
        try:
            result = _post_json(args.api_url, payload, timeout=args.timeout)
        except error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            result = {"received": 0, "created": 0, "updated": 0, "parse_errors": [{"error": text}]}
            if exc.code == 429:
                result["parse_errors"][0]["error"] = f"HTTP 429: {text}"
        except Exception as exc:  # noqa: BLE001 - printed progress is more useful than failing the whole backfill.
            result = {"received": 0, "created": 0, "updated": 0, "parse_errors": [{"error": repr(exc)}]}

        progress = {
            "label": label,
            "attempt": attempt + 1,
            "received": result.get("received", 0),
            "created": result.get("created", 0),
            "updated": result.get("updated", 0),
            "filtered": result.get("filtered", 0),
            "errors": result.get("parse_errors") or [],
        }
        print(json.dumps(progress, sort_keys=True), flush=True)

        if not _has_rate_limit(result):
            return result
        if attempt < args.retries:
            time.sleep(args.rate_limit_sleep)
    return result


def _intraday_source_url(security_id: str, start: date, end: date) -> str:
    query = parse.urlencode({
        "instrument": "INDEX",
        "fromDate": _format_intraday(start, "09:15:00"),
        "toDate": _format_intraday(end, "15:30:00"),
    })
    return f"dhan://IDX_I/{security_id}?{query}"


def _daily_source_url(security_id: str, start: date, end: date) -> str:
    query = parse.urlencode({
        "instrument": "INDEX",
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
    })
    return f"dhan://IDX_I/{security_id}?{query}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD. Defaults to end-date minus --years.")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="YYYY-MM-DD.")
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--chunk-days", type=int, default=80)
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframes", default=DEFAULT_TIMEFRAMES)
    parser.add_argument("--include-daily", action="store_true")
    parser.add_argument("--sleep", type=float, default=3.0)
    parser.add_argument("--rate-limit-sleep", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--max-rows", type=int, default=20000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    end = _parse_date(args.end_date)
    start = _parse_date(args.start_date) if args.start_date else end - timedelta(days=365 * args.years)
    chunk_days = max(1, min(args.chunk_days, 90))
    symbols = _symbols(args.symbols)
    timeframes = [item.strip().lower() for item in args.timeframes.split(",") if item.strip()]

    requests = []
    for chunk_start, chunk_end in _chunks(start, end, chunk_days):
        for symbol, security_id in symbols:
            for timeframe in timeframes:
                requests.append({
                    "label": f"{symbol} {timeframe} {chunk_start}..{chunk_end}",
                    "payload": {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "source_url": _intraday_source_url(security_id, chunk_start, chunk_end),
                        "source_name": f"provider:{symbol}:{timeframe}",
                        "max_rows": args.max_rows,
                    },
                })

    if args.include_daily:
        for symbol, security_id in symbols:
            requests.append({
                "label": f"{symbol} 1d {start}..{end}",
                "payload": {
                    "symbol": symbol,
                    "timeframe": "1d",
                    "source_url": _daily_source_url(security_id, start, end),
                    "source_name": f"provider:{symbol}:1d",
                    "max_rows": args.max_rows,
                },
            })

    print(json.dumps({
        "event": "dhan_backfill_start",
        "api_url": args.api_url,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "chunk_days": chunk_days,
        "request_count": len(requests),
        "dry_run": args.dry_run,
    }, sort_keys=True), flush=True)

    totals = {"received": 0, "created": 0, "updated": 0, "errors": 0}
    for item in requests:
        if args.dry_run:
            print(json.dumps({"label": item["label"], "payload": item["payload"]}, sort_keys=True), flush=True)
            continue
        result = _ingest_with_retry(args, item["payload"], item["label"])
        totals["received"] += int(result.get("received") or 0)
        totals["created"] += int(result.get("created") or 0)
        totals["updated"] += int(result.get("updated") or 0)
        if result.get("parse_errors"):
            totals["errors"] += 1
        time.sleep(args.sleep)

    print(json.dumps({"event": "dhan_backfill_finished", **totals}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
