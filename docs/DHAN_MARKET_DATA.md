# DhanHQ Market Data

Veda can use DhanHQ historical candle APIs through the existing provider ingestion bridge.

## Step-by-Step Setup

1. Log in to Dhan Web: `https://web.dhan.co`.
2. Open **My Profile**.
3. Open **Access DhanHQ APIs**.
4. Confirm **Data APIs** are enabled/subscribed. Historical candle APIs may require a Data API subscription.
5. Choose one authentication path:
   - Quick path: generate a 24-hour **Access Token** and share it for testing.
   - Better path: set up **TOTP** in DhanHQ API settings, then share `DHAN_CLIENT_ID`, `DHAN_PIN`, and `DHAN_TOTP_SECRET` so Veda can generate the access token automatically.
6. If Dhan asks for a static IP, use the Azure VM public IP:

```text
20.235.64.162
```

The official Dhan docs say static IP is mandatory for order placement APIs. We are using Dhan for data first, while live order placement stays disabled.

## Credentials

Store these only in the VM `.env`; do not commit them:

```text
DHAN_CLIENT_ID=
DHAN_ACCESS_TOKEN=
DHAN_PIN=
DHAN_TOTP_SECRET=
DHAN_HISTORY_DAYS=90
DHAN_TOKEN_CACHE_PATH=/app/data/dhan_access_token.json
```

You can provide either:

- `DHAN_ACCESS_TOKEN` for immediate 24-hour testing; or
- `DHAN_CLIENT_ID`, `DHAN_PIN`, and `DHAN_TOTP_SECRET` for automatic token generation.

## Provider Source Format

Use `dhan://EXCHANGE_SEGMENT/SECURITY_ID` inside `MARKET_DATA_SOURCES`:

```text
MARKET_DATA_SOURCES=NIFTY|5m|dhan://IDX_I/13?instrument=INDEX;BANKNIFTY|5m|dhan://IDX_I/25?instrument=INDEX
```

Optional query parameters:

```text
dhan://IDX_I/13?instrument=INDEX&interval=5&fromDate=2026-05-15%2009:15:00&toDate=2026-05-15%2015:30:00
```

For daily candles:

```text
NIFTY|1d|dhan://IDX_I/13?instrument=INDEX
```

Verify index security IDs in the official Dhan instrument list before production use:

```text
https://images.dhan.co/api-data/api-scrip-master.csv
https://images.dhan.co/api-data/api-scrip-master-detailed.csv
```

## Check Status

```bash
curl http://localhost:8000/market/dhan/status
curl http://localhost:8000/market/provider/status
```

## Run Ingestion

```bash
curl -X POST http://localhost:8000/market/provider/ingest-configured
```

## Notes

- Dhan intraday historical data supports minute intervals `1`, `5`, `15`, `25`, and `60`.
- Dhan documents a 90-day maximum per intraday request. Veda defaults to `DHAN_HISTORY_DAYS=90` for a deeper replay/tuning sample.
- Keep `MARKET_DATA_INGEST_LIMIT` high enough for the selected interval. The default is `10000`, and capped imports retain the newest candles.
- Veda stores generated Dhan access tokens in `DHAN_TOKEN_CACHE_PATH` so API and scheduler containers reuse the same token instead of hitting Dhan's token-generation rate limit.
- Keep live trading disabled while validating feed quality, candle gaps, symbol IDs, and paper-trade behavior.
