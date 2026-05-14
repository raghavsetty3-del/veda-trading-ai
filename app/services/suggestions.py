from collections import defaultdict

from sqlalchemy.orm import Session

from app.models import ExtractedInsight


SUGGESTION_RULES = [
    {
        "key": "wait_for_retracement",
        "principle_title": "Wait For Retracement",
        "rule_code": "SUGGEST-RETRACEMENT-LRHR",
        "rule_name": "Prefer LRHR retracement before entry",
        "expected_behavior": "Prefer entries after a pullback into an acceptable retracement zone instead of chasing expansion.",
    },
    {
        "key": "avoid_chasing",
        "principle_title": "Avoid Chasing",
        "rule_code": "SUGGEST-NO-CHASE",
        "rule_name": "Block extended chase entries",
        "expected_behavior": "If price is extended from the relevant moving average or structure, wait for reset.",
    },
    {
        "key": "requires_200ema_context",
        "principle_title": "Use 200 EMA Bias",
        "rule_code": "SUGGEST-EMA200-BIAS",
        "rule_name": "Require 200 EMA directional context",
        "expected_behavior": "Longs should prefer price above 200 EMA; shorts should prefer price below 200 EMA.",
    },
    {
        "key": "avoid_choppy_market",
        "principle_title": "Avoid Choppy Markets",
        "rule_code": "SUGGEST-AVOID-LOW-ADX",
        "rule_name": "Reduce trades in low ADX or sideways regimes",
        "expected_behavior": "When trend quality is poor, reduce or block trend-following setups.",
    },
    {
        "key": "requires_risk_control",
        "principle_title": "Protect Capital",
        "rule_code": "SUGGEST-RISK-CONTROL",
        "rule_name": "Require predefined risk before entry",
        "expected_behavior": "Every setup should include stop loss, target, quantity, and daily drawdown guardrails.",
    },
]


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
            "rule_name": item["rule_name"],
            "principle_title": item["principle_title"],
            "expected_behavior": item["expected_behavior"],
            "supporting_insights": hits,
            "average_confidence": round(item["confidence"] / max(hits, 1), 3),
            "source_insight_ids": item["source_insight_ids"],
            "status": "review",
        })
    return sorted(suggestions, key=lambda item: (-item["supporting_insights"], item["rule_code"]))
