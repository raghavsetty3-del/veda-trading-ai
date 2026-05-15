from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import AuthorPrinciple, ExtractedInsight, RuleMapping


SUGGESTION_RULES = [
    {
        "key": "wait_for_retracement",
        "principle_title": "Wait For Retracement",
        "rule_code": "SUGGEST-RETRACEMENT-LRHR",
        "draft_rule_code": "DRAFT-RETRACEMENT-LRHR",
        "rule_name": "Prefer LRHR retracement before entry",
        "expected_behavior": "Prefer entries after a pullback into an acceptable retracement zone instead of chasing expansion.",
        "logic_json": {"conditions": [{"field": "retracement_pct", "op": ">=", "value": 38.2}, {"field": "retracement_pct", "op": "<=", "value": 78.6}]},
    },
    {
        "key": "avoid_chasing",
        "principle_title": "Avoid Chasing",
        "rule_code": "SUGGEST-NO-CHASE",
        "draft_rule_code": "DRAFT-NO-CHASE",
        "rule_name": "Block extended chase entries",
        "expected_behavior": "If price is extended from the relevant moving average or structure, wait for reset.",
        "logic_json": {"conditions": [{"field": "distance_from_ema_pct", "op": "<=", "value": "$ema_extension_limit_pct"}]},
    },
    {
        "key": "requires_200ema_context",
        "principle_title": "Use 200 EMA Bias",
        "rule_code": "SUGGEST-EMA200-BIAS",
        "draft_rule_code": "DRAFT-EMA200-BIAS",
        "rule_name": "Require 200 EMA directional context",
        "expected_behavior": "Longs should prefer price above 200 EMA; shorts should prefer price below 200 EMA.",
        "logic_json": {"conditions": [{"field": "price_above_ema200", "op": "!=", "value": None}]},
    },
    {
        "key": "avoid_choppy_market",
        "principle_title": "Avoid Choppy Markets",
        "rule_code": "SUGGEST-AVOID-LOW-ADX",
        "draft_rule_code": "DRAFT-AVOID-LOW-ADX",
        "rule_name": "Reduce trades in low ADX or sideways regimes",
        "expected_behavior": "When trend quality is poor, reduce or block trend-following setups.",
        "logic_json": {"conditions": [{"field": "adx", "op": ">=", "value": "$low_adx_threshold"}]},
    },
    {
        "key": "requires_risk_control",
        "principle_title": "Protect Capital",
        "rule_code": "SUGGEST-RISK-CONTROL",
        "draft_rule_code": "DRAFT-RISK-CONTROL",
        "rule_name": "Require predefined risk before entry",
        "expected_behavior": "Every setup should include stop loss, target, quantity, and daily drawdown guardrails.",
        "logic_json": {"conditions": [{"field": "risk_points", "op": ">", "value": 0}]},
    },
]


def _template_by_rule_code(rule_code: str) -> dict | None:
    return next((item for item in SUGGESTION_RULES if item["rule_code"] == rule_code), None)


def serialize_principle(row: AuthorPrinciple) -> dict:
    return {
        "id": row.id,
        "code": row.code,
        "title": row.title,
        "description": row.description,
        "source_type": row.source_type,
        "source_ref": row.source_ref,
        "immutable": row.immutable,
        "active": row.active,
    }


def serialize_rule(row: RuleMapping) -> dict:
    return {
        "id": row.id,
        "principle_id": row.principle_id,
        "rule_code": row.rule_code,
        "rule_name": row.rule_name,
        "logic_json": row.logic_json,
        "expected_behavior": row.expected_behavior,
        "status": row.status,
        "version": row.version,
        "active": row.active,
    }


def rule_suggestions(db: Session, limit: int = 200) -> list[dict]:
    insights = (
        db.query(ExtractedInsight)
        .order_by(ExtractedInsight.created_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    grouped = defaultdict(lambda: {"source_insight_ids": [], "confidence": 0.0, "hits": 0})

    for insight in insights:
        conditions = insight.expected_conditions or {}
        for template in SUGGESTION_RULES:
            if conditions.get(template["key"]):
                item = grouped[template["rule_code"]]
                item.update({k: v for k, v in template.items() if k != "key"})
                item["source_insight_ids"].append(insight.id)
                item["confidence"] += insight.confidence or 0.0
                item["hits"] += 1

    suggestions = []
    for rule_code, item in grouped.items():
        hits = item["hits"]
        suggestions.append({
            "rule_code": rule_code,
            "draft_rule_code": item["draft_rule_code"],
            "rule_name": item["rule_name"],
            "principle_title": item["principle_title"],
            "expected_behavior": item["expected_behavior"],
            "logic_json": item["logic_json"],
            "supporting_insights": hits,
            "average_confidence": round(item["confidence"] / max(hits, 1), 3),
            "source_insight_ids": item["source_insight_ids"],
            "status": "review",
        })
    return sorted(suggestions, key=lambda item: (-item["supporting_insights"], item["rule_code"]))


def promote_rule_suggestion(db: Session, rule_code: str, review_note: str | None = None) -> dict | None:
    template = _template_by_rule_code(rule_code)
    if not template:
        return None

    suggestion = next((item for item in rule_suggestions(db) if item["rule_code"] == rule_code), None)
    if not suggestion:
        return None

    principle_code = "AP-" + template["draft_rule_code"].replace("DRAFT-", "SUG-")
    principle = db.query(AuthorPrinciple).filter_by(code=principle_code).first()
    principle_created = False
    if not principle:
        principle = AuthorPrinciple(
            code=principle_code,
            title=template["principle_title"],
            description=f"Review-derived principle from extracted source insights. {template['expected_behavior']}",
            source_type="suggestion",
            source_ref=",".join(str(item) for item in suggestion["source_insight_ids"]),
            immutable=False,
            active=True,
        )
        db.add(principle)
        db.commit()
        db.refresh(principle)
        principle_created = True

    existing = db.query(RuleMapping).filter_by(rule_code=template["draft_rule_code"]).first()
    if existing:
        return {
            "promoted": False,
            "reason": "Draft rule already exists",
            "principle_created": principle_created,
            "principle": serialize_principle(principle),
            "rule": serialize_rule(existing),
            "suggestion": suggestion,
        }

    expected_behavior = template["expected_behavior"]
    if review_note:
        expected_behavior = f"{expected_behavior}\n\nReview note: {review_note}"

    row = RuleMapping(
        principle_id=principle.id,
        rule_code=template["draft_rule_code"],
        rule_name=template["rule_name"],
        logic_json=template["logic_json"],
        expected_behavior=expected_behavior,
        status="draft",
        version="0.3.0",
        active=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "promoted": True,
        "principle_created": principle_created,
        "principle": serialize_principle(principle),
        "rule": serialize_rule(row),
        "suggestion": suggestion,
    }
