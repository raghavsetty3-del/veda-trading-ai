import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog, ExtractedInsight, MarketCandle, PaperTrade, SourceDocument, ValidationCase
from app.services.market_provider import market_provider_status
from app.ingestion.telegram_listener import telegram_status
from app.services.knowledge_extraction import extraction_status
from app.services.recovery import get_kill_switch
from app.services.x_ingestion import x_status


def _paper_metrics(db: Session, symbol: str) -> dict:
    rows = (
        db.query(PaperTrade)
        .filter(PaperTrade.symbol == symbol.upper())
        .order_by(PaperTrade.created_at.desc())
        .limit(500)
        .all()
    )
    closed = [row for row in rows if row.realized_pnl is not None]
    open_rows = [row for row in rows if row.status == "planned"]
    pnl_values = [row.realized_pnl for row in closed if row.realized_pnl is not None]
    r_values = [row.r_multiple for row in closed if row.r_multiple is not None]
    wins = [value for value in pnl_values if value > 0]
    open_risk_points = 0.0
    open_reward_points = 0.0
    for row in open_rows:
        if row.stop_loss is not None:
            open_risk_points += abs(row.entry_price - row.stop_loss) * row.quantity
        if row.target is not None:
            open_reward_points += abs(row.target - row.entry_price) * row.quantity
    gross_profit = round(sum(value for value in pnl_values if value > 0), 2)
    gross_loss = round(abs(sum(value for value in pnl_values if value < 0)), 2)
    if not pnl_values:
        profit_factor = None
        profit_factor_label = "N/A"
    elif gross_loss == 0 and gross_profit > 0:
        profit_factor = None
        profit_factor_label = "Infinite (no realized losses yet)"
    elif gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 3)
        profit_factor_label = str(profit_factor)
    else:
        profit_factor = 0.0
        profit_factor_label = "0.0"
    minimum_review_trades = 20
    closed_count = len(closed)
    net_realized_pnl = round(sum(pnl_values), 2)
    return {
        "symbol": symbol.upper(),
        "total_paper_trades": len(rows),
        "open_paper_trades": len(open_rows),
        "open_trade_ids": [row.id for row in open_rows],
        "open_sides": sorted({row.side for row in open_rows}),
        "open_risk_points": round(open_risk_points, 2),
        "open_reward_points": round(open_reward_points, 2),
        "open_reward_risk_ratio": round(open_reward_points / open_risk_points, 3) if open_risk_points > 0 else None,
        "closed_paper_trades": closed_count,
        "minimum_review_trades": minimum_review_trades,
        "remaining_review_trades": max(0, minimum_review_trades - closed_count),
        "sample_ready": closed_count >= minimum_review_trades,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_realized_pnl": net_realized_pnl,
        "pnl_positive": net_realized_pnl > 0,
        "forward_review_ready": closed_count >= minimum_review_trades and net_realized_pnl > 0,
        "profit_factor": profit_factor,
        "profit_factor_label": profit_factor_label,
        "closed_win_rate": round(len(wins) / len(pnl_values), 4) if pnl_values else None,
        "average_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
    }


def _candle_count(db: Session, symbol: str) -> int:
    return db.query(MarketCandle).filter(MarketCandle.symbol == symbol.upper()).count()


def _provider_candle_count(db: Session, symbol: str) -> int:
    blocked_source_markers = ["manual", "smoke", "test", "demo", "sample"]
    query = db.query(MarketCandle).filter(MarketCandle.symbol == symbol.upper())
    for marker in blocked_source_markers:
        query = query.filter(~MarketCandle.source.ilike(f"%{marker}%"))
    return query.count()


def _non_production_source_counts(db: Session) -> dict:
    blocked_source_markers = ["manual", "smoke", "test", "demo", "sample"]
    counts: dict[str, int] = {}
    rows = (
        db.query(MarketCandle.symbol, MarketCandle.timeframe, MarketCandle.source, func.count(MarketCandle.id))
        .group_by(MarketCandle.symbol, MarketCandle.timeframe, MarketCandle.source)
        .all()
    )
    for symbol, timeframe, source, count in rows:
        source = source or "unknown"
        if any(marker in source.lower() for marker in blocked_source_markers):
            counts[f"{symbol}:{timeframe}:{source}"] = count
    return counts


def _source_archive_summary(db: Session) -> dict:
    total = db.query(SourceDocument).count()
    processed = db.query(SourceDocument).filter(SourceDocument.processed.is_(True)).count()
    full_insights = db.query(ExtractedInsight).filter(ExtractedInsight.confidence.isnot(None)).count()
    preview_insights = db.query(ExtractedInsight).filter(ExtractedInsight.confidence.is_(None)).count()
    media_scanned_sources = 0
    media_pending_scan_sources = 0
    media_url_total = 0
    chart_backed_sources = 0
    chart_backed_pending_extraction = 0
    for media_paths, processed_flag, raw_html in db.query(
        SourceDocument.media_paths,
        SourceDocument.processed,
        SourceDocument.raw_html,
    ).all():
        if media_paths is None:
            if raw_html is not None:
                media_pending_scan_sources += 1
            continue
        media_scanned_sources += 1
        media_count = len(media_paths) if isinstance(media_paths, list) else 0
        media_url_total += media_count
        if media_count:
            chart_backed_sources += 1
            if not processed_flag:
                chart_backed_pending_extraction += 1
    chart_insights = 0
    chart_images_analyzed = 0
    for (conditions,) in (
        db.query(ExtractedInsight.expected_conditions)
        .filter(ExtractedInsight.confidence.isnot(None))
        .all()
    ):
        chart = ((conditions or {}).get("chart_analysis") or {}) if isinstance(conditions, dict) else {}
        image_count = int(chart.get("image_count") or 0)
        if chart.get("has_chart_context") or image_count > 0:
            chart_insights += 1
            chart_images_analyzed += image_count
    by_type = {
        source_type: count
        for source_type, count in (
            db.query(SourceDocument.source_type, func.count(SourceDocument.id))
            .group_by(SourceDocument.source_type)
            .all()
        )
    }
    blog_authors = {
        author or "unknown": count
        for author, count in (
            db.query(SourceDocument.author, func.count(SourceDocument.id))
            .filter(SourceDocument.source_type == "blog")
            .group_by(SourceDocument.author)
            .all()
        )
    }
    return {
        "total_sources": total,
        "processed_sources": processed,
        "pending_sources": max(0, total - processed),
        "insights": db.query(ExtractedInsight).count(),
        "full_insights": full_insights,
        "archive_preview_insights": preview_insights,
        "media_scanned_sources": media_scanned_sources,
        "media_pending_scan_sources": media_pending_scan_sources,
        "media_url_total": int(media_url_total or 0),
        "chart_backed_sources": chart_backed_sources,
        "chart_backed_pending_extraction": chart_backed_pending_extraction,
        "chart_insights": chart_insights,
        "chart_images_analyzed": chart_images_analyzed,
        "by_type": by_type,
        "blog_authors": blog_authors,
    }


def _latest_successful_audit(db: Session, event_type: str) -> dict | None:
    row = (
        db.query(AuditLog)
        .filter(AuditLog.event_type == event_type, AuditLog.severity == "INFO")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if not row:
        return None
    return {
        "message": row.message,
        "created_at": row.created_at.isoformat(),
        "payload": row.payload,
    }


def _latest_audit(db: Session, event_type: str) -> dict | None:
    row = (
        db.query(AuditLog)
        .filter(AuditLog.event_type == event_type)
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    if not row:
        return None
    return {
        "event_type": row.event_type,
        "severity": row.severity,
        "message": row.message,
        "created_at": row.created_at.isoformat(),
        "payload": row.payload,
    }


def _validation_summary(db: Session) -> dict:
    rows = db.query(ValidationCase).order_by(ValidationCase.created_at.desc()).limit(500).all()
    by_status: dict[str, int] = {}
    by_type_status: dict[str, dict[str, int]] = {}
    trade_export_failures = 0
    reviewed_trade_export_failures = 0
    unreviewed_trade_export_failures = 0
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        expected_type = (row.expected_json or {}).get("type")
        if expected_type:
            type_counts = by_type_status.setdefault(expected_type, {})
            type_counts[row.status] = type_counts.get(row.status, 0) + 1
        if expected_type == "trade_export_performance" and row.status != "pass":
            trade_export_failures += 1
            if _reviewed_failed_trade_export(row):
                reviewed_trade_export_failures += 1
            else:
                unreviewed_trade_export_failures += 1
    return {
        "total": len(rows),
        "by_status": by_status,
        "by_type_status": by_type_status,
        "trade_export_failures": trade_export_failures,
        "reviewed_trade_export_failures": reviewed_trade_export_failures,
        "unreviewed_trade_export_failures": unreviewed_trade_export_failures,
    }


def _reviewed_failed_trade_export(row: ValidationCase) -> bool:
    delivered = row.delivered_json or {}
    review = delivered.get("trade_export_review") if isinstance(delivered, dict) else None
    if isinstance(review, dict):
        disposition = str(review.get("disposition") or "").lower()
        if review.get("reviewed") is True and disposition in {"not_promoted", "needs_rework", "excluded"}:
            return True
    return "[reviewed_trade_export_failure]" in (row.notes or "").lower()


def _serialize_replay_validation(row: ValidationCase) -> dict:
    expected = row.expected_json or {}
    delivered = row.delivered_json or {}
    metrics = delivered.get("metrics") if isinstance(delivered, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    checks = delivered.get("checks") if isinstance(delivered, dict) else {}
    checks = checks if isinstance(checks, dict) else {}
    return {
        "case_code": row.case_code,
        "title": row.title,
        "symbol": str(expected.get("symbol") or delivered.get("symbol") or "").upper(),
        "timeframe": expected.get("timeframe") or delivered.get("timeframe"),
        "status": row.status,
        "score": row.score,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
        "source_candles": delivered.get("source_candles"),
        "exit_mode": delivered.get("exit_mode"),
        "cooldown_candles": delivered.get("cooldown_candles"),
        "realized_trades": metrics.get("realized_trades"),
        "net_realized_pnl": metrics.get("net_realized_pnl"),
        "profit_factor": metrics.get("profit_factor"),
        "profit_factor_label": metrics.get("profit_factor_label"),
        "average_r_multiple": metrics.get("average_r_multiple"),
        "checks": checks,
    }


def _historical_paper_replay_summary(db: Session, symbols: list[str]) -> dict:
    target_symbols = [symbol.upper() for symbol in symbols]
    rows = db.query(ValidationCase).order_by(ValidationCase.created_at.desc()).limit(500).all()
    latest_by_symbol: dict[str, dict] = {}
    passing_by_symbol: dict[str, dict] = {}
    total_seen = 0

    for row in rows:
        expected = row.expected_json or {}
        if expected.get("type") != "historical_paper_replay":
            continue
        delivered = row.delivered_json or {}
        symbol = str(expected.get("symbol") or delivered.get("symbol") or "").upper()
        if symbol not in target_symbols:
            continue
        total_seen += 1
        item = _serialize_replay_validation(row)
        if symbol not in latest_by_symbol:
            latest_by_symbol[symbol] = item
        if row.status == "pass" and symbol not in passing_by_symbol:
            passing_by_symbol[symbol] = item

    missing_symbols = [symbol for symbol in target_symbols if symbol not in passing_by_symbol]
    return {
        "type": "historical_paper_replay",
        "required_symbols": target_symbols,
        "total_seen": total_seen,
        "latest_by_symbol": latest_by_symbol,
        "passing_by_symbol": passing_by_symbol,
        "missing_symbols": missing_symbols,
        "all_symbols_passed": not missing_symbols,
    }


def _historical_replay_gate_detail(evidence: dict) -> str:
    passing = {
        symbol: item.get("case_code")
        for symbol, item in sorted((evidence.get("passing_by_symbol") or {}).items())
    }
    missing = evidence.get("missing_symbols") or []
    if not passing:
        return f"No passing historical paper replay validations yet. Missing: {missing}"
    if missing:
        return f"Passing historical paper replay validations: {passing}; missing: {missing}"
    return f"Passing historical paper replay validations: {passing}"


def _parallel_workstreams(
    *,
    market_status: dict,
    provider_candle_counts: dict,
    source_archive: dict,
    telegram: dict,
    x_sources: dict,
    extraction: dict,
    historical_paper_replay: dict,
    paper: list[dict],
    restore_drill: dict | None,
    offsite_backup: dict | None,
) -> list[dict]:
    forward_ready = all(item["forward_review_ready"] for item in paper)
    remaining_by_symbol = {
        item["symbol"]: item["remaining_review_trades"]
        for item in paper
    }
    pnl_by_symbol = {
        item["symbol"]: item["net_realized_pnl"]
        for item in paper
    }
    provider_counts_ready = all(count >= 100 for count in provider_candle_counts.values())
    source_pending = int(source_archive.get("pending_sources") or 0)
    chart_pending = int(source_archive.get("chart_backed_pending_extraction") or 0)
    external_alert_ready = bool(os.getenv("HEALTHWATCH_WEBHOOK_URL"))
    blog_ready = bool(settings.blog_feeds)
    telegram_ready = (
        telegram["configured"]
        or (telegram.get("public_web") or {}).get("configured", False)
        or (telegram.get("bot_api") or {}).get("configured", False)
    )
    backup_ready = restore_drill is not None and offsite_backup is not None

    return [
        {
            "workstream": "Market data provider",
            "status": "done" if market_status["configured"] and provider_counts_ready else "needs_attention",
            "owner": "system",
            "blocked_by": None,
            "inputs_needed": [],
            "can_complete_before_paper_gate": True,
            "next_action": "Keep scheduled Dhan ingestion running for NIFTY and BANKNIFTY.",
            "detail": f"{market_status['operational_source_count']} operational sources; provider candles {provider_candle_counts}.",
        },
        {
            "workstream": "Author rules and historical replay",
            "status": "done" if historical_paper_replay["all_symbols_passed"] else "needs_attention",
            "owner": "system",
            "blocked_by": None,
            "inputs_needed": [],
            "can_complete_before_paper_gate": True,
            "next_action": "Keep replay validation passing after rule changes.",
            "detail": "Timestamp-correct NIFTY and BANKNIFTY historical paper replay evidence is saved.",
        },
        {
            "workstream": "Forward paper evidence",
            "status": "done" if forward_ready else "blocked_by_market_evidence",
            "owner": "system",
            "blocked_by": "Trading-session outcomes",
            "inputs_needed": [],
            "can_complete_before_paper_gate": False,
            "next_action": "Let the strict LRHR scheduler collect and reconcile realized exits.",
            "detail": f"Remaining realized exits {remaining_by_symbol}; realized P&L {pnl_by_symbol}.",
        },
        {
            "workstream": "Knowledge extraction",
            "status": "in_progress" if extraction["openai_enabled"] and extraction["openai_key_present"] and source_pending else ("done" if extraction["openai_enabled"] and extraction["openai_key_present"] else "input_needed"),
            "owner": "system",
            "blocked_by": None if extraction["openai_enabled"] and extraction["openai_key_present"] else "OpenAI API key",
            "inputs_needed": [] if extraction["openai_key_present"] else ["OPENAI_API_KEY"],
            "can_complete_before_paper_gate": True,
            "next_action": "Continue scheduled chart-first extraction and media enrichment.",
            "detail": (
                f"Pending sources={source_pending}; chart-backed pending={chart_pending}; "
                f"chart insights={source_archive.get('chart_insights', 0)}; "
                f"OpenAI enrichment enabled={extraction['openai_enabled']}."
            ),
        },
        {
            "workstream": "Telegram live ingestion",
            "status": "done" if telegram_ready else "input_needed",
            "owner": "user",
            "blocked_by": None if telegram_ready else "Telegram API credentials, bot token, or public channel links",
            "inputs_needed": [] if telegram_ready else telegram["missing"] + ["TELEGRAM_BOT_TOKEN", "TELEGRAM_PUBLIC_CHANNELS"],
            "can_complete_before_paper_gate": True,
            "next_action": "Use Bot API for private channels, public web ingestion for public channels, or configure API credentials after my.telegram.org rate limit clears.",
            "detail": (
                f"Export ingestion works; bot API configured={(telegram.get('bot_api') or {}).get('configured', False)}; "
                f"public web configured={(telegram.get('public_web') or {}).get('configured', False)}; "
                f"API listener configured={telegram['configured']}."
            ),
        },
        {
            "workstream": "Blog/RSS ingestion",
            "status": "done" if blog_ready else "input_needed",
            "owner": "user",
            "blocked_by": None if blog_ready else "Production RSS feed URLs",
            "inputs_needed": [] if blog_ready else ["BLOG_FEEDS"],
            "can_complete_before_paper_gate": True,
            "next_action": "Keep Ilango-only scheduled ingestion running and process archived sources in controlled batches.",
            "detail": "Manual, scheduled, and backfill RSS ingestion are present.",
        },
        {
            "workstream": "X/Twitter ingestion",
            "status": "done" if x_sources["configured"] else "input_needed",
            "owner": "user",
            "blocked_by": None if x_sources["configured"] else "X API bearer token and usernames",
            "inputs_needed": x_sources["missing"],
            "can_complete_before_paper_gate": True,
            "next_action": "Add X_BEARER_TOKEN and X_USERNAMES, then scheduled ingestion will archive and extract recent posts.",
            "detail": "Official X API v2 ingestion is optional and depends on the account's API read access.",
        },
        {
            "workstream": "External health alerts",
            "status": "done" if external_alert_ready else "input_needed",
            "owner": "user",
            "blocked_by": None if external_alert_ready else "Webhook receiver URL",
            "inputs_needed": [] if external_alert_ready else ["HEALTHWATCH_WEBHOOK_URL"],
            "can_complete_before_paper_gate": True,
            "next_action": "Add webhook URL to .healthwatch.env if external alerts are desired.",
            "detail": "Healthwatch auto-healing and local audit logging are already active.",
        },
        {
            "workstream": "Backup and restore monitoring",
            "status": "done" if backup_ready else "needs_attention",
            "owner": "system",
            "blocked_by": None,
            "inputs_needed": [],
            "can_complete_before_paper_gate": True,
            "next_action": "Continue daily offsite backups and weekly restore drills.",
            "detail": "Latest restore drill and offsite backup are visible in readiness.",
        },
        {
            "workstream": "Shared-access security hardening",
            "status": "optional",
            "owner": "user",
            "blocked_by": "Decision to share the app beyond personal use",
            "inputs_needed": [],
            "can_complete_before_paper_gate": True,
            "next_action": "Keep Basic Auth for personal use; add stronger auth before sharing wider.",
            "detail": "Not required for paper evidence or personal operation.",
        },
    ]


def build_readiness_report(db: Session) -> dict:
    market_status = market_provider_status()
    telegram = telegram_status()
    x_sources = x_status()
    extraction = extraction_status()
    validation = _validation_summary(db)
    symbols = ["NIFTY", "BANKNIFTY"]
    paper = [_paper_metrics(db, symbol) for symbol in symbols]
    historical_paper_replay = _historical_paper_replay_summary(db, symbols)
    candle_counts = {symbol: _candle_count(db, symbol) for symbol in symbols}
    provider_candle_counts = {symbol: _provider_candle_count(db, symbol) for symbol in symbols}
    non_production_source_counts = _non_production_source_counts(db)
    source_archive = _source_archive_summary(db)
    restore_drill = _latest_successful_audit(db, "ops.restore_drill")
    offsite_backup = _latest_successful_audit(db, "ops.offsite_backup")
    latest_jobs = {
        "paper_scheduler": _latest_audit(db, "paper.scheduler_run"),
        "market_provider_ingest": _latest_audit(db, "market.provider_ingest_configured"),
        "source_extraction": _latest_audit(db, "extraction.scheduled_process_pending") or _latest_audit(db, "extraction.process_pending"),
        "source_media_enrichment": _latest_audit(db, "extraction.scheduled_media_enrichment"),
        "blog_ingest": _latest_audit(db, "blog.configured_ingest"),
        "telegram_bot_ingest": _latest_audit(db, "telegram.bot_ingested"),
        "telegram_public_ingest": _latest_audit(db, "telegram.public_ingested"),
        "x_ingest": _latest_audit(db, "x.configured_ingest"),
    }
    kill_switch = get_kill_switch(db)

    gates = [
        {
            "gate": "live_trading_disabled",
            "required": True,
            "ready": not settings.enable_live_trading and not kill_switch,
            "detail": "Live trading env flag is disabled and kill switch is off.",
        },
        {
            "gate": "market_data_provider_configured",
            "required": True,
            "ready": market_status["configured"],
            "detail": f"{market_status['source_count']} configured provider sources.",
        },
        {
            "gate": "historical_candles_loaded",
            "required": True,
            "ready": all(provider_candle_counts[symbol] >= 100 for symbol in symbols),
            "detail": f"Provider-backed candle counts: {provider_candle_counts}; total counts: {candle_counts}",
        },
        {
            "gate": "historical_paper_replay_passed",
            "required": True,
            "ready": historical_paper_replay["all_symbols_passed"],
            "detail": _historical_replay_gate_detail(historical_paper_replay),
        },
        {
            "gate": "closed_paper_trades_ready",
            "required": True,
            "ready": all(item["closed_paper_trades"] >= 20 for item in paper),
            "detail": f"Closed paper trades: { {item['symbol']: item['closed_paper_trades'] for item in paper} }",
        },
        {
            "gate": "paper_pnl_positive",
            "required": True,
            "ready": all(item["net_realized_pnl"] > 0 for item in paper),
            "detail": f"Net realized P&L: { {item['symbol']: item['net_realized_pnl'] for item in paper} }",
        },
        {
            "gate": "failed_trade_exports_reviewed",
            "required": True,
            "ready": validation["unreviewed_trade_export_failures"] == 0,
            "detail": (
                f"Unreviewed failed trade-export validations: {validation['unreviewed_trade_export_failures']}; "
                f"reviewed failures retained: {validation['reviewed_trade_export_failures']}"
            ),
        },
        {
            "gate": "restore_drill_seen",
            "required": True,
            "ready": restore_drill is not None,
            "detail": restore_drill["created_at"] if restore_drill else "No successful restore drill audit event found.",
        },
        {
            "gate": "offsite_backup_seen",
            "required": True,
            "ready": offsite_backup is not None,
            "detail": offsite_backup["created_at"] if offsite_backup else "No successful offsite backup audit event found.",
        },
        {
            "gate": "external_alert_receiver_configured",
            "required": False,
            "ready": bool(os.getenv("HEALTHWATCH_WEBHOOK_URL")),
            "detail": "HEALTHWATCH_WEBHOOK_URL visible to API process." if os.getenv("HEALTHWATCH_WEBHOOK_URL") else "Webhook hook exists; receiver URL not configured in API env.",
        },
        {
            "gate": "telegram_configured",
            "required": False,
            "ready": (
                telegram["configured"]
                or (telegram.get("bot_api") or {}).get("configured", False)
                or (telegram.get("public_web") or {}).get("configured", False)
            ),
            "detail": (
                f"API missing: {telegram['missing']}; "
                f"bot API configured={(telegram.get('bot_api') or {}).get('configured', False)}; "
                f"public web configured={(telegram.get('public_web') or {}).get('configured', False)}"
            ),
        },
        {
            "gate": "x_configured",
            "required": False,
            "ready": x_sources["configured"],
            "detail": f"Missing: {x_sources['missing']}",
        },
        {
            "gate": "openai_extraction_ready",
            "required": False,
            "ready": extraction["openai_enabled"] and extraction["openai_key_present"],
            "detail": "Optional enrichment only; deterministic extraction is active.",
        },
    ]

    missing_required_inputs = []
    optional_missing_inputs = []
    if not market_status["configured"]:
        missing_required_inputs.append("MARKET_DATA_SOURCES or broker/provider credentials")
    angelone = market_status.get("angelone", {})
    if angelone.get("source_count") and not angelone.get("configured"):
        missing_required_inputs.extend(angelone.get("missing", []))
    dhan = market_status.get("dhan", {})
    if dhan.get("source_count") and not dhan.get("configured"):
        missing_required_inputs.extend(dhan.get("missing", []))
    if not (
        telegram["configured"]
        or (telegram.get("bot_api") or {}).get("configured", False)
        or (telegram.get("public_web") or {}).get("configured", False)
    ):
        optional_missing_inputs.extend(telegram["missing"])
        optional_missing_inputs.append("TELEGRAM_BOT_TOKEN")
        optional_missing_inputs.append("TELEGRAM_PUBLIC_CHANNELS")
    if not x_sources["configured"]:
        optional_missing_inputs.extend(x_sources["missing"])
    if not extraction["openai_key_present"]:
        optional_missing_inputs.append("OPENAI_API_KEY if AI enrichment is desired")
    if not os.getenv("HEALTHWATCH_WEBHOOK_URL"):
        optional_missing_inputs.append("HEALTHWATCH_WEBHOOK_URL if external alerts are desired")
    if not settings.blog_feeds:
        optional_missing_inputs.append("BLOG_FEEDS for production RSS ingestion")

    required_gates = [gate for gate in gates if gate["required"]]
    advisory_gates = [gate for gate in gates if not gate["required"]]
    blocking_gates = [gate["gate"] for gate in required_gates if not gate["ready"]]
    ready_for_live_review = not blocking_gates
    missing_required_inputs = sorted(set(missing_required_inputs))
    optional_missing_inputs = sorted(set(optional_missing_inputs))
    parallel_workstreams = _parallel_workstreams(
        market_status=market_status,
        provider_candle_counts=provider_candle_counts,
        source_archive=source_archive,
        telegram=telegram,
        x_sources=x_sources,
        extraction=extraction,
        historical_paper_replay=historical_paper_replay,
        paper=paper,
        restore_drill=restore_drill,
        offsite_backup=offsite_backup,
    )
    return {
        "ready_for_live_review": ready_for_live_review,
        "live_trading_enabled": settings.enable_live_trading,
        "kill_switch": kill_switch,
        "gates": gates,
        "required_gates": required_gates,
        "advisory_gates": advisory_gates,
        "blocking_gates": blocking_gates,
        "missing_required_inputs": missing_required_inputs,
        "optional_missing_inputs": optional_missing_inputs,
        "missing_inputs": sorted(set(missing_required_inputs + optional_missing_inputs)),
        "market_provider": market_status,
        "telegram": telegram,
        "x_sources": x_sources,
        "extraction": extraction,
        "validation": validation,
        "historical_paper_replay": historical_paper_replay,
        "paper": paper,
        "candle_counts": candle_counts,
        "provider_candle_counts": provider_candle_counts,
        "non_production_source_counts": non_production_source_counts,
        "source_archive": source_archive,
        "restore_drill": restore_drill,
        "offsite_backup": offsite_backup,
        "latest_jobs": latest_jobs,
        "parallel_workstreams": parallel_workstreams,
    }
