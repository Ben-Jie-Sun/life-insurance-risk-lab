"""Validated use cases shared by HTTP clients and Python code."""

from dataclasses import replace
import platform
import threading

from .. import __version__
from ..actuarial import quote
from ..benchmarks import benchmark
from ..config import from_dict, _integer
from ..errors import ModelError, SimulationLimitError
from ..experiments import run_experiment
from ..money import to_paise
from ..monte_carlo import run_monte_carlo
from ..scenarios import from_dict as scenario_from_dict
from ..simulation import simulate
from .storage import Conflict, Store


class ExecutionError(ModelError):
    def __init__(self, message, status="failed", run_id=None):
        super().__init__(message)
        self.status, self.run_id = status, run_id


def fields(body, allowed):
    if not isinstance(body, dict):
        raise ModelError("Request body must be a JSON object.")
    extra = set(body)-set(allowed)
    if extra:
        raise ModelError(f"Unknown fields: {', '.join(sorted(extra))}")


def name_value(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ModelError("name must contain 1–200 characters.")
    return value.strip()


class Service:
    def __init__(self, store: Store | None = None):
        self.store = store
        self.compute_lock = threading.Lock()

    def validate_document(self, kind, document):
        if kind == "model":
            return from_dict(document).to_input_dict()
        if kind == "scenario":
            return scenario_from_dict(document).as_dict()
        raise ModelError("kind must be model or scenario.")

    def create_config(self, body):
        fields(body, {"name", "kind", "document"})
        if "document" not in body:
            raise ModelError("document is required.")
        kind = body.get("kind", "model")
        return self.store.create_config(kind, name_value(body.get("name")),
                                        self.validate_document(kind, body["document"]))

    def update_config(self, identifier, body):
        fields(body, {"name", "document", "expected_revision"})
        revision = _integer(body.get("expected_revision"), "expected_revision", 1, 2**31-1)
        if "document" not in body:
            raise ModelError("A complete replacement document is required.")
        existing = self.store.get_config(identifier)
        return self.store.update_config(identifier, name_value(body.get("name", existing["name"])),
                                        self.validate_document(existing["kind"], body["document"]), revision)

    def _resolve(self, body, field, default):
        identifier_key = field+"_id"
        if field in body and identifier_key in body:
            raise ModelError(f"Supply {field} or {identifier_key}, not both.")
        if identifier_key not in body:
            value = body.get(field, default)
            if not isinstance(value, dict):
                raise ModelError(f"{field} must be an object.")
            return value, None
        identifier = body[identifier_key]
        if self.store is None:
            raise ModelError("Saved configuration references require a database.")
        if not isinstance(identifier, str):
            raise ModelError(f"{identifier_key} must be a string.")
        saved = self.store.get_config(identifier)
        wanted = "model" if field == "config" else "scenario"
        if saved["kind"] != wanted:
            raise ModelError(f"{identifier_key} references the wrong configuration kind.")
        return saved["document"], {"id": identifier, "revision": saved["revision"]}

    def execute(self, kind: str, body: dict) -> dict:
        common = {"config", "config_id", "seed", "persist"}
        extra = {"quote": set(), "simulation": {"scenario", "scenario_id"},
                 "experiment": {"scenarios", "scenario_ids", "capitals", "paths"},
                 "benchmark": {"paths"}, "monte_carlo": {"paths", "scenario", "scenario_id"}}
        if kind not in extra:
            raise ModelError("Unknown computation.")
        fields(body, common | extra[kind])
        persist = body.get("persist", kind != "quote")
        if type(persist) is not bool:
            raise ModelError("persist must be true or false.")
        if persist and self.store is None:
            raise ModelError("Persistence requires a database; use persist=false for a transient calculation.")
        raw, config_ref = self._resolve(body, "config", {})
        config = from_dict(raw)
        if "seed" in body:
            config = replace(config, simulation=replace(config.simulation, seed=body["seed"]))
            config.validate()
        snapshot = {"config": config.to_input_dict(), "config_reference": config_ref,
                    "runtime": {"application": __version__, "python": platform.python_version()}}
        scenario = None
        scenarios, capitals, paths = [], [], None
        if kind in ("simulation", "monte_carlo"):
            raw_scenario, reference = self._resolve(body, "scenario", {})
            scenario = scenario_from_dict(raw_scenario)
            scenario.validate(config.policy.term_months+config.simulation.acquisition_months)
            snapshot.update(scenario=scenario.as_dict(), scenario_reference=reference)
        if kind in ("experiment", "benchmark", "monte_carlo"):
            paths = _integer(body.get("paths", 100 if kind == "experiment" else 200), "paths",
                             1 if kind == "experiment" else 2, 1000)
            snapshot["paths"] = paths
        if kind == "experiment":
            if "scenarios" in body and "scenario_ids" in body:
                raise ModelError("Supply scenarios or scenario_ids, not both.")
            references = []
            if "scenario_ids" in body:
                ids = body["scenario_ids"]
                if not isinstance(ids, list) or not 1 <= len(ids) <= 10:
                    raise ModelError("scenario_ids must be an array of 1–10 IDs.")
                for identifier in ids:
                    document, reference = self._resolve({"scenario_id": identifier}, "scenario", {})
                    scenarios.append(scenario_from_dict(document))
                    references.append(reference)
            else:
                entries = body.get("scenarios", [{"name": "baseline"}])
                if not isinstance(entries, list) or not 1 <= len(entries) <= 10:
                    raise ModelError("scenarios must contain 1–10 scenario objects.")
                scenarios = [scenario_from_dict(x) for x in entries]
            amounts = body.get("capitals", [config.to_input_dict()["simulation"]["starting_capital"]])
            if not isinstance(amounts, list) or not 1 <= len(amounts) <= 10:
                raise ModelError("capitals must contain 1–10 rupee amounts.")
            capitals = [to_paise(x, "capital") for x in amounts]
            snapshot.update(scenarios=[s.as_dict() for s in scenarios],
                            scenario_references=references, capitals_paise=capitals)
        if not self.compute_lock.acquire(blocking=False):
            raise Conflict("A computation is already running. Retry after it finishes.")
        identifier = None
        try:
            if persist:
                identifier = self.store.begin_run(kind, snapshot)
            if kind == "quote":
                pricing = quote(config.policy)
                result = {"schema_version": 2, "config": config.as_dict(), "pricing": pricing.as_dict(),
                          "contract": {"premium_paise": pricing.selected_premium_paise,
                                       "benefit_paise": pricing.selected_benefit_paise,
                                       "term_months": config.policy.term_months}}
            elif kind == "simulation":
                result = simulate(config, scenario=scenario).as_dict()
            elif kind == "monte_carlo":
                result = run_monte_carlo(config, paths, scenario)
            elif kind == "experiment":
                result = run_experiment(config, scenarios, capitals, paths)
            else:
                result = benchmark(config, paths)
            result["runtime"] = snapshot["runtime"]
            if identifier:
                self.store.finish_run(identifier, "completed", result)
            return {"id": identifier, "kind": kind, "status": "completed",
                    "persisted": bool(identifier), "result": result}
        except ModelError as exc:
            status = "incomplete" if isinstance(exc, SimulationLimitError) else "failed"
            if identifier:
                self.store.finish_run(identifier, status, error=str(exc))
            raise ExecutionError(str(exc), status, identifier) from exc
        except Exception:
            if identifier:
                self.store.finish_run(identifier, "failed", error="Unexpected computation error; inspect the server log.")
            raise
        finally:
            self.compute_lock.release()
