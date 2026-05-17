# Parallel Completion Plan

Date: 2026-05-16

The five-session forward paper evidence gate should continue in the background. It should not block finishing the rest of the system.

## Already Complete

- Azure deployment, dashboard, API, worker, scheduler, PostgreSQL, Redis, ChromaDB, and Nginx.
- DhanHQ provider ingestion for NIFTY and BANKNIFTY 5-minute, 15-minute, and 1-hour candles.
- Author-aligned rule stack: price action structure, 200 EMA bias, LRHR retracement, no-chase extension filter, higher-timeframe context, low-ADX/chop avoidance, predefined invalidation, and part-book/trail exits.
- Timestamp-correct stored-candle replay and historical paper replay validation for NIFTY and BANKNIFTY.
- OpenAI-assisted source extraction, deterministic extraction, rule suggestions, and validation evidence workflows.
- Backup, offsite backup, restore drill, and local healthwatch auto-healing.
- Telegram fallback ingestion paths are built, but Telegram is intentionally on hold because current content is expected to duplicate the blog feed.
- GitHub sync.

## Running In Background

- Forward paper evidence remains live in paper mode only.
- Live trading stays disabled.
- Paper scheduler waits for strict LRHR setups and reconciles target/stop/trailing exits from stored candles.
- Market data ingestion continues refreshing configured Dhan sources.

## Input-Bound Items

These can be completed immediately after inputs are available:

| Workstream | Needed Input | Current State | Completion After Input |
| --- | --- | --- | --- |
| External health alerts | `HEALTHWATCH_WEBHOOK_URL` | Healthwatch is built and logging locally | Add `.healthwatch.env`, restart timer, run healthwatch check |
| Blog/RSS ingestion | None for current JustNifty sources | Manual and scheduled RSS ingestion are built; JustNifty feeds are configured | Keep scheduled ingest running and process new sources |
| X/Twitter ingestion | None for current approved accounts | Official X API v2 connector is configured for approved accounts | Keep scheduled ingest running and process new sources |
| Telegram ingestion | Optional later if it provides unique content | Export, Bot API, public web, and API listener paths are built but on hold | Configure only if the source becomes useful and non-duplicative |
| Shared-access security | Target users and access policy | Basic Auth is OK for personal use | Add stronger auth before wider sharing |

Use the integration helper from the laptop when the values are available:

```powershell
Set-Location C:\Users\LENOVO\Downloads\veda-trading-ai-v0.2
powershell -ExecutionPolicy Bypass -File scripts\configure_integrations.ps1
```

The helper connects to the VM, prompts for the values, writes them only to deployment env files, restarts the relevant services, and prints readiness.

## Final Live-Review Blocker

Only forward paper evidence should block live-review:

- At least 20 realized closed paper trades per reviewed instrument.
- Positive realized P&L per reviewed instrument.
- Review of average R, profit factor, win rate, and trade notes.
- User approval before any live execution flag is changed.

Until those are satisfied, the system can continue improving data ingestion, observability, documentation, and review workflows without enabling live trading.
