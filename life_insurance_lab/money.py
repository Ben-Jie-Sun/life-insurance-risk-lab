"""Posted amounts are integer paise; valuation uses floating point separately."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

from .errors import ModelError, SimulationLimitError


def to_paise(value: object, name: str = "amount") -> int:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ModelError(f"{name} must be a finite non-negative amount.")
        if amount > Decimal(10**16):
            raise ModelError(f"{name} exceeds the supported monetary range.")
        paise = amount * 100
        if paise != paise.to_integral_value():
            raise ModelError(f"{name} must have at most two decimal places.")
        return int(paise)
    except (InvalidOperation, TypeError) as exc:
        raise ModelError(f"{name} must be a monetary amount.") from exc


def interest_paise(cash: int, monthly_rate: float) -> int:
    """Round the month's interest once, to nearest paisa, ties to even."""
    try:
        return int(
            (Decimal(cash) * Decimal(str(monthly_rate))).quantize(
                Decimal("1"), rounding=ROUND_HALF_EVEN
            )
        )
    except InvalidOperation as exc:
        raise SimulationLimitError("Interest exceeds the supported numeric range.") from exc


def format_inr(paise: float) -> str:
    return f"INR {paise / 100:,.2f}"
