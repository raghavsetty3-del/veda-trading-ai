import re

from sqlalchemy.orm import Session

from app.models import ExtractedInsight, SourceDocument
from app.services.psychology import extract_psychology


CONCEPT_KEYWORDS = {
    "price_action": ["hh/hl", "higher high", "higher low", "lh/ll", "lower high", "lower low"],
    "retracement": ["retracement", "pullback", "38.2", "50", "61.8", "lrhr"],
    "ema_200": ["200 ema", "ema200", "200ema"],
    "adx": ["adx", "choppy", "sideways"],
    "trendline_channel": ["trendline", "channel", "envelope"],
    "risk": ["stop loss", "stop-loss", "risk", "drawdown", "kill switch"],
    "psychology": ["patience", "revenge", "discipline", "wait", "avoid chasing"],
    "profit_booking": ["part booking", "book profit", "target", "trail"],
}


def _lower(text: str | None) -> str:
    return (text or "").lower()


def extract_symbols(text: str | None) -> list[str]:
    lower = _lower(text)
    symbols = []
    if "banknifty" in lower or "bank nifty" in lower:
        symbols.append("BANKNIFTY")
    if "nifty" in lower:
        symbols.append("NIFTY")
    return symbols


def extract_timeframe(text: str | None) -> str | None:
    lower = _lower(text)
    match = re.search(r"\b(1m|3m|5m|15m|30m|1h|1d|daily|weekly)\b", lower)
    if not match:
        return None
    value = match.group(1)
    if value == "daily":
        return "1d"
    if value == "weekly":
        return "1w"
    return value


def extract_concepts(text: str | None) -> list[str]:
    lower = _lower(text)
    concepts = []
    for concept, keywords in CONCEPT_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            concepts.append(concept)
    return concepts


def extract_bias(text: str | None) -> str | None:
    lower = _lower(text)
    bullish_score = sum(1 for token in ["hh/hl", "higher high", "higher low", "uptrend", "bullish", "above 200"] if token in lower)
    bearish_score = sum(1 for token in ["lh/ll", "lower high", "lower low", "downtrend", "bearish", "below 200"] if token in lower)
    if bullish_score > bearish_score:
        return "bullish"
    if bearish_score > bullish_score:
        return "bearish"
    return None


def expected_conditions(text: str | None) -> dict:
    lower = _lower(text)
    return {
        "wait_for_retracement": any(token in lower for token in ["retracement", "pullback", "lrhr"]),
        "avoid_chasing": any(token in lower for token in ["avoid chasing", "do not chase", "wait"]),
        "requires_200ema_context": any(token in lower for token in ["200 ema", "ema200", "200ema"]),
        "avoid_choppy_market": any(token in lower for token in ["choppy", "sideways", "low adx"]),
        "requires_risk_control": any(token in lower for token in ["stop loss", "stop-loss", "risk", "drawdown"]),
    }


def extract_knowledge(text: str | None) -> dict:
    concepts = extract_concepts(text)
    symbols = extract_symbols(text)
    psychology = extract_psychology(text)
    conditions = expected_conditions(text)
    confidence = min(1.0, round((len(concepts) * 0.12) + (len(symbols) * 0.1) + 0.2, 3))
    return {
        "bias": extract_bias(text),
        "timeframe": extract_timeframe(text),
        "symbols": symbols,
        "concepts": concepts,
        "psychology": psychology,
        "expected_conditions": conditions,
        "confidence": confidence,
    }


def process_source(db: Session, source_id: int) -> dict | None:
    source = db.get(SourceDocument, source_id)
    if not source:
        return None
    extracted = extract_knowledge(source.raw_text or source.raw_html)
    insight = ExtractedInsight(source_document_id=source.id, **extracted)
    source.processed = True
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return {"source_id": source.id, "insight_id": insight.id, **extracted}


def process_pending_sources(db: Session, limit: int = 50) -> dict:
    safe_limit = max(1, min(limit, 500))
    sources = (
        db.query(SourceDocument)
        .filter_by(processed=False)
        .order_by(SourceDocument.ingested_at.asc())
        .limit(safe_limit)
        .all()
    )
    results = []
    for source in sources:
        result = process_source(db, source.id)
        if result:
            results.append(result)
    return {"seen": len(sources), "processed": len(results), "results": results}
