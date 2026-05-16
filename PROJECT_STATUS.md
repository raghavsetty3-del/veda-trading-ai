# Veda Trading AI Project Status

Last updated: 2026-05-16

## Completed

- GitHub repository connected and the main project pushed.
- Azure VM deployment is running with API, dashboard, Postgres, Redis, scheduler, and extraction workers.
- Live trading is disabled and readiness gates block live review until enough forward paper evidence exists.
- Dhan market data is configured for NIFTY and BANKNIFTY.
- Historical Dhan backfill is loaded across trend, downtrend, sideways, and COVID-era regimes where provider data is available.
- Author framework from the book/blog is mapped into rule evaluation, paper trading, extraction, and validation workflows.
- Blog ingestion is limited to Illango/JustNifty sources; Telegram is on hold because the content overlaps with the blog feed.
- X/Twitter ingestion is configured for approved JustNifty accounts.
- OpenAI extraction enrichment is enabled for text and chart-backed source extraction.
- Historical replay validation is saved for NIFTY and BANKNIFTY.
- Replay risk reporting is generated with drawdown, monthly, side-wise, regime, and structure breakdowns.
- A dashboard page now surfaces replay risk reports without opening JSON or CSV files.
- BANKNIFTY sell-side replay-only tuning has started with a parameter sweep script; it does not change live or paper settings.

## Current Evidence

- NIFTY historical replay: 500 realized trades, profit factor 2.39, net 5056.55 points, max drawdown 198.96 points.
- BANKNIFTY historical replay: 500 realized trades, profit factor 1.881, net 22044.97 points, max drawdown 2024.03 points.
- BANKNIFTY sell side is the weakest replay pocket: profit factor 1.626, max drawdown 2024.03 points.
- BANKNIFTY sell-side quick tuning screen: best starter candidate uses part-book fraction 0.6 and trail lookback 2, improving 100-trade screened sell drawdown by 404.81 points and sell profit factor from 1.331 to 1.602.
- Forward paper evidence is not ready yet: NIFTY has 1 closed paper trade; BANKNIFTY has 0 closed paper trades.

## Pending

- Wait for regular market sessions to collect at least 20 closed forward paper trades per symbol.
- Confirm forward paper P&L remains positive for NIFTY and BANKNIFTY.
- Finish processing the remaining blog/chart extraction backlog.
- Validate BANKNIFTY sell-side tuning candidates on the full 500-trade replay before promoting any parameter change.
- Keep validating chart-image extraction quality against the author's chart annotations.
- Push any local commits that require laptop SSH passphrase entry.

## On Hold

- Telegram ingestion, because current Telegram content is expected to duplicate blog posts.
- External public sharing/webhook alerts, because external use is not needed for now.
- Live trading or broker order placement, until readiness gates and manual review pass.

## Next Actions That Do Not Depend On Market Sessions

- Review the new Replay Risk Report dashboard page after deployment.
- Run the larger BANKNIFTY sell-side tuning grid after the first-pass candidate is reviewed.
- Add a dashboard view for tuning candidates if the first sweep produces useful alternatives.
- Continue chart extraction and author-mechanism enrichment in the background.
