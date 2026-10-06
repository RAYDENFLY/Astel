# PHASE 14C-PREP.1 REVIEW — POWER ANALYSIS VERIFICATION & MATHEMATICAL AUDIT

> [!IMPORTANT]
> **READ-ONLY AUDIT REVIEW**: This report presents an independent, first-principles mathematical verification of the Phase 14C-Prep.1 statistical audit (`PHASE_14C_PREP_STATISTICAL_AUDIT.md`). CandidateSignalV2, the Phase 14B.1 frozen protocol manifest, and the accumulating Phase 14B.2 dataset remain 100% frozen and un-accessed.

---

## 1. Executive Verdict & Classification

- **Review Classification**: **`STATISTICAL_AUDIT_REQUIRES_CORRECTION`**
- **Overall Review Status**: **WARNING**
- **Primary Finding**: The initial draft of `PHASE_14C_PREP_STATISTICAL_AUDIT.md` contained a numerical discrepancy in its statistical power calculations (overstating power for $\delta = 0.20\%$ at $N=100$ as $88.5\%$ instead of the exact analytical two-sided $17.01\%$).
- **Protocol Immutability**: **PASS** (Frozen manifest `phase14b1_oos_protocol_manifest.json` SHA-256 remains 100% frozen and unmodified).
- **OOS Contamination Risk**: **ZERO** (Accumulating Phase 14B.2 dataset was NOT accessed).

---

## 2. Power Analysis — Mandatory First-Principles Recalculation

### A. Mathematical Formulation
For a two-sided $Z$-test at significance level $\alpha = 0.05$ ($z_{\text{crit}} = 1.95996$), standard deviation $\sigma = 0.02$, sample size $N$, and mean difference $\delta$:

$$SE = \frac{\sigma}{\sqrt{N}}$$

$$\text{Non-Centrality Parameter } (z_{\delta}) = \frac{\delta}{SE}$$

$$\text{Power} = P(Z > z_{\text{crit}} - z_{\delta}) + P(Z < -z_{\text{crit}} - z_{\delta})$$

---

### B. Explicit Sanity Check ($\delta = 0.20\% = 0.0020, \sigma = 0.02, N = 100$)

$$SE = \frac{0.02}{\sqrt{100}} = \frac{0.02}{10} = 0.0020$$

$$z_{\delta} = \frac{0.0020}{0.0020} = 1.0000$$

$$\text{Power} = P(Z > 1.96 - 1.00) + P(Z < -1.96 - 1.00) = P(Z > 0.96) + P(Z < -2.96)$$

$$P(Z > 0.96) \approx 0.16853 \quad (16.85\%)$$

$$P(Z < -2.96) \approx 0.00154 \quad (0.15\%)$$

$$\mathbf{\text{Exact Analytical Power} = 17.007\% \quad (\approx 17.01\%)}$$

> **Discrepancy Identification**: The previous draft reported $88.5\%$ power for $\delta = 0.20\%$ ($20$ bps) at $N=100$. To achieve $88.5\%$ power under $\sigma=0.02$ and $N=100$, the non-centrality parameter must be $z_{\delta} \approx 3.16$, which requires an effect size of $\delta = 3.16 \times 0.0020 = 0.00632 = \mathbf{0.632\%}$ ($63.2$ bps per trade).

---

### C. Complete Verified Power Table (Parametric Sensitivity Analysis)

| Paired Mean Edge ($\delta$) | $N=100$ (Nominal Eval N) | Hypothetical Statistical $N=196$ Scenario | Illustrative $N_{\text{eff}} \approx 50$ Sensitivity Scenario |
|---|---:|---:|---:|
| **$0.02\%$ ($2$ bps)** | **$5.11\%$** | **$5.22\%$** | **$5.06\%$** |
| **$0.05\%$ ($5$ bps)** | **$5.71\%$** | **$6.42\%$** | **$5.36\%$** |
| **$0.10\%$ ($10$ bps)** | **$7.90\%$** | **$10.97\%$** | **$6.45\%$** |
| **$0.20\%$ ($20$ bps)** | **$17.01\%$** | **$28.71\%$** | **$11.13\%$** |

> **Required Effect Size for 80% Power** ($\alpha = 0.05$ two-tailed, $z_{\delta} = 1.96 + 0.8416 = 2.8016$):
> - At nominal $N=100$: Requires a mean edge of $\delta = \mathbf{0.560\%}$ ($56$ bps per trade).
> - At hypothetical statistical $N=196$: Requires $\delta = \mathbf{0.400\%}$ ($40$ bps per trade).
> - At illustrative $N_{\text{eff}}=50$: Requires $\delta = \mathbf{0.792\%}$ ($79.2$ bps per trade).

---

## 3. Distinction Between Raw Candles and Nominal Evaluation $N$

- **$196$ Raw Completed Candles**: Represents the total data collection requirement per asset ($90 \text{ warmup} + 100 \text{ evaluation} + 6 \text{ horizon safety}$).
- **$100$ Nominal Evaluation Observations ($N=100$)**: Represents the actual evaluation sample size used in hypothesis testing.
- **Critical Rule**: $196$ raw collected candles MUST NOT be conflated as $N=196$ independent statistical evaluation observations.

---

## 4. Effective Sample Size ($N_{\text{eff}}$) Audit

$$N_{\text{eff}} = N \times \frac{1 - \rho_1}{1 + \rho_1}$$

| AR(1) Serial Correlation ($\rho_1$) | Theoretical $N_{\text{eff}}$ ($N=100$) |
|---|---:|
| **$\rho_1 = 0.00$** | $100.00$ |
| **$\rho_1 = 0.15$** | $73.91$ |
| **$\rho_1 = 0.30$** | $53.85$ |
| **$\rho_1 = 0.33$** | $50.38$ |
| **$\rho_1 = 0.35$** | $48.15$ |
| **$\rho_1 = 0.45$** | $37.93$ |

> **Audit Context**: $N_{\text{eff}} \approx 50$ is an **illustrative AR(1)-based sensitivity scenario**, NOT the empirically estimated effective sample size of CandidateSignalV2. The actual effective sample size of CandidateSignalV2 OOS data cannot be estimated until OOS data is evaluated.

---

## 5. Synthetic Bootstrap CI Expansion vs Empirical OOS

- The synthetic experiment finding ($+18.68\%$ CI width expansion under Moving Block Bootstrap $b=3$) is a **controlled simulation stress test** derived from a synthetic AR(1) process with $\rho_1 = 0.35$.
- These are synthetic scenario results demonstrating sensitivity of bootstrap uncertainty to dependence and distributional structure. They do NOT imply that CandidateSignalV2 OOS confidence intervals will widen by the exact same percentages in empirical testing.

---

## 6. Overlapping Horizon Interpretation ($T+3$)

- Evaluating consecutive 4H candles on a 3-bar forward horizon ($T+3$) means that adjacent observations $t$ and $t+1$ share 2 out of 3 underlying completed candles ($t+1$ and $t+2$).
- **$66.7\%$ Candle Overlap**: Represents moving-average covariance structure between adjacent evaluation bars. It does **NOT** equal a $66.7\%$ reduction in sample size.

---

## 7. Audit Limitations & Methodological Constraints

1. **Parametric Sensitivity Nature**: The power analysis is a parametric normal-approximation sensitivity analysis, not an empirical calculation of actual Phase 14C power.
2. **Raw Candle vs Evaluation N**: $196$ is the required raw completed candle count ($90 \text{ warmup} + 100 \text{ evaluation} + 6 \text{ horizon}$), NOT $196$ independent evaluation observations.
3. **Illustrative Effective Sample Size**: $N_{\text{eff}} \approx 50$ is an illustrative AR(1) sensitivity scenario, not an empirical estimate of CandidateSignalV2 OOS data.
4. **Synthetic Stress Test Scope**: Synthetic bootstrap CI width increases (+18.68% under AR(1)) demonstrate theoretical sensitivity and are not forecasts of actual OOS uncertainty.
5. **Data Unavailability**: Actual independent OOS evidence remains unavailable until Phase 14B.2 collects sufficient completed candles.
6. **No Premature Inference**: Zero Phase 14C performance evaluation or alpha claim is permitted until the dataset matures.

---

## 8. Machine-Readable Summary

```text
PHASE: 14C-PREP.1-REVIEW
STATUS: WARNING
CLASSIFICATION: STATISTICAL_AUDIT_REQUIRES_CORRECTION
POWER_ANALYSIS_VERIFIED: true
POWER_VALUES_CORRECT: false
N_196_INTERPRETATION_VERIFIED: true
N_EFF_FORMULA_VERIFIED: true
BOOTSTRAP_SYNTHETIC_RESULTS_VERIFIED: true
OOS_DATA_ACCESSED: false
CANDIDATE_V2_MODIFIED: false
PROTOCOL_MODIFIED: false
PHASE_14C_ALLOWED: false
```
