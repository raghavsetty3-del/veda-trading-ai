from datetime import datetime
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import AuditLog, AuthorPrinciple, ExtractedInsight, MarketCandle, RuleMapping, SourceDocument, SystemState, ValidationCase
from app.schemas import AuditEvent, MarketCandleCreate, MarketSnapshotRequest, PrincipleCreate, RuleEvaluationRequest, RuleMappingCreate, SetupEvaluationRequest, SourceDocumentCreate, ValidationCaseCreate, ValidationResultUpdate
from app.services.audit import audit
from app.services.instrument_profiles import PROFILES, apply_instrument_profile, get_instrument_profile
from app.services.market_data import latest_candles, market_snapshot, upsert_candle
from app.services.psychology import extract_psychology
from app.services.recovery import get_kill_switch, set_kill_switch
from app.services.rules import evaluate_rule, evaluate_setup
from app.services.scenarios import get_scenario, list_scenarios
from app.services.seed import seed_defaults
from app.ingestion.blog import fetch_blog_page, fetch_rss_entries

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Veda Trading AI", version="0.2.0")


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


@app.post("/market/snapshot")
def create_market_snapshot(payload: MarketSnapshotRequest, db: Session = Depends(get_db)):
    snapshot = market_snapshot(db, symbol=payload.symbol, timeframe=payload.timeframe, limit=payload.limit)
    audit(db, "market.snapshot", f"Created {snapshot['symbol']} market snapshot", payload={"symbol": snapshot["symbol"], "timeframe": snapshot["timeframe"], "candles": snapshot["candles"], "ready": snapshot["ready"]})
    return snapshot


@app.get("/sources")
def list_sources(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(SourceDocument).order_by(SourceDocument.ingested_at.desc()).limit(limit).all()


@app.post("/sources")
def create_source(payload: SourceDocumentCreate, db: Session = Depends(get_db)):
    existing = None
    if payload.source_url:
        existing = db.query(SourceDocument).filter_by(source_type=payload.source_type, source_url=payload.source_url).first()
    if existing:
        return existing
    row = SourceDocument(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    psychology = extract_psychology(row.raw_text)
    db.add(ExtractedInsight(source_document_id=row.id, psychology=psychology, concepts=[], confidence=None))
    db.commit()
    audit(db, "source.ingested", f"Ingested source {row.source_type}: {row.title}", entity_type="source_document", entity_id=str(row.id), payload={"psychology_preview": psychology})
    return row


@app.post("/ingest/blog/page")
def ingest_blog_page(url: str, db: Session = Depends(get_db)):
    data = fetch_blog_page(url)
    payload = SourceDocumentCreate(**data)
    return create_source(payload, db)


@app.post("/ingest/blog/rss")
def ingest_blog_rss(feed_url: str, limit: int = 20, db: Session = Depends(get_db)):
    entries = fetch_rss_entries(feed_url)[:limit]
    created = []
    for item in entries:
        payload = SourceDocumentCreate(**{k: v for k, v in item.items() if k in SourceDocumentCreate.model_fields})
        created.append(create_source(payload, db))
    audit(db, "blog.rss_ingested", f"Ingested RSS feed {feed_url}", payload={"count": len(created)})
    return {"count": len(created), "items": created}


@app.get("/insights")
def list_insights(limit: int = 100, db: Session = Depends(get_db)):
    return db.query(ExtractedInsight).order_by(ExtractedInsight.created_at.desc()).limit(limit).all()


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
