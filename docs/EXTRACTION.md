# Knowledge Extraction

The extraction workbench converts archived source text into structured insight records.

Extraction is deterministic by default and can be enriched with OpenAI when `OPENAI_EXTRACTION_ENABLED=true` and `OPENAI_API_KEY` is configured:

- Symbols: `NIFTY`, `BANKNIFTY`
- Timeframe hints: `5m`, `15m`, `1h`, `1d`, etc.
- Bias: bullish or bearish text hints
- Concepts: price action, retracement, 200 EMA, ADX, channels, psychology, risk, profit booking
- Expected conditions: avoid chasing, wait for retracement, require risk control, avoid choppy markets
- Chart context when image extraction is enabled: visible timeframes, indicators, price levels, pattern notes, trade context, and caveats
- Author mechanism: mindset, decision process, entry/exit mechanisms, risk logic, timeframe alignment, market-regime filters, automation candidates, and judgment that should stay review-only

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

Chart/image extraction is optional and uses archived `media_paths` from sources. It sends supported URLs directly to OpenAI and converts readable BMP/TIFF/extensionless chart images to PNG before analysis:

```text
OPENAI_IMAGE_EXTRACTION_ENABLED=true
OPENAI_IMAGE_EXTRACTION_MAX_IMAGES=3
OPENAI_IMAGE_FETCH_MAX_BYTES=6000000
```

Existing archived blog rows can be enriched with chart/media URLs from their saved HTML before extraction:

```bash
curl -X POST "http://localhost:8000/extraction/media/enrich?source_type=blog&limit=1000"
```
