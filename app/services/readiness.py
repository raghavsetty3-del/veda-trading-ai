import os

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
    closed = [row for row in rows if row.closed_at is not None or row.realized_pnl is not None]
    pnl_values = [row.realized_pnl for row in closed if row.realized_pnl is not None]
    r_values = [row.r_multiple for row in closed if row.r_multiple is not None]
    wins = [value for value in pnl_values if value > 0]
    return {
        "symbol": symbol.upper(),
        "total_paper_trades": len(rows),
        "closed_paper_trades": len(closed),
        "net_realized_pnl": round(sum(pnl_values), 2),
        "closed_win_rate": round(len(wins) / len(pnl_values), 4) if pnl_values else None,
        "average_r_multiple": round(sum(r_values) / len(r_values), 3) if r_values else None,
    }


def _candle_count(db: Session, symbol: str) -> int:
    return db.query(MarketCandle).filter(MarketCandle.symbol == symbol.upper()).count()


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
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        expected_type = (row.expected_json or {}).get("type")
        if expected_type == "trade_export_performance" and row.status != "pass":
            trade_export_failures += 1
    return {
        "total": len(rows),
        "by_status": by_status,
        "trade_export_failures": trade_export_failures,
    }


def build_readiness_report(db: Session) -> dict:
    market_status = market_provider_status()
    telegram = telegram_status()
    extraction = extraction_status()
    validation = _validation_summary(db)
    symbols = ["NIFTY", "BANKNIFTY"]
    paper = [_paper_metrics(db, symbol) for symbol in symbols]
    candle_counts = {symbol: _candle_count(db, symbol) for symbol in symbols}
    restore_drill = _latest_successful_audit(db, "ops.restore_drill")
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
            "ready": all(candle_counts[symbol] >= 100 for symbol in symbols),
            "detail": f"Candle counts: {candle_counts}",
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
            "ready": validation["trade_export_failures"] == 0,
            "detail": f"Failed trade-export validations: {validation['trade_export_failures']}",
        },
        {
            "gate": "restore_drill_seen",
            "ready": restore_drill is not None,
            "detail": restore_drill["created_at"] if restore_drill else "No successful restore drill audit event found.",
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
        "restore_drill": restore_drill,
    }
