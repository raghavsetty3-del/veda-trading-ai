from datetime import datetime

from sqlalchemy.orm import Session

from app.models import PaperTrade, RuleMapping, ValidationCase


def _case_code(symbol: str | None, timeframe: str | None, rule_code: str | None) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    parts = ["PAPER-TRADES"]
    if symbol:
        parts.append(symbol.upper())
    if timeframe:
        parts.append(timeframe.lower())
    if rule_code:
        parts.append(rule_code.upper())
    parts.append(stamp)
    return "-".join("".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in part) for part in parts)


def _query_trades(db: Session, payload) -> list[PaperTrade]:
    safe_limit = max(1, min(payload.limit, 500))
    query = db.query(PaperTrade)
    if payload.symbol:
        query = query.filter(PaperTrade.symbol == payload.symbol.upper())
    if payload.timeframe:
        query = query.filter(PaperTrade.timeframe == payload.timeframe.lower())
    if payload.status:
        query = query.filter(PaperTrade.status == payload.status)
    return query.order_by(PaperTrade.created_at.desc()).limit(safe_limit).all()


def _rule_match(row: PaperTrade, rule_code: str | None) -> tuple[bool, bool]:
    if not rule_code:
        return False, False
    context = row.context or {}
    setup = context.get("setup") or {}
    matched_rules = setup.get("matched_rules") or []
    failed_rules = setup.get("failed_rules") or []
    return rule_code in matched_rules, rule_code in failed_rules


def _trade_summary(rows: list[PaperTrade], rule_code: str | None) -> dict:
    statuses: dict[str, int] = {}
    stances: dict[str, int] = {}
    sides: dict[str, int] = {}
    observations = []
    rule_matches = 0
    rule_failures = 0

    for row in rows:
        statuses[row.status] = statuses.get(row.status, 0) + 1
        stances[row.stance] = stances.get(row.stance, 0) + 1
        sides[row.side] = sides.get(row.side, 0) + 1
        matched, failed = _rule_match(row, rule_code)
        if matched:
            rule_matches += 1
        if failed:
            rule_failures += 1
        observations.append({
            "id": row.id,
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "side": row.side,
            "stance": row.stance,
            "status": row.status,
            "entry_price": row.entry_price,
            "created_at": row.created_at.isoformat(),
            "matched_rule": matched if rule_code else None,
            "failed_rule": failed if rule_code else None,
        })

    return {
        "total_trades": len(rows),
        "statuses": statuses,
        "stances": stances,
        "sides": sides,
        "rule_code": rule_code,
        "rule_matches": rule_matches if rule_code else None,
        "rule_failures": rule_failures if rule_code else None,
        "observations": observations[:100],
    }


def create_paper_trade_validation(db: Session, payload) -> dict:
    rule = None
    if payload.rule_code:
        rule = db.query(RuleMapping).filter_by(rule_code=payload.rule_code).first()

    rows = _query_trades(db, payload)
    summary = _trade_summary(rows, payload.rule_code)
    expected_min_trades = max(1, payload.expected_min_trades)
    enough_trades = summary["total_trades"] >= expected_min_trades
    enough_rule_matches = True
    if payload.rule_code:
        enough_rule_matches = (summary["rule_matches"] or 0) >= expected_min_trades

    status = "pass" if enough_trades and enough_rule_matches and (not payload.rule_code or rule) else "fail"
    score_base = summary["rule_matches"] if payload.rule_code else summary["total_trades"]
    score = round(min(1.0, (score_base or 0) / expected_min_trades), 3)

    delivered_json = {
        "filters": {
            "symbol": payload.symbol.upper() if payload.symbol else None,
            "timeframe": payload.timeframe.lower() if payload.timeframe else None,
            "status": payload.status,
            "limit": max(1, min(payload.limit, 500)),
        },
        "summary": summary,
    }

    row = ValidationCase(
        case_code=_case_code(payload.symbol, payload.timeframe, payload.rule_code),
        title="Paper trade validation evidence",
        principle_id=rule.principle_id if rule else None,
        rule_id=rule.id if rule else None,
        expected_json={
            "type": "paper_trade_review",
            "rule_code": payload.rule_code,
            "expected_min_trades": expected_min_trades,
        },
        delivered_json=delivered_json,
        status=status,
        score=score,
        notes=payload.notes,
        evaluated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "validation_case_id": row.id,
        "case_code": row.case_code,
        "status": row.status,
        "score": row.score,
        "rule_found": rule is not None if payload.rule_code else None,
        "delivered_json": delivered_json,
    }
