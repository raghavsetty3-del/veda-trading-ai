import base64
from io import BytesIO
import json
from pathlib import Path
import re
import time

import httpx
from sqlalchemy.orm import Session

from app.models import ExtractedInsight, SourceDocument
from app.config import settings
from app.ingestion.media import is_supported_openai_image_url, unique_urls
from app.services.psychology import extract_psychology

try:
    from PIL import Image, UnidentifiedImageError
except Exception:  # pragma: no cover - optional runtime dependency during local tooling
    Image = None
    UnidentifiedImageError = Exception


class OpenAIRateLimited(RuntimeError):
    pass


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


def normalize_timeframe(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lower = raw.lower()
    if any(token in lower for token in ["multi", "multiple", "intraday frames", "daily and intraday"]):
        return "multi-timeframe"
    aliases = [
        (r"\b(1m|1[- ]?min(?:ute)?s?)\b", "1m"),
        (r"\b(3m|3[- ]?min(?:ute)?s?)\b", "3m"),
        (r"\b(5m|5[- ]?min(?:ute)?s?)\b", "5m"),
        (r"\b(15m|15[- ]?min(?:ute)?s?)\b", "15m"),
        (r"\b(30m|30[- ]?min(?:ute)?s?)\b", "30m"),
        (r"\b(60m|60[- ]?min(?:ute)?s?|1h|1[- ]?hour|hourly)\b", "1h"),
        (r"\b(1d|daily|day)\b", "1d"),
        (r"\b(1w|weekly|week)\b", "1w"),
        (r"\b(1mo|monthly|month)\b", "1mo"),
    ]
    matches = [code for pattern, code in aliases if re.search(pattern, lower)]
    if len(set(matches)) > 1:
        return "multi-timeframe"
    if matches:
        return matches[0]
    return raw[:50]


def extract_timeframe(text: str | None) -> str | None:
    lower = _lower(text)
    match = re.search(r"\b(1m|3m|5m|15m|30m|60m|1h|1d|daily|weekly|monthly|hourly)\b", lower)
    if not match:
        return None
    return normalize_timeframe(match.group(1))


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
        "timeframe": {
            "type": ["string", "null"],
            "description": "Use compact codes such as 5m, 15m, 30m, 1h, 1d, 1w, 1mo, or multi-timeframe.",
        },
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
                "chart_analysis": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "has_chart_context": {"type": "boolean"},
                        "image_count": {"type": "integer"},
                        "visible_timeframes": {"type": "array", "items": {"type": "string"}},
                        "visible_indicators": {"type": "array", "items": {"type": "string"}},
                        "price_levels": {"type": "array", "items": {"type": "string"}},
                        "pattern_notes": {"type": "array", "items": {"type": "string"}},
                        "trade_context": {"type": ["string", "null"]},
                        "caveats": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "has_chart_context",
                        "image_count",
                        "visible_timeframes",
                        "visible_indicators",
                        "price_levels",
                        "pattern_notes",
                        "trade_context",
                        "caveats",
                    ],
                },
                "author_mechanism": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "mindset": {"type": "array", "items": {"type": "string"}},
                        "decision_process": {"type": "array", "items": {"type": "string"}},
                        "entry_mechanisms": {"type": "array", "items": {"type": "string"}},
                        "exit_mechanisms": {"type": "array", "items": {"type": "string"}},
                        "risk_mechanisms": {"type": "array", "items": {"type": "string"}},
                        "timeframe_alignment": {"type": "array", "items": {"type": "string"}},
                        "market_regime_filter": {"type": "array", "items": {"type": "string"}},
                        "automation_candidates": {"type": "array", "items": {"type": "string"}},
                        "non_automatable_judgment": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "mindset",
                        "decision_process",
                        "entry_mechanisms",
                        "exit_mechanisms",
                        "risk_mechanisms",
                        "timeframe_alignment",
                        "market_regime_filter",
                        "automation_candidates",
                        "non_automatable_judgment",
                    ],
                },
            },
            "required": [
                "wait_for_retracement",
                "avoid_chasing",
                "requires_200ema_context",
                "avoid_choppy_market",
                "requires_risk_control",
                "chart_analysis",
                "author_mechanism",
            ],
        },
        "confidence": {"type": "number"},
    },
    "required": ["bias", "timeframe", "symbols", "concepts", "psychology", "expected_conditions", "confidence"],
}


def extraction_status() -> dict:
    backoff_until = _openai_backoff_until()
    now = time.time()
    return {
        "deterministic_enabled": True,
        "openai_enabled": settings.openai_extraction_enabled,
        "openai_key_present": bool(settings.openai_api_key),
        "openai_model": settings.openai_extraction_model,
        "openai_image_enabled": settings.openai_image_extraction_enabled,
        "openai_image_max_images": settings.openai_image_extraction_max_images,
        "openai_backoff_active": bool(backoff_until and backoff_until > now),
        "openai_backoff_until": backoff_until,
    }


def _chart_analysis_default(media_urls: list[str] | None = None, caveats: list[str] | None = None) -> dict:
    urls = unique_urls(media_urls or [])
    notes = list(caveats or [])
    if urls and not settings.openai_image_extraction_enabled:
        notes.append("Chart/media URLs were archived; image extraction is disabled.")
    return {
        "has_chart_context": bool(urls),
        "image_count": len(urls),
        "image_analysis_attempted": False,
        "image_inputs_prepared": 0,
        "visible_timeframes": [],
        "visible_indicators": [],
        "price_levels": [],
        "pattern_notes": [],
        "trade_context": None,
        "caveats": notes,
    }


def _author_mechanism_default(text: str | None = None) -> dict:
    lower = _lower(text)
    mindset = []
    if any(token in lower for token in ["patience", "wait", "sit tight"]):
        mindset.append("Wait for the setup instead of forcing trades.")
    if any(token in lower for token in ["discipline", "risk", "stop loss", "stop-loss"]):
        mindset.append("Protect capital with discipline and predefined risk.")
    if any(token in lower for token in ["avoid chasing", "do not chase", "chasing"]):
        mindset.append("Do not chase extended moves.")
    return {
        "mindset": mindset,
        "decision_process": [],
        "entry_mechanisms": [],
        "exit_mechanisms": [],
        "risk_mechanisms": ["Define risk before entry."] if any(token in lower for token in ["risk", "stop loss", "stop-loss"]) else [],
        "timeframe_alignment": [],
        "market_regime_filter": ["Avoid low-quality sideways/choppy markets."] if any(token in lower for token in ["sideways", "choppy", "low adx"]) else [],
        "automation_candidates": [],
        "non_automatable_judgment": [],
    }


def extract_deterministic_knowledge(text: str | None, media_urls: list[str] | None = None) -> dict:
    concepts = extract_concepts(text)
    symbols = extract_symbols(text)
    psychology = extract_psychology(text)
    conditions = expected_conditions(text)
    conditions["chart_analysis"] = _chart_analysis_default(media_urls)
    conditions["author_mechanism"] = _author_mechanism_default(text)
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


def _convert_image_url_to_png_data_url(client: httpx.Client, url: str) -> str | None:
    if Image is None:
        return None
    response = client.get(url)
    response.raise_for_status()
    if len(response.content) > settings.openai_image_fetch_max_bytes:
        return None
    try:
        image = Image.open(BytesIO(response.content))
    except UnidentifiedImageError:
        return None
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _openai_image_inputs(media_urls: list[str] | None) -> tuple[list[dict], list[str]]:
    if not settings.openai_image_extraction_enabled:
        return [], []
    max_images = max(0, min(settings.openai_image_extraction_max_images, 12))
    inputs = []
    skipped = []
    urls = unique_urls(media_urls or [])
    headers = {"User-Agent": "VedaTradingAI/0.2 chart-openai-prep"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        for url in urls:
            if len(inputs) >= max_images:
                break
            if is_supported_openai_image_url(url):
                inputs.append({"type": "input_image", "image_url": url, "detail": "high"})
                continue
            try:
                data_url = _convert_image_url_to_png_data_url(client, url)
            except Exception:
                data_url = None
            if data_url:
                inputs.append({"type": "input_image", "image_url": data_url, "detail": "high"})
            else:
                skipped.append(url)
            continue
            skipped.append(url)
    return inputs, skipped


def _openai_backoff_until() -> float | None:
    try:
        raw = Path(settings.openai_backoff_path).read_text(encoding="utf-8").strip()
        return float(raw) if raw else None
    except (OSError, ValueError):
        return None


def _openai_backoff_active() -> bool:
    until = _openai_backoff_until()
    return bool(until and until > time.time())


def _activate_openai_backoff() -> None:
    until = time.time() + max(60, int(settings.openai_rate_limit_backoff_seconds or 900))
    path = Path(settings.openai_backoff_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(until), encoding="utf-8")
    except OSError:
        return


def _openai_payload(text: str | None, media_urls: list[str] | None) -> tuple[dict, list[str], int]:
    image_inputs, skipped_images = _openai_image_inputs(media_urls)
    chart_note = (
        "Analyze the attached chart images together with the source text. Capture visible timeframes, "
        "indicators, price levels, market structure, trend/sideways context, support/resistance, "
        "entry/target/stop clues, the author's mindset, and any uncertainty. Do not invent numbers that are not readable."
    )
    source_text = text or ""
    if media_urls:
        source_text = f"{source_text}\n\nArchived chart/media URLs:\n" + "\n".join(unique_urls(media_urls))
    content = [
        {
            "type": "input_text",
            "text": f"{chart_note}\n\nSource text:\n{source_text[:12000]}",
        }
    ]
    content.extend(image_inputs)
    payload = {
        "model": settings.openai_extraction_model,
        "instructions": (
            "Extract trading-system knowledge from the source text and any chart images. Focus on NIFTY, BANKNIFTY, "
            "price action, risk control, psychology, rule-like market conditions, chart evidence, and the author's "
            "repeatable trading mechanisms. Separate automatable rules from judgment that should remain review-only. "
            "Return JSON only."
        ),
        "input": [{"role": "user", "content": content}],
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
    return payload, skipped_images, len(image_inputs)


def _post_openai_payload(payload: dict) -> dict | None:
    with httpx.Client(timeout=90) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code == 429:
            _activate_openai_backoff()
            raise OpenAIRateLimited("OpenAI rate limited; visual/text enrichment deferred.")
        response.raise_for_status()
    output_text = _response_output_text(response.json())
    if not output_text:
        return None
    return json.loads(output_text)


def extract_openai_knowledge(text: str | None, media_urls: list[str] | None = None) -> dict | None:
    if not settings.openai_extraction_enabled or not settings.openai_api_key or not (text or media_urls):
        return None
    if _openai_backoff_active():
        return None

    payload, skipped_images, image_count = _openai_payload(text, media_urls)
    result = _post_openai_payload(payload)
    if not result:
        return None
    conditions = result.setdefault("expected_conditions", {})
    chart = conditions.setdefault("chart_analysis", _chart_analysis_default(media_urls))
    chart["image_count"] = image_count
    chart["has_chart_context"] = bool(media_urls)
    chart["image_analysis_attempted"] = True
    chart["image_inputs_prepared"] = image_count
    if skipped_images:
        caveats = chart.setdefault("caveats", [])
        caveats.append(f"Skipped unsupported/unreadable chart images: {len(skipped_images)}")
    return result


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
    base_chart = ((base.get("expected_conditions") or {}).get("chart_analysis") or {})
    ai_chart = ((ai.get("expected_conditions") or {}).get("chart_analysis") or {})
    if base_chart or ai_chart:
        chart = {**base_chart, **ai_chart}
        if ai_chart:
            chart["image_count"] = int(ai_chart.get("image_count") or 0)
        else:
            chart["image_count"] = int(base_chart.get("image_count") or 0)
        chart["has_chart_context"] = bool(base_chart.get("has_chart_context") or ai_chart.get("has_chart_context"))
        chart["image_analysis_attempted"] = bool(
            base_chart.get("image_analysis_attempted") or ai_chart.get("image_analysis_attempted")
        )
        chart["image_inputs_prepared"] = int(
            ai_chart.get("image_inputs_prepared")
            or base_chart.get("image_inputs_prepared")
            or 0
        )
        chart["caveats"] = unique_urls([*(base_chart.get("caveats") or []), *(ai_chart.get("caveats") or [])])
        merged["expected_conditions"]["chart_analysis"] = chart
    base_mechanism = ((base.get("expected_conditions") or {}).get("author_mechanism") or {})
    ai_mechanism = ((ai.get("expected_conditions") or {}).get("author_mechanism") or {})
    if base_mechanism or ai_mechanism:
        keys = [
            "mindset",
            "decision_process",
            "entry_mechanisms",
            "exit_mechanisms",
            "risk_mechanisms",
            "timeframe_alignment",
            "market_regime_filter",
            "automation_candidates",
            "non_automatable_judgment",
        ]
        merged["expected_conditions"]["author_mechanism"] = {
            key: unique_urls([*(base_mechanism.get(key) or []), *(ai_mechanism.get(key) or [])])
            for key in keys
        }
    merged["confidence"] = max(float(base.get("confidence") or 0), float(ai.get("confidence") or 0))
    return merged


def _normalize_extracted_knowledge(extracted: dict) -> dict:
    normalized = {**extracted}
    raw_timeframe = normalized.get("timeframe")
    compact_timeframe = normalize_timeframe(raw_timeframe)
    if raw_timeframe and compact_timeframe != raw_timeframe:
        conditions = {**(normalized.get("expected_conditions") or {})}
        conditions["raw_timeframe_phrase"] = str(raw_timeframe)[:300]
        normalized["expected_conditions"] = conditions
    normalized["timeframe"] = compact_timeframe
    bias = normalized.get("bias")
    if bias is not None:
        normalized["bias"] = str(bias).strip()[:50] or None
    return normalized


def extract_knowledge(text: str | None, media_urls: list[str] | None = None) -> dict:
    base = extract_deterministic_knowledge(text, media_urls)
    try:
        return _normalize_extracted_knowledge(_merge_extractions(base, extract_openai_knowledge(text, media_urls)))
    except OpenAIRateLimited as exc:
        chart = base.setdefault("expected_conditions", {}).setdefault("chart_analysis", _chart_analysis_default(media_urls))
        chart["image_analysis_attempted"] = False
        chart["image_analysis_deferred"] = True
        chart.setdefault("caveats", []).append("OpenAI rate limit/backoff active; visual analysis deferred.")
        base["expected_conditions"] = {
            **base.get("expected_conditions", {}),
            "openai_extraction_error": str(exc)[:200],
        }
        return _normalize_extracted_knowledge(base)
    except Exception as exc:
        chart = base.setdefault("expected_conditions", {}).setdefault("chart_analysis", _chart_analysis_default(media_urls))
        chart["image_analysis_attempted"] = True
        chart.setdefault("caveats", []).append("OpenAI image/text extraction failed before returning structured chart details.")
        base["expected_conditions"] = {
            **base.get("expected_conditions", {}),
            "openai_extraction_error": str(exc)[:200],
        }
        return _normalize_extracted_knowledge(base)


def process_source(db: Session, source_id: int) -> dict | None:
    source = db.get(SourceDocument, source_id)
    if not source:
        return None
    media_urls = source.media_paths or []
    existing = (
        db.query(ExtractedInsight)
        .filter(
            ExtractedInsight.source_document_id == source.id,
            ExtractedInsight.confidence.isnot(None),
        )
        .order_by(ExtractedInsight.created_at.desc())
        .first()
    )
    existing_conditions = (existing.expected_conditions or {}) if existing else {}
    existing_chart = (existing_conditions.get("chart_analysis") or {}) if existing else {}
    needs_chart_reprocess = (
        bool(media_urls)
        and settings.openai_image_extraction_enabled
        and not existing_chart.get("image_analysis_attempted")
    )
    needs_mechanism_reprocess = existing is not None and not existing_conditions.get("author_mechanism")
    if existing and not (needs_chart_reprocess or needs_mechanism_reprocess):
        source.processed = True
        db.commit()
        return {
            "source_id": source.id,
            "insight_id": existing.id,
            "already_processed": True,
            "reconciled": True,
            "bias": existing.bias,
            "timeframe": existing.timeframe,
            "symbols": existing.symbols or [],
            "concepts": existing.concepts or [],
            "psychology": existing.psychology or {},
            "expected_conditions": existing.expected_conditions or {},
            "confidence": existing.confidence,
        }
    extracted = extract_knowledge(source.raw_text or source.raw_html, media_urls)
    insight = ExtractedInsight(source_document_id=source.id, **extracted)
    source.processed = True
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return {"source_id": source.id, "insight_id": insight.id, **extracted}


def process_pending_sources(
    db: Session,
    limit: int = 50,
    worker_index: int | None = None,
    worker_count: int | None = None,
) -> dict:
    safe_limit = max(1, min(limit, 500))
    safe_worker_count = max(1, min(int(worker_count or 1), 16))
    safe_worker_index = max(0, min(int(worker_index or 0), safe_worker_count - 1))
    query = db.query(SourceDocument).filter_by(processed=False)
    if safe_worker_count > 1:
        query = query.filter(SourceDocument.id.op("%")(safe_worker_count) == safe_worker_index)
    sources = (
        query.order_by(SourceDocument.media_paths.is_(None), SourceDocument.ingested_at.asc())
        .limit(safe_limit)
        .all()
    )
    results = []
    for source in sources:
        result = process_source(db, source.id)
        if result:
            results.append(result)
    reconciled = sum(1 for item in results if item.get("reconciled"))
    return {
        "seen": len(sources),
        "processed": len(results),
        "reconciled": reconciled,
        "worker_index": safe_worker_index,
        "worker_count": safe_worker_count,
        "results": results,
    }
