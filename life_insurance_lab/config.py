"""Validated, reproducible assumptions. Example inputs are synthetic."""

from dataclasses import asdict, dataclass
from decimal import Decimal
import math
from pathlib import Path
from typing import Any

from .errors import ModelError
from .money import to_paise


def _number(value: Any, name: str, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ModelError(f"{name} must be a number.")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ModelError(f"{name} is outside the supported numeric range.") from exc
    if not math.isfinite(result) or result < minimum or (
        maximum is not None and result > maximum
    ):
        raise ModelError(f"{name} is outside its allowed range.")
    return result


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ModelError(f"{name} must be an integer in [{minimum}, {maximum}].")
    return value


def _probabilities(value: Any, name: str, term: int) -> tuple[float, ...]:
    values = value if isinstance(value, list) else [value] * term
    if len(values) != term:
        raise ModelError(f"{name} must be a scalar or a list of {term} probabilities.")
    return tuple(_number(x, name, 0, 1) for x in values)


def _section(raw: dict, name: str, allowed: set[str]) -> dict:
    value = raw.get(name, {})
    if not isinstance(value, dict):
        raise ModelError(f"{name} must be a JSON object.")
    extra = set(value) - allowed
    if extra:
        raise ModelError(f"Unknown {name} fields: {', '.join(sorted(extra))}")
    return value


@dataclass(frozen=True)
class Policy:
    name: str
    term_months: int
    premium_paise: int
    monthly_expense_paise: int
    acquisition_expense_paise: int
    mortality: tuple[float, ...]
    lapse: tuple[float, ...]
    valuation_rate_monthly: float
    target_margin_paise: int
    sum_assured_paise: int | None
    pricing_mode: str = "auto"

    def validate(self) -> None:
        _integer(self.term_months, "term_months", 1, 1200)
        for name in (
            "premium_paise", "monthly_expense_paise",
            "acquisition_expense_paise", "target_margin_paise"
        ):
            _integer(getattr(self, name), name, 0, 10**18)
        if self.pricing_mode not in {"auto", "premium_to_benefit", "benefit_to_premium", "assess"}:
            raise ModelError("Unknown pricing_mode.")
        if self.premium_paise == 0 and self.pricing_mode != "benefit_to_premium":
            raise ModelError("A positive monthly premium is required in this product.")
        if self.pricing_mode in {"benefit_to_premium", "assess"} and self.sum_assured_paise is None:
            raise ModelError("This pricing mode requires sum_assured.")
        if self.pricing_mode == "premium_to_benefit" and self.sum_assured_paise is not None:
            raise ModelError("premium_to_benefit requires sum_assured to be null.")
        if self.sum_assured_paise is not None:
            _integer(self.sum_assured_paise, "sum_assured_paise", 1, 10**18)
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 200:
            raise ModelError("policy.name must contain 1–200 characters.")
        for name in ("mortality", "lapse"):
            schedule = getattr(self, name)
            if len(schedule) != self.term_months:
                raise ModelError(f"{name} must have term_months entries.")
            for probability in schedule:
                _number(probability, name, 0, 1)
        rate = _number(self.valuation_rate_monthly, "valuation_rate_monthly", -1)
        if rate <= -1:
            raise ModelError("valuation_rate_monthly must be greater than -1.")


@dataclass(frozen=True)
class Simulation:
    initial_policies: int
    acquisition_months: int
    yule_rate_monthly: float
    starting_capital_paise: int
    asset_rate_monthly: float
    capital_buffer_paise: int
    max_policies: int
    seed: int

    def validate(self) -> None:
        _integer(self.max_policies, "max_policies", 1, 100_000)
        _integer(self.initial_policies, "initial_policies", 0, self.max_policies)
        _integer(self.acquisition_months, "acquisition_months", 0, 1200)
        _integer(self.seed, "seed", 0, 2**63 - 1)
        _number(self.yule_rate_monthly, "yule_rate_monthly", 0)
        rate = _number(self.asset_rate_monthly, "asset_rate_monthly", -1)
        if rate <= -1:
            raise ModelError("asset_rate_monthly must be greater than -1.")
        for name in ("starting_capital_paise", "capital_buffer_paise"):
            _integer(getattr(self, name), name, 0, 10**18)


@dataclass(frozen=True)
class Config:
    policy: Policy
    simulation: Simulation

    def validate(self) -> None:
        self.policy.validate()
        self.simulation.validate()

    def as_dict(self) -> dict:
        """Normalized fields explicitly carry paise and monthly rate units."""
        return asdict(self)

    def to_input_dict(self) -> dict:
        """Complete replayable input, with exact rupee strings and all defaults resolved."""
        def rupees(paise):
            return f"{paise // 100}.{paise % 100:02d}"
        p, s = self.policy, self.simulation
        return {"policy": {
            "name": p.name, "pricing_mode": p.pricing_mode, "term_months": p.term_months,
            "monthly_premium": None if p.pricing_mode == "benefit_to_premium" else rupees(p.premium_paise),
            "sum_assured": None if p.sum_assured_paise is None else rupees(p.sum_assured_paise),
            "monthly_expense": rupees(p.monthly_expense_paise),
            "acquisition_expense": rupees(p.acquisition_expense_paise),
            "target_epv_margin": rupees(p.target_margin_paise),
            "mortality_monthly": list(p.mortality), "lapse_monthly": list(p.lapse),
            "valuation_interest_monthly": p.valuation_rate_monthly,
        }, "simulation": {
            "initial_policies": s.initial_policies, "acquisition_months": s.acquisition_months,
            "yule_rate_monthly": s.yule_rate_monthly, "starting_capital": rupees(s.starting_capital_paise),
            "capital_buffer": rupees(s.capital_buffer_paise), "asset_interest_monthly": s.asset_rate_monthly,
            "max_policies": s.max_policies, "seed": s.seed,
        }}


def from_dict(raw: dict) -> Config:
    if not isinstance(raw, dict) or set(raw) - {"policy", "simulation"}:
        raise ModelError("Config must contain only policy and simulation sections.")
    p = _section(raw, "policy", {
        "name", "term_months", "monthly_premium", "monthly_expense",
        "acquisition_expense", "mortality_monthly", "lapse_monthly",
        "valuation_interest_monthly", "target_epv_margin", "sum_assured", "pricing_mode"
    })
    s = _section(raw, "simulation", {
        "initial_policies", "acquisition_months", "yule_rate_monthly",
        "starting_capital", "asset_interest_monthly", "capital_buffer",
        "max_policies", "seed"
    })
    term = _integer(p.get("term_months", 36), "term_months", 1, 1200)
    mode = p.get("pricing_mode", "auto")
    if not isinstance(mode, str):
        raise ModelError("pricing_mode must be a string.")
    if mode == "benefit_to_premium" and p.get("monthly_premium") is not None:
        raise ModelError("Omit monthly_premium or set it to null in benefit_to_premium mode.")
    policy = Policy(
        name=p.get("name", "Synthetic term-life example"),
        term_months=term,
        premium_paise=0 if mode == "benefit_to_premium" else to_paise(p.get("monthly_premium", 1000), "monthly_premium"),
        monthly_expense_paise=to_paise(p.get("monthly_expense", 80), "monthly_expense"),
        acquisition_expense_paise=to_paise(p.get("acquisition_expense", 500), "acquisition_expense"),
        mortality=_probabilities(p.get("mortality_monthly", .001), "mortality_monthly", term),
        lapse=_probabilities(p.get("lapse_monthly", .005), "lapse_monthly", term),
        valuation_rate_monthly=_number(p.get("valuation_interest_monthly", .003), "valuation_interest_monthly", -1),
        target_margin_paise=to_paise(p.get("target_epv_margin", 500), "target_epv_margin"),
        sum_assured_paise=None if p.get("sum_assured") is None else to_paise(p["sum_assured"], "sum_assured"),
        pricing_mode=mode,
    )
    simulation = Simulation(
        initial_policies=s.get("initial_policies", 100),
        acquisition_months=s.get("acquisition_months", 12),
        yule_rate_monthly=_number(s.get("yule_rate_monthly", .03), "yule_rate_monthly", 0),
        starting_capital_paise=to_paise(s.get("starting_capital", 5_000_000), "starting_capital"),
        asset_rate_monthly=_number(s.get("asset_interest_monthly", .003), "asset_interest_monthly", -1),
        capital_buffer_paise=to_paise(s.get("capital_buffer", 500_000), "capital_buffer"),
        max_policies=s.get("max_policies", 10_000),
        seed=s.get("seed", 2026),
    )
    config = Config(policy, simulation)
    config.validate()
    return config


def load_config(path: str | Path) -> Config:
    from .jsonio import load
    return from_dict(load(path))
