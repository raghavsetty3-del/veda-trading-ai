import json
from typing import Any

from app.config import settings


EXIT_CONFIG_KEYS = {
    "exit_mode",
    "part_book_r_multiple",
    "part_book_fraction",
    "trail_lookback_candles",
    "cooldown_candles",
}


def global_paper_exit_config() -> dict[str, Any]:
    return {
        "exit_mode": settings.paper_exit_mode,
        "part_book_r_multiple": settings.paper_part_book_r_multiple,
        "part_book_fraction": settings.paper_part_book_fraction,
        "trail_lookback_candles": settings.paper_trail_lookback_candles,
        "cooldown_candles": settings.paper_trade_cooldown_candles,
    }


def paper_symbol_exit_overrides() -> dict[str, dict[str, Any]]:
    raw = settings.paper_symbol_exit_overrides
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, dict):
        return {}

    overrides = {}
    for symbol, config in decoded.items():
        if not isinstance(config, dict):
            continue
        clean = {key: value for key, value in config.items() if key in EXIT_CONFIG_KEYS}
        if clean:
            overrides[str(symbol).strip().upper()] = clean
    return overrides


def paper_exit_config_for_symbol(symbol: str) -> dict[str, Any]:
    config = global_paper_exit_config()
    override = paper_symbol_exit_overrides().get(symbol.strip().upper())
    if override:
        config.update(override)
        config["source"] = "symbol_override"
    else:
        config["source"] = "global"
    return config
