import json
import re

import httpx
from sqlalchemy.orm import Session

from app.models import ExtractedInsight, SourceDocument
from app.config import settings
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


OPENAI_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "bias": {"type": ["string", "null"], "enum": ["bullish", "bearish", "neutral", None]},
        "timeframe": {"type": ["string", "null"]},
        "symbols": {"type": "array", "items": {"type": "string"}},
        "concepts": {"type": "array", "items": {"type": "string"}},
        "psychology": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "conviction": {"type": "number"},
                "caution": {"type": "number"},
                "patience": {"type": "number"},
                "raw_counts": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "conviction": {"type": "integer"},
                        "caution": {"type": "integer"},
                        "patience": {"type": "integer"},
                    },
                    "required": ["conviction", "caution", "patience"],
                },
            },
            "required": ["conviction", "caution", "patience", "raw_counts"],
        },
        "expected_conditions": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "wait_for_retracement": {"type": "boolean"},
                "avoid_chasing": {"type": "boolean"},
                "requires_200ema_context": {"type": "boolean"},
                "avoid_choppy_market": {"type": "boolean"},
                "requires_risk_control": {"type": "boolean"},
            },
            "required": [
                "wait_for_retracement",
                "avoid_chasing",
                "requires_200ema_context",
                "avoid_choppy_market",
                "requires_risk_control",
            ],
        },
        "confidence": {"type": "number"},
    },
    "required": ["bias", "timeframe", "symbols", "concepts", "psychology", "expected_conditions", "confidence"],
}


def extraction_status() -> dict:
    return {
        "deterministic_enabled": True,
        "openai_enabled": settings.openai_extraction_enabled,
        "openai_key_present": bool(settings.openai_api_key),
        "openai_model": settings.openai_extraction_model,
    }


def extract_deterministic_knowledge(text: str | None) -> dict:
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


def _response_output_text(data: dict) -> str | None:
    if data.get("output_text"):
        return data["output_text"]
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                return content["text"]
    return None


def extract_openai_knowledge(text: str | None) -> dict | None:
    if not settings.openai_extraction_enabled or not settings.openai_api_key or not text:
        return None

    payload = {
        "model": settings.openai_extraction_model,
        "instructions": (
            "Extract trading-system knowledge from the source text. Focus on NIFTY, BANKNIFTY, "
            "price action, risk control, psychology, and rule-like market conditions. Return JSON only."
        ),
        "input": text[:12000],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "veda_knowledge_extraction",
                "strict": True,
                "schema": OPENAI_EXTRACTION_SCHEMA,
            }
        },
        "store": False,
    }

    with httpx.Client(timeout=45) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
    output_text = _response_output_text(response.json())
    if not output_text:
        return None
    return json.loads(output_text)


def _merge_extractions(base: dict, ai: dict | None) -> dict:
    if not ai:
        return base

    merged = {**base}
    for key in ["bias", "timeframe"]:
        if ai.get(key):
            merged[key] = ai[key]

    for key in ["symbols", "concepts"]:
        merged[key] = sorted({*(base.get(key) or []), *(ai.get(key) or [])})

    merged["psychology"] = {**(base.get("psychology") or {}), **(ai.get("psychology") or {})}
    merged["expected_conditions"] = {
        **(base.get("expected_conditions") or {}),
        **(ai.get("expected_conditions") or {}),
    }
    merged["confidence"] = max(float(base.get("confidence") or 0), float(ai.get("confidence") or 0))
    return merged


def extract_knowledge(text: str | None) -> dict:
    base = extract_deterministic_knowledge(text)
    try:
        return _merge_extractions(base, extract_openai_knowledge(text))
    except Exception as exc:
        base["expected_conditions"] = {
            **base.get("expected_conditions", {}),
            "openai_extraction_error": str(exc)[:200],
        }
        return base


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
