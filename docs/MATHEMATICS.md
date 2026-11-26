# Mathematics and correctness notes

These derivations describe the baseline model. See UPGRADE_MATHEMATICS.md for the v0.2 pricing, scenario and backend extensions. Correctness means implementing these stated stochastic and accounting rules. It does not mean the assumptions describe an actual insurer.

## 1. Yule–Furry acquisition

Let N(t) be the cumulative candidate population, with N(0) = n₀. Each member independently creates a new candidate at rate λ per month. The aggregate transition intensity from n to n + 1 is λn. Candidate members never leave this acquisition process; policyholders can leave the separate policy process.

For a short interval h:

$$
\Pr(N(t+h)=n+1\mid N(t)=n)=\lambda n h+o(h).
$$

While the population is n, no birth for u months has probability exp(−λnu), so the next holding time is exponential with rate λn. `issue_schedule` samples this holding time, increments the population, and repeats. This is an event-driven simulation of the specified pure-birth process, subject to floating-point arithmetic and pseudorandom sampling.

For λ > 0, the sum of mean holding times, Σₙ 1/(λn), diverges. The pure-birth non-explosion criterion therefore rules out infinitely many births in finite time. Finite-time samples can nevertheless be too large to compute; non-explosion is not a runtime guarantee.

The generator is Lf(n) = λn[f(n+1) − f(n)]. Applying it to f(n) = n gives:

$$
\frac{d}{dt}\mathbb E[N(t)] = \lambda\mathbb E[N(t)],
\qquad \mathbb E[N(t)] = n_0e^{\lambda t}.
$$

Applying it to f(n) = n² gives m₂′ = 2λm₂ + λm₁. Solving and subtracting m₁² yields:

$$
\operatorname{Var}(N(t)) = n_0e^{\lambda t}(e^{\lambda t}-1).
$$

For n₀ ≥ 1, the finite-time distribution is negative binomial:

$$
\Pr(N(t)=n)=\binom{n-1}{n_0-1}p^{n_0}(1-p)^{n-n_0},
\quad p=e^{-\lambda t},\quad n\ge n_0.
$$

For n₀ = 0, N(t) stays zero. For λ = 0, it stays n₀. There is no immigration term.

The continuous birth times are preserved for candidate generation. A birth in [k, k+1) is issued at the boundary k+1; the n₀ initial contracts issue at boundary 0. This is an explicit monthly issue convention. It does not claim to pay premiums or cover mortality at the exact continuous birth time.

## 2. The policy process

Each contract has M covered months. At the beginning of policy month k it is either active A, lapsed L, or already dead D. Set:

- qₖ = probability of death during month k, conditional on being active at its start;
- ℓₖ = probability of lapse at its end, conditional on surviving that month.

Before term expiry, the transition matrix in order (A, L, D) is:

$$
P_k=\begin{pmatrix}
(1-q_k)(1-\ell_k)&(1-q_k)\ell_k&q_k\\
0&1&0\\
0&0&1
\end{pmatrix}.
$$

Every entry is nonnegative when qₖ, ℓₖ ∈ [0, 1], and every row sums to one. The first row is a partition: die, survive and lapse, or survive and continue. Death and lapse are not sampled as two competing unconditional probabilities.

For a homogeneous cohort of n active policies, the implementation samples:

$$
D\sim\operatorname{Binomial}(n,q_k),\qquad
L\mid D\sim\operatorname{Binomial}(n-D,\ell_k),\qquad
A'=n-D-L.
$$

Conditional independence between policies makes these counts the same distribution as individually simulating their categorical outcomes. `binomial` uses Bernoulli trials, so it is exact for the stated model rather than a normal or Poisson approximation. Separate random streams drive acquisition, mortality, and lapse.

At the end of month M−1, surviving contracts expire. No final lapse is recorded, and there is no maturity benefit. Setting ℓ at that last step to zero does not change future cash flows, since no future covered month exists.

For pricing, define α₀ = 1 and:

$$
\alpha_{k+1}=\alpha_k(1-q_k)(1-\ell_k).
$$

By conditional probability and induction, αₖ is the probability of being active at the start of covered month k. Only α₀ through α₍M−1₎ are used in price factors; α_M is not used as post-expiry coverage.

## 3. A fixed premium determines a candidate benefit

Let p be the level monthly premium, B the fixed death benefit, eₖ the start-of-month expense, i > −1 the monthly valuation rate, and v = 1/(1+i). In month 0, e₀ includes the acquisition expense. Premiums and expenses occur at month start; deaths generate claims at month end.

Measured immediately before the first premium:

$$
a=\sum_{k=0}^{M-1}v^k\alpha_k,\qquad
b=\sum_{k=0}^{M-1}v^{k+1}\alpha_kq_k,\qquad
E=\sum_{k=0}^{M-1}v^k\alpha_ke_k.
$$

The expected present values of premiums, benefits, and expenses are pa, Bb, and E. This follows by writing each cash flow as an amount times its active/death indicator, taking expectations, then summing by linearity.

For an expected present-value margin m, solve pa − Bb − E = m:

$$
B^*=\frac{pa-E-m}{b}.
$$

Automatic pricing requires b > 0 and a positive available amount. The implementation works in paise and rounds the candidate benefit downward to a whole paisa. In exact arithmetic this weakly increases the expected margin; numerical valuation uses double-precision floating point. The API also permits a fixed B and reports whether it meets the margin target. It does not automatically change a fixed contract benefit during a simulation.

**Hand-check:** take M = 1, p = INR 1,000, e₀ = INR 150, q₀ = 0.1, i = 0.01, and m = INR 100. Then a = 1, b = 0.1/1.01, and B* = 750/(0.1/1.01) = INR 7,575. A test checks this independently calculated value.

No finite automatic benefit follows when b = 0. A near-zero b can produce an unrealistic or numerically unsupported benefit; the model must reject the unsupported calculation, not advertise unlimited coverage.

## 4. Prospective reserves

Let Vₖ be expected future outgo minus future premium income, immediately before the month-k premium, conditional on being active. There is no obligation beyond expiry, so V_M = 0. Conditioning on the next transition gives:

$$
V_k=e_k-p+v\left[q_kB+(1-q_k)(1-\ell_k)V_{k+1}\right].
$$

The first term is the current expense less premium. At month end, death costs B, continuation leaves reserve Vₖ₊₁, and lapse leaves no future benefit. Backward induction from V_M proves the recursion equals the conditional expected present value at every duration.

A separate test enumerates all possible exits for a three-month policy and compares its direct expected cash-flow sum with the recursion. At issue, V₀ = E + Bb − pa, which is approximately −m for a benefit priced to the target margin. A negative reserve therefore has a clear expected-value interpretation.

For the project's capital diagnostic, each active contract contributes ceil(max(0, Vₖ)) paise. This positive floor is a chosen conservative modeling convention; it is not claimed to be a statutory reserve. The capital buffer is also a user-supplied project assumption.

## 5. Event order and the cash ledger

At calendar month t:

1. Admit candidates scheduled for this boundary, unless an earlier payment shortfall stopped new issues.
2. Collect the premium from every active contract, including newly issued contracts.
3. Incur maintenance expenses and new-policy acquisition expenses; pay as much of total expense arrears as cash allows.
4. Apply the configured realized return to the remaining available cash (deterministic in the baseline). Round this posting once to the nearest paisa, ties to even.
5. Sample deaths, then survivor lapses or term expiries, within each issue cohort.
6. Incur death claims and pay as much of total claim arrears as cash allows.
7. Calculate remaining policy reserves, net assets, and the capital diagnostic.

This order defines the contract and settlement model. It does not establish legal payment priority. Customers cannot miss a current premium and keep this model's active status; grace periods require another state model.

Let Cₜ be closing cash, Uᶜₜ unpaid claims, Uᵉₜ unpaid expenses, and Aₜ = Cₜ − Uᶜₜ − Uᵉₜ. With initial cash C_init:

$$
C_t=C_{\mathrm{init}}+\sum_{j=0}^t
\left(\mathrm{premium}_j+\mathrm{interest}_j-
\mathrm{expensePaid}_j-\mathrm{claimPaid}_j\right),
$$

$$
A_t=C_{\mathrm{init}}+\sum_{j=0}^t
\left(\mathrm{premium}_j+\mathrm{interest}_j-
\mathrm{expenseIncurred}_j-\mathrm{claimIncurred}_j\right).
$$

These identities follow by induction: unpaid balances increase by incurred amounts and decrease by paid amounts. Adding those recurrences to the cash recurrence cancels settlement movements. Every month the code checks both identities exactly in integer paise, along with Cₜ ≥ 0 and:

$$
\mathrm{issuedToDate}=\mathrm{active}+\mathrm{deathsToDate}
+\mathrm{lapsesToDate}+\mathrm{expiriesToDate}.
$$

The diagnostic capital margin is Aₜ − reserveₜ − buffer. A negative margin is a **modeled capital breach**. An unpaid expense or claim is a **payment shortfall**. These are distinct events.

The first shortfall prevents later admissions, but issued contracts continue through their scheduled runoff. Later collection and settlement are diagnostic projections; insurer failure, policy transfer, legal priorities, and contract cancellation are outside this model.

The last possible issue is month T, where T is `acquisition_months`. Its final covered month is T+M−1. Projecting T+M months therefore covers every issued contract. Final economic surplus is final net assets minus initial capital, with any remaining unpaid obligations deducted. It is nominal, includes interest on initial capital, and is not an annualized or risk-adjusted investment return.

## 6. Simulation uncertainty

For each lapse scenario, R distinct seeds produce R complete model paths. Let x count paths with any payment shortfall and p̂ = x/R. The report gives a two-sided 95% Wilson interval with z = 1.959963984540054:

$$
\frac{\hat p+z^2/(2R)\ \pm\ z\sqrt{\hat p(1-\hat p)/R+z^2/(4R^2)}}{1+z^2/R}.
$$

This is a binomial proportion interval under independent paths from the specified scenario, not a guarantee of its real-world calibration. If x = 0, the additional exact one-sided 95% upper bound is:

$$
p_{\mathrm{upper}}=1-0.05^{1/R}.
$$

It follows by solving (1−p)^R = 0.05, so zero observed shortfalls does not imply zero probability. Scenarios share acquisition streams to aid comparison; results across scenarios are not independent samples to pool. The skeleton does not perform a significance test of the differences between scenarios.

## 7. What the verification establishes

The tests check analytical Yule moments and a known sampled distribution; transition probabilities and count conservation; a hand-priced contract; reserve recursion against independent path enumeration; certain death, certain lapse, expiry, zero population, unpaid liabilities, stop-sale behavior, deterministic seeds, rejected invalid assumptions, numerical limits, and safe report output.

Passing these checks supports correctness under the modeled rules. It does not prove optimal product design, calibrated mortality, lawful transactions, fraud detection, adequate regulatory capital, or profitable investing.
