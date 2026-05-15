import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import RuleMapping, ValidationCase


DATA_ROOT = Path("/app/data")


def _safe_path(source_path: str) -> Path:
    candidate = Path(source_path)
    if not candidate.is_absolute():
        candidate = DATA_ROOT / candidate
    resolved = candidate.resolve()
    data_root = DATA_ROOT.resolve()
    if data_root not in resolved.parents and resolved != data_root:
        raise ValueError("Trade export source_path must be inside /app/data.")
    if not resolved.exists():
        raise ValueError(f"Trade export not found: {resolved}")
    return resolved


def _float(value) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text:
        return 0.0
    return float(text)


def _case_code(symbol: str, strategy_name: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    scope = f"{symbol}-{strategy_name}-{stamp}".upper()
    safe_scope = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in scope)
    return f"TRADE-EXPORT-{safe_scope}"


def _trade_number(row: dict) -> str:
    for key in ("Trade #", "Trade", "trade_id", "id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _price(row: dict) -> float:
    for key in ("Price INR", "Price", "price"):
        if key in row:
            return _float(row.get(key))
    return 0.0


def _net_pnl(row: dict) -> float:
    for key in ("Net P&L INR", "Net P&L", "net_pnl", "pnl"):
        if key in row:
            return _float(row.get(key))
    return 0.0


def _cum_pnl(row: dict) -> float:
    for key in ("Cumulative P&L INR", "Cumulative P&L", "cumulative_pnl"):
        if key in row:
            return _float(row.get(key))
    return 0.0


def _parse_export(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Trade export has no CSV header.")
        rows = [row for row in reader if any((value or "").strip() for value in row.values())]
    if not rows:
        raise ValueError("Trade export has no rows.")
    return rows


def _summarize_trades(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for index, row in enumerate(rows, start=1):
        trade_id = _trade_number(row) or str(index)
        grouped[trade_id].append(row)

    trades = []
    cumulative = []
    for trade_id, trade_rows in grouped.items():
        entry = next((row for row in trade_rows if str(row.get("Type", "")).lower().startswith("entry")), None)
        exit_row = next((row for row in trade_rows if str(row.get("Type", "")).lower().startswith("exit")), None)
        metric_row = exit_row or trade_rows[0]
        net_pnl = _net_pnl(metric_row)
        cumulative_pnl = _cum_pnl(metric_row)
        cumulative.append(cumulative_pnl)
        trades.append({
            "trade_id": trade_id,
            "side": (entry or metric_row).get("Type"),
            "entry_time": (entry or {}).get("Date and time"),
            "exit_time": (exit_row or {}).get("Date and time"),
            "entry_price": _price(entry or {}),
            "exit_price": _price(exit_row or {}),
            "net_pnl": net_pnl,
            "cumulative_pnl": cumulative_pnl,
        })

    wins = [trade for trade in trades if trade["net_pnl"] > 0]
    losses = [trade for trade in trades if trade["net_pnl"] < 0]
    breakeven = [trade for trade in trades if trade["net_pnl"] == 0]
    gross_profit = sum(trade["net_pnl"] for trade in wins)
    gross_loss = abs(sum(trade["net_pnl"] for trade in losses))
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else None

    peak = 0.0
    max_drawdown = 0.0
    for value in cumulative:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, peak - value)

    total_trades = len(trades)
    net_pnl = sum(trade["net_pnl"] for trade in trades)
    return {
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "win_rate": round(len(wins) / total_trades, 4) if total_trades else 0.0,
        "net_pnl": round(net_pnl, 2),
        "average_trade_pnl": round(net_pnl / total_trades, 2) if total_trades else 0.0,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": profit_factor,
        "max_drawdown": round(max_drawdown, 2),
        "sample_trades": trades[:25],
    }


def _score(summary: dict, expected_min_trades: int, expected_min_net_pnl: float, expected_min_win_rate: float) -> float:
    min_trades_score = min(1.0, summary["total_trades"] / max(1, expected_min_trades))
    if expected_min_net_pnl > 0:
        pnl_score = min(1.0, max(0.0, summary["net_pnl"] / expected_min_net_pnl))
    else:
        pnl_score = 1.0 if summary["net_pnl"] >= expected_min_net_pnl else 0.0
    if expected_min_win_rate > 0:
        win_rate_score = min(1.0, max(0.0, summary["win_rate"] / expected_min_win_rate))
    else:
        win_rate_score = 1.0
    return round((min_trades_score + pnl_score + win_rate_score) / 3, 3)


def create_trade_export_validation(db: Session, payload) -> dict:
    source_path = _safe_path(payload.source_path)
    rows = _parse_export(source_path)
    summary = _summarize_trades(rows)
    expected_min_trades = max(1, payload.expected_min_trades)
    expected_min_win_rate = max(0.0, payload.expected_min_win_rate)

    rule = None
    if payload.rule_code:
        rule = db.query(RuleMapping).filter_by(rule_code=payload.rule_code).first()

    passed = (
        summary["total_trades"] >= expected_min_trades
        and summary["net_pnl"] >= payload.expected_min_net_pnl
        and summary["win_rate"] >= expected_min_win_rate
        and (not payload.rule_code or rule)
    )

    delivered_json = {
        "source_path": str(source_path),
        "symbol": payload.symbol.upper(),
        "timeframe": payload.timeframe,
        "strategy_name": payload.strategy_name,
        "summary": summary,
    }

    row = ValidationCase(
        case_code=_case_code(payload.symbol, payload.strategy_name),
        title=f"Trade export validation: {payload.symbol.upper()} {payload.strategy_name}",
        principle_id=rule.principle_id if rule else None,
        rule_id=rule.id if rule else None,
        expected_json={
            "type": "trade_export_performance",
            "symbol": payload.symbol.upper(),
            "timeframe": payload.timeframe,
            "strategy_name": payload.strategy_name,
            "rule_code": payload.rule_code,
            "expected_min_trades": expected_min_trades,
            "expected_min_net_pnl": payload.expected_min_net_pnl,
            "expected_min_win_rate": expected_min_win_rate,
        },
        delivered_json=delivered_json,
        status="pass" if passed else "fail",
        score=_score(summary, expected_min_trades, payload.expected_min_net_pnl, expected_min_win_rate),
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
