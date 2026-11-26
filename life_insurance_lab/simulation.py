"""Monthly cohorts and a cash ledger. No real payments or investments."""

from dataclasses import dataclass, field
import hashlib
import math
import random

from .actuarial import quote, reserve_schedule, resolved_policy
from .config import Config
from .errors import ModelError, SimulationLimitError
from .models.policy import advance
from .models.yule import issue_schedule, moments
from .money import interest_paise
from .scenarios import Scenario, draw_return, stressed_mortality

MAX_POLICY_MONTHS = 5_000_000  # explicit computational guard per path


def random_stream(seed: int, purpose: str) -> random.Random:
    key = f"{seed}:{purpose}".encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(key).digest()[:16], "big"))


@dataclass
class Cohort:
    issue_month: int
    active: int


@dataclass
class Result:
    config: dict
    pricing: dict
    summary: dict
    monthly: list[dict]
    contract: dict = field(default_factory=dict)
    scenario: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "schema_version": 2, "config": self.config, "pricing": self.pricing,
            "summary": self.summary, "monthly": self.monthly,
            "contract": self.contract, "scenario": self.scenario,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**{key: value[key] for key in
                      ("config", "pricing", "summary", "monthly", "contract", "scenario")})


def simulate(config: Config, seed: int | None = None, scenario: Scenario | None = None,
             work_limit: int = MAX_POLICY_MONTHS) -> Result:
    config.validate()
    pricing = quote(config.policy)
    p, s = resolved_policy(config.policy, pricing), config.simulation
    actual_seed = s.seed if seed is None else seed
    if type(actual_seed) is not int or not 0 <= actual_seed <= 2**63 - 1:
        raise ModelError("Simulation seed must be an integer in [0, 2**63-1].")
    benefit = pricing.selected_benefit_paise
    reserves = reserve_schedule(p, benefit)
    horizon = s.acquisition_months + p.term_months
    scenario = scenario or Scenario()
    scenario.validate(horizon)
    schedule = issue_schedule(
        s.initial_policies, s.yule_rate_monthly, s.acquisition_months,
        random_stream(actual_seed, "acquisition"), s.max_policies
    )
    if sum(schedule) * p.term_months > min(MAX_POLICY_MONTHS, work_limit):
        raise SimulationLimitError(
            f"Projection exceeds the remaining policy-month budget ({min(MAX_POLICY_MONTHS, work_limit):,}). Run incomplete."
        )
    death_rng = random_stream(actual_seed, "mortality")
    lapse_rng = random_stream(actual_seed, "lapse")
    return_rng = random_stream(actual_seed, "returns")
    cohorts: list[Cohort] = []
    cash = s.starting_capital_paise
    unpaid_claims = unpaid_expenses = 0
    totals = dict(premiums=0, expenses=0, expenses_paid=0,
                  interest=0, claims=0, claims_paid=0)
    issued_total = deaths_total = lapses_total = expired_total = 0
    candidate_total = 0
    policy_months = maximum_unpaid = 0
    first_shortfall = None
    first_capital_breach = -1 if cash < s.capital_buffer_paise else None
    minimum_net_assets = cash
    minimum_capital_margin = cash - s.capital_buffer_paise
    rows = []

    for month in range(horizon):
        conditions = scenario.at(month, s.asset_rate_monthly)
        candidates = schedule[month] if month < len(schedule) else 0
        candidate_total += candidates
        # A pedagogical stop-sale rule; existing contracts still run off.
        issued = candidates if first_shortfall is None else 0
        if issued:
            cohorts.append(Cohort(month, issued))
            issued_total += issued
        opening_active = sum(c.active for c in cohorts)
        policy_months += opening_active
        opening_cash = cash
        opening_unpaid_claims, opening_unpaid_expenses = unpaid_claims, unpaid_expenses
        premiums = opening_active * p.premium_paise
        expenses = (
            opening_active * p.monthly_expense_paise
            + issued * p.acquisition_expense_paise
        )
        cash += premiums

        # Expenses at start of month, including arrears from earlier months.
        expense_due = unpaid_expenses + expenses
        expenses_paid = min(cash, expense_due)
        cash -= expenses_paid
        unpaid_expenses = expense_due - expenses_paid
        shortfall = unpaid_expenses > 0
        if cash > 10**18:
            raise SimulationLimitError("Cash exceeds the supported numeric range.")
        asset_rate = draw_return(conditions["asset_return_monthly"],
                                 conditions["return_volatility_monthly"], return_rng)
        interest = interest_paise(cash, asset_rate)
        cash += interest
        if cash > 10**18:
            raise SimulationLimitError("Cash exceeds the supported numeric range after interest.")

        deaths = lapses = expired = 0
        mortality_values, lapse_values = [], []
        for cohort in cohorts:
            age = month - cohort.issue_month
            q = stressed_mortality(p.mortality[age], conditions["mortality_multiplier"])
            # At the final covered month, survivors expire rather than lapse.
            effective_lapse = p.lapse[age] if conditions["lapse_monthly"] is None else conditions["lapse_monthly"]
            lapse_probability = effective_lapse if age + 1 < p.term_months else 0.0
            mortality_values.append(q)
            lapse_values.append(lapse_probability)
            remaining, d, l = advance(
                cohort.active, q, lapse_probability, death_rng, lapse_rng
            )
            deaths += d
            lapses += l
            if age + 1 == p.term_months:
                expired += remaining
                remaining = 0
            cohort.active = remaining
        cohorts = [c for c in cohorts if c.active]
        deaths_total += deaths
        lapses_total += lapses
        expired_total += expired

        claims = deaths * benefit
        claims_due = unpaid_claims + claims
        claims_paid = min(cash, claims_due)
        cash -= claims_paid
        unpaid_claims = claims_due - claims_paid
        maximum_unpaid = max(maximum_unpaid, unpaid_claims + unpaid_expenses)
        shortfall = shortfall or unpaid_claims > 0
        if shortfall and first_shortfall is None:
            first_shortfall = month

        closing_active = sum(c.active for c in cohorts)
        # Positive policy values only; each per-policy value rounds upward.
        reserve = sum(
            c.active * math.ceil(max(0.0, reserves[month + 1 - c.issue_month]))
            for c in cohorts
        )
        net_assets = cash - unpaid_claims - unpaid_expenses
        capital_margin = net_assets - reserve - s.capital_buffer_paise
        if capital_margin < 0 and first_capital_breach is None:
            first_capital_breach = month
        minimum_net_assets = min(minimum_net_assets, net_assets)
        minimum_capital_margin = min(minimum_capital_margin, capital_margin)
        for key, amount in (
            ("premiums", premiums), ("expenses", expenses),
            ("expenses_paid", expenses_paid), ("interest", interest),
            ("claims", claims), ("claims_paid", claims_paid)
        ):
            totals[key] += amount

        # These checks are never disabled by Python's optimization flag.
        expected_cash = (
            s.starting_capital_paise + totals["premiums"] + totals["interest"]
            - totals["expenses_paid"] - totals["claims_paid"]
        )
        expected_net = (
            s.starting_capital_paise + totals["premiums"] + totals["interest"]
            - totals["expenses"] - totals["claims"]
        )
        if cash != expected_cash or net_assets != expected_net or cash < 0:
            raise ArithmeticError("Cash/obligation accounting invariant failed.")
        if issued_total != closing_active + deaths_total + lapses_total + expired_total:
            raise ArithmeticError("Policy conservation invariant failed.")
        rows.append({
            "month": month, "candidates": candidates, "issued": issued,
            "not_issued": candidates - issued, "cumulative_candidates": candidate_total,
            "cumulative_issued": issued_total, "active_open": opening_active,
            "deaths": deaths, "lapses": lapses, "expired": expired,
            "active_close": closing_active, "opening_cash_paise": opening_cash,
            "premiums_paise": premiums, "expenses_incurred_paise": expenses,
            "expenses_paid_paise": expenses_paid, "interest_paise": interest,
            "claims_incurred_paise": claims, "claims_paid_paise": claims_paid,
            "unpaid_claims_paise": unpaid_claims, "unpaid_expenses_paise": unpaid_expenses,
            "opening_unpaid_claims_paise": opening_unpaid_claims,
            "opening_unpaid_expenses_paise": opening_unpaid_expenses,
            "closing_cash_paise": cash, "net_assets_paise": net_assets,
            "reserve_requirement_paise": reserve, "capital_margin_paise": capital_margin,
            "payment_shortfall": shortfall, "capital_breach": capital_margin < 0,
            "mortality_multiplier": conditions["mortality_multiplier"],
            "mortality_probability_min": min(mortality_values, default=0.0),
            "mortality_probability_max": max(mortality_values, default=0.0),
            "lapse_probability_min": min(lapse_values, default=0.0),
            "lapse_probability_max": max(lapse_values, default=0.0),
            "asset_return_monthly": asset_rate,
            "expected_asset_return_monthly": conditions["asset_return_monthly"],
            "return_volatility_monthly": conditions["return_volatility_monthly"],
            "scenario_events": conditions["events"],
        })

    if cohorts:
        raise ArithmeticError("Projection ended before all issued policies ran off.")
    mean, variance = moments(s.initial_policies, s.yule_rate_monthly, s.acquisition_months)
    summary = {
        "status": "completed", "seed": actual_seed, "months_projected": horizon,
        "synthetic_assumptions": True,
        "sum_assured_paise": benefit, "monthly_premium_paise": p.premium_paise,
        "scenario_name": scenario.name, "reserve_basis": "fixed_original_pricing_assumptions",
        "policy_months_simulated": policy_months,
        "max_unpaid_obligations_paise": maximum_unpaid,
        "candidates_generated": sum(schedule),
        "policies_issued": issued_total, "candidates_not_issued": sum(schedule) - issued_total,
        "deaths": deaths_total, "lapses": lapses_total, "expired": expired_total,
        "active_at_end": 0, "closing_cash_paise": cash,
        "unpaid_claims_paise": unpaid_claims, "unpaid_expenses_paise": unpaid_expenses,
        "net_assets_paise": cash - unpaid_claims - unpaid_expenses,
        "economic_surplus_paise": cash - unpaid_claims - unpaid_expenses - s.starting_capital_paise,
        "minimum_net_assets_paise": minimum_net_assets,
        "minimum_capital_margin_paise": minimum_capital_margin,
        "payment_shortfall_ever": first_shortfall is not None,
        "first_shortfall_month": first_shortfall,
        "capital_breach_ever": first_capital_breach is not None,
        "first_capital_breach_month": first_capital_breach,
        "yule_expected_candidates": mean, "yule_candidate_variance": variance,
        "notes": [
            "One synthetic path; this is not a risk-probability estimate.",
            "New admissions stop after the first unpaid obligation; existing policies run off.",
            "Post-shortfall collections are diagnostic projections, not an insolvency administration model.",
            "A modeled capital breach is separate from an unpaid cash obligation.",
            "Contract premium/benefit and reserve valuation basis remain fixed across experience shocks.",
            "Random returns, if enabled, apply to one liquid aggregate fund; no portfolio allocation is modeled.",
        ],
    }
    summary.update({f"total_{key}_paise": value for key, value in totals.items()})
    normalized = config.as_dict()
    normalized["simulation"]["seed"] = actual_seed
    return Result(normalized, pricing.as_dict(), summary, rows,
                  {"name": p.name, "premium_paise": p.premium_paise,
                   "benefit_paise": benefit, "term_months": p.term_months}, scenario.as_dict())
