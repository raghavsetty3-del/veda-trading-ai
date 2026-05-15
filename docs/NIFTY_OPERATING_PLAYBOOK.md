# Nifty Operating Playbook

This playbook translates the extracted JustNifty context into a daily Veda workflow.

## Daily Preparation

1. Review higher timeframe context.
   - Week/month for investment and major trend context.
   - Day/hour for positional context.
   - 15-minute/5-minute for intraday execution.

2. Mark structure.
   - HH/HL means bullish structure.
   - LH/LL means bearish structure.
   - Mixed or overlapping structure means wait unless a high-conviction reversal is forming.

3. Mark zones.
   - Prior cluster support/resistance.
   - Trendlines and channels.
   - Retracement levels: 38.2, 50, 61.8, 78.6.
   - Relevant EMA areas.

4. Establish EMA bias.
   - 5-minute 200 EMA for conservative intraday direction.
   - 1-minute 200 EMA only for aggressive execution.
   - Hour 21/200 EMA for positional intraday context.
   - Day 8/21 EMA for swing context.

## Setup Evaluation

Use the `Setup Evaluator` dashboard page with a market-context JSON object.

Preferred fields:

```json
{
  "symbol": "NIFTY",
  "timeframe": "5m",
  "market_structure": "HH_HL",
  "price_above_ema200": true,
  "retracement_pct": 50.0,
  "distance_from_ema_pct": 0.7,
  "higher_timeframe_bias": "bullish",
  "at_channel_or_envelope_extreme": false,
  "core_tools_aligned": true,
  "emotional_state": "calm",
  "adx": 24
}
```

## Decision Rules

- `long_bias`: look only for long setups unless a separate reversal case is validated.
- `short_bias`: look only for short setups unless a separate reversal case is validated.
- `neutral_wait`: context is incomplete or mixed; observe.
- `wait`: risk flags are active; avoid fresh discretionary trades.

In the automated paper-trading path, `long_bias` and `short_bias` are treated as tradable setup signals only when price action structure, 200 EMA direction, LRHR retracement, and higher-timeframe direction are aligned. LRHR retracement is implemented as the 38.2 to 78.6 zone; shallower pullbacks are treated as chase risk.

## Fresh Entry Checklist

- Price action supports direction.
- 200 EMA supports direction.
- Retracement is in the 38.2 to 78.6 LRHR zone.
- Entry is near retracement, EMA, trendline, channel, or support/resistance confluence.
- Price is not too extended from the relevant EMA.
- Higher timeframe context is known.
- Emotional state is calm.
- Stop and invalidation are known before entry.

## Profit Management

- Part book near channel boundaries, envelope extremes, or target zones.
- Trail the remainder.
- Do not convert a planned trade into a hope-based hold.
- If structure invalidates, exit or reduce.

## No-Trade Conditions

- Low ADX/choppy regime.
- Pullback is too shallow or too deep for the LRHR zone.
- Price far away from the relevant EMA after expansion.
- Revenge trading or repeated plan violation.
- Conflicting structure across timeframes.
- No clear invalidation level.

## Weekly Review

Every weekend, review:

- Whether Veda stance matched actual market behavior.
- Whether the entry was a chase or an LRHR entry.
- Whether exits followed the part-book/trail plan.
- Which validation cases failed.
- Which new rules should be drafted.
