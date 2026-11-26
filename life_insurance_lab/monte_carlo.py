"""Monte Carlo summaries of the existing Yule/cohort/ledger engine.

No separate population or cash-flow simulator lives here. Every replication calls
simulate(), with a distinct seed and the same fixed input/scenario assumptions.
"""
import csv
import math
from pathlib import Path
import statistics

from .config import Config, _integer
from .errors import SimulationLimitError
from .experiments import percentile, wilson_interval
from .models.yule import moments
from .scenarios import Scenario
from .simulation import simulate
from .jsonio import dumps

MAX_ENSEMBLE_POLICY_MONTHS = 50_000_000
MAX_ENSEMBLE_OBSERVATIONS = 500_000
Z95 = 1.959963984540054


def describe(values):
    n = len(values)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    se = sd / math.sqrt(n)
    return {"mean": mean, "sample_sd": sd, "standard_error": se,
            "mean_normal_approx_95": [mean-Z95*se, mean+Z95*se],
            "p05": percentile(values, .05), "median": percentile(values, .5),
            "p95": percentile(values, .95), "min": min(values), "max": max(values)}


def risk(events, trials):
    return {"events": events, "paths": trials, "estimate": events/trials,
            "wilson_95": wilson_interval(events, trials),
            "zero_events_one_sided_95_upper": -math.expm1(math.log(.05)/trials) if events == 0 else None}


def run_monte_carlo(config: Config, paths: int = 200, scenario: Scenario | None = None) -> dict:
    config.validate()
    _integer(paths, "paths", 2, 1000)
    horizon = config.simulation.acquisition_months + config.policy.term_months
    if paths*horizon > MAX_ENSEMBLE_OBSERVATIONS:
        raise SimulationLimitError("Monte Carlo observation budget exceeded; reduce paths or horizon.")
    start = config.simulation.seed
    if start+paths-1 > 2**63-1:
        raise SimulationLimitError("Monte Carlo seed sequence exceeds its supported range.")
    scenario = scenario or Scenario()
    scenario.validate(horizon)
    remaining = MAX_ENSEMBLE_POLICY_MONTHS
    # Store just the series needed for the fan charts, not R full ledgers.
    columns = ("cumulative_candidates", "active_close", "net_assets_paise", "capital_margin_paise")
    series = {key: [[] for _ in range(horizon)] for key in columns}
    shortfall_counts = [0]*horizon
    metrics, convergence, example_paths = [], [], []
    checkpoints = {2, 10, 25, 50, 100, 200, 500, 1000, paths}
    first = None
    for index in range(paths):
        try:
            result = simulate(config, seed=start+index, scenario=scenario, work_limit=remaining)
        except SimulationLimitError as exc:
            raise SimulationLimitError(f"Monte Carlo incomplete at path {index+1}/{paths}; no paths were discarded: {exc}") from exc
        if first is None:
            first = result
        s = result.summary
        remaining -= s["policy_months_simulated"]
        metrics.append({"seed": start+index, "candidates_generated": s["candidates_generated"],
                        "policies_issued": s["policies_issued"], "deaths": s["deaths"],
                        "lapses": s["lapses"], "expired": s["expired"],
                        "economic_surplus_paise": s["economic_surplus_paise"],
                        "payment_shortfall": s["payment_shortfall_ever"],
                        "capital_breach": s["capital_breach_ever"],
                        "first_shortfall_month": s["first_shortfall_month"],
                        "max_unpaid_obligations_paise": s["max_unpaid_obligations_paise"]})
        for row in result.monthly:
            month = row["month"]
            for key in columns:
                series[key][month].append(row[key])
            shortfall_counts[month] += int(s["first_shortfall_month"] is not None and s["first_shortfall_month"] <= month)
        if index < 5:
            example_paths.append({"seed": start+index,
                                  "net_assets_paise": [r["net_assets_paise"] for r in result.monthly],
                                  "active_close": [r["active_close"] for r in result.monthly]})
        n = index+1
        if n in checkpoints:
            surplus = describe([m["economic_surplus_paise"] for m in metrics])
            convergence.append({"paths": n, "mean_surplus_paise": surplus["mean"],
                                "surplus_standard_error_paise": surplus["standard_error"],
                                "shortfall": risk(sum(m["payment_shortfall"] for m in metrics), n)})
    monthly = []
    for month in range(horizon):
        # Arrivals in [k,k+1) issue at k+1. At row k, candidate totals equal N(k)
        # until the acquisition horizon; this is deliberately not active exposure.
        exact_mean, exact_var = moments(config.simulation.initial_policies,
                                       config.simulation.yule_rate_monthly,
                                       min(month, config.simulation.acquisition_months))
        row = {"month": month, "yule_expected_candidates": exact_mean,
               "yule_candidate_variance": exact_var,
               "cumulative_shortfall_fraction": shortfall_counts[month]/paths}
        for key in columns:
            values = series[key][month]
            row[key] = {"mean": statistics.fmean(values), "p05": percentile(values, .05),
                        "median": percentile(values, .5), "p95": percentile(values, .95)}
        monthly.append(row)
    mean, variance = moments(config.simulation.initial_policies, config.simulation.yule_rate_monthly,
                             config.simulation.acquisition_months)
    candidates = describe([m["candidates_generated"] for m in metrics])
    exact_se = math.sqrt(variance/paths)
    benchmark = {"exact_mean": mean, "exact_variance": variance,
                 "simulated_mean": candidates["mean"],
                 "simulated_variance": candidates["sample_sd"]**2,
                 "exact_standard_error_of_sample_mean": exact_se,
                 "mean_error_in_exact_standard_errors": (candidates["mean"]-mean)/exact_se if exact_se else None}
    return {"schema_version": 3, "status": "completed", "experiment": "yule_monte_carlo",
            "synthetic_assumptions": True, "config": config.as_dict(),
            "replay_config": config.to_input_dict(), "scenario": scenario.as_dict(),
            "paths": paths, "seed_start": start, "seed_end": start+paths-1,
            "months_projected": horizon, "pricing": first.pricing, "contract": first.contract,
            "summary": {"payment_shortfall": risk(sum(m["payment_shortfall"] for m in metrics), paths),
                        "capital_breach": risk(sum(m["capital_breach"] for m in metrics), paths),
                        "economic_surplus_paise": describe([m["economic_surplus_paise"] for m in metrics]),
                        "candidates_generated": candidates,
                        "policies_issued": describe([m["policies_issued"] for m in metrics]),
                        "deaths": describe([m["deaths"] for m in metrics])},
            "yule_benchmark": benchmark, "monthly": monthly,
            "convergence": convergence, "path_metrics": metrics, "example_paths": example_paths,
            "policy_months_simulated": MAX_ENSEMBLE_POLICY_MONTHS-remaining,
            "notes": [
                "Yule-Furry describes cumulative potential acquisitions, not active policies.",
                "Birth times are exact for the Yule process; admission is delayed to the next monthly boundary.",
                "Each path uses the existing monthly ledger, death, lapse, expiry and stop-sale rules.",
                "A payment shortfall is an unpaid obligation; a capital breach includes the modeled reserve and buffer.",
                "5th-95th percentile bands describe outcomes, not confidence intervals for their mean.",
                "Wilson intervals measure finite-sample uncertainty conditional on the model. Zero observed failures do not prove zero risk.",
                "Mean intervals use a normal approximation; use substantially more than a few paths for interpretation.",
                "Convergence points reuse prefixes of one sample; they are correlated, not independent error experiments.",
                "Surplus subtracts starting capital but includes its investment earnings; it is not an annualized return.",
                "Guards abort incomplete experiments instead of silently discarding costly paths.",
            ]}


def monthly_csv_rows(result):
    for row in result["monthly"]:
        flat = {}
        for key, value in row.items():
            if isinstance(value, dict):
                flat.update({f"{key}_{stat}": number for stat, number in value.items()})
            else:
                flat[key] = value
        yield flat


def write_monte_carlo(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/"monte_carlo.json").write_text(dumps(result), encoding="utf-8")
    for filename, rows in (("monthly_bands.csv", list(monthly_csv_rows(result))),
                           ("path_metrics.csv", result["path_metrics"])):
        with (output/filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return output/"monte_carlo.json"
