# Veda Trading System Timeline

Date: 2026-05-17

This timeline assumes the current deployed Azure VM remains the target environment and that live trading stays disabled until paper evidence is strong enough to review.

## Current State

Completed as of 2026-05-15:

- Azure deployment is live behind Basic Auth.
- NIFTY and BANKNIFTY instrument profiles are present.
- Rule, setup, scenario, replay, paper-trade, and validation workflows are present.
- Paper trades can record and automatically reconcile exits, realized P&L, and R-multiple.
- BankNifty strategy trade export was imported and recorded as failed performance evidence because net P&L was negative.
- The failed BankNifty trade export has been reviewed as not promoted; the failed result is retained.
- DhanHQ is configured for NIFTY and BANKNIFTY 5-minute provider-backed candles.
- Provider-backed candles are loaded at production scale: about 197,716 NIFTY candles and 128,787 BANKNIFTY candles across configured timeframes.
- Dhan-backed stored-candle replay validation passes for the tuned RULE-RETRACEMENT-LRHR band on NIFTY and BANKNIFTY using rolling 200-candle windows.
- Timestamp-correct historical paper replay validation passes for NIFTY and BANKNIFTY using the author's part-book/trailing exit plan.
- Author-aligned tuning now requires price action structure, true EMA200 bias, LRHR retracement, and higher-timeframe direction before long/short bias.
- Pre-EMA200 open paper trades were cancelled as superseded so new evidence starts from the corrected strategy logic.
- Historical paper replay showed better 90-day metrics with a 5-candle cooldown, now applied to scheduled paper evaluation.
- Paper risk handling now follows the author's price-action invalidation guidance for stops and part-book/trail guidance for exits.
- Previous provider-backed open paper trades were cancelled because their retracement was too shallow under the tuned LRHR band.
- Non-paper workstreams are tracked separately from the forward paper evidence gate so ingestion, monitoring, documentation, and input-bound setup can continue in parallel.
- Healthwatch, daily offsite backups, and weekly restore drills are active.
- Live trading remains disabled.

## Timeline If Inputs Are Available Today

| Phase | Target Date | Estimate | Owner | Status |
| --- | --- | --- | --- | --- |
| GitHub sync | 2026-05-15 | Done | User + Codex | Current commits pushed |
| Real market data provider | 2026-05-15 | Done | Shared | DhanHQ active for NIFTY and BANKNIFTY |
| Historical NIFTY/BANKNIFTY candles | 2026-05-15 | Done | Shared | Dhan provider-backed candles loaded |
| Historical paper replay evidence | 2026-05-16 | Done | Codex | Timestamp-correct replay validations saved |
| Paper-trade evidence run | 2026-05-15 to 2026-05-24 | 5 trading sessions minimum | System | Provider candles active; collecting signals and exits |
| Rule tuning from evidence | 2026-05-25 to 2026-05-29 | 3-5 days | Codex + User review | Replay tuning done; forward tuning waits for paper exits |
| External alerts | 2026-05-15 | 30-60 minutes after webhook URL | Shared | Hook is built, URL needed |
| Blog/X production ingestion | 2026-05-16 to 2026-05-17 | Done | System | Illango/JustNifty blog feeds and approved X feeds configured |
| Telegram ingestion | On hold | Optional | User | Set aside because content is expected to duplicate blog posts |
| OpenAI extraction enrichment | 2026-05-16 | Done | Shared | Configured and active for optional enrichment |
| Live-readiness review | 2026-06-01 or later | 1 review session after evidence gates pass | User | Not ready yet |

## Readiness Gates Before Live Trading

Do not enable live execution until all gates are reviewed:

- At least 20 closed paper trades per instrument being considered.
- At least 100 provider-backed historical candles per instrument; smoke/manual/demo data is excluded.
- Net realized P&L is positive for the review window.
- Average R-multiple is positive.
- No single failed strategy export is being promoted as production evidence.
- Provider-backed replay and paper evidence agree with the intended rule behavior.
- Timestamp-correct historical paper replay validation passes for each reviewed instrument.
- Daily offsite backups and weekly restore drill are healthy.
- Kill switch remains tested and available.
- User explicitly approves the move from paper to live.

The dashboard `Timeline` page and API endpoint `/readiness` separate required live-readiness gates, optional advisories, and parallel workstreams such as RSS/blog ingestion, X ingestion, OpenAI enrichment, and external alert receiver configuration. Telegram remains optional and on hold.

## Best Next Actions

1. Let paper trading run for at least five trading sessions before reviewing live readiness.
2. Let the scheduler wait for new NIFTY and BANKNIFTY LRHR setups, then reconcile target or stop exits.
3. Keep Dhan, Blogspot/WordPress, X, and extraction workers running through the live market session.
4. Provide or choose an external alert receiver URL for `.healthwatch.env` only if alerts outside Codex are needed.
