# Validation record

Validated under Python 3.12.14 with the standard library only.

- `python -m unittest discover -s tests -v`: **49 tests passed**.
- Original seed-2026 baseline preserved: 163 issued policies and INR 7,943,821.06 final net assets.
- Reverse pricing example: INR 1,000,000 cover requires a monthly premium of INR 1,109.39 under the supplied assumptions.
- Full professor demo completed: 12 scenario/capital cells × 100 paths = 1,200 complete paths, plus 200 paths for each analytical benchmark.
- Analytical Yule check at month 12: theoretical mean 143.33294; 200-path empirical mean 143.59. Sampling deviations are reported, not suppressed.
- All 19 generated HTML reports/indexes had their local links checked.
- Live local HTTP client saved inputs, quoted a contract, ran a simulation, downloaded its CSV, and checked its monthly trace.
- The live client edited the model from INR 1,000 to INR 1,200 monthly; the earlier run retained its INR 1,000 contract and input revision.
- Stopping and restarting the actual API server preserved the saved run. Exporting that persisted result through the CLI produced a report and trace successfully.
- The distribution archive was checked and a demonstration was run from a fresh extraction.

Core tests cover hand calculations, reserve recursion against independent path enumeration, probability boundaries, conservation, unpaid obligations, seed reproduction, fixed promises under stress, calendar shocks across cohorts, zero-volatility recovery, and numerical guards.

Backend tests cover real HTTP requests, input rejection, revision conflicts, immutable snapshots, optional persistence, interrupted/incomplete states, loopback-origin restrictions, and result exports.

These checks support implementation correctness under the stated model. They do not calibrate the assumptions, establish insurance legality, or certify solvency or investment performance.
