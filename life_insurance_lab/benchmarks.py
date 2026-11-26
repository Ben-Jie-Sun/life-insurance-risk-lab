"""Independent analytical expectations versus repeated model paths."""

from dataclasses import dataclass, replace
import math

from .actuarial import quote, resolved_policy
from .config import Config, _integer
from .errors import ModelError, SimulationLimitError
from .experiments import MAX_EXPERIMENT_POLICY_MONTHS
from .models.yule import issue_schedule, moments
from .simulation import random_stream, simulate


@dataclass
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float):
        self.count += 1
        delta = value-self.mean
        self.mean += delta/self.count
        self.m2 += delta*(value-self.mean)

    def result(self, expected: float) -> dict:
        se = math.sqrt(max(0.0, self.m2)/(self.count-1)/self.count) if self.count > 1 else 0.0
        return {"expected": expected, "sample_mean": self.mean,
                "error": self.mean-expected, "standard_error": se,
                "sample_mean_normal_95": [self.mean-1.96*se, self.mean+1.96*se]}


def benchmark(config: Config, paths: int = 200) -> dict:
    config.validate()
    _integer(paths, "paths", 2, 1000)
    s = config.simulation
    if s.seed+paths-1 > 2**63-1:
        raise ModelError("Seed sequence exceeds the supported range.")
    pricing = quote(config.policy)
    p = resolved_policy(config.policy, pricing)
    fixed = replace(config, policy=p, simulation=replace(s, acquisition_months=0, yule_rate_monthly=0))
    yule_stats = [RunningStats() for _ in range(s.acquisition_months+1)]
    active_stats = [RunningStats() for _ in range(p.term_months)]
    premium_stats = [RunningStats() for _ in range(p.term_months)]
    claim_stats = [RunningStats() for _ in range(p.term_months)]
    margin_stats = RunningStats()
    remaining = MAX_EXPERIMENT_POLICY_MONTHS
    v = 1/(1+p.valuation_rate_monthly)
    for j in range(paths):
        seed = s.seed+j
        schedule = issue_schedule(s.initial_policies, s.yule_rate_monthly, s.acquisition_months,
                                  random_stream(seed, "acquisition"), s.max_policies)
        remaining -= sum(schedule)
        if remaining <= 0:
            raise SimulationLimitError("Benchmark work budget exhausted; incomplete.")
        population = 0
        for k, births in enumerate(schedule):
            population += births
            yule_stats[k].add(population)
        result = simulate(fixed, seed, work_limit=remaining)
        remaining -= result.summary["policy_months_simulated"]
        margin = 0.0
        for k, row in enumerate(result.monthly):
            active_stats[k].add(row["active_open"])
            premium_stats[k].add(row["premiums_paise"])
            claim_stats[k].add(row["claims_incurred_paise"])
            margin += ((row["premiums_paise"]-row["expenses_incurred_paise"])*v**k
                       -row["claims_incurred_paise"]*v**(k+1))
        margin_stats.add(margin)
    yule_rows = []
    for t, stats in enumerate(yule_stats):
        mean, variance = moments(s.initial_policies, s.yule_rate_monthly, t)
        yule_rows.append({"month": t, **stats.result(mean), "theoretical_variance": variance,
                          "theoretical_mean_standard_error": math.sqrt(variance/paths)})
    active_probability = 1.0
    cohort_rows = []
    for k in range(p.term_months):
        expected_active = s.initial_policies*active_probability
        cohort_rows.append({"month": k, "active_probability": active_probability,
                            "active": active_stats[k].result(expected_active),
                            "premiums_paise": premium_stats[k].result(expected_active*p.premium_paise),
                            "claims_incurred_paise": claim_stats[k].result(expected_active*p.mortality[k]*p.sum_assured_paise)})
        active_probability *= (1-p.mortality[k])*(1-p.lapse[k])
    return {"schema_version": 2, "status": "completed", "experiment": "analytical_benchmark",
            "config": config.as_dict(), "paths": paths, "seed_start": s.seed,
            "yule": yule_rows, "fixed_cohort": cohort_rows,
            "cohort_margin_epv_paise": margin_stats.result(s.initial_policies*pricing.expected_margin_paise),
            "notes": ["The Yule experiment uses the configured acquisition process.",
                      "The policy experiment uses only the initial cohort with no later admissions and baseline experience.",
                      "Incurred claims are compared; paid claims can be constrained by available cash.",
                      "Intervals are approximate pointwise normal intervals for sample means, not simultaneous bands.",
                      "No observed rare claims can give an uninformative zero empirical standard error; this is not proof of zero risk.",
                      "A random deviation is not automatically a correctness failure; inspect sampling uncertainty."]}
