# Professor demonstration guide

## Prepare before the meeting

Run `python run_demo.py` once and open `outputs/demo/index.html`. The supplied `sample_output/index.html` is a ready-made fallback. The prepared sample uses 100 paths per capital/scenario cell and 200 paths per benchmark; it is not a rare-event certification.

For a backend demonstration, start `python run_server.py` in one terminal and run `python api_demo.py` in another. Keep the API terminal open. All examples run without internet access or external packages.

## A 10–12 minute presentation

| Time | Show | Explain |
|---|---|---|
| 0–2 min | Baseline quote and Yule benchmark | Yule creates acquisition candidates; active policies can exit. Theoretical mean is n0 exp(lambda t). |
| 2–4 min | Premium-led and cover-led quotes | Derive p a − B b − E = m. Solve for either p or B. Distinguish expected margin from actual profit. |
| 4–6 min | Baseline report and its explained month | Trace premiums, expenses, interest and one claim. Show cash and policy conservation. |
| 6–8 min | Mortality/combined stress report | The same issued promise is exposed to different calendar conditions. Explain duration versus calendar month. |
| 8–10 min | Capital grid and benchmark | Compare shortfall fraction, uncertainty and severity. Show why a mean surplus does not guarantee adequate cash. |
| 10–12 min | API demo or saved request/result | Enter a model, store a run, edit the model, and show the earlier result remains unchanged. |

## Questions to be ready for

**Why use a pure-birth process when insured people can die?**

The pure-birth process models cumulative acquisition candidates. Mortality and lapse belong to a separate finite-duration policy process. Growth does not mean policies remain active forever.

**Why does lambda not appear in the individual pricing formula?**

Under homogeneous linear expected cash flows, a single policy's factors depend on its own probabilities, expenses and timing. Lambda changes aggregate exposure and company cash-flow outcomes.

**Why can INR 1,000 monthly support much larger death cover?**

The benefit is contingent on a covered death, and risks are pooled across policies. Not everyone receives it. Initial capital supports early and unexpectedly clustered claims.

**Why are baseline reserves zero?**

The baseline's future net expected policy outgo is nonpositive and the project floors negative values at zero. That expected-value result does not remove possible future claims or capital risk.

**Why is stress not changing the benefit?**

The benefit is a fixed contract promise. A stress changes experience. Repricing the promise during the experiment would compare different contracts.

**Are stressed reserves updated?**

No. This version explicitly keeps the original pricing basis for reference reserves. It is not a regulatory or stress-revalued capital model.

**Do deterministic mortality shocks create correlated deaths?**

No. They change the probabilities shared across cohorts at that calendar time. A random common regime would be needed to model that additional dependence.

**Does zero observed failure prove safety?**

No. For zero failures in R independent model paths, the exact one-sided 95% upper bound is 1 − 0.05^(1/R). Assumption error is separate from simulation uncertainty.

**What proves the algorithm is correct?**

State the model first, derive its pricing/reserve equations, compare known expectations against simulation, and show exact ledger/count invariants. Tests verify implementation cases; they do not prove the assumptions represent actual insurance experience.

**What does the backend add mathematically?**

It does not alter the equations. It provides validated input entry, versioned assumptions, reproducible run snapshots, optional persistence, and retrieval/export for experiments.

## Boundary demonstration

Open the guaranteed-shortfall example. One customer pays INR 1,000, expenses consume INR 580, and a claim of INR 100,000 occurs. Only INR 420 can be paid; INR 99,580 remains owed. Show that the ledger never labels the unpaid amount as a successful payment.

## Safe scope statement

This is a synthetic course model with an implemented local backend. AI Audit, actual customer transactions, calibrated underwriting, portfolio optimization, grace/reinstatement rules and public deployment are future stages.
