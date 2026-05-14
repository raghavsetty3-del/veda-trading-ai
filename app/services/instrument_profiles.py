DEFAULT_PROFILE = {
    "symbol": "DEFAULT",
    "label": "Default Index",
    "ema_extension_limit_pct": 1.5,
    "low_adx_threshold": 18,
    "preferred_timeframe": "5m",
    "risk_note": "Use conservative sizing until instrument-specific validation is complete.",
}

PROFILES = {
    "NIFTY": {
        "symbol": "NIFTY",
        "label": "Nifty 50",
        "ema_extension_limit_pct": 1.5,
        "low_adx_threshold": 18,
        "preferred_timeframe": "5m",
        "risk_note": "Use standard index risk profile; avoid chasing after large expansion.",
    },
    "BANKNIFTY": {
        "symbol": "BANKNIFTY",
        "label": "Bank Nifty",
        "ema_extension_limit_pct": 2.0,
        "low_adx_threshold": 20,
        "preferred_timeframe": "5m",
        "risk_note": "Use wider stops and smaller quantity than Nifty due to higher volatility.",
    },
}


def get_instrument_profile(symbol: str | None) -> dict:
    if not symbol:
        return DEFAULT_PROFILE
    return PROFILES.get(symbol.upper(), {**DEFAULT_PROFILE, "symbol": symbol.upper()})


def apply_instrument_profile(market_context: dict) -> dict:
    profile = get_instrument_profile(market_context.get("symbol"))
    enriched = {**market_context}
    enriched.setdefault("ema_extension_limit_pct", profile["ema_extension_limit_pct"])
    enriched.setdefault("low_adx_threshold", profile["low_adx_threshold"])
    enriched["instrument_profile"] = profile
    return enriched
