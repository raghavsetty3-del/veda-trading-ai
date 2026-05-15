# Veda Trading System Timeline

Date: 2026-05-15

This timeline assumes the current deployed Azure VM remains the target environment and that live trading stays disabled until paper evidence is strong enough to review.

## Current State

Completed as of 2026-05-15:

- Azure deployment is live behind Basic Auth.
- NIFTY and BANKNIFTY instrument profiles are present.
- Rule, setup, scenario, replay, paper-trade, and validation workflows are present.
- Paper trades can record exits, realized P&L, and R-multiple.
- BankNifty strategy trade export was imported and recorded as failed performance evidence because net P&L was negative.
- Healthwatch, daily offsite backups, and weekly restore drills are active.
- Live trading remains disabled.

## Timeline If Inputs Are Available Today

| Phase | Target Date | Estimate | Owner | Status |
| --- | --- | --- | --- | --- |
| GitHub sync | 2026-05-15 | 10 minutes | User | Blocked by SSH passphrase in interactive laptop shell |
| Real market data provider | 2026-05-15 to 2026-05-16 | 0.5-1 day after URL/API credentials | Shared | Waiting for provider details |
| Historical NIFTY/BANKNIFTY candles | 2026-05-16 to 2026-05-17 | 0.5-1 day after files/source | Shared | Waiting for OHLC data source |
| Paper-trade evidence run | 2026-05-18 to 2026-05-24 | 5 trading sessions minimum | System | Needs live/provider candles |
| Rule tuning from evidence | 2026-05-25 to 2026-05-29 | 3-5 days | Codex + User review | Depends on paper evidence |
| External alerts | 2026-05-15 | 30-60 minutes after webhook URL | Shared | Hook is built, URL needed |
| Telegram/blog production ingestion | 2026-05-16 to 2026-05-17 | 0.5-1 day after credentials | Shared | Waiting for Telegram/RSS details |
| OpenAI extraction enrichment | 2026-05-16 | 30-60 minutes after API key | Shared | Optional, disabled until configured |
| Live-readiness review | 2026-06-01 or later | 1 review session after evidence gates pass | User | Not ready yet |

## Readiness Gates Before Live Trading

Do not enable live execution until all gates are reviewed:

- At least 20 closed paper trades per instrument being considered.
- Net realized P&L is positive for the review window.
- Average R-multiple is positive.
- No single failed strategy export is being promoted as production evidence.
- Provider-backed replay and paper evidence agree with the intended rule behavior.
- Daily offsite backups and weekly restore drill are healthy.
- Kill switch remains tested and available.
- User explicitly approves the move from paper to live.

## Best Next Actions

1. Push local commits from the laptop shell:

```bash
cd ~/Downloads/veda-trading-ai-v0.2
git push
```

2. Provide one real market-data source:

```text
SYMBOL|timeframe|source_url
NIFTY|5m|https://...
BANKNIFTY|5m|https://...
```

3. Provide or choose an external alert receiver URL for `.healthwatch.env`.

4. Let paper trading run for at least five trading sessions before reviewing live readiness.
