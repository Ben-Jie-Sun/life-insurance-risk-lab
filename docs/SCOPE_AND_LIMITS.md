# Scope and limitations — v0.2

This version implements the core mathematical plan plus a local backend. It can price contracts in either direction, assess fixed contracts, apply calendar stresses, compare capital levels, test analytical expectations, explain ledger entries, and persist inputs/results.

## 1. Computation limits

- Candidate count is guarded by `max_policies` (default 10,000, configurable up to 100,000). The first birth beyond the guard makes the path incomplete; the Yule law is not clipped.
- Contract term and acquisition period each have a maximum of 1,200 months.
- A path has a conservative bound of 5,000,000 candidate-policy-months. The Bernoulli-sum binomial sampler takes O(active policy count) work per cohort update.
- An experiment supports up to 40 scenario/capital cells, 1,000 paths per cell, and 5,000 total paths. A shared work budget of 50,000,000 limits experiments and benchmarks.
- A computation guard may reject a path that would actually be shorter after lapses or a stop-sale. Incomplete paths are not omitted from a risk estimate; the entire experiment stops.
- Money inputs and selected premiums/benefits are limited to 10^18 paise; available cash is guarded at that range. Pricing uses floating point, while posted cash amounts use integer paise. Extreme valuation or return draws are rejected if numerical representation fails.
- Backend request bodies are limited to 1 MiB and numeric JSON tokens to 80 characters. A server executes one calculation at a time. This is not a distributed job system.

## 2. Missing information

All supplied mortality, lapse, expense, acquisition and return parameters are synthetic. The project contains no calibrated life table, age/health underwriting data, real transaction histories, asset-price data, expense study, or reinsurance quotation.

Mortality/lapse arrays vary by policy duration. They do not identify a customer's actual age or medical profile. The increasing-mortality example is an invented duration curve for inspection, not an empirical age table.

More simulation paths reduce Monte Carlo error under the model; they do not fix inaccurate assumptions. The stored inputs and examples make these assumptions visible for later calibration.

## 3. Questions outside the logic

- Transaction legality, fraud, identity, and claim authenticity are not inferred. Stored configurations are mathematical inputs, not verified customer records.
- Public product release, legal contract wording, regulatory reserves/capital, and operational servicing are not modeled.
- The capital grid is a comparison of tested values. It does not prove globally optimal capital, minimum possible risk, or regulatory adequacy.
- Pricing to an expected margin does not control tail losses. Actual adverse paths and unpaid claims remain possible.
- Death events are conditionally independent across policies. Deterministic shared calendar shocks change probabilities but do not create stochastic common mortality dependence.
- Optional return volatility applies to one liquid aggregate fund. Separate cash/invested assets, liquidity constraints, credit risk, transaction costs, taxes, portfolio selection, and asset-liability management remain outside the model.
- Reserves retain a fixed original pricing basis during stress. They are not revalued best-estimate liabilities under updated information, and they do not use realized future random paths.
- The HTTP service is local, without multi-user authentication, authorization, public deployment, or real-payment functions.

## 4. Boundary behavior

| Boundary | Behavior |
|---|---|
| Zero initial Yule population | No future candidates; there is no immigration term |
| Zero birth rate or zero acquisition horizon | Only the initial policies issue |
| Zero benefit EPV factor b | Automatic premium-to-benefit pricing is undefined and rejected; a supplied benefit can be assessed or used for reverse pricing |
| Premium cannot fund positive cover and the target margin | Reject automatic benefit selection; fixed contracts can still be assessed as underfunded |
| Reverse pricing with zero modeled costs and benefits | Minimum positive premium is one paisa, consistent with this product's positive-premium requirement |
| Death probability one | All active policies die at the covered month-end; no survivor lapses are drawn |
| Lapse probability one | All survivors lapse at a nonfinal month-end after paying the current month's premium |
| Final covered month | Deaths incur claims; survivors expire with no maturity/surrender payment |
| Insufficient cash | Pay only available cash; retain the rest as explicit unpaid claims/expenses |
| First unpaid obligation | Stop later admissions; already issued policies continue through diagnostic runoff |
| Negative capital margin with no unpaid obligation | Record a breach; this diagnostic alone does not stop sales |
| Event outside the horizon or ambiguous overlapping overrides | Reject the scenario |
| Negative deterministic or random return | Reduce available cash; gross return must remain positive and there is no borrowing |
| Zero return volatility | Exactly recover the deterministic-return branch |
| Stale configuration revision | Reject the write; earlier run snapshots stay unchanged |
| Service stopped during a stored run | Mark the run interrupted when the owning server restarts |

There is no grace period, reinstatement, premium arrears on active policies, surrender value, maturity benefit, claim verification delay, or reinsurance. Every active policy pays its current premium. Expense and claim arrears do not accrue penalties or interest. Diagnostics occur at the modeled start/end monthly events and cannot establish all intramonth liquidity requirements.

Post-shortfall runoff is a diagnostic projection, not insurer insolvency administration. It assumes the remaining modeled premiums are collected and applies the stated settlement order; legal priorities and policyholder reaction to insurer distress are absent.

## Next extensions after inspection

1. Calibrated mortality/expense assumptions and tracked customer age.
2. An explicit grace, lapse and reinstatement contract model, updating pricing and reserves together.
3. Random shared mortality regimes with validated dependence.
4. Separate liquid cash and invested assets before a portfolio adapter.
5. Individual policy IDs and an idempotent transaction ledger before an AI Audit adapter.
6. A separately designed authentication/deployment layer if a public service is ever required.
