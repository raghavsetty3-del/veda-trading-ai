from __future__ import annotations

import math
from statistics import mean, pstdev

from sqlalchemy.orm import Session

from app.models import MarketCandle

MAX_ML_CANDLE_QUERY_LIMIT = 10000


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return round(value, digits)


def _ema(values: list[float], period: int) -> float | None:
    if not values:
        return None
    alpha = 2 / (period + 1)
    ema = values[0]
    for value in values[1:]:
        ema = (value * alpha) + (ema * (1 - alpha))
    return ema


def _atr(candles: list[MarketCandle], period: int = 14) -> float | None:
    if len(candles) < 2:
        return None
    ranges = []
    for prev, current in zip(candles[:-1], candles[1:]):
        ranges.append(max(
            current.high - current.low,
            abs(current.high - prev.close),
            abs(current.low - prev.close),
        ))
    if not ranges:
        return None
    return mean(ranges[-period:])


def _slope_pct(values: list[float], lookback: int) -> float | None:
    if len(values) <= lookback or values[-lookback] == 0:
        return None
    return (values[-1] - values[-lookback]) / values[-lookback] * 100


def _zscore(value: float, values: list[float]) -> float | None:
    if len(values) < 10:
        return None
    sigma = pstdev(values)
    if sigma == 0:
        return 0.0
    return (value - mean(values)) / sigma


def _bounded_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min((value - low) / (high - low), 1.0))


def _regime_label(adx: float | None, atr_pct: float | None, compression_pct: float | None) -> str:
    if adx is None:
        return "unknown"
    if adx < 15 or (compression_pct is not None and compression_pct < 0.45):
        return "choppy_compression"
    if adx < 22:
        return "transition"
    if atr_pct is not None and atr_pct > 1.6:
        return "volatile_trend"
    return "trend"


def _author_alignment(context: dict, features: dict) -> dict:
    checks = {
        "wait_for_retracement": 38.2 <= float(context.get("retracement_pct") or 0) <= 78.6,
        "avoid_chasing": float(context.get("distance_from_ema_pct") or 0) <= float(context.get("ema_extension_limit_pct") or 0.8),
        "timeframe_agreement": str(context.get("higher_timeframe_agreement") or "").lower() == "aligned",
        "avoid_choppy_market": features.get("regime") not in {"choppy_compression", "unknown"},
        "risk_defined": bool(context.get("risk_points") or context.get("recent_high") or context.get("recent_low")),
    }
    score = sum(1 for value in checks.values() if value) / max(len(checks), 1)
    return {
        "score": _round(score, 3),
        "checks": checks,
        "missing": [key for key, ok in checks.items() if not ok],
    }


def analyze_candles(symbol: str, timeframe: str, candles: list[MarketCandle], market_context: dict | None = None) -> dict:
    context = market_context or {}
    closes = [row.close for row in candles]
    highs = [row.high for row in candles]
    lows = [row.low for row in candles]
    latest = candles[-1] if candles else None
    if not latest or len(candles) < 20:
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.lower(),
            "ready": False,
            "reason": "Need at least 20 candles for ML analysis",
        }

    ema20 = _ema(closes[-80:], 20)
    ema50 = _ema(closes[-120:], 50)
    ema200 = _ema(closes[-250:], 200)
    atr14 = _atr(candles, 14)
    atr_pct = (atr14 / latest.close * 100) if atr14 and latest.close else None
    recent_range = max(highs[-20:]) - min(lows[-20:])
    broader_range = max(highs[-80:]) - min(lows[-80:]) if len(candles) >= 80 else recent_range
    compression_pct = recent_range / broader_range if broader_range else None
    slope_20 = _slope_pct(closes, min(20, len(closes) - 1))
    slope_50 = _slope_pct(closes, min(50, len(closes) - 1))
    returns = [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100
        for i in range(1, len(closes))
        if closes[i - 1]
    ]
    last_return = returns[-1] if returns else 0.0
    return_zscore = _zscore(last_return, returns[-80:])
    adx = float(context.get("adx") or 0) or None
    regime = _regime_label(adx, atr_pct, compression_pct)

    trend_score = 0.0
    if ema20 and ema50 and latest.close:
        trend_score += 0.35 if latest.close >= ema20 else 0
        trend_score += 0.25 if ema20 >= ema50 else 0
    if ema50 and ema200:
        trend_score += 0.2 if ema50 >= ema200 else 0
    if slope_20 is not None:
        trend_score += 0.2 * _bounded_score(abs(slope_20), 0.05, 1.0)

    pullback_score = 1.0 - abs(float(context.get("retracement_pct") or 50) - 58.0) / 58.0
    extension_risk = _bounded_score(float(context.get("distance_from_ema_pct") or 0), 0.4, 1.8)
    volatility_risk = _bounded_score(atr_pct or 0, 0.6, 2.4)
    anomaly_risk = _bounded_score(abs(return_zscore or 0), 1.0, 3.0)
    risk_score = max(extension_risk, volatility_risk, anomaly_risk)
    opportunity_score = max(0.0, min((trend_score * 0.4) + (pullback_score * 0.35) + ((1 - risk_score) * 0.25), 1.0))

    features = {
        "symbol": symbol.upper(),
        "timeframe": timeframe.lower(),
        "ready": True,
        "regime": regime,
        "trend_score": _round(trend_score, 3),
        "pullback_quality_score": _round(pullback_score, 3),
        "risk_score": _round(risk_score, 3),
        "opportunity_score": _round(opportunity_score, 3),
        "features": {
            "ema20": _round(ema20, 2),
            "ema50": _round(ema50, 2),
            "ema200": _round(ema200, 2),
            "atr14": _round(atr14, 2),
            "atr_pct": _round(atr_pct, 3),
            "compression_pct": _round(compression_pct, 3),
            "slope_20_pct": _round(slope_20, 3),
            "slope_50_pct": _round(slope_50, 3),
            "last_return_zscore": _round(return_zscore, 3),
            "recent_range_points": _round(recent_range, 2),
        },
        "signals": [],
        "caveats": [],
    }
    features["author_alignment"] = _author_alignment(context, features)

    if regime == "choppy_compression":
        features["caveats"].append("Compression/choppy regime: prefer waiting for range expansion or clear LRHR edge.")
    if features["risk_score"] and features["risk_score"] >= 0.65:
        features["caveats"].append("High ML risk score: avoid chase entries and demand cleaner invalidation.")
    if features["opportunity_score"] and features["opportunity_score"] >= 0.65:
        features["signals"].append("Conditions are statistically cleaner for review, subject to author-rule gates.")
    if features["author_alignment"]["missing"]:
        features["caveats"].append("Author-alignment checks are incomplete; keep setup review-only.")

    return features


def ml_snapshot(db: Session, symbol: str, timeframe: str = "5m", limit: int = 250, market_context: dict | None = None) -> dict:
    safe_limit = max(20, min(limit, MAX_ML_CANDLE_QUERY_LIMIT))
    candles = list(reversed(
        db.query(MarketCandle)
        .filter_by(symbol=symbol.upper(), timeframe=timeframe.lower())
        .order_by(MarketCandle.ts.desc())
        .limit(safe_limit)
        .all()
    ))
    return analyze_candles(symbol, timeframe, candles, market_context=market_context)
