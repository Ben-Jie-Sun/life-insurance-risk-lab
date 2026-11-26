"""Errors callers can distinguish from programming failures."""


class ModelError(ValueError):
    """Invalid assumptions or an infeasible pricing request."""


class SimulationLimitError(ModelError):
    """A computational limit was reached; the run is incomplete."""
