# Life Insurance Lab v0.3 — Yule–Furry + Monte Carlo

A local Mathematical Modelling project. Yule–Furry generates potential arrivals; the existing policy and cash-flow engine handles admission, death, lapse and expiry. Monte Carlo repeats the complete engine to estimate payment-shortfall risk and show the distribution of outcomes.

## Run the dashboard

Python **3.10 or newer** is required. The application uses only the Python standard library; no pip install is needed.

1. Extract the ZIP to an ordinary folder.
2. Open a terminal in the folder containing `run_server.py`.
3. Run `python run_server.py` (on Windows, `py -3 run_server.py` also works).
4. Open **http://127.0.0.1:8000** in your browser.
5. Keep the terminal open. Stop the server with Ctrl+C.

If port 8000 is occupied, run `python run_server.py --port 8001` and open http://127.0.0.1:8001.

The database is created automatically at `data/lab.sqlite3`. Saving a run keeps its complete assumptions, scenario, seeds and result. Saved models can be loaded separately. Existing v0.2 databases remain compatible; back up a database before moving it between machines. This is a single-process, local service.

## What to demonstrate

- **Price contract:** calculate death cover from a monthly premium, or calculate the premium for a specified cover.
- **One path:** inspect premiums, expenses, claims, lapse and expiry in the monthly ledger.
- **Monte Carlo:** repeat 200 paths for a quick demonstration or 1,000 for the paper experiment.
- **Uncertainty:** shortfall frequency with a 95% Wilson interval; population and net-asset outcome bands; prefix convergence.
- **Analytical check:** compare simulated Yule candidate moments with exact formulas.
- **Stress:** choose dated mortality, lapse, poor-return, volatile-return or combined scenarios. The issued premium and benefit remain fixed.
- **Records:** save models and runs; inspect history; load inputs; download JSON or CSV.

Basic inputs use constant monthly probabilities. Advanced model JSON retains duration-specific schedules and all existing parameters. The seed field below the JSON determines the run seed. The UI limits seeds to JavaScript-safe integers; the CLI/API support the wider validated Python integer range.

## Features retained from v0.2

Exact-paise cash accounting, premium/cover quotation, discrete reserve recursion, fixed contracts under experience stress, dated scenario events, random aggregate fund returns, lapse and expiry, unpaid-obligation tracking, stop-sale after a shortfall, capital-buffer checks, month traces, scenario/capital grids, analytical benchmarks, configuration revision history and immutable SQLite run snapshots. Original examples, tests, sample reports and API clients remain available.

The old comparison command already repeated paths. v0.3 makes Monte Carlo a dedicated use case with a dashboard, monthly ensemble bands, uncertainty summaries and reproducible paper outputs. It calls the same simulation engine; there is no second, conflicting cash-flow model.

## Command-line use

```bash
python -m life_insurance_lab monte-carlo --config examples/baseline.json --paths 1000 --output outputs/mc
python -m life_insurance_lab monte-carlo --paths 1000 --scenario examples/scenarios/mortality_shock.json --db data/lab.sqlite3 --output outputs/stress
python -m life_insurance_lab run --config examples/baseline.json --output outputs/one_path
python -m life_insurance_lab experiment --paths 200 --capitals 1000000 5000000 --scenarios examples/scenarios/baseline.json examples/scenarios/combined_stress.json
python -m life_insurance_lab benchmark --paths 200
python -m unittest discover -s tests -v
```

`monte_carlo.json`, `monthly_bands.csv` and `path_metrics.csv` are exported. Existing commands and API routes remain supported. The new route is `POST /api/monte-carlo`.

## Paper and calculations

- `paper/Yule_Furry_Monte_Carlo_Project.pdf`: focused submission paper; group/name/repository fields await your details.
- `paper/run_experiments.py`: reproduces the four 1,000-path experiments using the application engine.
- `paper/results/`: complete actual outputs, numerical summaries and CSV data.
- `paper/build_paper.py`: builds the graphs and paper from those recorded outputs.
- `paper/cover_details.json`: edit group name, member/roll strings and GitHub URL.
- `docs/MONTE_CARLO.md`: equations, estimators, limits and implementation mapping.
- `docs/DEMO_GUIDE.md`: short presentation sequence, viva questions and three-day preparation plan.
- `docs/SOURCE_NOTES.md`: method and historical provenance, outside the submission PDF.

To rebuild results, run `python paper/run_experiments.py`. To rebuild the PDF, first install optional dependencies with `python -m pip install -r paper/requirements.txt`, then run `python paper/build_paper.py`. The core application does not require those packages.

## Scope

All bundled assumptions are synthetic. Payment shortfall, modeled capital breach and regulatory solvency are distinct. Outcome percentiles are not confidence intervals for a mean. Zero observed shortfalls does not prove zero risk. Existing customers are simulated in cohorts, not individual real payment records. Grace notices, KYC, fraud/legal verification, reinsurance and portfolio allocation are future extensions; there is no real payment or investment execution.

Yule–Furry is the cumulative potential-acquisition model, not the active-policy count. Departed candidates still contribute to the mathematical arrival rate. Work and population caps abort an experiment as incomplete rather than silently truncate the model or discard costly paths.
