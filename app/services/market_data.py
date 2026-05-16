from datetime import datetime

from sqlalchemy.orm import Session

from app.models import MarketCandle
from app.services.instrument_profiles import apply_instrument_profile
from app.services.ml_analysis import analyze_candles
from app.services.trading_calendar import should_use_candle

MAX_BULK_CANDLE_IMPORT = 20000
MAX_CANDLE_QUERY_LIMIT = 10000
HIGHER_TIMEFRAME_MAP = {
    "1m": ["5m", "15m"],
    "3m": ["15m", "1h"],
    "5m": ["15m", "1h"],
    "15m": ["1h"],
}


def _pct_distance(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0
    return abs(value - reference) / reference * 100


def _ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = (value * alpha) + (ema * (1 - alpha))
    return ema


def _derive_rule_context(candles: list[MarketCandle]) -> dict:
    latest = candles[-1]
    closes = [item.close for item in candles]
    recent_high = max(item.high for item in candles[-20:])
    recent_low = min(item.low for item in candles[-20:])
    range_points = max(recent_high - recent_low, 0.0)
    ema200 = _ema(closes[-200:], 200)
    price_above_ema = latest.close >= ema200

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

    distance_from_ema_pct = _pct_distance(latest.close, ema200)
    range_pct = range_points / latest.close * 100 if latest.close else 0.0
    extreme_band_points = range_points * 0.1 if range_points else 0.0
    at_recent_range_extreme = bool(
        range_points
        and (
            recent_high - latest.close <= extreme_band_points
            or latest.close - recent_low <= extreme_band_points
        )
    )

    return {
        "price_above_ema200": price_above_ema,
        "market_structure": market_structure,
        "retracement_pct": round(max(0.0, min(retracement_pct, 100.0)), 2),
        "distance_from_ema_pct": round(distance_from_ema_pct, 2),
        "higher_timeframe_bias": higher_timeframe_bias,
        "at_channel_or_envelope_extreme": at_recent_range_extreme,
        "core_tools_aligned": market_structure in {"HH_HL", "LH_LL"},
        "emotional_state": "calm",
        "adx": round(18 + min(range_pct * 4, 12), 2),
    }


def candle_market_context(symbol: str, timeframe: str, candles: list[MarketCandle]) -> dict:
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

    return apply_instrument_profile({
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


def _higher_timeframe_summary(candles: list[MarketCandle], timeframe: str) -> dict:
    context = _derive_rule_context(candles)
    latest = candles[-1]
    return {
        "timeframe": timeframe.lower(),
        "last_candle_at": latest.ts.isoformat(),
        "last_price": latest.close,
        "bias": context["higher_timeframe_bias"],
        "market_structure": context["market_structure"],
        "price_above_ema200": context["price_above_ema200"],
        "distance_from_ema_pct": context["distance_from_ema_pct"],
    }


def _consensus_bias(summaries: list[dict]) -> str:
    biases = [str(item.get("bias") or "unknown").lower() for item in summaries]
    directional = [item for item in biases if item in {"bullish", "bearish"}]
    if not directional:
        return "unknown"
    if len(directional) != len(biases):
        return "mixed"
    if all(item == "bullish" for item in directional):
        return "bullish"
    if all(item == "bearish" for item in directional):
        return "bearish"
    return "mixed"


def apply_higher_timeframe_context(
    db: Session,
    symbol: str,
    timeframe: str,
    market_context: dict,
    limit: int = 250,
    anchor_ts: datetime | None = None,
) -> dict:
    related_timeframes = HIGHER_TIMEFRAME_MAP.get(timeframe.lower(), [])
    summaries = []
    for higher_timeframe in related_timeframes:
        if anchor_ts:
            higher_rows = (
                db.query(MarketCandle)
                .filter_by(symbol=symbol.upper(), timeframe=higher_timeframe.lower())
                .filter(MarketCandle.ts <= anchor_ts)
                .order_by(MarketCandle.ts.desc())
                .limit(max(1, min(limit, MAX_CANDLE_QUERY_LIMIT)))
                .all()
            )
            candles = list(reversed(higher_rows))
        else:
            candles = list(reversed(latest_candles(db, symbol, higher_timeframe, limit)))
        if len(candles) < 20:
            continue
        summaries.append(_higher_timeframe_summary(candles, higher_timeframe))

    if not summaries:
        return {
            **market_context,
            "higher_timeframe_context": [],
            "higher_timeframe_bias_source": "entry_timeframe_fallback",
        }

    consensus = _consensus_bias(summaries)
    return {
        **market_context,
        "higher_timeframe_bias": consensus,
        "higher_timeframe_context": summaries,
        "higher_timeframe_bias_source": "+".join(item["timeframe"] for item in summaries),
        "higher_timeframe_agreement": "aligned" if consensus in {"bullish", "bearish"} else consensus,
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


def upsert_candles(db: Session, candles: list) -> dict:
    if len(candles) > MAX_BULK_CANDLE_IMPORT:
        raise ValueError(f"Bulk candle import is limited to {MAX_BULK_CANDLE_IMPORT} rows per request")

    created = 0
    updated = 0
    symbols: set[str] = set()
    timeframes: set[str] = set()

    for payload in candles:
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
        symbols.add(symbol)
        timeframes.add(timeframe)
        if row:
            for key, value in values.items():
                setattr(row, key, value)
            updated += 1
        else:
            db.add(MarketCandle(**values))
            created += 1

    db.commit()
    return {
        "received": len(candles),
        "created": created,
        "updated": updated,
        "symbols": sorted(symbols),
        "timeframes": sorted(timeframes),
    }


def latest_candles(db: Session, symbol: str, timeframe: str = "5m", limit: int = 50) -> list[MarketCandle]:
    safe_limit = max(1, min(limit, MAX_CANDLE_QUERY_LIMIT))
    fetch_limit = min(MAX_CANDLE_QUERY_LIMIT, max(safe_limit * 5, safe_limit + 100))
    rows = (
        db.query(MarketCandle)
        .filter_by(symbol=symbol.upper(), timeframe=timeframe.lower())
        .order_by(MarketCandle.ts.desc())
        .limit(fetch_limit)
        .all()
    )
    filtered = [row for row in rows if should_use_candle(row.symbol, row.timeframe, row.ts)]
    return filtered[:safe_limit]


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

    latest = candles[-1]
    market_context = apply_higher_timeframe_context(
        db,
        symbol,
        timeframe,
        candle_market_context(symbol, timeframe, candles),
    )
    market_context["ml_analysis"] = analyze_candles(symbol, timeframe, candles, market_context)
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
