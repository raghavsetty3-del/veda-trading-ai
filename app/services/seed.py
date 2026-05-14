from sqlalchemy.orm import Session
from app.models import AuthorPrinciple, RuleMapping, ValidationCase

DEFAULT_PRINCIPLES = [
    {"code": "AP-001", "title": "Trade with trend", "description": "Follow HH/HL in uptrend and LH/LL in downtrend. Avoid countertrend trades unless separately validated."},
    {"code": "AP-002", "title": "Avoid sideways markets", "description": "Most losses arise in flat/choppy regimes. Suppress trades when trend quality is poor."},
    {"code": "AP-003", "title": "Prefer retracement entries", "description": "Do not chase. Wait for retracement to LRHR zones such as 38.2, 50, 61.8, or 78.6."},
    {"code": "AP-004", "title": "Protect capital", "description": "Use predefined stop-loss, part booking, drawdown limits, and emergency kill switches."},
    {"code": "AP-005", "title": "Wait for high-conviction alignment", "description": "Prefer trades where price action, EMA bias, retracement, regime, and psychology align."},
    {"code": "AP-006", "title": "Price action is primary", "description": "Use HH/HL and LH/LL structure as the first evidence of demand and supply shift before indicators."},
    {"code": "AP-007", "title": "Respect 200 EMA bias", "description": "Use 200 EMA as the major intraday bias filter; prefer longs above it and shorts below it."},
    {"code": "AP-008", "title": "Use multi-timeframe context", "description": "Read larger timeframe context before taking lower timeframe entries; hour, day, week, and month charts define trade quality."},
    {"code": "AP-009", "title": "Part book and trail", "description": "At extremes or target zones, book partial profits and trail the remaining position instead of holding without a plan."},
    {"code": "AP-010", "title": "Weekly review builds skill", "description": "Review completed trades and chart behavior every weekend to identify missed context, mistakes, and repeatable patterns."},
    {"code": "AP-011", "title": "Optional Elliott Wave context", "description": "Use Elliott Wave only as optional context for LRHR zones; price action, retracement, moving averages, and channels remain sufficient."},
    {"code": "AP-012", "title": "Keep expectations small", "description": "Prefer small, consistent, plan-based wins over oversized leveraged trades or revenge trading."},
]

DEFAULT_RULES = [
    ("AP-002", "RULE-AVOID-LOW-ADX", "Avoid low ADX/choppy market", {"conditions": [{"field": "adx", "op": "<", "value": 18}]}, "If ADX is below threshold, system should reduce or block trend-following trades."),
    ("AP-001", "RULE-LONG-EMA-BIAS", "Long only above 200 EMA bias", {"conditions": [{"field": "price_above_ema200", "op": "==", "value": True}]}, "Long signals should be preferred only when price is above 200 EMA."),
    ("AP-003", "RULE-RETRACEMENT-LRHR", "Prefer LRHR retracement zone", {"conditions": [{"field": "retracement_pct", "op": "<=", "value": 61.8}]}, "Pullback entries near 38.2/50/61.8 should be preferred over chase entries."),
    ("AP-006", "RULE-BULLISH-PRICE-ACTION", "Bullish structure requires HH/HL", {"conditions": [{"field": "market_structure", "op": "==", "value": "HH_HL"}]}, "Long bias should require bullish price action unless the setup is explicitly classified as reversal."),
    ("AP-006", "RULE-BEARISH-PRICE-ACTION", "Bearish structure requires LH/LL", {"conditions": [{"field": "market_structure", "op": "==", "value": "LH_LL"}]}, "Short bias should require bearish price action unless the setup is explicitly classified as reversal."),
    ("AP-007", "RULE-SHORT-EMA-BIAS", "Short only below 200 EMA bias", {"conditions": [{"field": "price_above_ema200", "op": "==", "value": False}]}, "Short signals should be preferred only when price is below 200 EMA."),
    ("AP-003", "RULE-NO-CHASE-EXTENSION", "Avoid chasing extended price", {"conditions": [{"field": "distance_from_ema_pct", "op": "<=", "value": 1.5}]}, "If price is far away from the relevant EMA after expansion, wait for pullback or fresh structure."),
    ("AP-008", "RULE-MTF-CONTEXT-REQUIRED", "Require higher timeframe context", {"conditions": [{"field": "higher_timeframe_bias", "op": "!=", "value": "unknown"}]}, "Intraday setups should include higher timeframe bias before being classified high conviction."),
    ("AP-009", "RULE-PART-BOOK-AT-EXTREME", "Part book at extremes", {"conditions": [{"field": "at_channel_or_envelope_extreme", "op": "==", "value": True}]}, "When price reaches channel, envelope, or target extremes, the system should recommend partial profit booking."),
    ("AP-011", "RULE-EW-OPTIONAL-NOT-BLOCKING", "Elliott Wave is optional", {"conditions": [{"field": "core_tools_aligned", "op": "==", "value": True}]}, "A valid setup does not require Elliott Wave if price action, retracement, moving averages, and channels align."),
    ("AP-012", "RULE-BLOCK-REVENGE-TRADING", "Block revenge trading state", {"conditions": [{"field": "emotional_state", "op": "!=", "value": "revenge"}]}, "If recent behavior suggests revenge trading or repeated plan violation, block new discretionary trades."),
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

    validation_cases = [
        (
            "VAL-JN-001",
            "Bullish price action requires HH/HL",
            "AP-006",
            {"market_structure": "HH_HL", "system_should": "allow_long_bias"},
            "Derived from JustNifty price-action framework.",
        ),
        (
            "VAL-JN-002",
            "Bearish price action requires LH/LL",
            "AP-006",
            {"market_structure": "LH_LL", "system_should": "allow_short_bias"},
            "Derived from JustNifty price-action framework.",
        ),
        (
            "VAL-JN-003",
            "200 EMA should filter intraday bias",
            "AP-007",
            {"price_above_ema200": True, "system_should": "prefer_longs_over_shorts"},
            "Validates the 200 EMA bias filter.",
        ),
        (
            "VAL-JN-004",
            "Extended price should not be chased",
            "AP-003",
            {"distance_from_ema_pct": ">1.5", "system_should": "wait_for_pullback"},
            "Validates the no-chase rule after fast expansion.",
        ),
        (
            "VAL-JN-005",
            "Part booking should trigger at extremes",
            "AP-009",
            {"at_channel_or_envelope_extreme": True, "system_should": "part_book_and_trail"},
            "Validates profit management at channel/envelope/target extremes.",
        ),
    ]

    for case_code, title, ap_code, expected_json, notes in validation_cases:
        if not db.query(ValidationCase).filter_by(case_code=case_code).first():
            ap = db.query(AuthorPrinciple).filter_by(code=ap_code).first()
            db.add(ValidationCase(
                case_code=case_code,
                title=title,
                principle_id=ap.id if ap else None,
                expected_json=expected_json,
                status="pending",
                notes=notes,
            ))
    db.commit()
