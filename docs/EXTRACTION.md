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

For large backlogs, the Docker stack includes a continuous extraction runner:

```bash
docker compose up -d --build extraction-backlog
docker logs -f veda-trading-ai-extraction-backlog-1
```

It calls `/extraction/process-pending` in controlled batches until the archive is complete, then idles and checks again later. It does not alter live trading settings.

```text
EXTRACTION_BACKLOG_BATCH_LIMIT=25
EXTRACTION_BACKLOG_SLEEP_SECONDS=30
EXTRACTION_BACKLOG_DONE_SLEEP_SECONDS=900
EXTRACTION_BACKLOG_ERROR_SLEEP_SECONDS=300
```

The compose stack runs three sharded backlog workers (`extraction-backlog`, `extraction-backlog-1`, and `extraction-backlog-2`). Each worker passes its `worker_index` and shared `worker_count` to `/extraction/process-pending`, so simultaneous chart analysis avoids duplicate source rows.

```bash
docker logs -f veda-trading-ai-extraction-backlog-1
docker logs -f veda-trading-ai-extraction-backlog-1-1
docker logs -f veda-trading-ai-extraction-backlog-2-1
```

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

The strategy evaluator also includes a conservative ML-style analysis layer for regime, trend, volatility, pullback quality, author-rule alignment, and anomaly risk. This layer is advisory and can block weak paper setups, but it does not enable live trading or override required author-rule gates:

```bash
curl "http://localhost:8000/ml/snapshot?symbol=NIFTY&timeframe=5m&limit=250"
```

For NIFTY/BANKNIFTY intraday candles, provider ingestion and analysis accept regular NSE session rows and also accept off-hours candles that show real activity, such as price movement or volume. Flat zero-volume off-hours provider snapshots are ignored. This keeps special trading sessions available for present/future analysis without letting stale weekend snapshots become strategy evidence.

The scheduled paper engine also skips new index entries outside the regular NSE session unless the latest usable candle is classified as an inferred special-session candle, while still allowing reconciliation/evidence checks.
