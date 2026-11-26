# Monte Carlo integration and mathematical interpretation

## One model, repeated experiments

`models/yule.py` samples exact pure-birth waiting times: at population n, the next waiting time is exponential with rate lambda*n. With N(0)=n0,

$$E[N(t)]=n_0e^{\lambda t},\qquad \operatorname{Var}(N(t))=n_0e^{\lambda t}(e^{\lambda t}-1).$$

Time and lambda use months. Arrivals in [k,k+1) are admitted at boundary k+1. Seeds enter at month 0. The acquisition window is [0,A); the final batch can enter at month A. Every admitted cohort then receives its M covered months; the total projection has A+M monthly rows (0 through A+M-1).

Cumulative candidates continue to grow independently of death/lapse. Active policies can fall. New admissions stop after the first unpaid obligation, but already admitted policies run off. Cumulative potential candidates remain recorded even when admission is stopped. This is why the Yule benchmark uses candidates, not issued or active policies.

## Monte Carlo estimators

For path j, let I_j=1 if an expense or death claim is ever unpaid at its scheduled payment point. For R paths,

$$\widehat p_R=\frac{1}{R}\sum_{j=1}^{R}I_j,\qquad E[\widehat p_R]=p,\quad \operatorname{Var}(\widehat p_R)=p(1-p)/R.$$

These statements assume independent identically distributed replications of the specified model. The program uses distinct deterministic seeds and separate hashed pseudo-random streams for acquisition, mortality, lapse and investment returns. A seed supports reproducibility; it is not a proof of physical randomness.

The displayed 95% Wilson interval, with z=1.959963984540054, is

$$\frac{\widehat p+z^2/(2R)\ \pm\ z\sqrt{\widehat p(1-\widehat p)/R+z^2/(4R^2)}}{1+z^2/R}.$$

For no observed events, the one-sided exact 95% upper bound is 1-0.05^(1/R). This is not zero.

For economic surplus S, the sample mean has estimated standard error s/sqrt(R). The returned mean interval uses a normal approximation; it can be poor for small samples or strongly skewed outcomes. The 5th and 95th percentiles describe the distribution of path outcomes. They are not 95% confidence limits for the mean.

`convergence` reuses prefixes of one experiment. It illustrates stabilization and changing estimated uncertainty; those points are correlated and do not establish a measured asymptotic convergence order. The usual R^(-1/2) rate is the theoretical sampling-error rate under finite variance.

## Supporting pricing and cash-flow model

Let s_k be the probability of an original policy still being active at the start of covered month k, q_k its monthly death probability, l_k its conditional lapse probability, and v=(1+i)^(-1).

$$s_0=1,\quad s_{k+1}=s_k(1-q_k)(1-l_k).$$
$$a=\sum_{k=0}^{M-1}s_kv^k,\quad b=\sum_{k=0}^{M-1}s_kq_kv^{k+1}.$$

With premium P, expense EPV E, benefit B and target margin m, expected margin is Pa-Bb-E. The premium-to-cover mode selects floor((Pa-E-m)/b) in paise. The benefit-to-premium mode selects ceil((Bb+E+m)/a) in paise. If b=0, automatic death-benefit pricing is undefined; fixed-cover assessment remains possible. Stress changes experience without repricing the promise.

The reserve recursion uses V_M=0 and

$$V_k=e_k-P+v\{q_k B+(1-q_k)(1-l_k)V_{k+1}\}.$$

It is a supporting discrete valuation calculation, not a separate differential-equation research study. The cash ledger applies the positive reserve floor and upward per-policy rounding for the modeled capital test.

Cash is non-negative. Unpaid obligations are carried explicitly. Net assets equal cash minus unpaid claims and expenses; final economic surplus equals final net assets minus starting capital. It includes earnings on starting capital and is not an annual return. A capital breach means net assets minus positive reserves minus the configured buffer is negative; it is not the same as an unpaid obligation.

At every monthly row the engine checks:

- Cash = starting capital + collected premiums + interest - expenses paid - claims paid.
- Net assets = starting capital + premiums + interest - expenses incurred - claims incurred.
- Issued policies = active + cumulative deaths + cumulative lapses + cumulative expiries.

## Integration

`monte_carlo.run_monte_carlo` calls the existing `simulate` engine R times. It aggregates monthly counts and financial outcomes, terminal path metrics, risk intervals and a Yule moment comparison. `Service.execute('monte_carlo', ...)` resolves saved/inline inputs and records completed or incomplete status. The dashboard calls `POST /api/monte-carlo` and displays the returned summaries.

## Computational and modelling boundaries

- 2–1,000 paths per Monte Carlo request; at most 500,000 path-month observations and 50 million policy-month work budget, plus existing per-path guards.
- A limit aborts the whole request. No successful subset is reported as a completed unbiased experiment.
- Exact event times do not make monthly admission and cash-flow timing continuous.
- Fixed monthly death/lapse draws are ordered competing risks, not simultaneous continuous-time hazards.
- Mortality multipliers act as q_stress=1-(1-q)^h, not h*q without a probability cap.
- Zero population cannot grow without immigration. Large lambda*A gives computational and modelling problems.
- Constant/selected duration probabilities omit individual age, health, geography and common shocks. Dated stress scenarios are specified paths, not a fitted epidemic model.
- Few observed failures leave considerable rare-event uncertainty. More simulations cannot repair missing information or a wrong transition model.
