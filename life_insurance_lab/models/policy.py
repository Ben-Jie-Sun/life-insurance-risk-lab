"""Active/lapsed/death model; lapse is conditional on surviving the month."""

import math
import random

from ..errors import ModelError


def transition_matrix(q: float, lapse: float) -> tuple[tuple[float, ...], ...]:
    if not all(math.isfinite(p) and 0 <= p <= 1 for p in (q, lapse)):
        raise ModelError("Mortality and lapse probabilities must lie in [0,1].")
    return (
        ((1 - q) * (1 - lapse), (1 - q) * lapse, q),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )


def binomial(n: int, probability: float, rng: random.Random) -> int:
    """Transparent O(n) exact Bernoulli sum, portable to Python 3.10+."""
    if probability == 0:
        return 0
    if probability == 1:
        return n
    return sum(rng.random() < probability for _ in range(n))


def advance(
    active: int, q: float, lapse: float,
    mortality_rng: random.Random, lapse_rng: random.Random
) -> tuple[int, int, int]:
    """Return (remaining active, deaths, lapses), never double-counting an exit."""
    if type(active) is not int or active < 0:
        raise ModelError("Active count must be a non-negative integer.")
    transition_matrix(q, lapse)
    deaths = binomial(active, q, mortality_rng)
    survivors = active - deaths
    lapses = binomial(survivors, lapse, lapse_rng)
    return survivors - lapses, deaths, lapses
