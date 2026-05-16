from datetime import datetime, time


NSE_INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY"}
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)


def is_intraday_timeframe(timeframe: str | None) -> bool:
    value = (timeframe or "").lower()
    return value.endswith("m") or value.endswith("h")


def is_nse_index_symbol(symbol: str | None) -> bool:
    return (symbol or "").upper() in NSE_INDEX_SYMBOLS


def is_regular_nse_session(ts: datetime) -> bool:
    naive = ts.replace(tzinfo=None)
    return naive.weekday() < 5 and NSE_OPEN <= naive.time() <= NSE_CLOSE


def should_use_candle(symbol: str, timeframe: str, ts: datetime) -> bool:
    if is_nse_index_symbol(symbol) and is_intraday_timeframe(timeframe):
        return is_regular_nse_session(ts)
    return True
