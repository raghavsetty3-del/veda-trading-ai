# JustNifty to Veda Extraction

Source: `Practical Guide to Trading and Investing` by VanIlango / JustNifty.

This document is a derived trading-system summary for Veda. It intentionally avoids reproducing the source text wholesale.

## Core Thesis

The trading system should be simple, mechanical, and context-first. It should prioritize price action, retracement, moving averages, and trendlines/channels. Elliott Wave can add context, but it is optional until the trader has enough practice.

Veda should not try to predict every move. It should classify market context, wait for low-risk high-reward zones, validate bias with multiple tools, size positions conservatively, and record whether expected behavior occurred.

## Primary Tools

1. Price action
   - Track HH/HL for bullish structure.
   - Track LH/LL for bearish structure.
   - Treat structure shifts as the first evidence of demand/supply change.
   - Use cluster support/resistance zones from prior struggle areas.

2. Retracement
   - Use retracement zones to avoid chasing.
   - Preferred zones include 38.2, 50, 61.8, and 78.6 percent depending on context.
   - A retracement trade should be confirmed by price action, EMA bias, and nearby support/resistance.

3. Moving averages
   - Use 200 EMA as a major intraday bias filter.
   - Use 21 EMA and 55 EMA for shorter-term structure and re-entry.
   - Use 8/21 EMA crossover for directional shifts on suitable timeframes.
   - Use weekly Fibonacci EMAs such as 55, 89, 144, and 233 for investment context.

4. Trendlines and channels
   - Draw trendlines/channels from meaningful tops and bottoms.
   - Channel top/bottom can identify low-risk entry or exit zones.
   - Mid-channel breaks can warn of acceleration or failure.

## Optional Context Tools

- Elliott Wave: useful for spotting 2.C, 4.C, and fifth-wave endings, but optional.
- MACD/RSI/divergence: secondary confirmation, especially near extremes.
- VWAP/AVWAP: helps identify who is in control and whether price is extended.
- VF-ST-EMA-CPR/VF Trade Table: reference tool after price-action context is known.

## Nifty Trading Rules

### Bias

- Prefer long trades above the relevant 200 EMA.
- Prefer short trades below the relevant 200 EMA.
- Use 5-minute 200 EMA for conservative intraday bias.
- Use 1-minute 200 EMA only for aggressive traders.
- In hour timeframe, track 21 EMA and 200 EMA.
- In day timeframe, track 8 EMA and 21 EMA.

### Entry

- Do not chase price after large expansion away from moving averages.
- Prefer pullbacks into LRHR zones.
- Confirm that price action aligns with the trade direction.
- For longs, prefer HH/HL or a shift from LH/LL to HH/HL.
- For shorts, prefer LH/LL or a shift from HH/HL to LH/LL.
- Use retracement, trendline/channel, and EMA confluence for high-conviction entries.

### Exit

- Book partial profits at extremes, channel boundaries, envelope extremes, or predefined target zones.
- Trail the balance after partial booking.
- Exit or reduce when price action invalidates the trade structure.
- Avoid counting wins during execution; focus on plan adherence.

### Re-entry

- Re-enter after profit booking only when price returns to a low-risk zone.
- Re-entry can be based on moving-average pullback after trend confirmation.
- Re-entry can also be based on wave/retracement context if Elliott Wave is being used.

### Sideways and Whipsaw Control

- Moving averages are less reliable in sideways markets.
- Avoid or reduce trades when structure is choppy, overlapping, or without directional follow-through.
- Prefer fewer, higher-conviction trades over frequent low-quality signals.

## Positional and Investment Context

- For positional Nifty, combine hour/day price action with 200 EMA bias, 21 EMA minor bias, retracement, and channels.
- For investments, study day/week/month charts.
- Build a quality-stock list first.
- Use deep retracements and reliable weekly EMAs as low-risk zones.
- For Nifty, 89-week EMA is an important reference; in strong downtrends, watch deeper Fibonacci EMAs.
- For individual stocks, discover the EMA that the stock repeatedly respects.
- Review portfolio charts on weekends for reversal candles, divergences, and major trend breaks.

## Risk and Psychology

- Keep expectations small and consistent.
- Accept the predefined loss before entering.
- Reduce fear by entering only where risk is clear.
- Avoid revenge trading by stopping after plan violation or emotional escalation.
- Mechanical execution is more important than excitement over patterns.
- Large leveraged positions are disallowed unless explicitly approved by a future risk module.

## Veda Implementation Mapping

The system should represent the source as:

- Author principles: durable trading beliefs
- Rule mappings: executable logic assumptions
- Validation cases: expected behavior checks
- Audit events: record of ingestion, rule creation, and future decisions

## Validation Themes

- Did Veda identify market structure correctly?
- Did Veda suppress trades in choppy conditions?
- Did Veda wait for retracement instead of chasing?
- Did Veda align the trade with 200 EMA bias?
- Did Veda identify support/resistance clusters?
- Did Veda part-book/trail rather than hold without plan?
- Did Veda refuse live-trading behavior unless paper validations passed?
