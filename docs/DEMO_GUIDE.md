# Three-day preparation and demonstration

## Day 1: submit and understand the focused paper

Add the group names, roll numbers and repository link to paper/cover_details.json, then rebuild the PDF if desired. Read the summary, Yule mechanism and Monte Carlo estimator sections first. Be able to distinguish candidate count, issued count and active count. The paper's numerical results come from this exact program, not the earlier independent 500-policy study.

## Day 2: rehearse a complete run

Start with `python run_server.py` and open http://127.0.0.1:8000.

1. Select baseline and press Price contract: INR 1,000 monthly premium gives INR 890,283.83 death cover under the synthetic assumptions.
2. Run one path. Point out death, lapse, expiry, premiums, incurred claims, unpaid obligations and net assets.
3. Run 200 Monte Carlo paths. Explain that one path cannot estimate failure probability.
4. Use 1,000 paths and seed 2026 to reproduce the paper baseline: 11 shortfall paths (1.1%).
5. Change starting capital from INR 5,000,000 to INR 1,000,000, retaining seed and all other assumptions: 469/1,000 shortfalls (46.9%).
6. Restore baseline capital, choose mortality_shock: 27/1,000 (2.7%); combined_stress: 33/1,000 (3.3%). Show the intervals, not only the percentages.
7. Open Saved runs. View a previous result, load its inputs, and download JSON or CSV. Original assumptions remain attached to each result.

The program is pseudo-random and deterministic for fixed inputs/seeds in the recorded Python environment. Numeric-library/runtime differences can matter; keep the versioned paper/results outputs as the submission record.

## Day 3: verify and practise questions

Run `python -m unittest discover -s tests -v`. Rehearse on the actual demonstration laptop. Keep a copy of the provided result files and PDF for use if the browser or server cannot be started during the presentation. Avoid adding new product features immediately before the deadline.

## Short viva answers

**Why Yule–Furry?** It is a tractable pure-birth model: n cumulative candidates generate arrivals at rate lambda*n, with exact moments available for verification. It is an illustrative acquisition mechanism, not a universal law of customer behaviour.

**Why Monte Carlo?** Funding failure depends on an entire random cash-flow path. Repeating the model estimates how often the event occurs and how uncertain the estimate is.

**Are they two competing models?** No. Yule is inside each simulation path; Monte Carlo repeats the whole system.

**Does Yule model deaths?** No. Death and lapse are separate conditional monthly transitions among active policies.

**Why not use the Yule mean as active exposure?** Cumulative candidates include people who exited or were never admitted after stop-sale. Active exposure is tracked by issue cohort and policy duration.

**Does a profitable average guarantee enough cash?** No. The low-capital experiment has a positive mean final economic surplus and frequent interim shortfalls.

**What does the shaded band mean?** It is the empirical 5th-to-95th percentile range of outcomes. The Wilson interval instead describes uncertainty in an estimated probability.

**What if zero shortfalls occur?** Risk is not proven zero; report the upper confidence bound.

**What is expiry?** Scheduled end of coverage with no maturity payout in this term-life model. Lapse is early exit; death triggers the agreed benefit.

**What are the supporting contributions?** Premium/benefit quotation, reserve recursion, cash/obligation accounting, dated stress scenarios, deterministic replay, SQLite history, CSV exports and the dashboard.

**What is not implemented?** Real customer billing, grace notices, state-calibrated actuarial tables, KYC/fraud decisions, public underwriting, portfolio allocation and real investment execution.
