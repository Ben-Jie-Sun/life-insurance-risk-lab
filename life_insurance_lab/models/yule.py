"""Linear pure-birth process with exact exponential holding times."""

import math
import random

from ..errors import ModelError, SimulationLimitError


def moments(initial: int, rate: float, time: float) -> tuple[float, float]:
    if type(initial) is not int or initial < 0:
        raise ModelError("Yule initial population must be a non-negative integer.")
    if not all(math.isfinite(x) and x >= 0 for x in (rate, time)):
        raise ModelError("Yule rate and time must be finite and non-negative.")
    if initial == 0:
        return 0.0, 0.0
    try:
        growth = math.exp(rate * time)
        mean = initial * growth
        variance = initial * growth * math.expm1(rate * time)
    except OverflowError as exc:
        raise SimulationLimitError("Yule moments overflow; reduce the growth horizon.") from exc
    if not math.isfinite(mean) or not math.isfinite(variance):
        raise SimulationLimitError("Yule moments exceed the numeric range.")
    return mean, variance


def issue_schedule(
    initial: int, rate: float, months: int, rng: random.Random, max_population: int
) -> list[int]:
    """Seeds issue at month 0; births in [k,k+1) issue at boundary k+1.

    This cap is a computational guard, NOT a truncated Yule model.
    """
    if type(months) is not int or months < 0:
        raise ModelError("Acquisition horizon must be a non-negative integer.")
    moments(initial, rate, 0)
    if type(max_population) is not int or max_population < max(initial, 1):
        raise ModelError("max_population is below the initial population.")
    counts = [initial] + [0] * months
    if initial == 0 or rate == 0 or months == 0:
        return counts
    population, time = initial, 0.0
    while True:
        intensity = rate * population
        if not math.isfinite(intensity):
            raise SimulationLimitError("Yule intensity overflowed.")
        waiting = rng.expovariate(intensity)
        next_time = time + waiting
        if next_time >= months:
            break
        if next_time <= time:
            raise SimulationLimitError("Yule event spacing fell below numeric resolution.")
        if population == max_population:
            raise SimulationLimitError(
                f"Yule population would exceed {max_population}. Run incomplete; "
                "reduce the horizon/rate or explicitly raise max_policies."
            )
        time = next_time
        population += 1
        counts[math.floor(time) + 1] += 1
    return counts
