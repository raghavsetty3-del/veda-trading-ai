from sqlalchemy.orm import Session

from app.models import PaperTrade, RuleMapping, ValidationCase
from app.services.instrument_profiles import apply_instrument_profile
from app.services.rules import evaluate_rule
from app.services.scenarios import list_scenarios


def _condition_fields(logic_json: dict) -> list[str]:
    fields: set[str] = set()
    for condition in logic_json.get("conditions", []):
        field = condition.get("field")
        if field:
            fields.add(field)

        value = condition.get("value")
        if isinstance(value, str) and value.startswith("$") and len(value) > 1:
            fields.add(value[1:])

    return sorted(fields)


def build_rule_activation_evidence(db: Session, rule_code: str) -> dict | None:
    row = db.query(RuleMapping).filter_by(rule_code=rule_code).first()
    if not row:
        return None

    condition_fields = _condition_fields(row.logic_json)
    scenario_results = []
    scenario_count = 0
    fully_covered_count = 0
    matched_count = 0

    for scenario in list_scenarios():
        scenario_count += 1
        market_context = apply_instrument_profile(dict(scenario["market_context"]))
        missing_fields = sorted(field for field in condition_fields if field not in market_context)
        evaluation = evaluate_rule(row.logic_json, market_context)
        if not missing_fields:
            fully_covered_count += 1
        if evaluation["matched"]:
            matched_count += 1

        scenario_results.append({
            "scenario_id": scenario["id"],
            "title": scenario["title"],
            "symbol": market_context.get("symbol"),
            "expected_stance": scenario["expected_stance"],
            "matched": evaluation["matched"],
            "passed_conditions": evaluation["passed"],
            "failed_conditions": evaluation["failed"],
            "missing_fields": missing_fields,
        })

    validation_cases = db.query(ValidationCase).filter(ValidationCase.rule_id == row.id).count()
    passing_validation_cases = (
        db.query(ValidationCase)
        .filter(ValidationCase.rule_id == row.id, ValidationCase.status == "pass")
        .count()
    )
    paper_trade_observations = db.query(PaperTrade).count()

    blockers = []
    if not condition_fields:
        blockers.append("Rule has no machine-readable conditions.")
    if scenario_count == 0:
        blockers.append("No strategy scenarios are available for activation evidence.")
    if fully_covered_count < scenario_count:
        blockers.append("One or more scenarios do not contain all fields required by this rule.")
    if matched_count == 0:
        blockers.append("Rule did not match any validation scenario.")

    eligible_for_activation = not blockers

    return {
        "rule_code": row.rule_code,
        "rule_name": row.rule_name,
        "status": row.status,
        "active": row.active,
        "condition_fields": condition_fields,
        "scenario_count": scenario_count,
        "fully_covered_scenarios": fully_covered_count,
        "matched_scenarios": matched_count,
        "validation_cases": validation_cases,
        "passing_validation_cases": passing_validation_cases,
        "paper_trade_observations": paper_trade_observations,
        "eligible_for_activation": eligible_for_activation,
        "blockers": blockers,
        "scenarios": scenario_results,
    }
