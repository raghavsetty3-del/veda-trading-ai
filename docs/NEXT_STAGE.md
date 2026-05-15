# Next Stage v0.3

Recommended next build:
1. Push local commits to GitHub from an authenticated laptop shell.
2. Configure real market-data provider CSV/HTTP sources or broker credentials.
3. Load historical NIFTY and BANKNIFTY candle datasets through CSV or provider ingestion.
4. Let paper trading run for at least five trading sessions before live-readiness review.
5. Review accumulated paper-trade exit evidence before enabling any live execution.
6. Configure a real external webhook receiver for healthwatch alerts.
7. Monitor weekly restore drill logs and audit events.
8. Configure production blog RSS feeds and live Telegram listener credentials.
9. Run live Telegram ingestion after credentials/session are configured.
10. Add OpenAI-assisted extraction to enrich deterministic source extraction.
11. Tighten activation evidence from scenario coverage into provider-backed replay and paper-trade metrics.

See `docs/TIMELINE.md` for dates, estimates, blockers, and live-readiness gates.
