def evaluate_rule(rule_logic: dict, market_context: dict) -> dict:
    conditions = rule_logic.get("conditions", [])
    passed, failed = [], []

    for condition in conditions:
        field, op, value = condition.get("field"), condition.get("op"), condition.get("value")
        actual = market_context.get(field)
        ok = False
        try:
            if isinstance(value, str) and value.startswith("$"):
                value = market_context.get(value[1:])
            if op == ">": ok = actual > value
            elif op == "<": ok = actual < value
            elif op == ">=": ok = actual >= value
            elif op == "<=": ok = actual <= value
            elif op == "==": ok = actual == value
            elif op == "!=": ok = actual != value
        except Exception:
            ok = False

        (passed if ok else failed).append({"condition": condition, "actual": actual})

    return {"matched": not failed, "passed": passed, "failed": failed}


def evaluate_setup(market_context: dict, rule_results: list[dict]) -> dict:
    matched = {item["rule_code"] for item in rule_results if item["matched"]}
    failed = {item["rule_code"] for item in rule_results if not item["matched"]}

    long_score = 0
    short_score = 0
    risk_flags = []
    reasons = []
    has_bullish_structure = "RULE-BULLISH-PRICE-ACTION" in matched
    has_bearish_structure = "RULE-BEARISH-PRICE-ACTION" in matched
    has_long_ema_bias = "RULE-LONG-EMA-BIAS" in matched
    has_short_ema_bias = "RULE-SHORT-EMA-BIAS" in matched
    has_lrhr_retracement = "RULE-RETRACEMENT-LRHR" in matched
    has_known_mtf_context = "RULE-MTF-CONTEXT-REQUIRED" in matched

    if has_bullish_structure:
        long_score += 2
        reasons.append("Bullish HH/HL price action is present.")
    if has_bearish_structure:
        short_score += 2
        reasons.append("Bearish LH/LL price action is present.")

    if has_long_ema_bias:
        long_score += 2
        reasons.append("Price is above the 200 EMA bias filter.")
    if has_short_ema_bias:
        short_score += 2
        reasons.append("Price is below the 200 EMA bias filter.")

    if has_lrhr_retracement:
        long_score += 1
        short_score += 1
        reasons.append("Retracement is inside the LRHR threshold.")
    if has_known_mtf_context:
        long_score += 1
        short_score += 1
        reasons.append("Higher timeframe context is available.")
    if "RULE-EW-OPTIONAL-NOT-BLOCKING" in matched:
        reasons.append("Core tools align without requiring Elliott Wave.")

    if "RULE-AVOID-LOW-ADX" in matched:
        risk_flags.append("Low ADX/choppy regime risk.")
    if "RULE-NO-CHASE-EXTENSION" in failed:
        risk_flags.append("Price is extended from the relevant EMA; avoid chasing.")
    if "RULE-BLOCK-REVENGE-TRADING" in failed:
        risk_flags.append("Emotional/revenge-trading state blocks new trades.")
    if "RULE-PART-BOOK-AT-EXTREME" in matched:
        risk_flags.append("Price is at an extreme; prefer part booking or avoid fresh chase entries.")

    long_has_primary_confluence = has_bullish_structure and has_long_ema_bias
    short_has_primary_confluence = has_bearish_structure and has_short_ema_bias

    if risk_flags:
        stance = "wait"
    elif long_has_primary_confluence and long_score > short_score and long_score >= 4:
        stance = "long_bias"
    elif short_has_primary_confluence and short_score > long_score and short_score >= 4:
        stance = "short_bias"
    else:
        stance = "neutral_wait"

    return {
        "stance": stance,
        "long_score": long_score,
        "short_score": short_score,
        "risk_flags": risk_flags,
        "reasons": reasons,
        "matched_rules": sorted(matched),
        "failed_rules": sorted(failed),
        "market_context": market_context,
    }
