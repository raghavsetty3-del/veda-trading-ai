# BankNifty Operating Notes

BankNifty uses the same Veda/JustNifty framework as Nifty, but it needs a separate risk profile because it is usually more volatile.

## Shared Framework

- Price action remains primary.
- Use HH/HL for bullish structure and LH/LL for bearish structure.
- Use retracement and channel zones for LRHR entries.
- Use 200 EMA as the directional bias filter.
- Avoid revenge trading, chasing, and low-quality sideways setups.

## BankNifty Calibration

- EMA extension limit: 2.0 percent by default.
- Low ADX threshold: 20 by default.
- Use smaller quantity than Nifty for the same account risk.
- Use wider stop placement because BankNifty can reverse sharply and travel further intraday.
- Require cleaner multi-timeframe context before classifying a setup as high conviction.

## Practical Setup Guidance

- For conservative intraday trades, use the 5-minute 200 EMA as the major bias filter.
- Treat 1-minute structure as execution detail, not the main decision source.
- If BankNifty is above 200 EMA but ADX is below its profile threshold, Veda should wait.
- If price is extended but still inside the BankNifty threshold, Veda may continue evaluating the setup rather than blocking solely due to extension.
- If price is at a channel or envelope extreme, prefer part booking or waiting for a pullback rather than fresh chase entries.

## Validation Focus

- Compare BankNifty-specific stop width and extension thresholds against Nifty.
- Track false positives in low-ADX BankNifty sessions.
- Track whether the 2.0 percent EMA-extension threshold is too loose or too strict.
- Track whether 5-minute 200 EMA gives cleaner BankNifty bias than 1-minute 200 EMA.
