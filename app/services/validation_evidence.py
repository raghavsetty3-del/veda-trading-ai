from datetime import datetime

from sqlalchemy.orm import Session

from app.models import RuleMapping, ValidationCase
from app.services.backtesting import evaluate_candle_backtest


def _case_code(symbol: str, timeframe: str, rule_code: str | None) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    scope = rule_code or "SETUP"
    safe_scope = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in scope.upper())
    return f"CANDLE-REPLAY-{symbol.upper()}-{timeframe.lower()}-{safe_scope}-{stamp}"


def _rule_match_summary(result: dict, rule_code: str | None) -> dict:
    if not rule_code:
        return {"rule_code": None, "matches": None, "failures": None}

    matches = 0
    failures = 0
    observations = []
    for item in result.get("results", []):
        setup = item.get("setup", {})
        matched_rules = setup.get("matched_rules", [])
        failed_rules = setup.get("failed_rules", [])
        matched = rule_code in matched_rules
        failed = rule_code in failed_rules
        if matched:
            matches += 1
        if failed:
            failures += 1
        observations.append({
            "label": item.get("label"),
            "stance": setup.get("stance"),
            "matched": matched,
            "failed": failed,
        })
    return {
        "rule_code": rule_code,
        "matches": matches,
        "failures": failures,
        "observations": observations[:100],
    }


def create_candle_replay_validation(db: Session, payload) -> dict:
    result = evaluate_candle_backtest(db, payload)
    rule = None
    if payload.rule_code:
        rule = db.query(RuleMapping).filter_by(rule_code=payload.rule_code).first()

    match_summary = _rule_match_summary(result, payload.rule_code)
    expected_min_matches = max(0, payload.expected_min_matches)
    ready = bool(result.get("ready"))
    enough_matches = True
    if payload.rule_code:
        enough_matches = (match_summary.get("matches") or 0) >= expected_min_matches

    status = "pass" if ready and enough_matches and (not payload.rule_code or rule) else "fail"
    steps = max(1, int(result.get("steps") or 0))
    if payload.rule_code:
        score = round((match_summary.get("matches") or 0) / steps, 3)
    else:
        score = 1.0 if ready else 0.0

    delivered_json = {
        "ready": ready,
        "symbol": result.get("symbol"),
        "timeframe": result.get("timeframe"),
        "steps": result.get("steps"),
        "counts": result.get("counts"),
        "source_candles": result.get("source_candles"),
        "min_window": result.get("min_window"),
        "reason": result.get("reason"),
        "rule_match_summary": match_summary,
    }

    row = ValidationCase(
        case_code=_case_code(payload.symbol, payload.timeframe, payload.rule_code),
        title=f"Stored candle replay validation: {payload.symbol.upper()} {payload.timeframe}",
        principle_id=rule.principle_id if rule else None,
        rule_id=rule.id if rule else None,
        expected_json={
            "type": "stored_candle_replay",
            "symbol": payload.symbol.upper(),
            "timeframe": payload.timeframe.lower(),
            "ready": True,
            "rule_code": payload.rule_code,
            "expected_min_matches": expected_min_matches,
        },
        delivered_json=delivered_json,
        status=status,
        score=score,
        notes=payload.notes,
        evaluated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "validation_case_id": row.id,
        "case_code": row.case_code,
        "status": row.status,
        "score": row.score,
        "rule_found": rule is not None if payload.rule_code else None,
        "delivered_json": delivered_json,
    }
