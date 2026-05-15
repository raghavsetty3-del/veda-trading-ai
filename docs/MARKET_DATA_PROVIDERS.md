# Market Data Providers

Veda can ingest candle CSV from an HTTP URL, `file://` URL, local VM path, Angel One SmartAPI `angelone://` source, or DhanHQ `dhan://` source.

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
    "max_rows":10000
  }'
```

## Scheduled Sources

Set `MARKET_DATA_SOURCES` in `.env` as semicolon-separated entries:

```text
MARKET_DATA_SOURCES=NIFTY|5m|/home/traderadmin/data/nifty_5m.csv;BANKNIFTY|5m|https://example.com/banknifty_5m.csv
MARKET_DATA_INGEST_INTERVAL_SECONDS=900
MARKET_DATA_INGEST_LIMIT=10000
MARKET_DATA_INGEST_ON_START=false
```

Angel One SmartAPI sources use this format:

```text
MARKET_DATA_SOURCES=NIFTY|5m|angelone://NSE/99926000;BANKNIFTY|5m|angelone://NSE/99926009
```

See `docs/ANGELONE_MARKET_DATA.md` for credentials and operational notes.

DhanHQ sources use this format:

```text
MARKET_DATA_SOURCES=NIFTY|5m|dhan://IDX_I/13?instrument=INDEX;BANKNIFTY|5m|dhan://IDX_I/25?instrument=INDEX
```

See `docs/DHAN_MARKET_DATA.md` for credentials and operational notes.

Then run manually:

```bash
curl -X POST http://localhost:8000/market/provider/ingest-configured
```

The scheduler runs configured provider ingestion on the configured interval, and stored candles immediately feed:

- market snapshots;
- stored-candle replay;
- scheduled paper-trading evaluation.

When a provider returns more candles than the configured ingest limit, Veda keeps the newest candles so replay and paper-trading checks remain anchored to current market structure.

## Live-Readiness Evidence

The `/readiness` report shows both total candle counts and provider-backed candle counts. Live-readiness uses provider-backed counts only.

Sources whose labels contain `manual`, `smoke`, `test`, `demo`, or `sample` are treated as non-production evidence. They remain useful for deployment checks, but they do not satisfy the historical candle gate.

Use source labels that identify the real provider, for example:

```text
provider:zerodha:NIFTY:5m
provider:csv-vendor:BANKNIFTY:5m
```
