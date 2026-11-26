"""Fixed-contract scenario/capital comparisons with uncertainty and bounded work."""

from dataclasses import replace
import math
import statistics

from .actuarial import quote, resolved_policy
from .config import Config, _integer
from .errors import ModelError, SimulationLimitError
from .scenarios import Scenario
from .simulation import simulate

MAX_EXPERIMENT_POLICY_MONTHS = 50_000_000
MAX_TOTAL_PATHS = 5000


def wilson_interval(events: int, trials: int) -> list[float]:
    z = 1.959963984540054
    phat = events / trials
    denominator = 1 + z * z / trials
    center = (phat + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(phat * (1-phat) / trials + z*z/(4*trials*trials)) / denominator
    return [max(0.0, center-half), min(1.0, center+half)]


def percentile(values: list[int], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered)-1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high]-ordered[low]) * (position-low)


def run_experiment(config: Config, scenarios: list[Scenario], capitals_paise: list[int],
                   paths: int = 100) -> dict:
    config.validate()
    _integer(paths, "paths", 1, 1000)
    if not scenarios or not capitals_paise or len(scenarios)*len(capitals_paise) > 40:
        raise ModelError("Provide scenarios and capitals, with at most 40 comparison cells.")
    if paths * len(scenarios) * len(capitals_paise) > MAX_TOTAL_PATHS:
        raise ModelError(f"A comparison supports at most {MAX_TOTAL_PATHS} total paths.")
    if len({s.name for s in scenarios}) != len(scenarios):
        raise ModelError("Scenario names must be unique within a comparison.")
    if len(set(capitals_paise)) != len(capitals_paise):
        raise ModelError("Capital levels must be distinct.")
    for capital in capitals_paise:
        _integer(capital, "starting capital in paise", 0, 10**18)
    for scenario in scenarios:
        scenario.validate(config.simulation.acquisition_months + config.policy.term_months)
    if config.simulation.seed + paths-1 > 2**63-1:
        raise ModelError("The requested seed sequence exceeds its supported range.")
    pricing = quote(config.policy)
    frozen = resolved_policy(config.policy, pricing)
    remaining_work = MAX_EXPERIMENT_POLICY_MONTHS
    cells = []
    for scenario in scenarios:
        for capital in capitals_paise:
            case = replace(config, policy=frozen,
                           simulation=replace(config.simulation, starting_capital_paise=capital))
            summaries = []
            for j in range(paths):
                try:
                    result = simulate(case, config.simulation.seed+j, scenario, remaining_work)
                except SimulationLimitError as exc:
                    raise SimulationLimitError(
                        f"{scenario.name}, capital {capital} paise, path {j}: comparison incomplete; "
                        f"no failed or incomplete paths discarded. {exc}") from exc
                summaries.append(result.summary)
                remaining_work -= result.summary["policy_months_simulated"]
            shortfalls = sum(x["payment_shortfall_ever"] for x in summaries)
            breaches = sum(x["capital_breach_ever"] for x in summaries)
            surpluses = [x["economic_surplus_paise"] for x in summaries]
            metrics = [{"seed": x["seed"], "surplus_paise": x["economic_surplus_paise"],
                        "payment_shortfall": x["payment_shortfall_ever"],
                        "capital_breach": x["capital_breach_ever"],
                        "max_unpaid_obligations_paise": x["max_unpaid_obligations_paise"],
                        "minimum_capital_margin_paise": x["minimum_capital_margin_paise"]}
                       for x in summaries]
            cells.append({
                "scenario": scenario.name, "starting_capital_paise": capital, "paths": paths,
                "payment_shortfall_paths": shortfalls,
                "payment_shortfall_fraction": shortfalls/paths,
                "payment_shortfall_wilson_95": wilson_interval(shortfalls, paths),
                "zero_shortfalls_one_sided_95_upper": -math.expm1(math.log(.05)/paths) if shortfalls == 0 else None,
                "capital_breach_paths": breaches, "capital_breach_fraction": breaches/paths,
                "capital_breach_wilson_95": wilson_interval(breaches, paths),
                "mean_surplus_paise": statistics.fmean(surpluses),
                "median_surplus_paise": statistics.median(surpluses),
                "surplus_p05_paise": percentile(surpluses, .05),
                "worst_surplus_paise": min(surpluses),
                "mean_max_unpaid_paise": statistics.fmean(x["max_unpaid_obligations_paise"] for x in summaries),
                "worst_max_unpaid_paise": max(x["max_unpaid_obligations_paise"] for x in summaries),
                "mean_minimum_capital_margin_paise": statistics.fmean(x["minimum_capital_margin_paise"] for x in summaries),
                "worst_minimum_capital_margin_paise": min(x["minimum_capital_margin_paise"] for x in summaries),
                "mean_premiums_paise": statistics.fmean(x["total_premiums_paise"] for x in summaries),
                "mean_claims_paise": statistics.fmean(x["total_claims_paise"] for x in summaries),
                "mean_policies_issued": statistics.fmean(x["policies_issued"] for x in summaries),
                "per_policy_expected_margin_paise": pricing.expected_margin_paise,
                "path_metrics": metrics,
            })
    return {
        "schema_version": 2, "status": "completed", "experiment": "fixed_contract_scenario_capital_grid",
        "synthetic_assumptions": True, "config": config.as_dict(),
        "scenario_definitions": [s.as_dict() for s in scenarios],
        "fixed_sum_assured_paise": frozen.sum_assured_paise,
        "fixed_premium_paise": frozen.premium_paise,
        "seed_start": config.simulation.seed, "paths_per_scenario": paths,
        "reserve_basis": "fixed_original_pricing_assumptions", "cells": cells,
        "notes": [
            "Issued premium and benefit remain fixed. No stress scenario reprices existing promises.",
            "Reserve valuations use the original pricing basis, not realized future shocks or returns.",
            "Each cell uses the same seed sequence with separate acquisition, mortality, lapse and return streams.",
            "Within-path outcomes can diverge after changes in exposure; matching seeds do not identify individual customers.",
            "Intervals condition on the specified synthetic model. Small experiments do not certify rare-event risk.",
            "Capital levels are tested grid points; the output does not claim a global optimum or regulatory adequacy.",
            "Economic surplus includes earnings on starting capital and is not an annualized return.",
        ],
    }


def compare_lapse(config: Config, paths: int = 100) -> dict:
    data = run_experiment(config, [Scenario(name="no_lapse", lapse_monthly=0),
                                 Scenario(name="configured_lapse"),
                                 Scenario(name="synthetic_2_percent_lapse", lapse_monthly=.02)],
                          [config.simulation.starting_capital_paise], paths)
    data["experiment"] = "fixed_contract_lapse_comparison"
    data["scenarios"] = data.pop("cells")
    return data
