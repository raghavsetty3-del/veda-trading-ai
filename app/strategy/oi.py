def classify_oi(price_change: float, oi_change: float) -> str:
    if price_change > 0 and oi_change > 0:
        return "long_buildup"
    if price_change < 0 and oi_change > 0:
        return "short_buildup"
    if price_change > 0 and oi_change < 0:
        return "short_covering"
    if price_change < 0 and oi_change < 0:
        return "long_unwinding"
    return "neutral"
