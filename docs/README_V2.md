# Yule–Furry Life Insurance Lab — v0.2

A course project connecting pure-birth acquisition, actuarial pricing, policy exits, company cash flows, stress experiments, and a local backend with optional SQLite storage.

**Python 3.10+; no third-party packages, API keys, or internet connection required.** All examples use synthetic assumptions and virtual money.

## Inspect the project immediately

Open **`sample_output/index.html`** in your browser. It contains the prepared professor demonstration: two pricing directions, six experience scenarios, increasing-duration mortality, a guaranteed shortfall, a capital comparison, and a theory-versus-simulation benchmark.

To regenerate it, open a terminal in the extracted project folder:

```bash
python run_demo.py
```

Then open `outputs/demo/index.html`. Use `py` on Windows or `python3` on macOS/Linux if that is your Python command. The capital experiment may take several seconds; progress messages identify each calculation.

## Start the backend

In terminal 1:

```bash
python run_server.py
```

Open **http://127.0.0.1:8000** to read the endpoint guide. The database is created automatically at `data/lab.sqlite3` beside the project. There is no database server to install.

In terminal 2, from the same project folder:

```bash
python api_demo.py
```

This demonstration uses real local HTTP requests to:

1. Save a model and a mortality-shock scenario.
2. Obtain a quote and run a stored simulation.
3. Download the ledger and explain month 8.
4. Update the saved model from a monthly premium of INR 1,000 to INR 1,200.
5. Verify that the earlier run still contains its original INR 1,000 contract.

Results download to `outputs/api_demo`. Restarting the backend preserves saved configurations, revision history, and calculation results. Ctrl+C stops the server. An interrupted calculation is marked `interrupted` on the next startup rather than presented as complete.

The backend is a **local teaching service** bound to loopback. It has no user accounts, public hosting, or real-payment functions. Use one backend server process per database.

## Enter your own data

Edit `examples/api/save_model.json`, then submit it:

```bash
python api_client.py POST /api/configs --file examples/api/save_model.json
python api_client.py GET /api/configs
```

The response contains a configuration ID, revision, and complete validated document. Use the ID in later requests instead of copying all its fields. Names must be unique within each configuration kind.

You can also compute directly from a JSON request without saving a configuration:

```bash
python api_client.py POST /api/quote --file examples/api/quote_cover.json
python api_client.py POST /api/simulations --file examples/api/simulate.json
python api_client.py POST /api/experiments --file examples/api/experiment.json
python api_client.py POST /api/benchmarks --file examples/api/benchmark.json
python api_client.py GET /api/runs
```

Add `--output outputs/response.json` to save a client response. Add `--url http://127.0.0.1:8001` when using another port. See [docs/API.md](docs/API.md) for edits, revision conflicts, deletion, exports, and complete request shapes.

**Storage is optional for computations:** simulation, experiment, and benchmark API requests default to `"persist": true`; set it to `false` for a transient result. Quotes default to transient. Explicitly saving a configuration always stores it.

## What changed from v0.1

| Area | v0.2 behavior |
|---|---|
| Pricing | Premium-to-benefit, benefit-to-premium, and fixed-contract assessment modes |
| Contract terms | Premium and benefit are resolved once and remain fixed during experience shocks |
| Assumptions | Separate policy-duration mortality/lapse schedules from calendar-month stress events |
| Experience scenarios | Mortality, lapse, poor-return, combined, and optional stochastic-return examples |
| Reserves | Explicit original-pricing reference basis; experience shocks do not silently reprice promises or revalue reserves |
| Capital experiments | Multiple capital levels and scenarios, mean/median/5th-percentile surplus, shortfall intervals, and severity metrics |
| Benchmarks | Yule theoretical moments and fixed-cohort expected premiums/claims compared with simulation means |
| Explainability | Month-by-month arithmetic traces with exact accounting checks |
| Backend | Validated HTTP JSON API, SQLite configuration CRUD, optimistic revision checks, immutable run snapshots, history, and CSV export |
| Verification | 49 tests, plus a live API-client/restart/export smoke check |

The original seed-2026 baseline still selects INR 890,283.83 of cover and closes with INR 7,943,821.06 in net assets. New reports add scenario, trace, and contract information.

## Pricing modes

Set `policy.pricing_mode` in a model JSON:

| Mode | Required inputs | Calculated output |
|---|---|---|
| `premium_to_benefit` | Positive `monthly_premium`; absent/null `sum_assured` | Benefit rounded down to whole paise |
| `benefit_to_premium` | Positive `sum_assured`; absent/null `monthly_premium` | Premium rounded up to whole paise |
| `assess` | Both premium and benefit | Expected margin and target-margin flag |
| `auto` (default) | Original v0.1 input format | Calculate benefit if it is absent; otherwise assess the given contract |

With premium factor a, death-benefit factor b, expense EPV E, and target margin m:

- Benefit from premium: **B = (p a − E − m) / b**.
- Premium from benefit: **p = (B b + E + m) / a**.

A positive expected margin does not eliminate payment-shortfall risk. Pricing a fixed benefit under unrealistic assumptions is not a real insurance quotation.

## Scenarios and timing

Model mortality/lapse arrays are indexed by **policy duration**. Scenario events are indexed by **calendar month**, so one shock reaches contracts issued at different dates.

```json
{
  "name": "temporary_mortality_shock",
  "events": [
    {
      "name": "three-month shock",
      "start_month": 8,
      "end_month": 11,
      "mortality_multiplier": 3
    }
  ]
}
```

The interval is **[8, 11)**: months 8, 9, and 10. The end is exclusive. Mortality is transformed as `q_stress = 1 - (1 - q)^multiplier`. Lapse and return overrides replace the configured experience value for that period. Overlapping events that change the same field are rejected; events must fit within the projection horizon.

Supported global/event assumption fields:

- `mortality_multiplier`: positive multiplier of monthly cumulative mortality hazard.
- `lapse_monthly`: survivor lapse probability; null inherits the policy-duration schedule.
- `asset_return_monthly`: mean monthly return; null inherits the simulation's configured cash return.
- `return_volatility_monthly`: monthly log-return standard deviation; zero gives deterministic returns.

The optional return model uses a lognormal gross return with the stated expected monthly return. Returns apply to one liquid aggregate fund. Cash/bond/equity allocation, illiquidity, and asset-liability optimization are future work.

## Offline commands

```bash
python -m life_insurance_lab quote --config examples/cover_based.json
python -m life_insurance_lab run --config examples/baseline.json --scenario examples/scenarios/combined_stress.json --output outputs/stress
python -m life_insurance_lab run --config examples/increasing_mortality.json --output outputs/increasing
python -m life_insurance_lab compare --paths 100 --output outputs/lapse_comparison
python -m life_insurance_lab experiment --scenarios examples/scenarios/baseline.json examples/scenarios/mortality_shock.json --capitals 1000000 2500000 5000000 7500000 --paths 100 --output outputs/capital
python -m life_insurance_lab benchmark --paths 200 --output outputs/benchmark
python -m life_insurance_lab trace --input outputs/stress/result.json --month 8 --output outputs/month_8
python -m unittest discover -s tests -v
```

Add `--db data/lab.sqlite3` to a quote, run, comparison, experiment, or benchmark command to store it. With no `--db`, offline calculations only write their output files.

```bash
python -m life_insurance_lab run --db data/lab.sqlite3
python -m life_insurance_lab history --db data/lab.sqlite3
python -m life_insurance_lab export --db data/lab.sqlite3 --run-id REPLACE_WITH_RUN_ID --output outputs/exported
```

Using the same output directory replaces its generated files. Failed calculations do not produce new completed reports; an older report can remain in a reused directory. Use a fresh output directory for each important experiment.

## Units and reproducibility

- Input money is in **INR**, with at most two decimal places. Decimal strings such as `"1000.01"` preserve exact money amounts even through clients that use binary floats.
- Posted output money is in integer **paise**. Expected present values and across-path averages can contain fractional paise.
- Rates and probabilities are **monthly**. Yule's lambda is a continuous-time rate per member per month, not a probability.
- A seed makes runs repeatable under the same code and runtime. Stored snapshots include the application/Python versions, resolved defaults, and source configuration revisions.
- Comparisons preserve premium, benefit, original reserve basis, and seed sequence while changing the selected experience assumptions and capital.
- The maximum candidate count is a computational guard. Exceeding it makes a run incomplete; it does not turn the model into a capped Yule process.
- The entire comparison aborts if a constituent path is incomplete. No difficult paths are discarded from a risk estimate.

## Code map

| Module | Responsibility |
|---|---|
| `config.py`, `jsonio.py` | Validated assumptions, exact money inputs, replayable configuration documents |
| `models/yule.py`, `models/policy.py` | Acquisition events and policy transitions |
| `actuarial.py` | Both pricing directions and reference reserves |
| `scenarios.py` | Calendar events, hazard changes, optional random returns |
| `simulation.py` | Cohorts, fixed contracts, actual ledger, unpaid obligations, invariants |
| `experiments.py`, `benchmarks.py` | Capital/scenario comparisons and independent analytical expectations |
| `traces.py`, `reporting.py` | Calculation explanations and offline reports |
| `backend/storage.py` | SQLite transactions, configuration revisions, immutable calculation snapshots |
| `backend/service.py` | Shared validated operations used by CLI and API |
| `backend/server.py` | Local HTTP routes, request limits, JSON/CSV responses |

## Read before the professor demonstration

- [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md): a short presentation sequence and likely questions.
- [docs/MATHEMATICS.md](docs/MATHEMATICS.md): derivations of the original pricing and process equations.
- [docs/UPGRADE_MATHEMATICS.md](docs/UPGRADE_MATHEMATICS.md): reverse pricing, stress, volatility, benchmarks, and preserved contracts.
- [docs/API.md](docs/API.md): backend operation and data storage.
- [docs/SCOPE_AND_LIMITS.md](docs/SCOPE_AND_LIMITS.md): computational, information, model, and boundary limitations.

AI Audit, portfolio integration, grace/reinstatement states, individual customer records, real mortality calibration, and public release operations remain outside this version.
