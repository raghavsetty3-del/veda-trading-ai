from typing import Any

from sqlalchemy.orm import Session

from app.models import ExtractedInsight, SourceDocument


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _join_list(value: Any) -> str:
    return ", ".join(str(item) for item in _as_list(value) if item not in (None, ""))


def _detail_score(groups: list[Any]) -> int:
    return sum(1 for group in groups for item in _as_list(group) if str(item).strip())


def _text_preview(value: str | None, limit: int = 320) -> str | None:
    if not value:
        return None
    clean = " ".join(str(value).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _source_dict(source: SourceDocument | None) -> dict[str, Any]:
    if source is None:
        return {
            "id": None,
            "source_type": None,
            "title": None,
            "author": None,
            "source_url": None,
            "published_at": None,
            "ingested_at": None,
            "media_count": 0,
            "text_preview": None,
        }
    media_paths = source.media_paths if isinstance(source.media_paths, list) else []
    return {
        "id": source.id,
        "source_type": source.source_type,
        "title": source.title,
        "author": source.author,
        "source_url": source.source_url,
        "published_at": source.published_at.isoformat() if source.published_at else None,
        "ingested_at": source.ingested_at.isoformat() if source.ingested_at else None,
        "media_count": len(media_paths),
        "text_preview": _text_preview(source.raw_text or source.raw_html),
    }


def _insight_row(insight: ExtractedInsight, source: SourceDocument | None) -> dict[str, Any]:
    conditions = insight.expected_conditions or {}
    chart = conditions.get("chart_analysis") or {}
    mechanism = conditions.get("author_mechanism") or {}
    image_count = int(chart.get("image_count") or 0)
    has_chart = bool(chart.get("has_chart_context") or image_count > 0)
    chart_detail_score = _detail_score([
        chart.get("visible_timeframes"),
        chart.get("visible_indicators"),
        chart.get("price_levels"),
        chart.get("pattern_notes"),
        chart.get("trade_context"),
    ])
    mechanism_detail_score = _detail_score([
        mechanism.get("mindset"),
        mechanism.get("decision_process"),
        mechanism.get("entry_mechanisms"),
        mechanism.get("exit_mechanisms"),
        mechanism.get("risk_mechanisms"),
        mechanism.get("timeframe_alignment"),
        mechanism.get("market_regime_filter"),
        mechanism.get("automation_candidates"),
    ])
    if chart_detail_score:
        review_quality = "visual_actionable"
    elif mechanism_detail_score:
        review_quality = "mechanism_actionable"
    elif has_chart:
        review_quality = "archived_only"
    else:
        review_quality = "text_only"
    return {
        "insight_id": insight.id,
        "source": _source_dict(source),
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
        "bias": insight.bias,
        "timeframe": insight.timeframe,
        "symbols": insight.symbols or [],
        "concepts": insight.concepts or [],
        "confidence": insight.confidence,
        "has_chart_context": has_chart,
        "image_count": image_count,
        "image_analysis_attempted": bool(chart.get("image_analysis_attempted")),
        "image_inputs_prepared": int(chart.get("image_inputs_prepared") or 0),
        "chart_detail_score": chart_detail_score,
        "mechanism_detail_score": mechanism_detail_score,
        "review_quality": review_quality,
        "visible_timeframes": _as_list(chart.get("visible_timeframes")),
        "visible_indicators": _as_list(chart.get("visible_indicators")),
        "price_levels": _as_list(chart.get("price_levels")),
        "pattern_notes": _as_list(chart.get("pattern_notes")),
        "trade_context": chart.get("trade_context"),
        "chart_caveats": _as_list(chart.get("caveats")),
        "mindset": _as_list(mechanism.get("mindset")),
        "decision_process": _as_list(mechanism.get("decision_process")),
        "entry_mechanisms": _as_list(mechanism.get("entry_mechanisms")),
        "exit_mechanisms": _as_list(mechanism.get("exit_mechanisms")),
        "risk_mechanisms": _as_list(mechanism.get("risk_mechanisms")),
        "timeframe_alignment": _as_list(mechanism.get("timeframe_alignment")),
        "market_regime_filter": _as_list(mechanism.get("market_regime_filter")),
        "automation_candidates": _as_list(mechanism.get("automation_candidates")),
        "non_automatable_judgment": _as_list(mechanism.get("non_automatable_judgment")),
        "table_summary": {
            "review_quality": review_quality,
            "image_analysis_attempted": str(bool(chart.get("image_analysis_attempted"))),
            "symbols": _join_list(insight.symbols),
            "concepts": _join_list(insight.concepts),
            "visible_timeframes": _join_list(chart.get("visible_timeframes")),
            "visible_indicators": _join_list(chart.get("visible_indicators")),
            "price_levels": _join_list(chart.get("price_levels")),
            "pattern_notes": _join_list(chart.get("pattern_notes")),
            "mindset": _join_list(mechanism.get("mindset")),
            "entry": _join_list(mechanism.get("entry_mechanisms")),
            "exit": _join_list(mechanism.get("exit_mechanisms")),
            "risk": _join_list(mechanism.get("risk_mechanisms")),
        },
    }


def chart_insight_samples(
    db: Session,
    limit: int = 25,
    chart_only: bool = True,
    actionable_only: bool = False,
    visual_only: bool = False,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 25), 200))
    query = (
        db.query(ExtractedInsight, SourceDocument)
        .outerjoin(SourceDocument, ExtractedInsight.source_document_id == SourceDocument.id)
        .filter(ExtractedInsight.confidence.isnot(None))
        .order_by(ExtractedInsight.created_at.desc())
        .limit(limit * 50 if chart_only or actionable_only or visual_only else limit)
    )

    rows = []
    scanned = 0
    quality_counts = {"visual_actionable": 0, "mechanism_actionable": 0, "archived_only": 0, "text_only": 0}
    for insight, source in query.all():
        scanned += 1
        row = _insight_row(insight, source)
        quality_counts[row["review_quality"]] = quality_counts.get(row["review_quality"], 0) + 1
        if chart_only and not row["has_chart_context"]:
            continue
        if actionable_only and row["review_quality"] not in {"visual_actionable", "mechanism_actionable"}:
            continue
        if visual_only and row["review_quality"] != "visual_actionable":
            continue
        rows.append(row)
        if len(rows) >= limit:
            break

    return {
        "available": bool(rows),
        "limit": limit,
        "chart_only": chart_only,
        "actionable_only": actionable_only,
        "visual_only": visual_only,
        "scanned": scanned,
        "quality_counts": quality_counts,
        "items": rows,
    }
