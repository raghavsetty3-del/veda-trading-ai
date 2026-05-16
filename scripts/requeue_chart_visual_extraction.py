#!/usr/bin/env python3
"""Requeue chart-backed sources whose visual image analysis was never attempted."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models import ExtractedInsight, SourceDocument  # noqa: E402


def latest_insight(db, source_id: int) -> ExtractedInsight | None:
    return (
        db.query(ExtractedInsight)
        .filter(
            ExtractedInsight.source_document_id == source_id,
            ExtractedInsight.confidence.isnot(None),
        )
        .order_by(ExtractedInsight.created_at.desc())
        .first()
    )


def needs_visual_attempt(insight: ExtractedInsight | None) -> bool:
    if insight is None:
        return True
    conditions = insight.expected_conditions or {}
    chart = conditions.get("chart_analysis") or {}
    return not bool(chart.get("image_analysis_attempted"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    safe_limit = max(1, min(args.limit, 1000))
    with SessionLocal() as db:
        candidates = (
            db.query(SourceDocument)
            .filter(SourceDocument.media_paths.isnot(None))
            .filter(SourceDocument.processed.is_(True))
            .order_by(SourceDocument.ingested_at.asc())
            .limit(safe_limit * 10)
            .all()
        )
        selected = []
        for source in candidates:
            if not source.media_paths:
                continue
            insight = latest_insight(db, source.id)
            if needs_visual_attempt(insight):
                selected.append(source)
            if len(selected) >= safe_limit:
                break

        if args.apply:
            for source in selected:
                source.processed = False
            db.commit()

        print(json.dumps({
            "apply": args.apply,
            "requested_limit": safe_limit,
            "scanned": len(candidates),
            "requeued": len(selected),
            "source_ids": [source.id for source in selected[:50]],
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
