def evaluate_rule(rule_logic: dict, market_context: dict) -> dict:
    conditions = rule_logic.get("conditions", [])
    passed, failed = [], []

    for condition in conditions:
        field, op, value = condition.get("field"), condition.get("op"), condition.get("value")
        actual = market_context.get(field)
        ok = False
        try:
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
