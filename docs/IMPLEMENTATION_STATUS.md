# Implementation Status

Date: 2026-05-16

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
- Eight NIFTY/BANKNIFTY scenario validations are passing.
- Live trading remains disabled by default with kill switch controls.
- Offsite PostgreSQL backup script and operating notes are present.
- Market data candle storage and manual ingestion skeleton are present.
- Bulk CSV candle import is present.
- Provider-style CSV/HTTP market-data ingestion is present and schedulable.
- Angel One SmartAPI historical candle ingestion is present through `angelone://` provider sources.
- DhanHQ historical candle ingestion is present through `dhan://` provider sources.
- DhanHQ is configured as the active provider for NIFTY and BANKNIFTY 5-minute, 15-minute, and 1-hour candles.
- Provider-backed NIFTY and BANKNIFTY history is loaded from DhanHQ with a 90-day intraday window and more than 6,300 candles per instrument across configured timeframes.
- Dhan token generation now uses a shared on-disk token cache so API and scheduler containers do not repeatedly hit Dhan's token-generation rate limit.
- Provider ingestion keeps the newest candles when an import is capped, preserving current market context for replay and paper trading.
- Paper-trading simulation endpoints and dashboard page are present.
- Scheduled paper-trading evaluation is present and skips duplicate latest candles.
- Paper trades can record exits, realized P&L, and R-multiple.
- Open paper trades can be reconciled automatically against later stored candles for target/stop exits.
- Paper scheduler is active with a 250-candle context window, a 5-candle cooldown, and strict JustNifty-aligned LRHR setup gating before opening new trades.
- Paper scheduler now uses real 15-minute and 1-hour stored candles for higher-timeframe context on 5-minute entries.
- Higher-timeframe alignment is treated as necessary but not sufficient; entry-timeframe HH/HL or LH/LL price action is still required before a directional paper setup can open.
- Paper trades now use author-aligned price-action invalidation stops rather than generic percentage stops.
- Paper exits now support the author-backed part-book-and-trail plan: book part when price moves in favor, move the balance to a trailing stop, and let structure manage the rest.
- Historical paper replay is available for non-live provider-backed outcome checks; author-style part-book/trail replay improved both NIFTY and BANKNIFTY risk-adjusted results.
- Historical paper replay and stored-candle replay now use timestamp-correct 15-minute and 1-hour higher-timeframe context, avoiding lookahead while matching live paper evaluation.
- Backtest Replay dashboard exposes historical paper replay with author-style part-book/trail metrics.
- Historical paper replay can now create validation evidence cases. Timestamped-MTF replay evidence passed for both NIFTY and BANKNIFTY using the author part-book/trail exit plan.
- Live-readiness now includes a required historical paper replay gate, separate from forward paper evidence collection.
- Paper performance reports now show remaining realized exits, positive-P&L status, and forward-review readiness per instrument.
- Readiness now surfaces latest paper scheduler, market ingest, source extraction, and blog ingestion audit events for operational status checks.
- Setup evaluation now blocks directional bias when no predefined risk or price-action invalidation level is available.
- Paper-trading observations and closed-trade P&L can now create validation evidence cases.
- Strategy trade-export CSVs can now create performance validation evidence cases.
- Failed trade-export evidence can be reviewed as not promoted while preserving the failed result.
- Backtest/replay evaluator and stored-candle replay are present.
- Stored-candle replay can now create validation evidence cases.
- Dhan-backed stored-candle replay validation is passing for the tuned RULE-RETRACEMENT-LRHR band on both NIFTY and BANKNIFTY over rolling 200-candle windows.
- Setup scoring was retuned to match the JustNifty extraction: directional bias now requires aligned price action structure, true EMA200 bias, LRHR retracement, and higher-timeframe direction.
- Scheduled blog RSS ingestion is present and configurable through `BLOG_FEEDS`.
- Telegram export ingestion, credential readiness status, and live Telethon ingestion endpoint are present.
- Local deterministic knowledge extraction workbench is present.
- Optional OpenAI-assisted extraction is configured and active for source enrichment.
- Pending source extraction is scheduled so newly ingested source documents can become insights automatically.
- Review-only rule suggestion generator is present.
- Reviewed suggestion promotion to inactive draft rules is present.
- Draft rule activation/deactivation workflow with validation notes is present.
- Draft rule activation now checks automated scenario evidence and blocks incomplete activations.
- Timeline and live-readiness gates are documented and visible in the dashboard.
- Parallel workstreams are now visible in readiness and the Timeline dashboard so non-paper work can continue while forward paper evidence accumulates.
- Integration setup helpers are present for Telegram, RSS feeds, and healthwatch webhook configuration without committing secrets.
- Historical candle readiness now distinguishes provider-backed candles from smoke/manual/demo data.

## Pending

- Let provider-backed paper trades accumulate and reconcile until each reviewed instrument has at least 20 realized closed outcomes.
- Review paper-trade exit outcomes before enabling any live execution.
- Configure production blog RSS feeds and live Telegram listener credentials.
- Add stronger user authentication than Basic Auth if the app will be shared beyond personal access.
- Monitor weekly restore drill logs and audit events.
- Configure an external webhook receiver for healthwatch alerts if desired.

See `docs/PARALLEL_COMPLETION.md` for the work that can continue while paper evidence accumulates.

## Current Access

- Dashboard: `http://20.235.64.162/`
- API proxy: `http://20.235.64.162/api/`
- Username: `veda`
- Password is intentionally not stored in Git.
