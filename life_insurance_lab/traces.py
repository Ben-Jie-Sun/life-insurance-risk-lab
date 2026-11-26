"""Explain stored monthly arithmetic without resimulating or changing its inputs."""

from .config import _integer
from .money import interest_paise


def explain_month(result: dict, month: int) -> dict:
    rows = result["monthly"]
    _integer(month, "month", 0, len(rows)-1)
    row = rows[month]
    policy, sim = result["config"]["policy"], result["config"]["simulation"]
    contract = result["contract"]
    premium = row["active_open"]*contract["premium_paise"]
    maintenance = row["active_open"]*policy["monthly_expense_paise"]
    acquisition = row["issued"]*policy["acquisition_expense_paise"]
    expense_due = row["opening_unpaid_expenses_paise"]+maintenance+acquisition
    interest_base = row["opening_cash_paise"]+premium-row["expenses_paid_paise"]
    interest = interest_paise(interest_base, float(row["asset_return_monthly"]))
    claims = row["deaths"]*contract["benefit_paise"]
    claims_due = row["opening_unpaid_claims_paise"]+claims
    closing = interest_base+interest-row["claims_paid_paise"]
    net = closing-row["unpaid_claims_paise"]-row["unpaid_expenses_paise"]
    margin = net-row["reserve_requirement_paise"]-sim["capital_buffer_paise"]
    checks = {
        "premiums_match": premium == row["premiums_paise"],
        "expenses_match": maintenance+acquisition == row["expenses_incurred_paise"],
        "interest_matches": interest == row["interest_paise"],
        "claims_match": claims == row["claims_incurred_paise"],
        "cash_matches": closing == row["closing_cash_paise"],
        "net_assets_match": net == row["net_assets_paise"],
        "capital_margin_matches": margin == row["capital_margin_paise"],
        "claim_arrears_match": claims_due-row["claims_paid_paise"] == row["unpaid_claims_paise"],
        "expense_arrears_match": expense_due-row["expenses_paid_paise"] == row["unpaid_expenses_paise"],
        "policies_conserved": row["active_open"] == row["active_close"]+row["deaths"]+row["lapses"]+row["expired"],
    }
    return {"month": month, "units": "paise", "contract": contract,
            "scenario": result["scenario"]["name"], "row": row,
            "steps": [
                {"operation": "premiums = active_open × premium", "active_open": row["active_open"], "premium_paise": contract["premium_paise"], "result_paise": premium},
                {"operation": "expenses incurred = maintenance + acquisition", "maintenance_paise": maintenance, "acquisition_paise": acquisition, "result_paise": maintenance+acquisition},
                {"operation": "expenses paid = min(cash after premiums, old + new expenses)", "due_paise": expense_due, "result_paise": row["expenses_paid_paise"]},
                {"operation": "interest = round_to_paisa(remaining cash × realized return)", "base_paise": interest_base, "rate": row["asset_return_monthly"], "result_paise": interest},
                {"operation": "new claims = deaths × fixed benefit", "deaths": row["deaths"], "benefit_paise": contract["benefit_paise"], "result_paise": claims},
                {"operation": "claims paid = min(available cash, old + new claims)", "due_paise": claims_due, "result_paise": row["claims_paid_paise"]},
                {"operation": "closing cash = interest base + interest - claims paid", "result_paise": closing},
                {"operation": "net assets = cash - unpaid claims - unpaid expenses", "result_paise": net},
                {"operation": "capital margin = net assets - reference reserve - buffer", "result_paise": margin},
            ], "checks": checks, "all_checks_pass": all(checks.values()),
            "note": "Probability ranges in the row span active cohorts at different policy durations. Cash amounts are exact integer paise."}
