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
- A dashboard page now surfaces BANKNIFTY tuning reports and top candidates without opening JSON files.
- BANKNIFTY sell-side replay-only tuning has started with a parameter sweep script; it does not change live or paper settings.

## Current Evidence

- NIFTY historical replay: 500 realized trades, profit factor 2.39, net 5056.55 points, max drawdown 198.96 points.
- BANKNIFTY historical replay: 500 realized trades, profit factor 1.881, net 22044.97 points, max drawdown 2024.03 points.
- BANKNIFTY sell side is the weakest replay pocket: profit factor 1.626, max drawdown 2024.03 points.
- BANKNIFTY sell-side quick tuning screen: best starter candidate uses part-book fraction 0.6 and trail lookback 2, improving 100-trade screened sell drawdown by 404.81 points and sell profit factor from 1.331 to 1.602.
- BANKNIFTY best-candidate 500-trade replay: profit factor 2.348, net 26602.07 points, max drawdown 1619.22 points; sell-side profit factor 1.972 across 219 sell trades.
- BANKNIFTY full-grid top 500-trade replay: part-book R 1.25, part-book fraction 0.6, trail lookback 3; profit factor 2.45, net 31200.27 points, max drawdown 1619.22 points; sell-side profit factor 1.985 across 234 sell trades.
- Forward paper evidence is not ready yet: NIFTY has 1 closed paper trade; BANKNIFTY has 0 closed paper trades.

## Pending

- Wait for regular market sessions to collect at least 20 closed forward paper trades per symbol.
- Confirm forward paper P&L remains positive for NIFTY and BANKNIFTY.
- Finish processing the remaining blog/chart extraction backlog.
- Review full-grid BANKNIFTY tuning evidence before promoting any parameter change to scheduled paper trading.
- Keep validating chart-image extraction quality against the author's chart annotations.
- Push any local commits that require laptop SSH passphrase entry.

## On Hold

- Telegram ingestion, because current Telegram content is expected to duplicate blog posts.
- External public sharing/webhook alerts, because external use is not needed for now.
- Live trading or broker order placement, until readiness gates and manual review pass.

## Next Actions That Do Not Depend On Market Sessions

- Review the new Replay Risk Report dashboard page after deployment.
- Add paper-setting promotion controls after the full-grid BANKNIFTY candidate is manually reviewed.
- Add a dashboard view for tuning candidates if the first sweep produces useful alternatives.
- Continue chart extraction and author-mechanism enrichment in the background.
