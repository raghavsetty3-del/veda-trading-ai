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
- A dashboard page now surfaces NIFTY tuning reports and top candidates without opening JSON files.
- BANKNIFTY and NIFTY replay-only tuning have produced reviewed per-symbol paper exit candidates.
- Scheduled paper trading uses per-symbol paper exit overrides for NIFTY and BANKNIFTY.
- Promotion readiness is exposed per symbol; live promotion remains blocked until forward paper evidence is ready.
- Promotion drawdown gates use symbol-scaled tuning evidence so NIFTY is not judged by BANKNIFTY-sized point thresholds.
- System Evidence dashboard shows latest scheduler, ingestion, extraction, X/blog, and paper-exit override audit status.
- Chart Insight Review dashboard exposes chart-backed extracted insights, author mechanisms, price levels, pattern notes, and source previews.
- Chart visual extraction now tracks whether image analysis was attempted separately from whether chart URLs were archived.

## Current Evidence

- NIFTY current tuned 500-trade replay: part-book R 0.75, part-book fraction 0.6, trail lookback 4, cooldown 5; profit factor 3.12, sell profit factor 3.55 across 171 sell trades.
- BANKNIFTY current tuned 500-trade replay: part-book R 1.25, part-book fraction 0.6, trail lookback 3, cooldown 5; profit factor 2.45, net 31200.27 points, max drawdown 1619.22 points; sell-side profit factor 1.985 across 234 sell trades.
- The earlier BANKNIFTY baseline weak pocket was sell-side profit factor 1.626 with max drawdown 2024.03 points; tuned validation improved sell profit factor and reduced drawdown.
- Effective paper scheduler configs: NIFTY uses R 0.75, fraction 0.6, trail 4, cooldown 5; BANKNIFTY uses R 1.25, fraction 0.6, trail 3, cooldown 5.
- Forward paper evidence is not ready yet: NIFTY has 1 closed paper trade; BANKNIFTY has 0 closed paper trades.

## Pending

- Wait for regular market sessions to collect at least 20 closed forward paper trades per symbol.
- Confirm forward paper P&L remains positive for NIFTY and BANKNIFTY.
- Finish processing the remaining blog/chart extraction backlog.
- Keep collecting forward paper evidence under the per-symbol exit settings before any live review.
- Keep validating chart-image extraction quality against the author's chart annotations.
- Push any local commits that require laptop SSH passphrase entry.

## On Hold

- Telegram ingestion, because current Telegram content is expected to duplicate blog posts.
- External public sharing/webhook alerts, because external use is not needed for now.
- Live trading or broker order placement, until readiness gates and manual review pass.

## Next Actions That Do Not Depend On Market Sessions

- Keep reviewing per-symbol promotion readiness and latest background jobs in the System Evidence dashboard.
- Continue chart extraction and author-mechanism enrichment in the background.
- Requeue older chart-backed sources in controlled batches when they were archived before visual image-analysis tracking existed.
- Convert stable chart/mechanism patterns into additional candidate rules only after enough repeated evidence is visible.
