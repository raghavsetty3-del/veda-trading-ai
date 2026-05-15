# Angel One SmartAPI Market Data

Veda can use Angel One SmartAPI as a market-data source through the existing provider ingestion bridge.

## Required Credentials

Store these only in the VM `.env`; do not commit them:

```text
ANGELONE_API_KEY=
ANGELONE_CLIENT_CODE=
ANGELONE_PIN=
ANGELONE_TOTP_SECRET=
ANGELONE_CLIENT_PUBLIC_IP=
ANGELONE_CLIENT_LOCAL_IP=127.0.0.1
ANGELONE_CLIENT_MAC=00:00:00:00:00:00
ANGELONE_HISTORY_DAYS=5
```

`ANGELONE_TOTP_SECRET` is the base32 QR/setup key used to generate the current 6-digit TOTP. Veda computes the current TOTP at login time.

## Provider Source Format

Use `angelone://EXCHANGE/SYMBOLTOKEN` inside `MARKET_DATA_SOURCES`:

```text
MARKET_DATA_SOURCES=NIFTY|5m|angelone://NSE/99926000;BANKNIFTY|5m|angelone://NSE/99926009
```

Optional query parameters:

```text
angelone://NSE/99926000?interval=FIVE_MINUTE&fromdate=2026-05-15%2009:15&todate=2026-05-15%2015:30
```

If dates are omitted, Veda requests the last `ANGELONE_HISTORY_DAYS` calendar days. If interval is omitted, Veda maps local timeframes such as `1m`, `5m`, `15m`, `1h`, and `1d` to Angel One intervals.

## Check Status

```bash
curl http://localhost:8000/market/angelone/status
curl http://localhost:8000/market/provider/status
```

## Run Ingestion

```bash
curl -X POST http://localhost:8000/market/provider/ingest-configured
```

Angel One candle data is stored with provider labels such as `provider:NIFTY:5m`, so it counts as provider-backed evidence in `/readiness`.

## Notes

- Index token examples above are included as operational defaults, but verify symbol tokens in Angel One SmartAPI before production use.
- Keep live trading disabled while validating feed quality, missing candles, timezones, and paper-trade behavior.
- If Angel One returns login or rate-limit errors, ingestion fails safely and reports the API message in `parse_errors`.
