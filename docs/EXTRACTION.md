# Knowledge Extraction

The extraction workbench converts archived source text into structured insight records.

Extraction is deterministic by default and can be enriched with OpenAI when `OPENAI_EXTRACTION_ENABLED=true` and `OPENAI_API_KEY` is configured:

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

The scheduler can also process pending source documents automatically:

```text
SOURCE_EXTRACTION_INTERVAL_SECONDS=1800
SOURCE_EXTRACTION_LIMIT=25
SOURCE_EXTRACTION_ON_START=false
```

This keeps newly ingested RSS, Telegram, or manually archived source material flowing into insights and rule suggestions without changing live trading settings.
