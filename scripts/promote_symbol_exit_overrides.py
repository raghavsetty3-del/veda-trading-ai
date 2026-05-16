#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import urllib.parse
import urllib.request


DEFAULT_API_URL = "http://localhost:8000"
SAFE_LIVE_FALSE_VALUES = {"", "0", "false", "no", "off"}


def fetch_json(api_url: str, path: str, params: dict | None = None) -> dict:
    query = "?" + urllib.parse.urlencode(params) if params else ""
    with urllib.request.urlopen(api_url.rstrip("/") + path + query, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(api_url: str, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        api_url.rstrip("/") + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
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


def values_match(left, right) -> bool:
    if left is None or right is None:
        return left == right
    try:
        return abs(float(left) - float(right)) < 0.000001
    except (TypeError, ValueError):
        return str(left) == str(right)


def config_matches(left: dict, right: dict) -> bool:
    keys = ["part_book_r_multiple", "part_book_fraction", "trail_lookback_candles", "cooldown_candles"]
    return all(values_match(left.get(key), right.get(key)) for key in keys)


def candidate_config(item: dict) -> dict:
    config = dict(item.get("config") or {})
    config.setdefault("exit_mode", "author_part_book_trail")
    return config


def banknifty_config(api_url: str) -> dict:
    payload = fetch_json(api_url, "/reports/banknifty-promotion-readiness")
    if not payload.get("ready_for_paper_candidate_review"):
        raise RuntimeError(f"BANKNIFTY paper candidate blocked: {payload.get('paper_candidate_blocking_gates')}")
    return candidate_config({"config": payload.get("candidate_config") or {}})


def nifty_config(api_url: str) -> dict:
    tuning = fetch_json(api_url, "/reports/nifty-tuning/latest")
    top = ((tuning.get("report") or {}).get("top_candidates") or [{}])[0]
    config = candidate_config(top)
    validation = fetch_json(api_url, "/reports/replay-risk/latest", {"symbol": "NIFTY"})
    validation_config = (validation.get("report") or {}).get("config") or {}
    symbol_rows = (validation.get("report") or {}).get("symbols") or []
    nifty = next((item for item in symbol_rows if item.get("symbol") == "NIFTY"), {})
    metrics = nifty.get("metrics") or {}
    sell = next((item for item in nifty.get("by_side", []) if item.get("side") == "sell"), {})
    if not config_matches(config, validation_config):
        raise RuntimeError(f"NIFTY validation config does not match top candidate: {validation_config} vs {config}")
    if int(metrics.get("trades") or 0) < 500:
        raise RuntimeError(f"NIFTY validation sample too small: {metrics.get('trades')}")
    if float(metrics.get("profit_factor") or 0) < 2.0 or float(sell.get("profit_factor") or 0) < 2.0:
        raise RuntimeError(
            f"NIFTY validation PF below threshold: overall={metrics.get('profit_factor_label')}, "
            f"sell={sell.get('profit_factor_label')}"
        )
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply reviewed per-symbol paper exit overrides.")
    parser.add_argument("--api-url", default=os.getenv("VEDA_API_URL", DEFAULT_API_URL))
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"Env file not found: {env_path}", file=sys.stderr)
        return 2

    lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    existing = parse_env(lines)
    live_value = existing.get("ENABLE_LIVE_TRADING", "false").strip().lower()
    if live_value not in SAFE_LIVE_FALSE_VALUES:
        print("Refusing override promotion because ENABLE_LIVE_TRADING is not false.", file=sys.stderr)
        return 3

    overrides = {
        "BANKNIFTY": banknifty_config(args.api_url),
        "NIFTY": nifty_config(args.api_url),
    }
    override_value = json.dumps(overrides, separators=(",", ":"), sort_keys=True)
    print("Paper symbol exit overrides:")
    print(json.dumps(overrides, indent=2, sort_keys=True))

    if not args.apply:
        print("Dry run only. Re-run with --apply to write .env.")
        return 0

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S")
    backup_path = env_path.with_name(f"{env_path.name}.symbol-overrides-{stamp}.bak")
    shutil.copy2(env_path, backup_path)
    env_path.write_text(
        "\n".join(update_env_lines(lines, {"PAPER_SYMBOL_EXIT_OVERRIDES": override_value})) + "\n",
        encoding="utf-8",
    )
    env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"Updated {env_path}. Backup: {backup_path}")
    try:
        post_json(
            args.api_url,
            "/audit",
            {
                "event_type": "paper.symbol_exit_overrides_promoted",
                "severity": "WARN",
                "message": "Applied reviewed per-symbol paper exit overrides",
                "payload": {
                    "symbols": sorted(overrides),
                    "overrides": overrides,
                    "env_file": str(env_path),
                    "backup_file": str(backup_path),
                    "live_trading_remained_disabled": True,
                },
            },
        )
        print("Recorded audit event paper.symbol_exit_overrides_promoted.")
    except Exception as exc:
        print(f"Warning: override was applied, but audit event could not be recorded: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
