def classify_regime(adx: float | None, atr_pct: float | None = None) -> str:
    if adx is None:
        return "unknown"
    if adx < 15:
        return "choppy"
    if adx < 22:
        return "transition"
    return "trending"
