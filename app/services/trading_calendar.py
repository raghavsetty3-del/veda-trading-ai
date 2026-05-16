from datetime import datetime, time
from zoneinfo import ZoneInfo


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


def is_regular_nse_session_now() -> bool:
    return is_regular_nse_session(datetime.now(ZoneInfo("Asia/Kolkata")))


def candle_has_activity(open_price: float | None, high: float | None, low: float | None, close: float | None, volume: float | None) -> bool:
    prices = [value for value in [open_price, high, low, close] if value is not None]
    has_range = high is not None and low is not None and float(high) != float(low)
    has_price_change = len(prices) >= 2 and len({float(value) for value in prices}) > 1
    has_volume = volume is not None and float(volume) > 0
    return has_range or has_price_change or has_volume


def candle_session_label(
    symbol: str,
    timeframe: str,
    ts: datetime,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    volume: float | None = None,
) -> str:
    if not (is_nse_index_symbol(symbol) and is_intraday_timeframe(timeframe)):
        return "unrestricted"
    if is_regular_nse_session(ts):
        return "regular"
    if candle_has_activity(open_price, high, low, close, volume):
        return "inferred_special_session"
    return "off_session_flat_snapshot"


def should_use_candle(
    symbol: str,
    timeframe: str,
    ts: datetime,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    volume: float | None = None,
) -> bool:
    if is_nse_index_symbol(symbol) and is_intraday_timeframe(timeframe):
        return candle_session_label(symbol, timeframe, ts, open_price, high, low, close, volume) in {
            "regular",
            "inferred_special_session",
        }
    return True
