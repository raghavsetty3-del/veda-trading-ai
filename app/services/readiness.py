import os

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog, MarketCandle, PaperTrade, ValidationCase
from app.services.market_provider import market_provider_status
from app.ingestion.telegram_listener import telegram_status
from app.services.knowledge_extraction import extraction_status
from app.services.recovery import get_kill_switch


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
    return {
        "symbol": symbol.upper(),
        "total_paper_trades": len(rows),
        "open_paper_trades": len(open_rows),
        "open_trade_ids": [row.id for row in open_rows],
        "open_sides": sorted({row.side for row in open_rows}),
        "open_risk_points": round(open_risk_points, 2),
        "open_reward_points": round(open_reward_points, 2),
        "open_reward_risk_ratio": round(open_reward_points / open_risk_points, 3) if open_risk_points > 0 else None,
        "closed_paper_trades": len(closed),
        "minimum_review_trades": 20,
        "sample_ready": len(closed) >= 20,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_realized_pnl": round(sum(pnl_values), 2),
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


def _validation_summary(db: Session) -> dict:
    rows = db.query(ValidationCase).order_by(ValidationCase.created_at.desc()).limit(500).all()
    by_status: dict[str, int] = {}
    trade_export_failures = 0
    reviewed_trade_export_failures = 0
    unreviewed_trade_export_failures = 0
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        expected_type = (row.expected_json or {}).get("type")
        if expected_type == "trade_export_performance" and row.status != "pass":
            trade_export_failures += 1
            if _reviewed_failed_trade_export(row):
                reviewed_trade_export_failures += 1
            else:
                unreviewed_trade_export_failures += 1
    return {
        "total": len(rows),
        "by_status": by_status,
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


def build_readiness_report(db: Session) -> dict:
    market_status = market_provider_status()
    telegram = telegram_status()
    extraction = extraction_status()
    validation = _validation_summary(db)
    symbols = ["NIFTY", "BANKNIFTY"]
    paper = [_paper_metrics(db, symbol) for symbol in symbols]
    candle_counts = {symbol: _candle_count(db, symbol) for symbol in symbols}
    provider_candle_counts = {symbol: _provider_candle_count(db, symbol) for symbol in symbols}
    non_production_source_counts = _non_production_source_counts(db)
    restore_drill = _latest_successful_audit(db, "ops.restore_drill")
    offsite_backup = _latest_successful_audit(db, "ops.offsite_backup")
    kill_switch = get_kill_switch(db)

    gates = [
        {
            "gate": "live_trading_disabled",
            "ready": not settings.enable_live_trading and not kill_switch,
            "detail": "Live trading env flag is disabled and kill switch is off.",
        },
        {
            "gate": "market_data_provider_configured",
            "ready": market_status["configured"],
            "detail": f"{market_status['source_count']} configured provider sources.",
        },
        {
            "gate": "historical_candles_loaded",
            "ready": all(provider_candle_counts[symbol] >= 100 for symbol in symbols),
            "detail": f"Provider-backed candle counts: {provider_candle_counts}; total counts: {candle_counts}",
        },
        {
            "gate": "closed_paper_trades_ready",
            "ready": all(item["closed_paper_trades"] >= 20 for item in paper),
            "detail": f"Closed paper trades: { {item['symbol']: item['closed_paper_trades'] for item in paper} }",
        },
        {
            "gate": "paper_pnl_positive",
            "ready": all(item["net_realized_pnl"] > 0 for item in paper),
            "detail": f"Net realized P&L: { {item['symbol']: item['net_realized_pnl'] for item in paper} }",
        },
        {
            "gate": "failed_trade_exports_reviewed",
            "ready": validation["unreviewed_trade_export_failures"] == 0,
            "detail": (
                f"Unreviewed failed trade-export validations: {validation['unreviewed_trade_export_failures']}; "
                f"reviewed failures retained: {validation['reviewed_trade_export_failures']}"
            ),
        },
        {
            "gate": "restore_drill_seen",
            "ready": restore_drill is not None,
            "detail": restore_drill["created_at"] if restore_drill else "No successful restore drill audit event found.",
        },
        {
            "gate": "offsite_backup_seen",
            "ready": offsite_backup is not None,
            "detail": offsite_backup["created_at"] if offsite_backup else "No successful offsite backup audit event found.",
        },
        {
            "gate": "external_alert_receiver_configured",
            "ready": bool(os.getenv("HEALTHWATCH_WEBHOOK_URL")),
            "detail": "HEALTHWATCH_WEBHOOK_URL visible to API process." if os.getenv("HEALTHWATCH_WEBHOOK_URL") else "Webhook hook exists; receiver URL not configured in API env.",
        },
        {
            "gate": "telegram_configured",
            "ready": telegram["configured"],
            "detail": f"Missing: {telegram['missing']}",
        },
        {
            "gate": "openai_extraction_ready",
            "ready": extraction["openai_enabled"] and extraction["openai_key_present"],
            "detail": "Optional enrichment only; deterministic extraction is active.",
        },
    ]

    missing_inputs = []
    if not market_status["configured"]:
        missing_inputs.append("MARKET_DATA_SOURCES or broker/provider credentials")
    angelone = market_status.get("angelone", {})
    if angelone.get("source_count") and not angelone.get("configured"):
        missing_inputs.extend(angelone.get("missing", []))
    dhan = market_status.get("dhan", {})
    if dhan.get("source_count") and not dhan.get("configured"):
        missing_inputs.extend(dhan.get("missing", []))
    if not telegram["configured"]:
        missing_inputs.extend(telegram["missing"])
    if not extraction["openai_key_present"]:
        missing_inputs.append("OPENAI_API_KEY if AI enrichment is desired")
    if not os.getenv("HEALTHWATCH_WEBHOOK_URL"):
        missing_inputs.append("HEALTHWATCH_WEBHOOK_URL if external alerts are desired")
    if not settings.blog_feeds:
        missing_inputs.append("BLOG_FEEDS for production RSS ingestion")

    ready_for_live_review = all(gate["ready"] for gate in gates[:7])
    return {
        "ready_for_live_review": ready_for_live_review,
        "live_trading_enabled": settings.enable_live_trading,
        "kill_switch": kill_switch,
        "gates": gates,
        "missing_inputs": sorted(set(missing_inputs)),
        "market_provider": market_status,
        "telegram": telegram,
        "extraction": extraction,
        "validation": validation,
        "paper": paper,
        "candle_counts": candle_counts,
        "provider_candle_counts": provider_candle_counts,
        "non_production_source_counts": non_production_source_counts,
        "restore_drill": restore_drill,
        "offsite_backup": offsite_backup,
    }
