# Next Stage v0.3

Recommended next build:
1. Let Dhan-backed EMA200 paper trading continue until each reviewed instrument has at least 20 realized closed outcomes.
2. Review accumulated paper-trade exit evidence before enabling any live execution.
3. Keep all other workstreams moving in parallel; see `docs/PARALLEL_COMPLETION.md`.
4. Keep historical paper replay validation passing with timestamp-correct higher-timeframe context for every reviewed instrument.
5. Configure a real external webhook receiver for healthwatch alerts after the webhook URL is available.
6. Monitor weekly restore drill logs and audit events.
7. Configure production blog RSS feeds and live Telegram listener credentials after inputs are available.
8. Continue tuning from provider-backed rolling replay sweeps and realized paper-trade metrics.

See `docs/TIMELINE.md` for dates, estimates, blockers, and live-readiness gates.
