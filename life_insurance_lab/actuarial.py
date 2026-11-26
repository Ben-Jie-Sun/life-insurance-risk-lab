"""Expected present values and prospective reserves for a level-premium term."""

from dataclasses import asdict, dataclass, replace
import math

from .config import Policy
from .errors import ModelError


@dataclass(frozen=True)
class Quote:
    premium_factor: float
    benefit_factor: float
    expected_premiums_paise: float
    expected_expenses_paise: float
    candidate_benefit_paise: int | None
    selected_benefit_paise: int
    expected_benefits_paise: float
    expected_margin_paise: float
    target_margin_paise: int
    meets_target_margin: bool
    selection: str
    selected_premium_paise: int
    required_premium_paise: int
    mode: str

    def as_dict(self) -> dict:
        return asdict(self)


def factors(policy: Policy) -> tuple[float, float, float]:
    """Premium/benefit factors and expense EPV, before month-0 premium."""
    policy.validate()
    active, discount = 1.0, 1.0
    v = 1 / (1 + policy.valuation_rate_monthly)
    a = b = e = 0.0
    for k, (q, lapse) in enumerate(zip(policy.mortality, policy.lapse)):
        a += discount * active
        b += discount * v * active * q
        expense = policy.monthly_expense_paise
        if k == 0:
            expense += policy.acquisition_expense_paise
        e += discount * active * expense
        active *= (1 - q) * (1 - lapse)
        discount *= v
        if not all(math.isfinite(x) for x in (a, b, e, discount)):
            raise ModelError("Valuation overflow: shorten the term or change the rate.")
    return a, b, e


def quote(policy: Policy) -> Quote:
    a, b, e = factors(policy)
    mode = policy.pricing_mode
    if mode == "auto":
        mode = "assess" if policy.sum_assured_paise is not None else "premium_to_benefit"
    selected_premium = policy.premium_paise
    if mode == "benefit_to_premium":
        raw_premium = (policy.sum_assured_paise * b + e + policy.target_margin_paise) / a
        if not math.isfinite(raw_premium) or raw_premium > 10**18:
            raise ModelError("Calculated premium exceeds the supported monetary range.")
        selected_premium = max(1, math.ceil(raw_premium))
    premium_epv = selected_premium * a
    available = premium_epv - e - policy.target_margin_paise
    candidate = None
    if b > 0 and available > 0:
        raw = available / b
        if not math.isfinite(raw) or raw > 10**18:
            if mode == "premium_to_benefit":
                raise ModelError("Calculated benefit exceeds the supported monetary range.")
        else:
            candidate = math.floor(raw)
    if mode == "premium_to_benefit":
        if b <= 0:
            raise ModelError("Automatic pricing is undefined when death-benefit EPV is zero.")
        if candidate is None or candidate < 1:
            raise ModelError("Premiums do not fund a positive benefit and the selected margin.")
        selected, selection = candidate, "calculated_from_monthly_premium"
    else:
        selected, selection = policy.sum_assured_paise, "fixed_by_configuration"
    benefits = selected * b
    margin = premium_epv - e - benefits
    raw_required = (benefits + e + policy.target_margin_paise) / a
    if not all(math.isfinite(x) for x in (premium_epv, benefits, margin, raw_required)):
        raise ModelError("Pricing calculation overflowed.")
    if raw_required > 10**18:
        raise ModelError("Required premium exceeds the supported monetary range.")
    required = max(1, math.ceil(raw_required))
    return Quote(a, b, premium_epv, e, candidate, selected, benefits, margin,
                 policy.target_margin_paise, margin + 1e-6 >= policy.target_margin_paise,
                 selection, selected_premium, required, mode)


def resolved_policy(policy: Policy, pricing: Quote | None = None) -> Policy:
    """Freeze the issued premium/benefit while retaining the original valuation basis."""
    pricing = pricing or quote(policy)
    return replace(policy, premium_paise=pricing.selected_premium_paise,
                   sum_assured_paise=pricing.selected_benefit_paise, pricing_mode="assess")


def reserve_schedule(policy: Policy, benefit_paise: int) -> list[float]:
    """V[k] before month-k premium, conditional on the policy still active.

    Lapsed/death values are zero after their obligations are booked.
    V[M]=0; the acquisition expense occurs only at age 0.
    """
    policy.validate()
    if type(benefit_paise) is not int or benefit_paise <= 0:
        raise ModelError("Benefit must be positive integer paise.")
    values = [0.0] * (policy.term_months + 1)
    v = 1 / (1 + policy.valuation_rate_monthly)
    for k in range(policy.term_months - 1, -1, -1):
        q, lapse = policy.mortality[k], policy.lapse[k]
        expense = policy.monthly_expense_paise
        if k == 0:
            expense += policy.acquisition_expense_paise
        values[k] = expense - policy.premium_paise + v * (
            q * benefit_paise + (1 - q) * (1 - lapse) * values[k + 1]
        )
        if not math.isfinite(values[k]):
            raise ModelError("Reserve valuation overflowed.")
    return values
