# Paper Evidence Review

Date: 2026-05-16

This review is required before any live-trading setting changes. It applies separately to NIFTY and BANKNIFTY.

## Minimum Evidence

- At least 20 realized closed paper trades for the instrument.
- Positive realized P&L for the review window.
- Positive average R-multiple.
- Profit factor reviewed with enough losing trades to be meaningful.
- No open paper trade with unmanaged risk.

Review the current snapshot in `/paper/evidence-state` and the change log in
`/paper/evidence-history`. The dashboard surfaces both on the Paper Trading page,
and the Timeline page shows the latest compact history.

## Author Alignment Checks

Every reviewed winning and losing sample should answer:

- Did entry follow HH/HL for long or LH/LL for short?
- Was price on the correct side of the 200 EMA?
- Was the pullback inside the LRHR zone: 38.2, 50, 61.8, or 78.6?
- Was higher-timeframe direction aligned, not merely known?
- Was price not extended from the relevant EMA or structure?
- Was ADX/regime acceptable for the instrument?
- Was the stop based on price-action invalidation before entry?
- Did the exit follow part-book and trailing logic?

## Failure Review

Do not tune from one loss. Group losses by repeated cause:

| Cause | Review Action |
| --- | --- |
| Choppy/low ADX | Raise caution or reduce setups in that regime |
| Shallow retracement | Keep or tighten LRHR minimum |
| Extended entry | Keep no-chase filter strict |
| Mixed higher timeframe | Keep MTF alignment strict |
| Stop too close/wide | Recheck structure-based invalidation logic |
| Profit gave back | Recheck part-book and trail settings |

## Promotion Decision

Only consider live review when:

- Required readiness gates are green.
- Historical replay and forward paper evidence agree.
- NIFTY and/or BANKNIFTY are reviewed independently.
- The failed BankNifty trade export remains excluded from promotion.
- User explicitly approves live review.

Live execution must remain disabled until that approval is recorded.
