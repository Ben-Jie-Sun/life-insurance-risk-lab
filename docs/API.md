# Local backend and data entry

Start `python run_server.py` from the project folder. Its default URL is `http://127.0.0.1:8000`, and its database is `data/lab.sqlite3` beside the script. To choose a location or port:

```bash
python run_server.py --db data/my_experiment.sqlite3 --port 8001
```

There are no external services. The API uses Python's HTTP server and SQLite. It binds only to loopback, rejects unexpected Host/Origin headers, and does not enable cross-origin access. It is intended for one local user and is not a public production service.

## Data model

**Configurations** are editable, validated documents of kind `model` or `scenario`. Each has an ID, unique name within its kind, integer revision, creation time, and update time. Every update retains an earlier revision while the configuration exists.

**Runs** contain the operation kind, state, exact resolved input snapshot, runtime versions, output, and any error. Run snapshots do not reference mutable configuration contents at execution time after capture: changing or deleting a configuration cannot change an existing run.

All money in input documents is in INR. Model documents returned by the backend use exact decimal strings for money and resolve all default fields. Output ledger amounts use integer paise.

Run states are `running`, `completed`, `incomplete`, `failed`, or `interrupted`. `completed` means computation finished; a completed simulation can still contain payment shortfalls. `incomplete` means a computational guard stopped it. A restarted server marks abandoned running records `interrupted`.

Only one calculation runs at a time in a server instance. Other threads can read history or edit inputs while it works. A second calculation request gets HTTP 409 and can be retried after completion. Calculations are synchronous; a client disconnect does not necessarily cancel a calculation, so inspect history before retrying.

## Routes

| Method and path | Action |
|---|---|
| `GET /api/health` | Version, storage readiness, and calculation status |
| `GET /api/examples` | Bundled model/scenario inputs |
| `GET /api/schema` | Descriptive request shapes, units, limits; not an OpenAPI document |
| `POST /api/configs` | Save a validated configuration |
| `GET /api/configs` | List configuration metadata |
| `GET /api/configs/{id}` | Read a complete current document |
| `GET /api/configs/{id}?revision=1` | Read a retained historical revision |
| `PUT /api/configs/{id}` | Replace the complete document with a revision check |
| `DELETE /api/configs/{id}` | Delete the configuration and its revision history; retain runs |
| `POST /api/quote` | Price or assess a contract |
| `POST /api/simulations` | Run a single scenario |
| `POST /api/experiments` | Run a scenario/capital grid |
| `POST /api/benchmarks` | Compare theoretical expectations with samples |
| `GET /api/runs` | List saved calculations |
| `GET /api/runs/{id}` | Read the request snapshot, state, and result |
| `GET /api/runs/{id}/result` | Export completed result JSON |
| `GET /api/runs/{id}/ledger.csv` | Export a completed simulation ledger |
| `GET /api/runs/{id}/trace?month=8` | Explain stored arithmetic without resimulation |

Lists accept `?limit=50&offset=0`, with limit 1–100. IDs in braces above are placeholders; use IDs returned by the service.

## Save and edit inputs

POST `/api/configs`:

```json
{
  "name": "My first model",
  "kind": "model",
  "document": {
    "policy": {"monthly_premium": "1000.00", "term_months": 36},
    "simulation": {"starting_capital": "5000000.00", "seed": 2026}
  }
}
```

Other fields use documented defaults and appear explicitly in the returned document. This convenience means a missing field is not an assertion that the default is realistic.

An edit must send the **complete replacement document** and the revision you read. This Python example uses the included API client:

```python
from api_client import request

saved = request("GET", "/api/configs/REPLACE_WITH_CONFIG_ID")
document = saved["document"]
document["policy"]["monthly_premium"] = "1200.00"
updated = request("PUT", "/api/configs/" + saved["id"], {
    "document": document,
    "expected_revision": saved["revision"]
})
print(updated["revision"])
```

If another edit already changed that revision, the API returns HTTP 409. Read the latest document and apply the intended change to it. The backend does not silently overwrite newer entries.

Deletion also requires a JSON body:

```json
{"expected_revision": 2}
```

## Compute with inline data or saved IDs

Quote from desired cover:

```json
{
  "config": {
    "policy": {
      "pricing_mode": "benefit_to_premium",
      "sum_assured": "1000000.00"
    }
  },
  "persist": false
}
```

Single simulation using saved documents:

```json
{
  "config_id": "REPLACE_WITH_MODEL_CONFIG_ID",
  "scenario_id": "REPLACE_WITH_SCENARIO_CONFIG_ID",
  "seed": 2026,
  "persist": true
}
```

Inline `config` replaces `config_id`; inline `scenario` replaces `scenario_id`. Supplying both forms for the same input is rejected. A model ID cannot be used as a scenario ID or vice versa.

A successful calculation response contains:

```json
{
  "id": "run_ID_RETURNED_BY_SERVER",
  "kind": "simulation",
  "status": "completed",
  "persisted": true,
  "result": {"schema_version": 2}
}
```

The shown result is abbreviated. An unstored result has `id: null`. Quotes default to unstored; other calculations default to stored.

## Capital and scenario experiment

POST `/api/experiments`:

```json
{
  "config": {},
  "scenarios": [
    {"name": "baseline"},
    {
      "name": "temporary_mortality_shock",
      "events": [
        {"start_month": 8, "end_month": 11, "mortality_multiplier": 3}
      ]
    }
  ],
  "capitals": [1000000, 2500000, 5000000, 7500000],
  "paths": 100,
  "persist": true
}
```

`scenario_ids` can replace `scenarios`. Each scenario name and each capital value must be distinct. The selected contract is frozen for every cell; the original reserve basis is also fixed. The response includes aggregate risk metrics and per-path seed/shortfall/severity summaries.

POST `/api/benchmarks` accepts `config` or `config_id`, `paths`, optional `seed`, and `persist`. Its policy benchmark deliberately uses a fixed initial cohort with no later issues, so analytical expectations are directly comparable.

## Validation and limits

All modifying requests use `Content-Type: application/json`. Unknown fields, duplicate JSON keys, invalid probabilities, nonfinite values, and ambiguous pricing modes are rejected.

| Limit | Value |
|---|---:|
| Request body | 1 MiB |
| Scenarios/capital values supplied through API | Up to 10 each |
| Scenario/capital cells | 40 |
| Paths per cell | 1–1,000 |
| Total paths in one experiment | 5,000 |
| Policy-month budget per path | 5,000,000 |
| Work budget per experiment/benchmark | 50,000,000 |
| Scenario event windows | 50 |
| Concurrent calculations per server | 1 |

The path budget uses a conservative candidate-count × term bound. If an experiment hits a limit, it aborts without reporting a completed estimate from only the easier paths.

Errors have an `error` object containing `code` and `message`. A failed persisted calculation also returns its `run_id`:

- `403`: unexpected Host/Origin.
- `404`: missing record or route.
- `409`: revision/name conflict, busy engine, or result not complete.
- `413`: body too large.
- `415`: wrong content type.
- `422`: invalid model/request or incomplete computation; inspect the error code and message.
- `500`/`503`: unexpected server or storage problem; inspect terminal logs.

## Database persistence and backup

SQLite uses transactions and parameterized SQL. Each update records a revision atomically. Completed run records have no update endpoint. References record the chosen configuration revision, and full input snapshots remain available after the configuration is deleted.

Keep one backend server process per database. For a simple backup, stop the server and copy the `data` folder. No sample database with personal or real customer information is included. `api_demo.py` creates synthetic demonstration records for you.

There is no user authentication, authorization model, TLS termination, distributed job queue, or customer transaction service in this local version. Those require a separate deployment design before any public use.

## v0.3: dedicated Monte Carlo ensemble

`POST /api/monte-carlo` accepts `config` or `config_id`, `scenario` or `scenario_id`, `paths` (2–1000), optional `seed`, and `persist` (default true). It uses the same simulation engine as the single-path endpoint.

```json
{"config": {}, "scenario": {"name": "baseline"}, "paths": 200, "seed": 2026, "persist": true}
```

The result includes `summary.payment_shortfall`, `summary.capital_breach`, terminal surplus statistics, `monthly` percentile bands, `yule_benchmark`, `convergence`, `path_metrics`, `example_paths`, `replay_config` and interpretation notes. Monetary fields explicitly named `paise` use paise; monthly counts are dimensionless.

For a saved Monte Carlo run, `GET /api/runs/{id}/bands.csv` and `GET /api/runs/{id}/paths.csv` provide CSV exports. `GET /api/runs/{id}/result` provides JSON. Ledger and trace routes still require a single simulation. The dashboard is at `/`; the original API index is at `/api`.

The ensemble supports at most 500,000 path-month observations and a 50-million policy-month work budget. An exceeded guard records an incomplete run, without reporting a partially accepted sample. Existing v0.2 endpoints and the SQLite schema remain compatible.
