from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import SourceDocument
from app.services.paper_scheduler import paper_scheduler_config
from app.services.paper_trading import paper_performance_metrics
from app.services.replay_reports import latest_replay_risk_report, sell_tuning_report


PROMOTION_KEYS = [
    ("exit_mode", "PAPER_EXIT_MODE"),
    ("part_book_r_multiple", "PAPER_PART_BOOK_R_MULTIPLE"),
    ("part_book_fraction", "PAPER_PART_BOOK_FRACTION"),
    ("trail_lookback_candles", "PAPER_TRAIL_LOOKBACK_CANDLES"),
    ("cooldown_candles", "PAPER_TRADE_COOLDOWN_CANDLES"),
]

MIN_REPLAY_TRADES = 500
MIN_VALIDATION_OVERALL_PF = 2.0
MIN_VALIDATION_SELL_PF = 1.8
MIN_DRAWDOWN_IMPROVEMENT_POINTS = 300.0
MIN_RELATIVE_DRAWDOWN_IMPROVEMENT = 0.20
MIN_ABSOLUTE_DRAWDOWN_IMPROVEMENT_POINTS = 10.0
MIN_FORWARD_PAPER_TRADES = 20
MIN_FORWARD_PAPER_PF = 1.3


def _candidate_config(item: dict[str, Any]) -> dict[str, Any]:
    config = dict(item.get("config") or {})
    config.setdefault("exit_mode", "author_part_book_trail")
    return config


def _values_match(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left == right
    try:
        return abs(float(left) - float(right)) < 0.000001
    except (TypeError, ValueError):
        return str(left) == str(right)


def _config_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(_values_match(left.get(key), right.get(key)) for key, _ in PROMOTION_KEYS)


def _float_value(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gate(gate: str, ready: bool, detail: str, required: bool = True, value: Any = None) -> dict[str, Any]:
    item = {
        "gate": gate,
        "required": required,
        "ready": bool(ready),
        "detail": detail,
    }
    if value is not None:
        item["value"] = value
    return item


def _env_values(config: dict[str, Any]) -> dict[str, Any]:
    return {
        env_key: config.get(config_key)
        for config_key, env_key in PROMOTION_KEYS
        if config.get(config_key) is not None
    }


def _find_symbol(report: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    symbols = report.get("symbols") or []
    target = symbol.strip().upper()
    return next((item for item in symbols if item.get("symbol") == target), None)


def _side_metrics(symbol_report: dict[str, Any] | None, side: str) -> dict[str, Any]:
    for item in (symbol_report or {}).get("by_side", []) or []:
        if item.get("side") == side:
            return item
    return {}


def _paper_item(performance: dict[str, Any], symbol: str) -> dict[str, Any]:
    target = symbol.strip().upper()
    for item in performance.get("items") or []:
        if item.get("symbol") == target:
            return item
    return {
        "symbol": target,
        "total_trades": 0,
        "realized_closed_trades": 0,
        "remaining_review_trades": MIN_FORWARD_PAPER_TRADES,
        "gross_loss": 0,
        "net_realized_pnl": 0,
        "profit_factor": None,
        "profit_factor_label": "N/A",
    }


def _author_source_count(db: Session) -> int:
    return (
        db.query(SourceDocument)
        .filter(SourceDocument.source_type.in_(["blog", "x", "telegram", "telegram_public", "telegram_bot"]))
        .filter(SourceDocument.author.ilike("%Ilango%") | SourceDocument.title.ilike("%JustNifty%"))
        .count()
    )


def build_symbol_promotion_readiness(
    db: Session,
    symbol: str = "BANKNIFTY",
    tuning_name: str | None = None,
    replay_name: str | None = None,
) -> dict[str, Any]:
    target = symbol.strip().upper()
    tuning_payload = sell_tuning_report(symbol=target, name=tuning_name)
    tuning_report = tuning_payload.get("report") or {}
    top_candidate = (tuning_report.get("top_candidates") or [{}])[0]
    candidate_config = _candidate_config(top_candidate)

    replay_payload = latest_replay_risk_report(name=replay_name, symbol=target)
    replay_report = replay_payload.get("report") or {}
    replay_config = replay_report.get("config") or {}
    symbol_replay = _find_symbol(replay_report, target)
    validation_metrics = (symbol_replay or {}).get("metrics") or {}
    validation_sell = _side_metrics(symbol_replay, "sell")
    scheduler = paper_scheduler_config()
    effective_scheduler = (scheduler.get("effective_exit_by_symbol") or {}).get(target) or scheduler
    performance = paper_performance_metrics(db, symbols=[target], limit=500)
    paper = _paper_item(performance, target)
    author_sources = _author_source_count(db)

    baseline_sell = tuning_report.get("baseline_sell") or {}
    candidate_sell = top_candidate.get("sell") or {}
    baseline_drawdown = _float_value(baseline_sell.get("max_drawdown_points"))
    validation_drawdown = _float_value(validation_metrics.get("max_drawdown_points"))
    validation_sell_drawdown = _float_value(validation_sell.get("max_drawdown_points"))
    drawdown_to_compare = validation_sell_drawdown if validation_sell_drawdown is not None else validation_drawdown
    tuning_drawdown_improvement = _float_value(top_candidate.get("drawdown_improvement_points"))
    if tuning_drawdown_improvement is None and baseline_drawdown is not None:
        candidate_drawdown = _float_value(candidate_sell.get("max_drawdown_points"))
        if candidate_drawdown is not None:
            tuning_drawdown_improvement = baseline_drawdown - candidate_drawdown
    validation_drawdown_delta = None
    if baseline_drawdown is not None and drawdown_to_compare is not None:
        validation_drawdown_delta = round(baseline_drawdown - drawdown_to_compare, 2)
    drawdown_improvement = round(tuning_drawdown_improvement, 2) if tuning_drawdown_improvement is not None else validation_drawdown_delta
    drawdown_improvement_required = MIN_DRAWDOWN_IMPROVEMENT_POINTS
    if baseline_drawdown is not None:
        drawdown_improvement_required = min(
            MIN_DRAWDOWN_IMPROVEMENT_POINTS,
            max(
                MIN_ABSOLUTE_DRAWDOWN_IMPROVEMENT_POINTS,
                baseline_drawdown * MIN_RELATIVE_DRAWDOWN_IMPROVEMENT,
            ),
        )
        drawdown_improvement_required = round(drawdown_improvement_required, 2)

    overall_pf = _float_value(validation_metrics.get("profit_factor"))
    sell_pf = _float_value(validation_sell.get("profit_factor"))
    paper_pf = _float_value(paper.get("profit_factor"))
    paper_closed = int(paper.get("realized_closed_trades") or 0)
    paper_net = _float_value(paper.get("net_realized_pnl")) or 0.0
    paper_gross_loss = _float_value(paper.get("gross_loss")) or 0.0

    replay_gates = [
        _gate(
            "tuning_report_available",
            tuning_payload.get("available") is True and bool(top_candidate),
            f"Latest tuning report: {tuning_payload.get('name') or 'missing'}",
        ),
        _gate(
            "replay_validation_available",
            replay_payload.get("available") is True and symbol_replay is not None,
            f"Latest replay validation: {replay_payload.get('name') or 'missing'}",
        ),
        _gate(
            "author_exit_logic_retained",
            candidate_config.get("exit_mode") == "author_part_book_trail"
            and replay_config.get("exit_mode") == "author_part_book_trail",
            "Candidate and validation both use author_part_book_trail exit logic.",
        ),
        _gate(
            "candidate_matches_validation_config",
            _config_matches(candidate_config, replay_config),
            f"Candidate config {candidate_config}; validation config {replay_config}",
        ),
        _gate(
            "validation_sample_size_ready",
            int(validation_metrics.get("trades") or 0) >= MIN_REPLAY_TRADES,
            f"{target} validation trades: {validation_metrics.get('trades', 0)} / {MIN_REPLAY_TRADES}",
            value=validation_metrics.get("trades"),
        ),
        _gate(
            "validation_profit_factor_ready",
            (overall_pf or 0) >= MIN_VALIDATION_OVERALL_PF and (sell_pf or 0) >= MIN_VALIDATION_SELL_PF,
            (
                f"Overall PF {validation_metrics.get('profit_factor_label', 'N/A')} >= {MIN_VALIDATION_OVERALL_PF}; "
                f"sell PF {validation_sell.get('profit_factor_label', 'N/A')} >= {MIN_VALIDATION_SELL_PF}."
            ),
        ),
        _gate(
            "sell_drawdown_improved",
            drawdown_improvement is not None and drawdown_improvement >= drawdown_improvement_required,
            (
                f"Tuning baseline sell DD {baseline_drawdown}; candidate tuning sell DD "
                f"{candidate_sell.get('max_drawdown_points')}; tuning improvement {drawdown_improvement} points; "
                f"validation sell DD {drawdown_to_compare}; validation delta {validation_drawdown_delta}; "
                f"required improvement {drawdown_improvement_required} points."
            ),
            value=drawdown_improvement,
        ),
        _gate(
            "author_sources_archived",
            author_sources > 0,
            f"Archived Ilango/JustNifty sources visible: {author_sources}.",
            required=False,
            value=author_sources,
        ),
    ]

    paper_gates = [
        _gate(
            "paper_scheduler_matches_candidate",
            _config_matches(candidate_config, effective_scheduler),
            f"Current paper scheduler {effective_scheduler}; candidate {candidate_config}",
        ),
        _gate(
            "forward_paper_sample_ready",
            paper_closed >= MIN_FORWARD_PAPER_TRADES,
            f"{target} closed paper trades: {paper_closed} / {MIN_FORWARD_PAPER_TRADES}",
            value=paper_closed,
        ),
        _gate(
            "forward_paper_pnl_positive",
            paper_net > 0,
            f"{target} net realized paper P&L: {paper_net}.",
            value=paper_net,
        ),
        _gate(
            "forward_paper_profit_factor_reviewable",
            paper_gross_loss > 0 and paper_pf is not None and paper_pf >= MIN_FORWARD_PAPER_PF,
            (
                f"{target} paper PF {paper.get('profit_factor_label', 'N/A')} >= {MIN_FORWARD_PAPER_PF}; "
                f"gross loss sample {paper_gross_loss}."
            ),
            value=paper.get("profit_factor"),
        ),
        _gate(
            "live_trading_still_disabled",
            not settings.enable_live_trading,
            "Live trading remains disabled; promotion is review-only until explicit manual approval.",
        ),
    ]

    replay_required = [gate for gate in replay_gates if gate["required"]]
    live_required = replay_required + [gate for gate in paper_gates if gate["required"]]
    paper_candidate_blocking = [gate["gate"] for gate in replay_required if not gate["ready"]]
    live_candidate_blocking = [gate["gate"] for gate in live_required if not gate["ready"]]

    return {
        "symbol": target,
        "ready_for_paper_candidate_review": not paper_candidate_blocking,
        "ready_for_live_candidate_review": not live_candidate_blocking,
        "paper_candidate_blocking_gates": paper_candidate_blocking,
        "live_candidate_blocking_gates": live_candidate_blocking,
        "thresholds": {
            "min_replay_trades": MIN_REPLAY_TRADES,
            "min_validation_overall_pf": MIN_VALIDATION_OVERALL_PF,
            "min_validation_sell_pf": MIN_VALIDATION_SELL_PF,
            "min_drawdown_improvement_points": MIN_DRAWDOWN_IMPROVEMENT_POINTS,
            "min_relative_drawdown_improvement": MIN_RELATIVE_DRAWDOWN_IMPROVEMENT,
            "drawdown_improvement_required_points": drawdown_improvement_required,
            "min_forward_paper_trades": MIN_FORWARD_PAPER_TRADES,
            "min_forward_paper_pf": MIN_FORWARD_PAPER_PF,
        },
        "candidate_config": candidate_config,
        "candidate_env": _env_values(candidate_config),
        "current_paper_scheduler": scheduler,
        "effective_paper_scheduler": effective_scheduler,
        "tuning_report": {
            "name": tuning_payload.get("name"),
            "available": tuning_payload.get("available"),
            "generated_at": tuning_report.get("generated_at"),
            "mode": tuning_report.get("mode"),
            "baseline_sell": baseline_sell,
            "top_candidate": top_candidate,
        },
        "replay_validation": {
            "name": replay_payload.get("name"),
            "available": replay_payload.get("available"),
            "generated_at": replay_report.get("generated_at"),
            "config": replay_config,
            "metrics": validation_metrics,
            "sell": validation_sell,
            "drawdown_improvement_points": drawdown_improvement,
        },
        "paper_performance": paper,
        "replay_gates": replay_gates,
        "paper_gates": paper_gates,
        "all_gates": replay_gates + paper_gates,
        "notes": [
            "This endpoint is review-only and never mutates .env, scheduler, paper trades, or live settings.",
            "Paper candidate review means the replay evidence is strong enough to consider a manual paper-setting promotion.",
            "Live candidate review additionally requires forward paper evidence under the candidate settings.",
        ],
    }


def build_banknifty_promotion_readiness(
    db: Session,
    tuning_name: str | None = None,
    replay_name: str | None = None,
) -> dict[str, Any]:
    return build_symbol_promotion_readiness(
        db,
        symbol="BANKNIFTY",
        tuning_name=tuning_name,
        replay_name=replay_name,
    )
