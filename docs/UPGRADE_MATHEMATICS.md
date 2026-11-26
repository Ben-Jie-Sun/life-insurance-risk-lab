# v0.2 model extensions and their correctness obligations

The baseline equations are in `MATHEMATICS.md`. These additions preserve the original contract timing: start-of-month premiums and expenses, interest on remaining cash, end-of-month deaths and then survivor lapses/expiry, and settlement of claims. All probabilities and rates below are monthly.

## Reverse pricing and fixed contracts

With the original factors a, b, and E, the expected margin is p a − B b − E. Solving for the premium instead of the benefit gives:

$$p^* = \frac{B b + E + m}{a}.$$

The current expense assumptions do not depend on p. Since the first premium is due immediately and the policy starts active, a ≥ 1. The premium is rounded upward to whole paise; the premium-led benefit is rounded downward. A positive premium is required even for a degenerate fixed-benefit example with zero modeled mortality and zero costs.

The quote returns both the selected premium and selected benefit. `resolved_policy` freezes those terms. Experience changes affect outcomes, not the already selected promise. Assessment mode reports an inadequate expected margin rather than silently modifying the contract.

These modes can be checked with a one-month hand example: B = INR 5,000, q = 0.1, no interest, expenses INR 30, margin INR 70. Then the required premium is INR 600. A test independently checks that contract and its first premium posting.

## Calendar time versus policy duration

For a cohort issued at month j, its duration at calendar month t is k = t − j. Base q_k and lapse l_k are indexed by duration. The scenario engine selects a calendar-time condition and applies it to every active cohort at t.

A stress window `[start_month, end_month)` includes the start and excludes the end. Global assumptions apply unless a window explicitly overrides that field. Overlapping windows that specify the same field are rejected to avoid order-dependent behavior.

For mortality multiplier s_t > 0, the stressed death probability is:

$$q_{k,t}^{stress}=1-(1-q_k)^{s_t}.$$

To derive this, write the original monthly cumulative hazard as h_k = −log(1−q_k). Multiplying it by s_t changes survival to exp(−s_t h_k) = (1−q_k)^{s_t}. The resulting death probability stays within [0,1]. The code uses `log1p` and `expm1` for small-probability accuracy and handles q = 0 and q = 1 explicitly.

For each cohort, deaths remain Binomial(n, q_stress); survivor lapses use the applicable conditional lapse probability. At final expiry, surviving policies expire instead of lapsing. The partition and count-conservation arguments therefore continue to hold.

A deterministic mortality stress shared across cohorts does not by itself create random dependence between individual deaths. Random common mortality regimes are future work.

## Optional return volatility

Let r_bar > −1 be the expected monthly return, sigma ≥ 0 the monthly log-return standard deviation, and Z_t independent standard normal draws. The model is:

$$1+r_t=\exp\left(\log(1+\bar r)-\frac{\sigma^2}{2}+\sigma Z_t\right).$$

Because E[exp(sigma Z)] = exp(sigma²/2), E[1+r_t] = 1+r_bar. Gross return is positive, and sigma = 0 recovers the configured deterministic rate exactly through an explicit code path.

There is a separate seeded random stream for returns. Enabling it does not consume acquisition, mortality, or lapse random draws. Finite-precision overflow or a numerically unrepresentable gross return makes the run incomplete instead of silently clipping an extreme outcome.

This is one liquid aggregate fund, not a portfolio with a separate cash account. It assumes immediate liquidity, no transaction costs, no default, and no investment restrictions. Its parameters are synthetic, and its independent lognormal increments do not describe all forms of market stress.

## Reserves under stress

The reserve recursion retains the **original pricing mortality, lapse, expense, and discount basis**, using the fixed selected premium and benefit. Calendar experience shocks and realized asset-return draws do not enter that reference recursion.

This is deliberate: it prevents a stress experiment from repricing contracts, and it avoids using future realized random returns as if they were known in advance. The output identifies its reserve basis explicitly. A stress-revalued best-estimate liability or regulatory capital calculation is not implemented.

In particular, the baseline's nonpositive policy values are floored at zero. This does not eliminate its possible future claims or justify zero risk capital.

## Capital grid and statistical summaries

Every scenario/capital cell uses the same selected contract and the same seed sequence. Different exposure paths may consume different numbers of mortality/lapse draws; shared seeds do not imply the same individual policy outcomes after paths diverge.

Per cell, the project records mean and median surplus, a linearly interpolated empirical 5th percentile, shortfall and capital-breach fractions with Wilson intervals, and per-path severity. Maximum unpaid obligations include both claims and expenses. Minimum capital margin includes the opening buffer position and subsequent month-end diagnostics.

These are grid comparisons, not a continuous optimization. A positive mean does not bound tail losses, and a small number of paths cannot establish a rare-event probability precisely. No comparison is completed after silently dropping a path that hit a computation guard.

## Analytical benchmark

The acquisition benchmark compares simulation means with n0 exp(lambda t), and reports the theoretical variance n0 exp(lambda t)(exp(lambda t)−1).

The policy benchmark uses only the initial cohort, with no subsequent admissions and no experience shocks. It therefore has:

$$E[A_k]=n_0\alpha_k,$$

$$E[Premium_k]=p n_0\alpha_k,$$

$$E[ClaimsIncurred_k]=B n_0\alpha_k q_k.$$

Claims incurred are used because claims paid can be constrained by cash. A fixed initial cohort is not affected by the later stop-sale rule. The cohort's total expected policy margin EPV is n0 times the priced per-policy margin, excluding returns on company capital.

Welford's method accumulates sample means and sample variances. The displayed mean intervals use mean ± 1.96 × standard error; they are approximate pointwise intervals. They are not simultaneous confidence bands, and zero observed rare claims can produce an uninformative zero empirical standard error. No numerical deviation is labeled a formal proof of error or correctness.

## Stored trace and backend invariants

A trace reconstructs arithmetic from the stored monthly row rather than resimulating a path. It checks premiums, maintenance/acquisition expenses, rounded interest, claims, outstanding balances, cash, net assets, capital margin, and policy conservation.

A stored run captures all resolved configuration defaults, source configuration IDs/revisions, scenario definitions, seed, and application/Python versions. Subsequent configuration edits do not change its snapshot. SQLite transactions make each document update and its revision record atomic. Updates and deletes require the version read by the caller; stale writes are rejected.

A computation that exceeds a budget is recorded as incomplete; an abandoned running computation is marked interrupted on server restart. Neither is counted as a successful zero-loss path.
