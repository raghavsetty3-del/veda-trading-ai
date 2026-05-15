# Implementation Status

Date: 2026-05-14

## Completed

- Deployed Veda Trading AI v0.2 on Azure VM `vm-ai-trading-india`.
- Preserved the previous SQLite deployment backup before v0.2 rollout.
- Runs through Docker Compose with API, dashboard, worker, scheduler, PostgreSQL, Redis, ChromaDB, and Nginx.
- Public Nginx front door is protected with Basic Auth.
- `/api/` proxy is verified for authenticated API access.
- PostgreSQL backup and restore scripts are present and a live backup checkpoint was created.
- Dedicated Azure Blob backup storage `vedabkp260514rs/veda-postgres-backups` is configured.
- Daily off-VM PostgreSQL backup upload is scheduled for `18:45 UTC` / `00:15 IST`.
- Cron-compatible offsite backup script is verified with a successful upload.
- Azure Blob lifecycle retention policy is present for 90-day PostgreSQL backup cleanup.
- Non-destructive PostgreSQL restore drill script is present and verified.
- Weekly non-destructive PostgreSQL restore drill timer is present.
- Healthwatch auto-healer and systemd timer are present for the Docker Compose stack.
- Healthwatch supports optional external webhook alerts through `.healthwatch.env`.
- Crypto bot proxy is available at `/crypto/` behind the same Basic Auth boundary.
- Healthwatch also keeps the crypto bot project healthy when `/home/traderadmin/ai-trading-system` exists.
- ChatGPT project context was extracted from the accessible `Veda trading system` project.
- JustNifty PDF context was extracted from `Practical Guide to Trading and Investing`.
- NIFTY operating playbook added.
- BANKNIFTY operating notes added.
- Instrument profiles added for NIFTY and BANKNIFTY.
- Rule evaluator API and dashboard workbench added.
- Setup evaluator API and dashboard page added.
- Scenario lab API and dashboard page added.
- Five NIFTY/BANKNIFTY scenario validations are passing.
- Live trading remains disabled by default with kill switch controls.
- Offsite PostgreSQL backup script and operating notes are present.
- Market data candle storage and manual ingestion skeleton are present.
- Bulk CSV candle import is present.
- Provider-style CSV/HTTP market-data ingestion is present and schedulable.
- Angel One SmartAPI historical candle ingestion is present through `angelone://` provider sources.
- Paper-trading simulation endpoints and dashboard page are present.
- Scheduled paper-trading evaluation is present and skips duplicate latest candles.
- Paper trades can record exits, realized P&L, and R-multiple.
- Paper-trading observations and closed-trade P&L can now create validation evidence cases.
- Strategy trade-export CSVs can now create performance validation evidence cases.
- Backtest/replay evaluator and stored-candle replay are present.
- Stored-candle replay can now create validation evidence cases.
- Scheduled blog RSS ingestion is present and configurable through `BLOG_FEEDS`.
- Telegram export ingestion, credential readiness status, and live Telethon ingestion endpoint are present.
- Local deterministic knowledge extraction workbench is present.
- Optional OpenAI-assisted extraction is present and remains disabled until credentials are configured.
- Review-only rule suggestion generator is present.
- Reviewed suggestion promotion to inactive draft rules is present.
- Draft rule activation/deactivation workflow with validation notes is present.
- Draft rule activation now checks automated scenario evidence and blocks incomplete activations.
- Timeline and live-readiness gates are documented and visible in the dashboard.
- Historical candle readiness now distinguishes provider-backed candles from smoke/manual/demo data.

## Pending

- Configure real market-data provider CSV/HTTP sources or Angel One broker credentials.
- Review paper-trade exit outcomes before enabling any live execution.
- Configure production blog RSS feeds and live Telegram listener credentials.
- Configure OpenAI extraction credentials if AI enrichment should run in production.
- Load historical NIFTY and BANKNIFTY candle datasets through CSV or provider ingestion.
- Add stronger user authentication than Basic Auth if the app will be shared beyond personal access.
- Monitor weekly restore drill logs and audit events.
- Configure an external webhook receiver for healthwatch alerts if desired.

## Current Access

- Dashboard: `http://20.235.64.162/`
- API proxy: `http://20.235.64.162/api/`
- Username: `veda`
- Password is intentionally not stored in Git.
