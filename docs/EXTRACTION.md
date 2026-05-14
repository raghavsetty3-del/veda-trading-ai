# Knowledge Extraction

The extraction workbench converts archived source text into structured insight records.

Current extraction is deterministic and local:

- Symbols: `NIFTY`, `BANKNIFTY`
- Timeframe hints: `5m`, `15m`, `1h`, `1d`, etc.
- Bias: bullish or bearish text hints
- Concepts: price action, retracement, 200 EMA, ADX, channels, psychology, risk, profit booking
- Expected conditions: avoid chasing, wait for retracement, require risk control, avoid choppy markets

API:

```bash
curl -X POST "http://localhost:8000/extraction/process-pending?limit=50"
```

This marks source documents as processed and writes `ExtractedInsight` rows.

OpenAI-assisted extraction can be added later by replacing or enriching this deterministic extractor while preserving the same output shape.
