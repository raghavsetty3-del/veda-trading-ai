# Market Data Providers

Veda can ingest candle CSV from an HTTP URL, `file://` URL, or local VM path. This is the provider bridge until a broker/vendor-specific connector is configured.

## CSV Format

Required columns:

```text
ts,open,high,low,close
```

Optional columns:

```text
symbol,timeframe,volume,source
```

Accepted timestamp column names are `ts`, `timestamp`, `datetime`, or `date`.

## One-Off Import

```bash
curl -X POST http://localhost:8000/market/provider/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol":"NIFTY",
    "timeframe":"5m",
    "source_url":"/home/traderadmin/data/nifty_5m.csv",
    "source_name":"provider:nifty-csv",
    "max_rows":5000
  }'
```

## Scheduled Sources

Set `MARKET_DATA_SOURCES` in `.env` as semicolon-separated entries:

```text
MARKET_DATA_SOURCES=NIFTY|5m|/home/traderadmin/data/nifty_5m.csv;BANKNIFTY|5m|https://example.com/banknifty_5m.csv
MARKET_DATA_INGEST_INTERVAL_SECONDS=900
MARKET_DATA_INGEST_LIMIT=5000
MARKET_DATA_INGEST_ON_START=false
```

Then run manually:

```bash
curl -X POST http://localhost:8000/market/provider/ingest-configured
```

The scheduler runs configured provider ingestion on the configured interval, and stored candles immediately feed:

- market snapshots;
- stored-candle replay;
- scheduled paper-trading evaluation.

## Live-Readiness Evidence

The `/readiness` report shows both total candle counts and provider-backed candle counts. Live-readiness uses provider-backed counts only.

Sources whose labels contain `manual`, `smoke`, `test`, `demo`, or `sample` are treated as non-production evidence. They remain useful for deployment checks, but they do not satisfy the historical candle gate.

Use source labels that identify the real provider, for example:

```text
provider:zerodha:NIFTY:5m
provider:csv-vendor:BANKNIFTY:5m
```
