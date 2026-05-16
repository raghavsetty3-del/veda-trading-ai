from sqlalchemy.orm import Session

from app.models import RuleMapping
from app.services.instrument_profiles import apply_instrument_profile
from app.services.market_data import apply_higher_timeframe_context, candle_market_context, latest_candles
from app.services.rules import evaluate_rule, evaluate_setup


def evaluate_backtest(db: Session, payload) -> dict:
    rows = db.query(RuleMapping).filter_by(active=True).order_by(RuleMapping.rule_code).all()
    results = []
    counts = {"long_bias": 0, "short_bias": 0, "wait": 0}

    for index, step in enumerate(payload.steps, start=1):
        context = apply_instrument_profile({
            "symbol": payload.symbol,
            "timeframe": payload.timeframe,
            **step.market_context,
        })
        rule_results = []
        for row in rows:
            evaluation = evaluate_rule(row.logic_json, context)
            rule_results.append({
                "rule_code": row.rule_code,
                "rule_name": row.rule_name,
                "matched": evaluation["matched"],
                "passed": evaluation["passed"],
                "failed": evaluation["failed"],
            })
        setup = evaluate_setup(context, rule_results)
        counts[setup["stance"]] = counts.get(setup["stance"], 0) + 1
        results.append({
            "index": index,
            "label": step.label or f"step-{index}",
            "market_context": context,
            "setup": setup,
        })

    return {
        "name": payload.name,
        "symbol": payload.symbol.upper(),
        "timeframe": payload.timeframe,
        "steps": len(payload.steps),
        "counts": counts,
        "results": results,
    }


def evaluate_candle_backtest(db: Session, payload) -> dict:
    candles = list(reversed(latest_candles(db, payload.symbol, payload.timeframe, payload.limit)))
    min_window = max(2, payload.min_window)
    if len(candles) < min_window:
        return {
            "name": payload.name,
            "symbol": payload.symbol.upper(),
            "timeframe": payload.timeframe,
            "steps": 0,
            "counts": {},
            "results": [],
            "ready": False,
            "reason": f"Need at least {min_window} candles; found {len(candles)}",
        }

    class Step:
        def __init__(self, label: str, market_context: dict):
            self.label = label
            self.market_context = market_context

    steps = []
    for index in range(min_window, len(candles) + 1):
        window = candles[index - min_window:index]
        latest = window[-1]
        context = apply_higher_timeframe_context(
            db,
            payload.symbol,
            payload.timeframe,
            candle_market_context(payload.symbol, payload.timeframe, window),
            anchor_ts=latest.ts,
        )
        steps.append(Step(latest.ts.isoformat(), context))

    replay_payload = type("ReplayPayload", (), {
        "name": payload.name,
        "symbol": payload.symbol,
        "timeframe": payload.timeframe,
        "steps": steps,
    })()
    result = evaluate_backtest(db, replay_payload)
    result["ready"] = True
    result["source_candles"] = len(candles)
    result["min_window"] = min_window
    return result
