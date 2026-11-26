"""Calendar-time experience assumptions, separate from issued policy promises."""

from dataclasses import asdict, dataclass
import math
import random

from .config import _integer, _number
from .errors import ModelError, SimulationLimitError
from .jsonio import load

FIELDS = {"mortality_multiplier", "lapse_monthly", "asset_return_monthly",
          "return_volatility_monthly"}


def _name(value, field="name") -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ModelError(f"{field} must contain 1–200 characters.")
    return value


def _assumption(name, value):
    if value is None:
        return None
    if name == "mortality_multiplier":
        result = _number(value, name, 0, 1000)
        if result == 0:
            raise ModelError("mortality_multiplier must be positive.")
        return result
    if name == "lapse_monthly":
        return _number(value, name, 0, 1)
    if name == "return_volatility_monthly":
        return _number(value, name, 0, 2)
    result = _number(value, name, -1)
    if result <= -1:
        raise ModelError("asset_return_monthly must be greater than -1.")
    return result


@dataclass(frozen=True)
class Event:
    name: str
    start_month: int
    end_month: int  # exclusive; a window [8, 11) includes months 8, 9, 10
    mortality_multiplier: float | None = None
    lapse_monthly: float | None = None
    asset_return_monthly: float | None = None
    return_volatility_monthly: float | None = None


@dataclass(frozen=True)
class Scenario:
    name: str = "baseline"
    mortality_multiplier: float = 1.0
    lapse_monthly: float | None = None
    asset_return_monthly: float | None = None
    return_volatility_monthly: float = 0.0
    events: tuple[Event, ...] = ()

    def as_dict(self) -> dict:
        result = asdict(self)
        result["events"] = list(result["events"])
        return result

    def validate(self, horizon: int | None = None) -> None:
        _name(self.name)
        for field in FIELDS:
            _assumption(field, getattr(self, field))
        if self.mortality_multiplier is None or self.return_volatility_monthly is None:
            raise ModelError("Global multiplier and volatility cannot be null.")
        if len(self.events) > 50:
            raise ModelError("At most 50 scenario events are supported.")
        names = set()
        for j, event in enumerate(self.events):
            _name(event.name, "event.name")
            if event.name in names:
                raise ModelError("Scenario event names must be unique.")
            names.add(event.name)
            _integer(event.start_month, "start_month", 0, 2399)
            _integer(event.end_month, "end_month", 1, 2400)
            if event.end_month <= event.start_month:
                raise ModelError("Event end_month must exceed start_month.")
            if horizon is not None and event.end_month > horizon:
                raise ModelError("A scenario event extends beyond the projection horizon.")
            specified = {f for f in FIELDS if getattr(event, f) is not None}
            if not specified:
                raise ModelError("An event must change at least one assumption.")
            for field in specified:
                _assumption(field, getattr(event, field))
            for previous in self.events[:j]:
                overlap = max(event.start_month, previous.start_month) < min(event.end_month, previous.end_month)
                duplicate_fields = specified & {f for f in FIELDS if getattr(previous, f) is not None}
                if overlap and duplicate_fields:
                    raise ModelError("Overlapping events cannot override the same assumption.")

    def at(self, month: int, default_return: float) -> dict:
        result = {field: getattr(self, field) for field in FIELDS}
        if result["asset_return_monthly"] is None:
            result["asset_return_monthly"] = default_return
        names = []
        for event in self.events:
            if event.start_month <= month < event.end_month:
                names.append(event.name)
                for field in FIELDS:
                    value = getattr(event, field)
                    if value is not None:
                        result[field] = value
        result["events"] = "; ".join(names)
        return result


def from_dict(raw: dict) -> Scenario:
    if not isinstance(raw, dict) or set(raw) - (FIELDS | {"name", "events"}):
        raise ModelError("Unknown scenario fields or invalid scenario object.")
    entries = raw.get("events", [])
    if not isinstance(entries, list):
        raise ModelError("events must be an array.")
    events = []
    for j, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) - (FIELDS | {"name", "start_month", "end_month"}):
            raise ModelError("Unknown event fields or invalid event object.")
        if "start_month" not in entry or "end_month" not in entry:
            raise ModelError("Events require start_month and end_month.")
        events.append(Event(entry.get("name", f"event_{j+1}"), entry["start_month"], entry["end_month"],
                            **{f: _assumption(f, entry[f]) for f in FIELDS if f in entry}))
    scenario = Scenario(name=raw.get("name", "baseline"), events=tuple(events),
                        **{f: _assumption(f, raw[f]) for f in FIELDS if f in raw})
    scenario.validate()
    return scenario


def load_scenario(path) -> Scenario:
    return from_dict(load(path))


def stressed_mortality(probability: float, multiplier: float) -> float:
    if multiplier == 1 or probability in (0, 1):
        return probability
    return -math.expm1(multiplier * math.log1p(-probability))


def draw_return(mean: float, volatility: float, rng: random.Random) -> float:
    """Monthly lognormal gross return, preserving E[r] = mean at every volatility."""
    if volatility == 0:
        return mean
    exponent = math.log1p(mean) - volatility**2 / 2 + volatility * rng.gauss(0, 1)
    try:
        result = math.expm1(exponent)
    except OverflowError as exc:
        raise SimulationLimitError("Return draw overflowed; run incomplete.") from exc
    if not math.isfinite(result) or result <= -1:
        raise SimulationLimitError("Return draw exceeds numeric resolution; run incomplete.")
    return result
