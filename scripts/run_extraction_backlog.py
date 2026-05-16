import json
import os
import sys
import time
import urllib.error
import urllib.request


API_URL = os.getenv("VEDA_API_URL", "http://localhost:8000").rstrip("/")
BATCH_LIMIT = max(1, min(int(os.getenv("EXTRACTION_BACKLOG_BATCH_LIMIT", "50")), 500))
SLEEP_SECONDS = max(5, int(os.getenv("EXTRACTION_BACKLOG_SLEEP_SECONDS", "30")))
DONE_SLEEP_SECONDS = max(60, int(os.getenv("EXTRACTION_BACKLOG_DONE_SLEEP_SECONDS", "900")))
ERROR_SLEEP_SECONDS = max(30, int(os.getenv("EXTRACTION_BACKLOG_ERROR_SLEEP_SECONDS", "300")))
MAX_CONSECUTIVE_ERRORS = max(1, int(os.getenv("EXTRACTION_BACKLOG_MAX_CONSECUTIVE_ERRORS", "5")))
WORKER_COUNT = max(1, min(int(os.getenv("EXTRACTION_BACKLOG_WORKER_COUNT", "1")), 16))
WORKER_INDEX = max(0, min(int(os.getenv("EXTRACTION_BACKLOG_WORKER_INDEX", "0")), WORKER_COUNT - 1))


def _log(message: str, **fields) -> None:
    payload = {"message": message, "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}
    print(json.dumps(payload, sort_keys=True), flush=True)


def _request_json(path: str, method: str = "GET", timeout: int = 120) -> dict:
    request = urllib.request.Request(f"{API_URL}{path}", method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _source_archive() -> dict:
    readiness = _request_json("/readiness", timeout=180)
    return readiness.get("source_archive") or {}


def _health_ok() -> bool:
    health = _request_json("/health", timeout=30)
    return health.get("status") == "ok" and not bool(health.get("kill_switch"))


def main() -> int:
    _log(
        "extraction_backlog_runner_started",
        api_url=API_URL,
        batch_limit=BATCH_LIMIT,
        worker_index=WORKER_INDEX,
        worker_count=WORKER_COUNT,
        sleep_seconds=SLEEP_SECONDS,
        done_sleep_seconds=DONE_SLEEP_SECONDS,
    )
    consecutive_errors = 0
    while True:
        try:
            if not _health_ok():
                _log("api_not_ready_or_kill_switch_on")
                time.sleep(ERROR_SLEEP_SECONDS)
                continue

            before = _source_archive()
            pending_before = int(before.get("pending_sources") or 0)
            chart_pending_before = int(before.get("chart_backed_pending_extraction") or 0)
            if pending_before <= 0:
                _log("extraction_backlog_complete", source_archive=before)
                time.sleep(DONE_SLEEP_SECONDS)
                consecutive_errors = 0
                continue

            query = f"limit={BATCH_LIMIT}&worker_index={WORKER_INDEX}&worker_count={WORKER_COUNT}"
            result = _request_json(f"/extraction/process-pending?{query}", method="POST", timeout=1800)
            after = _source_archive()
            _log(
                "extraction_batch_finished",
                worker_index=WORKER_INDEX,
                worker_count=WORKER_COUNT,
                seen=result.get("seen"),
                processed=result.get("processed"),
                reconciled=result.get("reconciled"),
                pending_before=pending_before,
                pending_after=after.get("pending_sources"),
                chart_pending_before=chart_pending_before,
                chart_pending_after=after.get("chart_backed_pending_extraction"),
                chart_insights=after.get("chart_insights"),
                chart_images_analyzed=after.get("chart_images_analyzed"),
            )
            consecutive_errors = 0
            if int(result.get("seen") or 0) == 0:
                time.sleep(min(DONE_SLEEP_SECONDS, max(SLEEP_SECONDS, 300)))
            else:
                time.sleep(SLEEP_SECONDS)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            consecutive_errors += 1
            _log("extraction_backlog_error", error=str(exc)[:500], consecutive_errors=consecutive_errors)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                _log("too_many_errors_sleeping_longer", max_consecutive_errors=MAX_CONSECUTIVE_ERRORS)
                time.sleep(ERROR_SLEEP_SECONDS * 2)
                consecutive_errors = 0
            else:
                time.sleep(ERROR_SLEEP_SECONDS)
        except KeyboardInterrupt:
            _log("extraction_backlog_runner_stopped")
            return 0


if __name__ == "__main__":
    sys.exit(main())
