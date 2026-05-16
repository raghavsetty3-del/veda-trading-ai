from datetime import datetime
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import AuditLog, AuthorPrinciple, ExtractedInsight, MarketCandle, PaperTrade, RuleMapping, SourceDocument, SystemState, ValidationCase
from app.schemas import AuditEvent, BacktestRequest, BlogBackfillRequest, CandleBacktestRequest, CandleReplayValidationRequest, MarketCandleBulkCreate, MarketCandleCreate, MarketProviderIngestRequest, MarketSnapshotRequest, PaperReplayBacktestRequest, PaperReplayValidationRequest, PaperSchedulerRunRequest, PaperTradeReconcileRequest, PaperTradeRequest, PaperTradeStatusUpdate, PaperTradeValidationRequest, PrincipleCreate, RuleActivationRequest, RuleEvaluationRequest, RuleMappingCreate, RuleSuggestionPromotionRequest, SetupEvaluationRequest, SourceDocumentCreate, TelegramBotIngestRequest, TelegramExportIngestRequest, TelegramLiveIngestRequest, TelegramPublicIngestRequest, TradeExportValidationRequest, ValidationCaseCreate, ValidationResultUpdate, XExportIngestRequest, XIngestRequest
from app.services.audit import audit
from app.services.angelone_market_data import angelone_status
from app.services.backtesting import evaluate_backtest, evaluate_candle_backtest
from app.services.blog_ingestion import backfill_feed_pages, backfill_wordpress_site, ingest_blog_feed, ingest_configured_blog_feeds
from app.services.dhan_market_data import dhan_status
from app.services.instrument_profiles import PROFILES, apply_instrument_profile, get_instrument_profile
from app.services.knowledge_extraction import extraction_status, process_pending_sources, process_source
from app.services.market_data import latest_candles, market_snapshot, upsert_candle, upsert_candles
from app.services.market_provider import ingest_configured_market_sources, ingest_market_source, market_provider_status
from app.services.ml_analysis import ml_snapshot
from app.services.paper_scheduler import paper_scheduler_config, run_scheduled_paper_trading
from app.services.paper_evidence_state import build_paper_evidence_review, build_paper_evidence_snapshot, list_paper_evidence_history, record_paper_evidence_snapshot
from app.services.paper_replay import evaluate_historical_paper_replay
from app.services.paper_trading import create_paper_trade, list_paper_trades, paper_performance_metrics, reconcile_open_paper_trades, update_paper_trade_status
from app.services.paper_replay_validation import create_paper_replay_validation
from app.services.paper_validation import create_paper_trade_validation
from app.services.recovery import get_kill_switch, set_kill_switch
from app.services.readiness import build_readiness_report
from app.services.rule_evidence import build_rule_activation_evidence
from app.services.rule_lifecycle import set_rule_activation
from app.services.rules import evaluate_rule, evaluate_setup
from app.services.scenarios import get_scenario, list_scenarios
from app.services.schema_migrations import ensure_additive_schema
from app.services.seed import seed_defaults
from app.services.source_archive import archive_source_document
from app.services.source_media_enrichment import enrich_sources_media
from app.services.suggestions import promote_rule_suggestion, rule_suggestions
from app.services.telegram_ingestion import ingest_telegram_export
from app.services.telegram_live_ingestion import ingest_live_telegram
from app.services.telegram_bot_ingestion import ingest_bot_telegram
from app.services.telegram_public_ingestion import ingest_configured_public_telegram, ingest_public_telegram
from app.services.trade_export_validation import create_trade_export_validation
from app.services.validation_evidence import create_candle_replay_validation
from app.services.x_ingestion import ingest_configured_x_usernames, ingest_x_export, x_status
from app.ingestion.blog import fetch_blog_page
from app.ingestion.telegram_listener import telegram_status

Base.metadata.create_all(bind=engine)
ensure_additive_schema(engine)
app = FastAPI(title="Veda Trading AI", version="0.2.0")


@app.get("/")
def api_home(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "service": "Veda Trading AI API",
        "version": "0.2.0",
        "kill_switch": get_kill_switch(db),
        "health": "/health",
        "docs": "/docs",
        "dashboard": "http://20.235.64.162/",
    }


@app.on_event("startup")
def startup():
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        seed_defaults(db)
        audit(db, "system.startup", "API started and v0.2 defaults seeded")
    finally:
        db.close()


@app.get("/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "version": "0.2.0", "kill_switch": get_kill_switch(db)}


@app.get("/readiness")
def readiness(db: Session = Depends(get_db)):
    return build_readiness_report(db)


@app.get("/principles")
def list_principles(db: Session = Depends(get_db)):
    return db.query(AuthorPrinciple).order_by(AuthorPrinciple.code).all()


@app.post("/principles")
def create_principle(payload: PrincipleCreate, db: Session = Depends(get_db)):
    if db.query(AuthorPrinciple).filter_by(code=payload.code).first():
        raise HTTPException(status_code=409, detail="Principle code already exists")
    row = AuthorPrinciple(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    audit(db, "principle.create", f"Created principle {row.code}", entity_type="principle", entity_id=str(row.id))
    return row


@app.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    return db.query(RuleMapping).order_by(RuleMapping.rule_code).all()


@app.get("/instruments")
def list_instruments():
    return list(PROFILES.values())


@app.get("/instruments/{symbol}")
def get_instrument(symbol: str):
    return get_instrument_profile(symbol)


@app.post("/rules")
def create_rule(payload: RuleMappingCreate, db: Session = Depends(get_db)):
    if db.query(RuleMapping).filter_by(rule_code=payload.rule_code).first():
        raise HTTPException(status_code=409, detail="Rule code already exists")
    row = RuleMapping(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    audit(db, "rule.create", f"Created rule {row.rule_code}", entity_type="rule", entity_id=str(row.id))
    return row


@app.patch("/rules/{rule_code}/activation")
def update_rule_activation(rule_code: str, payload: RuleActivationRequest, db: Session = Depends(get_db)):
    result = set_rule_activation(db, rule_code=rule_code, active=payload.active, validation_note=payload.validation_note)
    if not result:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = result["rule"]
    audit(db, "rule.activation", f"Rule {rule_code} active={payload.active}", severity="WARN" if result["blocked"] else "INFO", entity_type="rule", entity_id=str(rule["id"]), payload={"active": payload.active, "validation_note": payload.validation_note, "blocked": result["blocked"], "evidence": result["evidence"]})
    if result["blocked"]:
        raise HTTPException(status_code=409, detail=result)
    return result


@app.get("/rules/{rule_code}/evidence")
def get_rule_evidence(rule_code: str, db: Session = Depends(get_db)):
    evidence = build_rule_activation_evidence(db, rule_code)
    if not evidence:
        raise HTTPException(status_code=404, detail="Rule not found")
    return evidence


@app.post("/rules/evaluate")
def evaluate_rules(payload: RuleEvaluationRequest, db: Session = Depends(get_db)):
    market_context = apply_instrument_profile(payload.market_context)
    rows = db.query(RuleMapping).filter_by(active=True).order_by(RuleMapping.rule_code).all()
    results = []
    for row in rows:
        evaluation = evaluate_rule(row.logic_json, market_context)
        results.append({
            "rule_code": row.rule_code,
            "rule_name": row.rule_name,
            "principle_id": row.principle_id,
            "matched": evaluation["matched"],
            "passed": evaluation["passed"],
            "failed": evaluation["failed"],
            "expected_behavior": row.expected_behavior,
        })
    return {"market_context": market_context, "results": results}


@app.post("/strategy/evaluate-setup")
def evaluate_strategy_setup(payload: SetupEvaluationRequest, db: Session = Depends(get_db)):
    market_context = apply_instrument_profile(payload.market_context)
    rows = db.query(RuleMapping).filter_by(active=True).order_by(RuleMapping.rule_code).all()
    rule_results = []
    for row in rows:
        evaluation = evaluate_rule(row.logic_json, market_context)
        rule_results.append({
            "rule_code": row.rule_code,
            "rule_name": row.rule_name,
            "principle_id": row.principle_id,
            "matched": evaluation["matched"],
            "passed": evaluation["passed"],
            "failed": evaluation["failed"],
            "expected_behavior": row.expected_behavior,
        })
    setup = evaluate_setup(market_context, rule_results)
    audit(db, "strategy.evaluate_setup", f"Evaluated setup stance: {setup['stance']}", payload=setup)
    return {"setup": setup, "rules": rule_results}


def _evaluate_market_context(market_context: dict, db: Session) -> dict:
    enriched_context = apply_instrument_profile(market_context)
    rows = db.query(RuleMapping).filter_by(active=True).order_by(RuleMapping.rule_code).all()
    rule_results = []
    for row in rows:
        evaluation = evaluate_rule(row.logic_json, enriched_context)
        rule_results.append({
            "rule_code": row.rule_code,
            "rule_name": row.rule_name,
            "principle_id": row.principle_id,
            "matched": evaluation["matched"],
            "passed": evaluation["passed"],
            "failed": evaluation["failed"],
            "expected_behavior": row.expected_behavior,
        })
    return {"setup": evaluate_setup(enriched_context, rule_results), "rules": rule_results}


@app.get("/strategy/scenarios")
def strategy_scenarios():
    return list_scenarios()


@app.post("/strategy/scenarios/{scenario_id}/evaluate")
def evaluate_strategy_scenario(scenario_id: str, db: Session = Depends(get_db)):
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    result = _evaluate_market_context(scenario["market_context"], db)
    passed = result["setup"]["stance"] == scenario["expected_stance"]
    audit(db, "strategy.evaluate_scenario", f"Evaluated scenario {scenario_id}: {'pass' if passed else 'fail'}", payload={"scenario_id": scenario_id, "passed": passed, "expected_stance": scenario["expected_stance"], "actual_stance": result["setup"]["stance"]})
    return {"scenario": scenario, "passed": passed, **result}


@app.get("/market/candles")
def list_market_candles(symbol: str = "NIFTY", timeframe: str = "5m", limit: int = 50, db: Session = Depends(get_db)):
    return latest_candles(db, symbol=symbol, timeframe=timeframe, limit=limit)


@app.post("/market/candles")
def create_market_candle(payload: MarketCandleCreate, db: Session = Depends(get_db)):
    row = upsert_candle(db, payload)
    audit(db, "market.candle_upsert", f"Upserted {row.symbol} {row.timeframe} candle", entity_type="market_candle", entity_id=str(row.id), payload={"symbol": row.symbol, "timeframe": row.timeframe, "ts": row.ts.isoformat(), "source": row.source})
    return row


@app.post("/market/candles/bulk")
def create_market_candles_bulk(payload: MarketCandleBulkCreate, db: Session = Depends(get_db)):
    try:
        result = upsert_candles(db, payload.candles)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    audit(db, "market.candle_bulk_upsert", "Bulk upserted market candles", payload=result)
    return result


@app.post("/market/snapshot")
def create_market_snapshot(payload: MarketSnapshotRequest, db: Session = Depends(get_db)):
    snapshot = market_snapshot(db, symbol=payload.symbol, timeframe=payload.timeframe, limit=payload.limit)
    audit(db, "market.snapshot", f"Created {snapshot['symbol']} market snapshot", payload={"symbol": snapshot["symbol"], "timeframe": snapshot["timeframe"], "candles": snapshot["candles"], "ready": snapshot["ready"]})
    return snapshot


@app.get("/ml/snapshot")
def create_ml_snapshot(symbol: str = "NIFTY", timeframe: str = "5m", limit: int = 250, db: Session = Depends(get_db)):
    snapshot = market_snapshot(db, symbol=symbol, timeframe=timeframe, limit=limit)
    result = ml_snapshot(
        db,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        market_context=snapshot.get("market_context") or {},
    )
    audit(db, "ml.snapshot", f"Created ML analysis snapshot for {symbol}", payload=result)
    return result


@app.get("/market/provider/status")
def get_market_provider_status():
    return market_provider_status()


@app.get("/market/angelone/status")
def get_angelone_market_status():
    return angelone_status()


@app.get("/market/dhan/status")
def get_dhan_market_status():
    return dhan_status()


@app.post("/market/provider/ingest")
def ingest_market_provider(payload: MarketProviderIngestRequest, db: Session = Depends(get_db)):
    result = ingest_market_source(db, payload.model_dump())
    audit(db, "market.provider_ingest", f"Ingested market provider source for {payload.symbol}", payload=result)
    return result


@app.post("/market/provider/ingest-configured")
def ingest_configured_market_provider(db: Session = Depends(get_db)):
    result = ingest_configured_market_sources(db)
    audit(db, "market.provider_ingest_configured", "Ingested configured market provider sources", payload=result)
    return result


@app.get("/paper/trades")
def paper_trades(limit: int = 100, db: Session = Depends(get_db)):
    return list_paper_trades(db, limit=limit)


@app.get("/paper/performance")
def paper_performance(symbols: str | None = None, limit: int = 500, db: Session = Depends(get_db)):
    parsed_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    return paper_performance_metrics(db, symbols=parsed_symbols, limit=limit)


@app.get("/paper/evidence-state")
def paper_evidence_state(symbols: str | None = None, db: Session = Depends(get_db)):
    parsed_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    return build_paper_evidence_snapshot(db, symbols=parsed_symbols)


@app.get("/paper/evidence-history")
def paper_evidence_history(symbols: str | None = None, limit: int = 25, db: Session = Depends(get_db)):
    parsed_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    return list_paper_evidence_history(db, symbols=parsed_symbols, limit=limit)


@app.get("/paper/evidence-review")
def paper_evidence_review(symbols: str | None = None, db: Session = Depends(get_db)):
    parsed_symbols = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    return build_paper_evidence_review(db, symbols=parsed_symbols)


@app.post("/paper/trades")
def create_trade(payload: PaperTradeRequest, db: Session = Depends(get_db)):
    result = create_paper_trade(db, payload)
    audit(db, "paper.trade_create", "Evaluated paper trade request", payload={"created": result["created"], "blocked": result["blocked"], "symbol": result["market_context"]["symbol"], "stance": result["setup"]["stance"], "side": result["side"]})
    record_paper_evidence_snapshot(db, trigger="trade_create", symbols=[result["market_context"]["symbol"]])
    return result


@app.patch("/paper/trades/{trade_id}")
def update_trade(trade_id: int, payload: PaperTradeStatusUpdate, db: Session = Depends(get_db)):
    row = update_paper_trade_status(db, trade_id=trade_id, payload=payload)
    if not row:
        raise HTTPException(status_code=404, detail="Paper trade not found")
    audit(db, "paper.trade_update", f"Paper trade {trade_id} -> {row.status}", entity_type="paper_trade", entity_id=str(row.id), payload={"exit_price": row.exit_price, "realized_pnl": row.realized_pnl, "r_multiple": row.r_multiple})
    record_paper_evidence_snapshot(db, trigger="trade_update", symbols=[row.symbol])
    return row


@app.post("/paper/trades/reconcile")
def reconcile_trades(payload: PaperTradeReconcileRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or PaperTradeReconcileRequest()
    result = reconcile_open_paper_trades(
        db,
        symbols=payload.symbols,
        timeframe=payload.timeframe,
        limit=payload.limit,
    )
    audit(db, "paper.trade_reconcile", "Reconciled open paper trades against stored candles", payload=result)
    record_paper_evidence_snapshot(db, trigger="trade_reconcile", symbols=payload.symbols)
    return result


@app.get("/paper/scheduler")
def paper_scheduler_status():
    return paper_scheduler_config()


@app.post("/paper/scheduler/run")
def run_paper_scheduler(payload: PaperSchedulerRunRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or PaperSchedulerRunRequest()
    return run_scheduled_paper_trading(
        db,
        symbols=payload.symbols,
        timeframe=payload.timeframe,
        limit=payload.limit,
        quantity=payload.quantity,
    )


@app.post("/backtests/evaluate")
def evaluate_backtest_request(payload: BacktestRequest, db: Session = Depends(get_db)):
    result = evaluate_backtest(db, payload)
    audit(db, "backtest.evaluate", f"Evaluated backtest {result['name']}", payload={"symbol": result["symbol"], "timeframe": result["timeframe"], "steps": result["steps"], "counts": result["counts"]})
    return result


@app.post("/backtests/candles")
def evaluate_candle_backtest_request(payload: CandleBacktestRequest, db: Session = Depends(get_db)):
    result = evaluate_candle_backtest(db, payload)
    audit(db, "backtest.candle_replay", f"Evaluated candle replay {result['name']}", payload={"symbol": result["symbol"], "timeframe": result["timeframe"], "steps": result["steps"], "ready": result["ready"], "counts": result["counts"]})
    return result


@app.post("/backtests/paper-replay")
def evaluate_paper_replay_request(payload: PaperReplayBacktestRequest, db: Session = Depends(get_db)):
    result = evaluate_historical_paper_replay(db, payload)
    audit(
        db,
        "backtest.paper_replay",
        f"Evaluated historical paper replay {result['name']}",
        payload={
            "symbol": result["symbol"],
            "timeframe": result["timeframe"],
            "ready": result["ready"],
            "source_candles": result["source_candles"],
            "metrics": result.get("metrics", {}),
        },
    )
    return result


@app.get("/sources")
def list_sources(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(SourceDocument).order_by(SourceDocument.ingested_at.desc()).limit(limit).all()


@app.post("/sources")
def create_source(payload: SourceDocumentCreate, db: Session = Depends(get_db)):
    row, was_created, psychology = archive_source_document(db, payload.model_dump())
    if was_created:
        audit(db, "source.ingested", f"Ingested source {row.source_type}: {row.title}", entity_type="source_document", entity_id=str(row.id), payload={"psychology_preview": psychology})
    return row


@app.post("/ingest/blog/page")
def ingest_blog_page(url: str, db: Session = Depends(get_db)):
    data = fetch_blog_page(url)
    payload = SourceDocumentCreate(**data)
    return create_source(payload, db)


@app.post("/ingest/blog/rss")
def ingest_blog_rss(feed_url: str, limit: int = 20, db: Session = Depends(get_db)):
    result = ingest_blog_feed(db, feed_url, limit=limit)
    audit(db, "blog.rss_ingested", f"Ingested RSS feed {feed_url}", payload=result)
    return result


@app.post("/ingest/blog/configured")
def ingest_configured_blogs(db: Session = Depends(get_db)):
    return ingest_configured_blog_feeds(db)


@app.post("/ingest/blog/backfill")
def ingest_blog_backfill(payload: BlogBackfillRequest, db: Session = Depends(get_db)):
    if payload.wordpress_site:
        return backfill_wordpress_site(
            db,
            site=payload.wordpress_site,
            max_pages=payload.max_pages,
            per_page=payload.page_size,
        )
    if payload.feed_url:
        return backfill_feed_pages(
            db,
            feed_url=payload.feed_url,
            max_pages=payload.max_pages,
            page_size=payload.page_size,
        )
    raise HTTPException(status_code=400, detail="Provide wordpress_site or feed_url")


@app.get("/ingest/telegram/status")
def ingest_telegram_status():
    return telegram_status()


@app.post("/ingest/telegram/export")
def ingest_telegram_export_request(payload: TelegramExportIngestRequest, db: Session = Depends(get_db)):
    return ingest_telegram_export(db, payload)


@app.post("/ingest/telegram/live")
async def ingest_telegram_live_request(payload: TelegramLiveIngestRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or TelegramLiveIngestRequest()
    try:
        return await ingest_live_telegram(db, limit=payload.limit, channels=payload.channels)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ingest/telegram/public")
def ingest_telegram_public_request(payload: TelegramPublicIngestRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or TelegramPublicIngestRequest()
    try:
        return ingest_public_telegram(db, limit=payload.limit, channels=payload.channels)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ingest/telegram/public-configured")
def ingest_telegram_public_configured_request(db: Session = Depends(get_db)):
    try:
        return ingest_configured_public_telegram(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ingest/telegram/bot")
def ingest_telegram_bot_request(payload: TelegramBotIngestRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or TelegramBotIngestRequest()
    try:
        return ingest_bot_telegram(db, limit=payload.limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/ingest/x/status")
def ingest_x_status():
    return x_status()


@app.post("/ingest/x/configured")
def ingest_x_configured(payload: XIngestRequest | None = None, db: Session = Depends(get_db)):
    payload = payload or XIngestRequest()
    return ingest_configured_x_usernames(db, usernames=payload.usernames, limit=payload.limit)


@app.post("/ingest/x/export")
def ingest_x_export_request(payload: XExportIngestRequest, db: Session = Depends(get_db)):
    return ingest_x_export(db, payload)


@app.get("/insights")
def list_insights(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(ExtractedInsight).order_by(ExtractedInsight.created_at.desc()).limit(limit).all()


@app.get("/extraction/status")
def get_extraction_status():
    return extraction_status()


@app.post("/extraction/process-pending")
def extraction_process_pending(limit: int = 50, db: Session = Depends(get_db)):
    result = process_pending_sources(db, limit=limit)
    audit(db, "extraction.process_pending", "Processed pending source documents", payload={"processed": result["processed"], "seen": result["seen"]})
    return result


@app.post("/extraction/media/enrich")
def extraction_enrich_media(source_type: str | None = None, limit: int = 100, only_missing: bool = True, db: Session = Depends(get_db)):
    result = enrich_sources_media(db, source_type=source_type, limit=limit, only_missing=only_missing)
    audit(db, "extraction.media_enrich", "Enriched source chart/media URLs", payload=result)
    return result


@app.post("/extraction/sources/{source_id}")
def extraction_process_source(source_id: int, db: Session = Depends(get_db)):
    result = process_source(db, source_id)
    if not result:
        raise HTTPException(status_code=404, detail="Source not found")
    audit(db, "extraction.process_source", f"Processed source {source_id}", entity_type="source_document", entity_id=str(source_id), payload={"insight_id": result["insight_id"]})
    return result


@app.get("/suggestions/rules")
def suggestions_rules(limit: int = 200, db: Session = Depends(get_db)):
    suggestions = rule_suggestions(db, limit=limit)
    return {"count": len(suggestions), "items": suggestions}


@app.post("/suggestions/rules/{rule_code}/promote")
def suggestions_promote_rule(rule_code: str, payload: RuleSuggestionPromotionRequest, db: Session = Depends(get_db)):
    result = promote_rule_suggestion(db, rule_code=rule_code, review_note=payload.review_note)
    if not result:
        raise HTTPException(status_code=404, detail="Rule suggestion not found")
    rule = result["rule"]
    audit(db, "suggestion.rule_promote", f"Promoted suggestion {rule_code} to {rule['rule_code']}", entity_type="rule", entity_id=str(rule["id"]), payload={"promoted": result["promoted"], "principle_id": result["principle"]["id"], "active": rule["active"]})
    return result


@app.get("/validation")
def list_validation(db: Session = Depends(get_db)):
    return db.query(ValidationCase).order_by(ValidationCase.created_at.desc()).all()


@app.post("/validation")
def create_validation_case(payload: ValidationCaseCreate, db: Session = Depends(get_db)):
    if db.query(ValidationCase).filter_by(case_code=payload.case_code).first():
        raise HTTPException(status_code=409, detail="Validation case already exists")
    row = ValidationCase(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    audit(db, "validation.create", f"Created validation case {row.case_code}", entity_type="validation_case", entity_id=str(row.id))
    return row


@app.post("/validation/from-candle-replay")
def create_validation_from_candle_replay(payload: CandleReplayValidationRequest, db: Session = Depends(get_db)):
    result = create_candle_replay_validation(db, payload)
    audit(db, "validation.candle_replay", f"Created candle replay validation {result['case_code']}", entity_type="validation_case", entity_id=str(result["validation_case_id"]), payload=result)
    return result


@app.post("/validation/from-paper-replay")
def create_validation_from_paper_replay(payload: PaperReplayValidationRequest, db: Session = Depends(get_db)):
    result = create_paper_replay_validation(db, payload)
    audit(db, "validation.paper_replay", f"Created paper replay validation {result['case_code']}", entity_type="validation_case", entity_id=str(result["validation_case_id"]), payload=result)
    return result


@app.post("/validation/from-paper-trades")
def create_validation_from_paper_trades(payload: PaperTradeValidationRequest, db: Session = Depends(get_db)):
    result = create_paper_trade_validation(db, payload)
    audit(db, "validation.paper_trades", f"Created paper trade validation {result['case_code']}", entity_type="validation_case", entity_id=str(result["validation_case_id"]), payload=result)
    return result


@app.post("/validation/from-trade-export")
def create_validation_from_trade_export(payload: TradeExportValidationRequest, db: Session = Depends(get_db)):
    try:
        result = create_trade_export_validation(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(db, "validation.trade_export", f"Created trade export validation {result['case_code']}", entity_type="validation_case", entity_id=str(result["validation_case_id"]), payload=result)
    return result


@app.patch("/validation/{case_id}")
def update_validation_case(case_id: int, payload: ValidationResultUpdate, db: Session = Depends(get_db)):
    row = db.get(ValidationCase, case_id)
    if not row:
        raise HTTPException(status_code=404, detail="Validation case not found")
    row.delivered_json = payload.delivered_json
    row.status = payload.status
    row.score = payload.score
    row.notes = payload.notes
    row.evaluated_at = datetime.utcnow()
    db.commit(); db.refresh(row)
    audit(db, "validation.update", f"Updated validation case {row.case_code} -> {row.status}", entity_type="validation_case", entity_id=str(row.id), payload={"score": row.score})
    return row


@app.get("/audit")
def list_audit(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


@app.post("/audit")
def create_audit(payload: AuditEvent, db: Session = Depends(get_db)):
    return audit(db, **payload.model_dump())


@app.get("/system/state")
def system_state(db: Session = Depends(get_db)):
    rows = db.query(SystemState).all()
    return {row.key: row.value for row in rows}


@app.post("/system/kill-switch")
def update_kill_switch(enabled: bool, reason: str = "manual", db: Session = Depends(get_db)):
    row = set_kill_switch(db, enabled=enabled, reason=reason)
    audit(db, "risk.kill_switch", f"Kill switch set to {enabled}: {reason}", severity="WARN")
    return row
