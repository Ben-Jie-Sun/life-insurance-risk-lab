MATHEMATICAL MODELLING / COURSE PROJECT

Yule-Furry Acquisition and Monte Carlo Risk Analysis

A cohort-based life-insurance laboratory

Code and reproducible results

GitHub: __________________________________________________

Mathematical Modelling

Project overview

Yule-Furry supplies the acquisition process inside each simulation path. Monte Carlo repeats the complete insurance model. Pricing, reserves, policy states, stress scenarios and storage support these two main methods.

One integrated experiment

The same configuration and monthly cash-flow engine are used in the dashboard, the command-line interface and the numerical results in this paper. The pure-birth process describes cumulative potential candidates; it does not describe the surviving insured population.

Summary and numerical assumptions

This project studies the funding risk of a growing book of term-life contracts. Potential policy arrivals follow a Yule-Furry pure-birth process. Monthly cohorts track premium payments, death, lapse and scheduled expiry. Monte Carlo simulation estimates the chance of an unpaid obligation and the distribution of financial outcomes. Exact Yule moments and accounting identities provide checks independent of the risk estimate. All numerical inputs are synthetic.

Input | Baseline specification
Acquisition | 100 initial candidates; lambda = 0.03 per candidate per month; 12-month acquisition window
Contract | 36 covered months per admitted policy; no maturity or surrender benefit
Premium and death cover | INR 1,000 per month; calculated death benefit INR 890,283.83
Probabilities | Monthly death probability 0.001; lapse probability 0.005 among survivors before the final month
Expenses and margin | INR 80 monthly expense; INR 500 at issue; target pricing-basis EPV margin INR 500 per policy
Interest and capital | Valuation and expected asset return 0.003 per month; initial capital INR 5,000,000; modeled buffer INR 500,000
Simulation | 48 calendar months including run-off; 1,000 paths per scenario; seeds 2026 through 3025
Computational guard | Maximum 10,000 candidates per path in the baseline; exceeded guards abort rather than truncate

Variants and principal findings

The lower-capital case uses INR 1,000,000 with all other inputs unchanged. The mortality shock multiplies the implied mortality hazard by three in calendar months 8, 9 and 10. The combined stress also replaces the asset return by -2% in those months. Existing premium and benefit promises remain fixed.

Case | Shortfall paths / 1,000 | Estimated probability
Baseline | 11 | 1.10%
Lower capital | 469 | 46.90%
Mortality shock | 27 | 2.70%
Combined stress | 33 | 3.30%

These are finite-sample results for the stated model, not observed insurance-company failure rates. Confidence intervals and the distinction between cash shortfall and capital breach are reported below.

1. Yule-Furry acquisition model

State and event mechanism

Let N(t) be the cumulative potential-acquisition population, starting at n0. Each member contributes the same birth rate lambda. At state n, the next event increases the population to n+1 and has exponential waiting time with rate lambda*n. Departures from insurance do not reduce N. The model therefore represents a continuing acquisition network rather than referrals only from active policyholders.

$$
q_{n,n+1}=\lambda n,\qquad \tau_n\sim\operatorname{Exp}(\lambda n)
$$

First and second moments

For a function f, the generator is Lf(n)=lambda*n[f(n+1)-f(n)]. Taking f(n)=n and f(n)=n squared gives equations for m(t)=E[N(t)] and u(t)=E[N(t) squared].

$$
m^{\prime}=\lambda m,\qquad u^{\prime}=2\lambda u+\lambda m
$$

Solving with m(0)=n0 and u(0)=n0 squared yields the following benchmarks.

$$
E[N(t)]=n_0e^{\lambda t},\qquad \operatorname{Var}(N(t))=n_0e^{\lambda t}(e^{\lambda t}-1)
$$

Exact events, monthly admission

The simulator samples a waiting time, moves the event clock forward, increments the population and repeats until the acquisition horizon. Births occurring in [k,k+1) are scheduled for admission at boundary k+1. Initial policies enter at month zero. The event process is simulated without a time-step approximation; admission and financial cash flows are deliberately monthly.

Correctness and boundary cases

The exponential holding time and unit jump match the prescribed generator. The sum of reciprocal birth rates diverges, so the linear pure-birth process is non-explosive for finite initial population and rate. This mathematical property is not a practical runtime bound: expected population grows exponentially. If n0=0 or lambda=0, no new births occur. The program records an incomplete experiment if its population or work guard is reached; it never reports a silently capped Yule trajectory.

Potential candidates, admitted policies and active policies are separate quantities. After a payment shortfall, admissions cease, although the potential-acquisition process remains recorded. Already issued policies continue to death, lapse or expiry.

2. Policy and financial calculations

Premium-to-cover valuation

Let s_k be the probability of being active at the start of covered month k, q_k the monthly death probability, l_k the lapse probability conditional on survival, and v=1/(1+i) the monthly discount factor. Premiums and expenses occur at month-start; claims occur at month-end.

$$
s_0=1,\quad s_{k+1}=s_k(1-q_k)(1-l_k),\quad a=\sum_{k=0}^{M-1}s_kv^k,\quad b=\sum_{k=0}^{M-1}s_kq_kv^{k+1}
$$

With premium P, benefit B, expense EPV E and target margin m, the pricing condition is Pa-Bb-E=m. For a fixed premium, the selected benefit is rounded downward to the nearest paise. For a fixed benefit, the required premium is rounded upward.

$$
B=\left\lfloor\frac{Pa-E-m}{b}\right\rfloor_{\rm paise},\qquad P=\left\lceil\frac{Bb+E+m}{a}\right\rceil_{\rm paise}
$$

For the baseline, a=30.884190, b=0.03079181, and E=INR 2,970.74. A monthly premium of INR 1,000 gives benefit INR 890,283.83 and expected margin approximately INR 500. These are valuation expectations per issued policy; they do not determine a pathwise funding guarantee.

Policy states and monthly ledger

For each cohort, deaths are drawn first. Lapses are drawn among the remaining survivors except in the final covered month, when survivors expire. Death triggers the agreed claim; lapse and expiry produce no benefit in this term-life contract. This ordered monthly model is not a simultaneous continuous-time competing-risks model.

Available cash pays expenses, earns the scenario return and then pays claims. Unpaid amounts remain explicit liabilities. New admissions stop after the first unpaid obligation, while existing policies run off. Cash is never made negative to simulate fictitious financing.

Reserve and capital check

$$
V_M=0,\quad V_k=e_k-P+v\{q_kB+(1-q_k)(1-l_k)V_{k+1}\}
$$

Reserves remain on the original pricing basis under stress. For the modeled capital test, each positive per-policy reserve is rounded upward. A capital breach occurs when cash minus unpaid obligations minus this reserve requirement minus the configured buffer is negative. A payment shortfall instead means an obligation was unpaid when due.

The ledger uses integer paise for money movements and verifies both cash and obligation identities after every month. Expected values and reserve calculations use floating-point arithmetic.

3. Monte Carlo risk estimation

Replicate the complete model

For each of R paths, the program generates a candidate schedule, admits cohorts, runs the monthly ledger to complete run-off and records whether any payment was missed. It uses seeds 2026+j for j=0,...,R-1, with separate deterministic pseudo-random streams for acquisition, mortality, lapse and returns. No new cash-flow model is introduced by the Monte Carlo wrapper.

$$
I_j=\mathbf{1}\{\text{path }j\text{ has an unpaid obligation}\},\qquad \widehat p_R=\frac{1}{R}\sum_{j=1}^{R}I_j
$$

Correctness of the estimator

Under independent identically distributed replications of the specified model, E[I_j]=p. Linearity gives E[p-hat]=p, independence gives Var(p-hat)=p(1-p)/R, and the strong law gives convergence to p. Distinct pseudo-random seeds implement reproducible sampling; these probabilistic conclusions are conditional on the modelling and random-number assumptions.

$$
E[\widehat p_R]=p,\qquad \operatorname{Var}(\widehat p_R)=\frac{p(1-p)}{R}
$$

Confidence intervals and outcome ranges

A naive normal interval can collapse when there are no observed failures. The reported probability interval is the 95% Wilson interval, with z=1.959963984540054.

$$
\frac{\widehat p+z^2/(2R)\ \pm\ z\sqrt{\widehat p(1-\widehat p)/R+z^2/(4R^2)}}{1+z^2/R}
$$

If no events occur, the exact one-sided 95% upper bound is 1-0.05^(1/R), derived from the probability (1-p)^R of seeing no events. Zero observations do not prove zero risk. For a sample mean, the estimated standard error is s/sqrt(R); its displayed interval uses a normal approximation.

$$
\overline{S}=\frac{1}{R}\sum_{j=1}^R S_j,\qquad \widehat{\operatorname{SE}}(\overline{S})=\frac{s_S}{\sqrt{R}}
$$

The monthly 5th-to-95th percentile band describes the spread of path outcomes, not confidence limits for a mean. Prefix convergence points reuse earlier samples and are correlated. They illustrate stabilization rather than independently measuring an asymptotic convergence order.

No selective acceptance of paths

The ensemble has a 1,000-path limit, a 500,000-observation limit and a 50-million policy-month work budget, in addition to per-path guards. A guard aborts the experiment and records incomplete status. A successful subset is never presented as the completed sample.

4. Population results and verification

Figure 1. Baseline monthly candidate and active-policy distributions from 1,000 paths. Shading shows empirical outcome percentiles; it is not a confidence band for the mean. Candidate growth ends after the acquisition window while admitted policies continue to run off.

At month 12 | Exact Yule model | Simulation
Candidate mean | 143.332941 | 143.733000
Candidate variance | 62.110380 | 61.295006
SE of sample mean | 0.249220 | Based on exact variance

The mean difference is 0.400059 candidates, or 1.605 exact standard errors. This is a sampling discrepancy under the selected seeds; it is not evidence that the arrival mechanism has been calibrated to real customers.

Why the two population curves differ

Cumulative candidates never decrease, while active policies leave by death, lapse and scheduled expiry. Candidate generation ends after month 12, but the final admitted cohort may remain covered through month 47. All admitted policies have left by the final month. The stop-sale rule can also prevent some candidates from becoming policies.

Scope of the analytical check

The exact formula checks the potential-acquisition component independently of downstream cash flow. It does not validate mortality, lapse or investment assumptions, and it does not provide an exact mean formula for active exposure under the state-dependent stop-sale rule. Policy conservation is checked directly on every simulated path.

5. Capital and stress results

Figure 2. Four experiments with 1,000 paths each. Left: shortfall estimates and 95% Wilson intervals. Right: mean economic surplus with approximate normal 95% intervals. Economic surplus includes earnings on initial capital; it is not an annualized return.

Case | Shortfall | 95% Wilson interval | Mean surplus (INR)
Baseline | 1.10% | 0.62% - 1.96% | 1,010,493.45
Lower capital | 46.90% | 43.82% - 50.00% | 404,816.08
Mortality shock | 2.70% | 1.86% - 3.90% | 289,762.54
Combined stress | 3.30% | 2.36% - 4.60% | -88,202.08

Expected performance and funding risk

The lower-capital experiment has positive mean final economic surplus but an estimated 46.9% chance of an interim payment shortfall. A positive average terminal outcome therefore does not guarantee that all obligations can be paid on time. Lower capital also changes investment earnings and may change admissions after stop-sale.

Experience stresses preserve the contract

The mortality shock uses q_stress=1-(1-q)^3 in months 8-10. This multiplies the implied mortality hazard and keeps probabilities valid. Combined stress additionally applies a -2% monthly asset return in the same interval. The premium and death benefit are fixed at their original quoted values.

Each case uses the same seed sequence and separate streams, which supports comparable experiments. These are marginal confidence intervals, not formal paired tests of differences. The scenarios are prescribed stresses, not forecasts of pandemics or market crises.

6. Sampling uncertainty and interpretation

Figure 3. Left: shortfall estimates as more paths from the same sample are included; shading gives Wilson intervals. Right: distribution of baseline final economic surplus. The prefix points are dependent, and a narrow mean interval does not imply a narrow distribution of outcomes.

What additional paths resolve

Increasing R reduces sampling uncertainty under a fixed model. The theoretical standard error of a sample mean decreases as R to the power -1/2 when the variance is finite. Approximately four times as many paths are needed to halve that error. More simulation does not repair incorrect mortality assumptions, omitted dependence or missing policy data.

Case | Mean surplus SE (INR) | Modeled capital-breach fraction
Baseline | 64,103.99 | 2.10%
Lower capital | 61,872.25 | 64.90%
Mortality shock | 68,666.91 | 4.10%
Combined stress | 67,273.18 | 4.80%

Three quantities that must be separated

Outcome variability is the spread across policy-book futures. Sampling error is uncertainty in an estimated mean or probability caused by using finitely many futures. Model error is the discrepancy between the specified transition/cash-flow assumptions and real behaviour. The percentile band, confidence interval and scenario limitations address these different questions.

After the first shortfall

The engine continues collecting modeled premiums and settling obligations during run-off so that outstanding liabilities remain visible. This continuation is a diagnostic projection, not a legal insolvency-administration process. Its final surplus should be read together with the indicator of whether a payment shortfall occurred.

7. Implementation and validation

Module | Role in the integrated system
models/yule.py | Exact arrival waiting times and analytical candidate moments
models/policy.py + simulation.py | Cohorts, monthly events, stop-sale, run-off, cash and unpaid obligations
actuarial.py + scenarios.py | Fixed-contract pricing, discrete reserves and dated experience stresses
monte_carlo.py | Repeated full paths, percentile bands, risk intervals and moment checks
backend/service.py + storage.py | Validated requests, SQLite snapshots, versioned models and completion status
web/ + CLI | Local dashboard, parameter entry, recorded outputs and CSV/JSON exports

Conservation identities

The following identities are checked in every monthly step, using integer-paise cash movements. Failures raise an error rather than silently accepting an inconsistent path.

$$
C_t=C_0+\sum_{k\leq t}(P_k+J_k-E_k^{\rm paid}-K_k^{\rm paid})
$$

$$
A_t^{\rm net}=C_0+\sum_{k\leq t}(P_k+J_k-E_k^{\rm incurred}-K_k^{\rm incurred})
$$

$$
N_t^{\rm issued}=N_t^{\rm active}+D_t+L_t+X_t
$$

Here P denotes premiums, J investment earnings, E expenses, K claims, and D, L, X cumulative death, lapse and expiry counts. Net assets also equal cash minus unpaid expenses and claims.

Automated verification

The suite contains 55 passing checks: the 49 existing checks plus six Monte Carlo integration tests. They cover agreement with direct calls to the original simulation engine, deterministic cash-flow and certain-claim cases, nonzero uncertainty after zero observed failures, reproducible seeds, saved-run replay, incomplete-run recording, HTTP responses and CSV exports. Validation covers the model and HTTP interfaces; an interactive browser walkthrough remains a separate acceptance check.

Reproducibility

The four experiments are generated by paper/run_experiments.py, using the same baseline configuration and scenario files as the application. Each contains 1,000 paths with seed range 2026-3025. Complete path metrics and monthly bands accompany the paper. The application requires Python 3.10 or later and uses no third-party runtime packages; plotting and PDF generation have optional dependencies.

8. Applications, boundaries and next steps

Connection to real-world problems

Premium setting and long-term expected profitability do not by themselves answer whether a growing portfolio can meet every payment. This laboratory links acquisition, policy exits and payment timing, making that funding question explicit. It can support classroom stress comparisons and development of the ongoing insurance application.

The COVID-19 mortality shock illustrates why baseline mortality must be challenged. WHO documented substantial excess mortality in 2020-2021. The present dated multiplier examines one financial consequence of elevated mortality; it does not represent epidemic transmission, common-shock dependence or regional exposure.

The Bank of England documented collateral calls and forced gilt sales in the UK pension-sector LDI episode in 2022. It illustrates the difference between long-term funding and immediate liquidity. The current cash-shortfall metric addresses payment timing, but excludes leverage, collateral and forced-sale feedback. These events motivate stress analysis; they were not calibrated or reconstructed here.

Questions partially answered

Practical question | Answer within this model
Does acquisition growth equal insured exposure? | No: exits, expiry and stopped admissions separate candidates from active contracts.
Can positive mean surplus coexist with missed payments? | Yes: the lower-capital experiment exhibits both.
Can a computed probability be trusted exactly? | No: finite sampling requires intervals; model uncertainty remains.

Boundaries

Computation: exponential growth and rare shortfalls can require costly samples. Information: synthetic rates omit age, health and region-specific calibration. Model structure: prescribed stresses, conditional independent policy events and one liquid aggregate investment fund omit important common risks. Boundary cases: zero population requires immigration to restart growth; automatic death-cover pricing is undefined with zero death-benefit EPV; infeasible premium/expense combinations and numerical overflows must be rejected.

Future capabilities

The next development is a validated policy/payment record layer with explicit issue dates, cover status and maturity dates. Then add calibrated age/region schedules, common mortality shocks, reinsurance and asset-liability scenarios. Existing random-return and dated-stress features provide starting points. AI Audit could flag inconsistent payment records for human review, while a portfolio module could test investment constraints; neither integration is present here, and anomaly flags would not establish fraud or legal compliance.
