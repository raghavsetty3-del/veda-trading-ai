#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import urllib.request


DEFAULT_API_URL = "http://localhost:8000"
PROMOTION_ENDPOINT = "/reports/banknifty-promotion-readiness"
SAFE_LIVE_FALSE_VALUES = {"", "0", "false", "no", "off"}


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_env(lines: list[str]) -> dict[str, str]:
    values = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.startswith("export "):
            key = key[7:].strip()
        values[key.strip()] = value.strip()
    return values


def update_env_lines(lines: list[str], updates: dict[str, str]) -> list[str]:
    seen = set()
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _ = stripped.split("=", 1)
            prefix = ""
            if key.startswith("export "):
                prefix = "export "
                key = key[7:].strip()
            key = key.strip()
            if key in updates:
                output.append(f"{prefix}{key}={updates[key]}")
                seen.add(key)
                continue
        output.append(line)

    for key in updates:
        if key not in seen:
            output.append(f"{key}={updates[key]}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the reviewed BANKNIFTY candidate to paper-only env settings."
    )
    parser.add_argument("--api-url", default=os.getenv("VEDA_API_URL", DEFAULT_API_URL))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--apply", action="store_true", help="Write the env changes. Omit for dry run.")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"Env file not found: {env_path}", file=sys.stderr)
        return 2

    payload = fetch_json(args.api_url.rstrip("/") + PROMOTION_ENDPOINT)
    if not payload.get("ready_for_paper_candidate_review"):
        blockers = payload.get("paper_candidate_blocking_gates") or []
        print(f"Paper candidate review is blocked: {blockers}", file=sys.stderr)
        return 3

    candidate_env = payload.get("candidate_env") or {}
    allowed_keys = {
        "PAPER_EXIT_MODE",
        "PAPER_PART_BOOK_R_MULTIPLE",
        "PAPER_PART_BOOK_FRACTION",
        "PAPER_TRAIL_LOOKBACK_CANDLES",
        "PAPER_TRADE_COOLDOWN_CANDLES",
    }
    updates = {key: str(value) for key, value in candidate_env.items() if key in allowed_keys}
    missing = sorted(allowed_keys - set(updates))
    if missing:
        print(f"Candidate env is missing expected paper keys: {missing}", file=sys.stderr)
        return 4

    lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    existing = parse_env(lines)
    live_value = existing.get("ENABLE_LIVE_TRADING", "false").strip().lower()
    if live_value not in SAFE_LIVE_FALSE_VALUES:
        print("Refusing paper promotion because ENABLE_LIVE_TRADING is not false.", file=sys.stderr)
        return 5

    print("BANKNIFTY paper candidate is replay-ready.")
    print("Paper-only env updates:")
    for key in sorted(updates):
        current = existing.get(key, "<unset>")
        print(f"  {key}: {current} -> {updates[key]}")

    if not args.apply:
        print("Dry run only. Re-run with --apply to write .env.")
        return 0

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    backup_name = f"{env_path.name}.banknifty-paper-{stamp}.bak"
    backup_path = env_path.with_name(backup_name)
    shutil.copy2(env_path, backup_path)

    updated_lines = update_env_lines(lines, updates)
    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"Updated {env_path}. Backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
