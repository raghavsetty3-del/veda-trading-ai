from sqlalchemy.orm import Session
from app.models import AuthorPrinciple, RuleMapping, ValidationCase

DEFAULT_PRINCIPLES = [
    {"code": "AP-001", "title": "Trade with trend", "description": "Follow HH/HL in uptrend and LH/LL in downtrend. Avoid countertrend trades unless separately validated."},
    {"code": "AP-002", "title": "Avoid sideways markets", "description": "Most losses arise in flat/choppy regimes. Suppress trades when trend quality is poor."},
    {"code": "AP-003", "title": "Prefer retracement entries", "description": "Do not chase. Wait for retracement to LRHR zones such as 38.2, 50, 61.8, or 78.6."},
    {"code": "AP-004", "title": "Protect capital", "description": "Use predefined stop-loss, part booking, drawdown limits, and emergency kill switches."},
    {"code": "AP-005", "title": "Wait for high-conviction alignment", "description": "Prefer trades where price action, EMA bias, retracement, regime, and psychology align."},
]

DEFAULT_RULES = [
    ("AP-002", "RULE-AVOID-LOW-ADX", "Avoid low ADX/choppy market", {"conditions": [{"field": "adx", "op": "<", "value": 18}]}, "If ADX is below threshold, system should reduce or block trend-following trades."),
    ("AP-001", "RULE-LONG-EMA-BIAS", "Long only above 200 EMA bias", {"conditions": [{"field": "price_above_ema200", "op": "==", "value": True}]}, "Long signals should be preferred only when price is above 200 EMA."),
    ("AP-003", "RULE-RETRACEMENT-LRHR", "Prefer LRHR retracement zone", {"conditions": [{"field": "retracement_pct", "op": "<=", "value": 61.8}]}, "Pullback entries near 38.2/50/61.8 should be preferred over chase entries."),
]


def seed_defaults(db: Session):
    for item in DEFAULT_PRINCIPLES:
        if not db.query(AuthorPrinciple).filter_by(code=item["code"]).first():
            db.add(AuthorPrinciple(**item, source_type="book", immutable=True, active=True))
    db.commit()

    for ap_code, rule_code, name, logic, expected in DEFAULT_RULES:
        ap = db.query(AuthorPrinciple).filter_by(code=ap_code).first()
        if ap and not db.query(RuleMapping).filter_by(rule_code=rule_code).first():
            db.add(RuleMapping(principle_id=ap.id, rule_code=rule_code, rule_name=name, logic_json=logic, expected_behavior=expected, status="draft", version="0.2.0", active=True))
    db.commit()

    if not db.query(ValidationCase).filter_by(case_code="VAL-001").first():
        ap = db.query(AuthorPrinciple).filter_by(code="AP-002").first()
        db.add(ValidationCase(
            case_code="VAL-001",
            title="Low ADX should suppress trend trades",
            principle_id=ap.id if ap else None,
            expected_json={"when": {"adx": "<18"}, "system_should": "avoid_or_reduce_trades"},
            status="pending",
            notes="Baseline expectation for sideways/choppy market behavior."
        ))
        db.commit()
