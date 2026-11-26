# v0.3 validation record

The original v0.2 validation notes are retained in VALIDATION_V2.md. The following checks were performed on the Yule–Furry + Monte Carlo update:

- `python -m unittest discover -s tests -q`: **55 passing tests** (49 original and 6 new integration tests).
- New ensemble output matches direct calls to the existing simulation engine with the same seeds, including every monthly active-population mean.
- Deterministic cash flow matches a hand-calculated result; certain claims produce shortfall on every path.
- Zero observed failures retain a positive probability upper bound.
- Invalid path counts and observation limits are rejected; a failed path aborts the whole experiment and records `incomplete` without partial results.
- SQLite snapshots round-trip through JSON and replay the same result.
- Actual localhost HTTP requests serve the dashboard and script, run Monte Carlo, and download correctly sized monthly-band and path-metric CSV exports.
- `node --check life_insurance_lab/web/app.js`: JavaScript syntax passes.
- The four paper cases completed with 1,000 paths each using the unchanged application simulation engine. Full results and seeds are retained in paper/results.
- All 11 paper pages were rendered and visually inspected, including the diagram and six chart panels.

A complete interactive browser walkthrough was **not** completed in the authoring environment: the browser runtime could not access the local application, and the local browser binary was unavailable. Rehearse the dashboard on the demonstration laptop using DEMO_GUIDE.md. HTTP checks are not a substitute for browser acceptance testing.

Model correctness under these synthetic inputs does not establish real-world calibration, solvency, legal compliance or investment performance.
