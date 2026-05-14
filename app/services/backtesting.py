from sqlalchemy.orm import Session

from app.models import RuleMapping
from app.services.instrument_profiles import apply_instrument_profile
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
