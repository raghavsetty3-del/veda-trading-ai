from sqlalchemy.orm import Session

from app.models import MarketCandle
from app.services.instrument_profiles import apply_instrument_profile


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
