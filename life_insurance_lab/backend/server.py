"""Loopback-only HTTP JSON API. A local teaching backend, not a public web host."""

import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
import re
import sqlite3
import traceback
from urllib.parse import parse_qs, urlsplit

from .. import __version__
from ..config import _integer
from ..errors import ModelError
from ..jsonio import dumps, load, loads
from ..monte_carlo import monthly_csv_rows
from ..traces import explain_month
from .service import ExecutionError, Service, fields
from .storage import Conflict, NotFound, Store

MAX_BODY_BYTES = 1_048_576
ROOT = Path(__file__).resolve().parents[2]
ENDPOINTS = {
    "GET /api/health": "Service version, database availability, and computation status",
    "GET /api/examples": "Bundled model and scenario inputs",
    "GET /api/schema": "Request shapes, units, and limits",
    "GET /api/configs?limit=50&offset=0": "List saved configurations",
    "POST /api/configs": "Save a validated model or scenario",
    "GET /api/configs/{id}?revision=1": "Read current or historical configuration",
    "PUT /api/configs/{id}": "Replace a configuration with expected_revision",
    "DELETE /api/configs/{id}": "Delete a configuration with expected_revision; retain run snapshots",
    "POST /api/quote": "Price from premium, price from benefit, or assess a fixed contract",
    "POST /api/simulations": "Run one scenario; persist by default",
    "POST /api/experiments": "Compare scenarios and capital levels; persist by default",
    "POST /api/monte-carlo": "Repeat the complete Yule/cohort model; fan charts and uncertainty",
    "GET /api/runs/{id}/bands.csv": "Export Monte Carlo monthly bands",
    "GET /api/runs/{id}/paths.csv": "Export Monte Carlo path metrics",
    "POST /api/benchmarks": "Compare simulations with analytical expectations; persist by default",
    "GET /api/runs?limit=50&offset=0": "List calculation history and completion status",
    "GET /api/runs/{id}": "Read immutable request snapshot and result",
    "GET /api/runs/{id}/result": "Export the result JSON",
    "GET /api/runs/{id}/ledger.csv": "Export a simulation's monthly ledger",
    "GET /api/runs/{id}/trace?month=8": "Explain stored monthly arithmetic",
}


def schema() -> dict:
    return {
        "application_version": __version__, "format": "descriptive request schema (not OpenAPI)",
        "units": {"input_money": "INR number or exact decimal string", "result_money": "paise",
                  "probabilities_and_returns": "monthly", "event_windows": "start inclusive, end exclusive"},
        "model_fields": {
            "policy": ["name", "pricing_mode", "term_months", "monthly_premium", "sum_assured",
                       "monthly_expense", "acquisition_expense", "target_epv_margin", "mortality_monthly",
                       "lapse_monthly", "valuation_interest_monthly"],
            "simulation": ["initial_policies", "acquisition_months", "yule_rate_monthly", "starting_capital",
                           "asset_interest_monthly", "capital_buffer", "max_policies", "seed"],
        },
        "pricing_modes": ["auto", "premium_to_benefit", "benefit_to_premium", "assess"],
        "scenario_fields": ["name", "mortality_multiplier", "lapse_monthly", "asset_return_monthly",
                            "return_volatility_monthly", "events"],
        "event_fields": ["name", "start_month", "end_month", "mortality_multiplier", "lapse_monthly",
                         "asset_return_monthly", "return_volatility_monthly"],
        "requests": {
            "save_config": {"name": "My model", "kind": "model", "document": {}},
            "update_config": {"name": "My updated model", "expected_revision": 1, "document": {}},
            "delete_config": {"expected_revision": 1},
            "quote": {"config": {"policy": {"pricing_mode": "benefit_to_premium", "sum_assured": "1000000.00"}}, "persist": False},
            "simulation": {"config": {}, "scenario": {"name": "baseline"}, "seed": 2026, "persist": True},
            "experiment": {"config": {}, "scenarios": [{"name": "baseline"}], "capitals": [1000000, 5000000], "paths": 100},
            "benchmark": {"config": {}, "paths": 200},
            "monte_carlo": {"config": {}, "scenario": {"name": "baseline"}, "paths": 200, "persist": True},
        },
        "references": "config_id replaces config; scenario_id replaces scenario; scenario_ids replaces scenarios.",
        "limits": {"body_bytes": MAX_BODY_BYTES, "paths_per_cell": 1000, "total_experiment_paths": 5000,
                   "monte_carlo_paths": 1000, "monte_carlo_observations": 500000,
                   "comparison_cells": 40, "concurrent_calculations": 1,
                   "policy_months_per_path": 5000000, "policy_months_per_experiment": 50000000},
        "endpoints": ENDPOINTS,
        "notes": ["Unknown fields and duplicate JSON keys are rejected.",
                  "Saved model documents contain every resolved default and can be edited and resubmitted.",
                  "PUT replaces the complete document. Read the current revision first.",
                  "Simulation, experiment and benchmark results are persisted unless persist is false.",
                  "Quote results are transient unless persist is true.",
                  "Input validation does not certify that the assumptions are realistic or that a benefit is affordable."],
    }


class HTTPProblem(Exception):
    def __init__(self, code: int, message: str):
        self.code, self.message = code, message


class LabHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service: Service, quiet=False):
        if address[0] not in {"127.0.0.1", "localhost"}:
            raise ModelError("This local backend binds only to 127.0.0.1 or localhost.")
        self.service, self.quiet = service, quiet
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "LifeInsuranceLab/0.3"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, fmt, *args):
        if not self.server.quiet:
            super().log_message(fmt, *args)

    def send_payload(self, code, value, content_type="application/json; charset=utf-8"):
        payload = value.encode("utf-8") if isinstance(value, str) else dumps(value).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # A completed persisted run remains available after a disconnected client.

    def check_local_request(self):
        port = self.server.server_port
        authorities = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            authorities |= {"127.0.0.1", "localhost"}
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0] not in authorities:
            raise HTTPProblem(403, "Unexpected Host header; use the displayed localhost URL.")
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] not in {"http://"+x for x in authorities}):
            raise HTTPProblem(403, "Cross-origin requests are disabled for this local service.")

    def body(self):
        if self.headers.get("Transfer-Encoding"):
            raise HTTPProblem(400, "Chunked request bodies are not supported.")
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPProblem(415, "Use Content-Type: application/json.")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise HTTPProblem(411, "One Content-Length header is required.")
        try:
            size = int(lengths[0])
        except ValueError as exc:
            raise HTTPProblem(400, "Invalid Content-Length.") from exc
        if size < 0 or size > MAX_BODY_BYTES:
            raise HTTPProblem(413, "JSON request body exceeds the size limit.")
        data = self.rfile.read(size)
        if len(data) != size:
            raise HTTPProblem(400, "Incomplete request body.")
        value = loads(data)
        if not isinstance(value, dict):
            raise ModelError("Request body must be a JSON object.")
        return value

    @staticmethod
    def query_number(query, name, default, minimum, maximum):
        if name not in query:
            return default
        try:
            if len(query[name]) != 1:
                raise ValueError
            value = int(query[name][0])
        except ValueError as exc:
            raise ModelError(f"{name} must be one integer.") from exc
        return _integer(value, name, minimum, maximum)

    def dispatch(self, method):
        self.check_local_request()
        url = urlsplit(self.path)
        path, query = url.path.rstrip("/") or "/", parse_qs(url.query, keep_blank_values=True)
        if len(self.path) > 4096:
            raise HTTPProblem(414, "Request URL is too long.")
        service, store = self.server.service, self.server.service.store
        web_files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
        if method == "GET" and path in web_files:
            filename, content_type = web_files[path]
            self.send_payload(200, (Path(__file__).resolve().parents[1]/"web"/filename).read_text(encoding="utf-8"), content_type+"; charset=utf-8")
            return
        if method == "GET" and path == "/api":
            rows = "".join(f"<tr><td><code>{endpoint}</code></td><td>{description}</td></tr>"
                           for endpoint, description in ENDPOINTS.items())
            self.send_payload(200, "<!doctype html><html lang='en'><meta charset='utf-8'><title>Insurance Lab API</title>"
                              "<style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;line-height:1.5}"
                              "td{padding:10px;border-bottom:1px solid #ddd}code{white-space:nowrap}</style>"
                              "<h1>Life Insurance Lab — local backend</h1>"
                              "<p>The API is running. Use the JSON examples and api_demo.py to enter data and save results.</p>"
                              "<p><a href='/api/schema'>Request schema</a> · <a href='/api/examples'>Example inputs</a> · "
                              "<a href='/api/configs'>Saved configurations</a> · <a href='/api/runs'>Saved runs</a></p>"
                              "<table>"+rows+"</table><p>Synthetic course model. This local server has no user accounts or public deployment support.</p></html>",
                              "text/html; charset=utf-8")
            return
        if method == "GET" and path == "/api/health":
            with store.connection() as db:
                db.execute("SELECT 1")
            self.send_payload(200, {"status": "ok", "version": __version__, "database": "ready",
                                    "calculation_running": service.compute_lock.locked()})
            return
        if method == "GET" and path == "/api/schema":
            self.send_payload(200, schema())
            return
        if method == "GET" and path == "/api/examples":
            self.send_payload(200, {"models": {p.stem: load(p) for p in sorted((ROOT/"examples").glob("*.json"))},
                                    "scenarios": {p.stem: load(p) for p in sorted((ROOT/"examples/scenarios").glob("*.json"))}})
            return
        if method == "GET" and path in {"/api/configs", "/api/runs"}:
            if set(query)-{"limit", "offset"}:
                raise ModelError("Unknown list query parameter.")
            limit = self.query_number(query, "limit", 50, 1, 100)
            offset = self.query_number(query, "offset", 0, 0, 2**31-1)
            items = store.list_configs(limit, offset) if path.endswith("configs") else store.list_runs(limit, offset)
            self.send_payload(200, {"items": items, "limit": limit, "offset": offset})
            return
        if method == "POST" and path == "/api/configs":
            self.send_payload(201, service.create_config(self.body()))
            return
        match = re.fullmatch(r"/api/configs/(cfg_[a-f0-9]{32})", path)
        if match:
            identifier = match[1]
            if method == "GET":
                if set(query)-{"revision"}:
                    raise ModelError("Unknown configuration query parameter.")
                self.send_payload(200, store.get_config(identifier, self.query_number(query, "revision", None, 1, 2**31-1)))
                return
            if method == "PUT":
                self.send_payload(200, service.update_config(identifier, self.body()))
                return
            if method == "DELETE":
                body = self.body()
                fields(body, {"expected_revision"})
                store.delete_config(identifier, _integer(body.get("expected_revision"), "expected_revision", 1, 2**31-1))
                self.send_payload(200, {"deleted": identifier, "run_snapshots_retained": True})
                return
        actions = {"/api/quote": "quote", "/api/simulations": "simulation",
                   "/api/experiments": "experiment", "/api/benchmarks": "benchmark",
                   "/api/monte-carlo": "monte_carlo"}
        if method == "POST" and path in actions:
            self.send_payload(200, service.execute(actions[path], self.body()))
            return
        match = re.fullmatch(r"/api/runs/(run_[a-f0-9]{32})(?:/(result|ledger\.csv|bands\.csv|paths\.csv|trace))?", path)
        if method == "GET" and match:
            saved = store.get_run(match[1])
            resource = match[2]
            if resource is None:
                self.send_payload(200, saved)
                return
            result = saved["result"]
            if saved["status"] != "completed" or result is None:
                raise Conflict("This run has no completed result. Inspect its status and error.")
            if resource == "result":
                self.send_payload(200, result)
                return
            if resource in {"bands.csv", "paths.csv"}:
                if saved["kind"] != "monte_carlo":
                    raise ModelError("Bands and path metrics require a Monte Carlo run.")
                rows = list(monthly_csv_rows(result)) if resource == "bands.csv" else result["path_metrics"]
                stream = StringIO(newline="")
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
                self.send_payload(200, stream.getvalue(), "text/csv; charset=utf-8")
                return
            if saved["kind"] != "simulation":
                raise ModelError("Ledger and trace resources require a simulation run.")
            if resource == "trace":
                if set(query)-{"month"}:
                    raise ModelError("Unknown trace query parameter.")
                month = self.query_number(query, "month", 0, 0, len(result["monthly"])-1)
                self.send_payload(200, explain_month(result, month))
                return
            stream = StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=list(result["monthly"][0]))
            writer.writeheader()
            writer.writerows(result["monthly"])
            self.send_payload(200, stream.getvalue(), "text/csv; charset=utf-8")
            return
        raise NotFound("Endpoint or resource not found.")

    def handle_request(self, method):
        try:
            self.dispatch(method)
        except HTTPProblem as exc:
            self.send_payload(exc.code, {"error": {"code": "http_error", "message": exc.message}})
        except NotFound as exc:
            self.send_payload(404, {"error": {"code": "not_found", "message": str(exc)}})
        except Conflict as exc:
            self.send_payload(409, {"error": {"code": "conflict", "message": str(exc)}})
        except ExecutionError as exc:
            self.send_payload(422, {"error": {"code": exc.status, "message": str(exc), "run_id": exc.run_id}})
        except ModelError as exc:
            self.send_payload(422, {"error": {"code": "validation_error", "message": str(exc)}})
        except TimeoutError:
            self.send_payload(408, {"error": {"code": "timeout", "message": "Request body timed out."}})
        except sqlite3.OperationalError:
            traceback.print_exc()
            self.send_payload(503, {"error": {"code": "storage_error", "message": "Database unavailable or busy."}})
        except Exception:
            traceback.print_exc()
            self.send_payload(500, {"error": {"code": "internal_error", "message": "Unexpected error; inspect the server log."}})

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PUT(self):
        self.handle_request("PUT")

    def do_DELETE(self):
        self.handle_request("DELETE")


def make_server(database: str | Path, host="127.0.0.1", port=8000, quiet=False):
    _integer(port, "port", 0, 65535)
    server = LabHTTPServer((host, port), Service(Store(database)), quiet)
    server.service.store.recover_interrupted()
    return server


def serve(database: str | Path, host="127.0.0.1", port=8000):
    server = make_server(database, host, port)
    print(f"Insurance Lab API: http://{host}:{server.server_port}")
    print(f"SQLite database: {server.service.store.path}")
    print("Local use only. Press Ctrl+C to stop. Use one server process per database.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping the local API.")
    finally:
        server.server_close()
