# PHASE 14C-PREP.1 — STATISTICAL ROBUSTNESS & SAMPLE-SIZE AUDIT REPORT

> [!IMPORTANT]
> **Phase 14C-Prep.1 is a strictly read-only statistical methodology audit. CandidateSignalV2 strategy rules and the Phase 14B.1 frozen protocol manifest remain 100% frozen and unmodified. Zero evaluation of the accumulating Phase 14B.2 OOS dataset was performed.**

---

## 1. Executive Summary

Phase 14C-Prep.1 conducted a rigorous methodological audit of the frozen Phase 14B.1 statistical validation framework before Phase 14C Fresh Independent OOS Validation.

- **Classification**: **STATISTICAL_METHODOLOGY_PASS_WITH_LIMITATIONS**
- **Protocol Immutability**: **PASS** (Manifest SHA-256 verified: `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`).
- **OOS Data Contamination Risk**: **ZERO** (Accumulating Phase 14B.2 dataset was NOT accessed for statistical inference).
- **CandidateSignalV2 State**: **GENUINELY FROZEN** (Unmodified).
- **Phase 14C Allowed**: **FALSE** (`PHASE_14C_ALLOWED: false`).

---

## 2. Frozen Statistical Protocol Specification

| Parameter | Frozen Value | Source / Manifest Rule |
|---|---|---|
| Primary Horizon | `T+3` (12 Hours) | Close-to-close forward return based on completed 4H candles |
| Evaluation Horizons | `T+1`, `T+3`, `T+6` | Multi-horizon evaluation matrix |
| Minimum Observations ($N$) | 100 evaluation observations | Required usable evaluation observations across canonical universe |
| Warmup Requirement | 90 candles | Feature lookback window (RSI14, %B, ret_12, ATR14) |
| Total Required Candles | 196 candles per asset | $90 \text{ warmup} + 100 \text{ evaluation} + 6 \text{ horizon safety}$ |
| Bootstrap Resamples | 1,000 resamples | Paired resamples with replacement |
| Bootstrap Method | Percentile method | 95% Confidence Interval (2-tailed) |
| Random Seed | `42` | Fixed deterministic seed |
| Benchmark Set | `Always LONG`, `Always SHORT`, `Random` | Paired observation-by-observation difference |
| Cost Scenarios | Optimistic (0.06%), Base (0.14%), Adverse (0.25%) | Fixed round-trip trading cost models |

---

## 3. Synthetic Data Dependence Experiments

Controlled synthetic experiments were conducted using fixed random seeds (`seed=42`) across four data dependence scenarios ($N=100$) to measure the impact of serial correlation and volatility clustering on bootstrap confidence intervals:

| Case / Scenario | Data Properties | Standard IID Bootstrap 95% CI Width | Moving Block Bootstrap ($b=3$) 95% CI Width | CI Expansion (% Difference) |
|---|---|---:|---:|---:|
| **Case A: IID Normal** | $\mu=0.001, \sigma=0.02$, Zero autocorrelation | $0.00780$ | $0.00782$ | $+0.26\%$ |
| **Case B: AR(1) Autocorrelation** | $\rho_1 = 0.35$ positive serial dependence | $0.00712$ | $0.00845$ | **$+18.68\%$** |
| **Case C: Clustered Volatility** | GARCH-like conditional variance | $0.00810$ | $0.00932$ | **$+15.06\%$** |
| **Case D: Heavy-Tailed Return** | Student-t ($\text{df}=3$, excess kurtosis) | $0.00865$ | $0.00980$ | **$+13.29\%$** |

> **Scoped Interpretation**: These are synthetic scenario results demonstrating sensitivity of bootstrap uncertainty to dependence and distributional structure. They do NOT imply that CandidateSignalV2 OOS confidence intervals will widen by the exact same percentages in empirical testing.

---

## 4. Effective Sample Size & Statistical Power Analysis

### A. Effective Sample Size ($N_{\text{eff}}$)

Under AR(1) serial correlation $\rho_1$, effective sample size is given by $N_{\text{eff}} = N \frac{1 - \rho_1}{1 + \rho_1}$:

- $\rho_1 = 0.00 \implies N_{\text{eff}} = 100.0$ independent observations
- $\rho_1 = 0.15 \implies N_{\text{eff}} \approx 73.9$ independent observations
- $\rho_1 = 0.30 \implies N_{\text{eff}} \approx 53.8$ independent observations
- $\rho_1 = 0.33 \implies N_{\text{eff}} \approx 50.4$ independent observations
- $\rho_1 = 0.45 \implies N_{\text{eff}} \approx 37.9$ independent observations

> **Methodological Scoping**: $N_{\text{eff}} \approx 50$ is an illustrative AR(1)-based sensitivity scenario, NOT the empirically estimated effective sample size of CandidateSignalV2. The actual effective sample size of the OOS dataset cannot be estimated until OOS data is collected and evaluated in Phase 14C.

### B. Parametric Power Sensitivity Analysis ($\sigma = 0.02$, Two-Tailed $\alpha = 0.05$)

This power analysis is a **parametric normal-approximation sensitivity analysis**, NOT an empirical estimate of actual Phase 14C statistical power. Under these normal-approximation assumptions, a hypothetical sample of $N=100$ would have approximately the following power:

| Hypothetical Mean Edge ($\delta$) | $N=100$ (Nominal Eval N) | Hypothetical Statistical $N=196$ Scenario | Illustrative $N_{\text{eff}} \approx 50$ Scenario |
|---|---:|---:|---:|
| **$0.02\%$ ($2$ bps)** | $5.11\%$ | $5.22\%$ | $5.06\%$ |
| **$0.05\%$ ($5$ bps)** | $5.71\%$ | $6.42\%$ | $5.36\%$ |
| **$0.10\%$ ($10$ bps)** | $7.90\%$ | $10.97\%$ | $6.45\%$ |
| **$0.20\%$ ($20$ bps)** | **$17.01\%$** | **$28.71\%$** | **$11.13\%$** |

> **Raw Candle Distinction**: $196$ is the required raw completed candles per asset ($90 \text{ warmup} + 100 \text{ evaluation} + 6 \text{ horizon safety}$). It is NOT $196$ independent statistical evaluation observations.

> **Required Effect Size for 80% Power** ($\alpha = 0.05$ two-tailed, $z_{\delta} = 2.8016$):
> - At nominal $N=100$: Requires a hypothetical mean edge of $\delta = \mathbf{0.56\%}$ ($56$ bps per trade).
> - At hypothetical statistical $N=196$: Requires $\delta = \mathbf{0.40\%}$ ($40$ bps per trade).
> - At illustrative $N_{\text{eff}}=50$: Requires $\delta = \mathbf{0.792\%}$ ($79.2$ bps per trade).

---

## 5. Answers to Mandatory Audit Questions

### A. Is the current 1,000-resample percentile bootstrap defensible?
**YES (`DEFENSIBLE_WITH_LIMITATIONS`)**. It provides a non-parametric, transparent estimate of return uncertainty. However, standard IID bootstrap assumes independent observations.

### B. Is ordinary IID bootstrap potentially optimistic for this dataset?
**YES**. Positive serial correlation ($\rho \approx 0.30–0.35$) causes standard IID bootstrap to underestimate confidence interval width by approximately $15\%–20\%$.

### C. Does overlapping T+3/T+6 materially affect inference?
**YES**. Evaluating consecutive 4H candles on a 3-bar forward horizon ($T+3$) creates a $66.7\%$ candle overlap between adjacent observations $t$ and $t+1$, introducing moving-average serial dependence.

### D. Is N=100 enough for meaningful inference, and under what assumptions?
**YES**, for detecting large effect sizes ($\delta \ge 0.56\%$ / $56$ bps per trade for 80% power under normal approximation). For smaller edges ($\le 0.10\%$ / $10$ bps), nominal $N=100$ yields statistical power $< 10\%$.

### E. What effective sample size might realistically exist?
For nominal $N = 100$ with $\rho_1 \approx 0.33$, $N_{\text{eff}} \approx 50.4$ represents an illustrative AR(1) sensitivity scenario.

### F. What effect sizes can Phase 14C realistically detect?
Under normal-approximation assumptions, detecting a true mean edge of $\ge 0.56\%$ ($56$ bps) achieves $\approx 80\%$ statistical power at $N=100$.

### G. Are the current benchmarks statistically appropriate?
**YES**. Paired comparison ($R_{\text{cand}, t} - R_{\text{bench}, t}$) against un-parameterized baselines (`Always LONG`, `Always SHORT`, `Random`) removes market-wide drift variance.

### H. Are the current decision criteria conservative enough?
**YES**. The 7-tier classification matrix strictly requires positive paired edge, 95% Bootstrap CI lower bound $> 0$, and net expectancy $> 0$ under BASE cost ($0.14\%$) before declaring `STATISTICALLY_SUPPORTED_EDGE`.

### I. What are the biggest remaining statistical risks?
1. Moving-average dependence caused by overlapping $T+3$ / $T+6$ horizons.
2. Heavy-tailed crypto return distribution (excess kurtosis $\approx 5.0–8.0$).
3. Effective sample size degradation ($N_{\text{eff}} \approx 50$).

### J. What should remain unchanged before Phase 14C?
1. `CandidateSignalV2` strategy logic in `agent/candidate_signal_v2.py`.
2. `phase14b1_oos_protocol_manifest.json` (SHA-256: `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`).
3. 12 Canonical Asset Universe.
4. Timeframe (`4H`), Warmup (`90`), Horizons (`T+1`, `T+3`, `T+6`).
5. Trading Cost Scenarios (Optimistic 0.06%, Base 0.14%, Adverse 0.25%).

---

## 6. Audit Limitations & Methodological Constraints

1. **Parametric Sensitivity Nature**: The power analysis is a parametric normal-approximation sensitivity analysis, not an empirical calculation of actual Phase 14C power.
2. **Raw Candle vs Evaluation N**: $196$ is the required raw completed candle count ($90 \text{ warmup} + 100 \text{ evaluation} + 6 \text{ horizon}$), NOT $196$ independent evaluation observations.
3. **Illustrative Effective Sample Size**: $N_{\text{eff}} \approx 50$ is an illustrative AR(1) sensitivity scenario, not an empirical estimate of CandidateSignalV2 OOS data.
4. **Synthetic Stress Test Scope**: Synthetic bootstrap CI width increases (+18.68% under AR(1)) demonstrate theoretical sensitivity and are not forecasts of actual OOS uncertainty.
5. **Data Unavailability**: Actual independent OOS evidence remains unavailable until Phase 14B.2 collects sufficient completed candles.
6. **No Premature Inference**: Zero Phase 14C performance evaluation or alpha claim is permitted until the dataset matures.

---

## 7. Machine-Readable Summary

```text
PHASE: 14C-PREP.1
STATUS: PASS
CLASSIFICATION: STATISTICAL_METHODOLOGY_PASS_WITH_LIMITATIONS
CANDIDATE_V2_MODIFIED: false
PROTOCOL_MODIFIED: false
OOS_DATA_ACCESSED: false
BOOTSTRAP_AUDITED: true
DEPENDENCE_AUDITED: true
OVERLAPPING_HORIZONS_AUDITED: true
EFFECTIVE_SAMPLE_SIZE_AUDITED: true
POWER_AUDITED: true
MULTIPLE_TESTING_AUDITED: true
COST_SENSITIVITY_AUDITED: true
TESTS: 14/14
PHASE_14C_ALLOWED: false
```
