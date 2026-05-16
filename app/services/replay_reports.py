import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_DIRS = [
    Path("/app/data/reports"),
    Path("data/reports"),
    Path("reports"),
]


def _report_files(pattern: str) -> list[Path]:
    files_by_name: dict[str, Path] = {}
    for directory in REPORT_DIRS:
        if directory.exists():
            for path in directory.glob(pattern):
                existing = files_by_name.get(path.name)
                if existing is None or path.stat().st_mtime > existing.stat().st_mtime:
                    files_by_name[path.name] = path
    return sorted(files_by_name.values(), key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def _load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        "available": True,
        "name": path.name,
        "path": str(path),
        "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat(),
        "report": report,
    }


def list_replay_risk_reports() -> dict[str, Any]:
    files = _report_files("replay_risk_report_*.json")
    if not files:
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "items": [],
        }

    items = []
    for path in files:
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        symbols = [
            {
                "symbol": item.get("symbol"),
                "trades": (item.get("metrics") or {}).get("trades"),
                "profit_factor": (item.get("metrics") or {}).get("profit_factor_label"),
            }
            for item in report.get("symbols") or []
        ]
        items.append({
            "name": path.name,
            "path": str(path),
            "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat(),
            "generated_at": report.get("generated_at"),
            "symbols": symbols,
            "config": report.get("config") or {},
        })
    return {
        "available": True,
        "items": items,
    }


def _report_has_symbol(report: dict[str, Any], symbol: str | None) -> bool:
    if not symbol:
        return True
    target = symbol.upper()
    return any(item.get("symbol") == target for item in report.get("symbols") or [])


def latest_replay_risk_report(name: str | None = None, symbol: str | None = None) -> dict[str, Any]:
    files = _report_files("replay_risk_report_*.json")
    if not files:
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "report": None,
        }

    if name:
        safe_name = Path(name).name
        for path in files:
            if path.name == safe_name:
                payload = _load_report(path)
                if _report_has_symbol(payload.get("report") or {}, symbol):
                    return payload
                break
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "report": None,
            "error": f"Replay risk report not found: {safe_name}" if not symbol else f"Replay risk report not found for {symbol.upper()}: {safe_name}",
        }

    for path in files:
        try:
            payload = _load_report(path)
        except (OSError, json.JSONDecodeError):
            continue
        if _report_has_symbol(payload.get("report") or {}, symbol):
            return payload

    return {
        "available": False,
        "searched_paths": [str(path) for path in REPORT_DIRS],
        "report": None,
        "error": f"No replay risk report found for {symbol.upper()}" if symbol else "No replay risk report found.",
    }


def list_sell_tuning_reports(symbol: str = "BANKNIFTY") -> dict[str, Any]:
    target = symbol.strip().lower()
    files = _report_files(f"{target}_sell_tuning_*.json")
    if not files:
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "items": [],
        }

    items = []
    for path in files:
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        top = (report.get("top_candidates") or [{}])[0]
        sell = top.get("sell") or {}
        items.append({
            "name": path.name,
            "path": str(path),
            "updated_at": datetime.utcfromtimestamp(path.stat().st_mtime).isoformat(),
            "symbol": report.get("symbol") or target.upper(),
            "generated_at": report.get("generated_at"),
            "mode": report.get("mode"),
            "purpose": report.get("purpose"),
            "baseline_sell": report.get("baseline_sell") or {},
            "top_candidate": top,
            "top_sell_profit_factor": sell.get("profit_factor_label"),
            "top_sell_drawdown": sell.get("max_drawdown_points"),
            "top_sell_net_points": sell.get("net_points"),
            "candidate_count": len(report.get("results") or []),
        })
    return {
        "available": bool(items),
        "items": items,
    }


def sell_tuning_report(symbol: str = "BANKNIFTY", name: str | None = None) -> dict[str, Any]:
    target = symbol.strip().lower()
    files = _report_files(f"{target}_sell_tuning_*.json")
    if not files:
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "report": None,
        }

    if name:
        safe_name = Path(name).name
        for path in files:
            if path.name == safe_name:
                return _load_report(path)
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "report": None,
            "error": f"{target.upper()} tuning report not found: {safe_name}",
        }

    return _load_report(files[0])


def list_banknifty_tuning_reports() -> dict[str, Any]:
    return list_sell_tuning_reports("BANKNIFTY")


def banknifty_tuning_report(name: str | None = None) -> dict[str, Any]:
    return sell_tuning_report("BANKNIFTY", name=name)


def list_nifty_tuning_reports() -> dict[str, Any]:
    return list_sell_tuning_reports("NIFTY")


def nifty_tuning_report(name: str | None = None) -> dict[str, Any]:
    return sell_tuning_report("NIFTY", name=name)
