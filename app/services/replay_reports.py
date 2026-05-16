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
    files: list[Path] = []
    for directory in REPORT_DIRS:
        if directory.exists():
            files.extend(directory.glob(pattern))
    return sorted(set(files), key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def latest_replay_risk_report() -> dict[str, Any]:
    files = _report_files("replay_risk_report_*.json")
    if not files:
        return {
            "available": False,
            "searched_paths": [str(path) for path in REPORT_DIRS],
            "report": None,
        }

    latest = files[0]
    report = json.loads(latest.read_text(encoding="utf-8-sig"))
    return {
        "available": True,
        "path": str(latest),
        "updated_at": datetime.utcfromtimestamp(latest.stat().st_mtime).isoformat(),
        "report": report,
    }
