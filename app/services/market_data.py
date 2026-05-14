from sqlalchemy.orm import Session

from app.models import MarketCandle
from app.services.instrument_profiles import apply_instrument_profile


def _pct_distance(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return abs(value - reference) / reference * 100


def _derive_rule_context(candles: list[MarketCandle]) -> dict:
    latest = candles[-1]
    closes = [item.close for item in candles]
    recent_high = max(item.high for item in candles[-20:])
    recent_low = min(item.low for item in candles[-20:])
    range_points = max(recent_high - recent_low, 0.0)
    ema_proxy = sum(closes[-50:]) / min(len(closes), 50)
    price_above_ema = latest.close >= ema_proxy

    if latest.close > closes[0] and price_above_ema:
        market_structure = "HH_HL"
        higher_timeframe_bias = "bullish"
    elif latest.close < closes[0] and not price_above_ema:
        market_structure = "LH_LL"
        higher_timeframe_bias = "bearish"
    else:
        market_structure = "sideways"
        higher_timeframe_bias = "mixed"

    if range_points:
        if market_structure == "LH_LL":
            retracement_pct = (latest.close - recent_low) / range_points * 100
        else:
            retracement_pct = (recent_high - latest.close) / range_points * 100
    else:
        retracement_pct = 100.0

    distance_from_ema_pct = _pct_distance(latest.close, ema_proxy)
    range_pct = range_points / latest.close * 100 if latest.close else 0.0

    return {
        "price_above_ema200": price_above_ema,
        "market_structure": market_structure,
        "retracement_pct": round(max(0.0, min(retracement_pct, 100.0)), 2),
        "distance_from_ema_pct": round(distance_from_ema_pct, 2),
        "higher_timeframe_bias": higher_timeframe_bias,
        "at_channel_or_envelope_extreme": latest.close >= recent_high * 0.995 or latest.close <= recent_low * 1.005,
        "core_tools_aligned": market_structure in {"HH_HL", "LH_LL"},
        "emotional_state": "calm",
        "adx": round(18 + min(range_pct * 4, 12), 2),
    }


def upsert_candle(db: Session, payload) -> MarketCandle:
    symbol = payload.symbol.upper()
    timeframe = payload.timeframe.lower()
    row = (
        db.query(MarketCandle)
        .filter_by(symbol=symbol, timeframe=timeframe, ts=payload.ts)
        .first()
    )
    values = payload.model_dump()
    values["symbol"] = symbol
    values["timeframe"] = timeframe
    if row:
        for key, value in values.items():
            setattr(row, key, value)
    else:
        row = MarketCandle(**values)
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_candles(db: Session, symbol: str, timeframe: str = "5m", limit: int = 50) -> list[MarketCandle]:
    safe_limit = max(1, min(limit, 500))
    return (
        db.query(MarketCandle)
        .filter_by(symbol=symbol.upper(), timeframe=timeframe.lower())
        .order_by(MarketCandle.ts.desc())
        .limit(safe_limit)
        .all()
    )


def market_snapshot(db: Session, symbol: str, timeframe: str = "5m", limit: int = 50) -> dict:
    candles = list(reversed(latest_candles(db, symbol, timeframe, limit)))
    if not candles:
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.lower(),
            "candles": 0,
            "market_context": apply_instrument_profile({"symbol": symbol.upper()}),
            "ready": False,
            "reason": "No candles available",
        }

    closes = [item.close for item in candles]
    latest = candles[-1]
    previous = candles[-2] if len(candles) > 1 else None
    recent_high = max(item.high for item in candles[-20:])
    recent_low = min(item.low for item in candles[-20:])
    momentum = "flat"
    if previous and latest.close > previous.close:
        momentum = "up"
    elif previous and latest.close < previous.close:
        momentum = "down"

    market_context = apply_instrument_profile({
        "symbol": symbol.upper(),
        "timeframe": timeframe.lower(),
        "last_price": latest.close,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "momentum": momentum,
        "close_change": latest.close - closes[0],
        "source": latest.source,
        "last_candle_at": latest.ts.isoformat(),
        **_derive_rule_context(candles),
    })
    return {
        "symbol": market_context["symbol"],
        "timeframe": timeframe.lower(),
        "candles": len(candles),
        "latest": {
            "ts": latest.ts.isoformat(),
            "open": latest.open,
            "high": latest.high,
            "low": latest.low,
            "close": latest.close,
            "volume": latest.volume,
            "source": latest.source,
        },
        "market_context": market_context,
        "ready": len(candles) >= 20,
        "reason": "Ready for evaluator context" if len(candles) >= 20 else "Need at least 20 candles",
    }
