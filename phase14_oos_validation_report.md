# PHASE 14 — INDEPENDENT OOS VALIDATION, PAIRED EDGE & TRADING-COST AUDIT REPORT

> [!IMPORTANT]
> **Phase 14 is an audit of the frozen Candidate V2, not a strategy optimization phase. No production strategy changes are permitted based solely on this audit.**

---

## 1. Executive Summary

Phase 14 conducted a strictly read-only, quantitative validation and trading-cost audit of `CandidateSignalV2`. The purpose was to audit the baseline performance, paired benchmark superiority, conflict behavior, regime performance, asset breakdown, temporal stability, trading cost tolerance, and safety isolation of Candidate V2.

### Key Audit Findings:
- **Data Provenance**: The workspace dataset (`quant_system/data/csv`, 12 assets, 4H candles, 1000 bars per asset spanning April to October 2026) overlaps with the historical dataset used during Phase 12.4–12.9 research, Candidate V2 rule freezing, and Phase 13 shadow observation. Genuinely unseen independent OOS data was unavailable in local workspace storage.
- **Data Quality**: 100% clean data across all 12 assets (12,000 total OHLCV bars, 0 gaps, 0 duplicates, 100% valid OHLC relations).
- **Candidate V2 Standalone Performance**: Across 3,923 active observations, Candidate V2 produced **+0.2141% T+3 mean expectancy**, 47.62% directional accuracy, and **1.30 Profit Factor**.
- **Paired Benchmark Analysis**:
  - vs **Always LONG**: Paired mean difference = **+0.0068%** (95% Bootstrap CI: **[-0.0693%, +0.0893%]**, Prob > 0: **58.70%**).
  - vs **Always SHORT**: Paired mean difference = **+0.4214%** (95% Bootstrap CI: **[+0.2922%, +0.5437%]**, Prob > 0: **100.00%**).
  - *Conclusion*: Candidate V2 does **not** demonstrate a statistically significant paired incremental edge over `Always LONG` on the exact same signal observations (bootstrap 95% CI spans zero).
- **Conflict Behavior Asymmetry**:
  - `MR_SHORT_MOM_LONG` (FOLLOW_MOMENTUM → LONG): **+0.7290% T+3 expectancy**, 50.89% accuracy, **2.00 PF** (N = 847, STRONG). Paired difference vs Always LONG = +0.0000%.
  - `MR_LONG_MOM_SHORT` (FOLLOW_MOMENTUM → SHORT): **-0.0778% T+3 expectancy**, 42.89% accuracy, **0.90 PF** (N = 774, STRONG). Paired difference vs Always LONG = -0.1556%.
- **Trading Cost Model**:
  - **OPTIMISTIC** (0.06% round-trip): Net expectancy = **+0.1541%**, Net PF = **1.21**.
  - **BASE** (0.14% round-trip): Net expectancy = **+0.0741%**, Net PF = **1.09**.
  - **ADVERSE** (0.25% round-trip): Net expectancy = **-0.0359%**, Net PF = **0.96**.
  - **Break-Even Round-Trip Cost**: **0.2141%** (0.1071% per leg).
  - **Cost to Erode Paired Edge vs Always LONG to Zero**: **+0.0068%**.
- **Execution Safety**: Enforced `EXECUTION_MODE = "SHADOW"` with fail-closed assertion. 0 exchange order API calls executed.

---

## 2. Final Classification & Recommendation

### Final Classification

```text
INSUFFICIENT_OOS_DATA
```

**Reason**: Genuinely fresh, non-overlapping independent dataset was unavailable in the workspace data cache. The evaluated dataset overlaps with data used during Candidate V2 development, rule freezing, and Phase 13 shadow observation.

### Recommendation Logic

```text
INSUFFICIENT_OOS_DATA
    → Collect additional independent data before Phase 15 Production Readiness Audit
```

---

## 3. Data Integrity & Provenance Audit

### Data Provenance Table

| Field | Value |
|---|---|
| Provenance Source | `quant_system/data/csv` |
| Asset Count | 12 Assets (`BTC_USDT`, `ETH_USDT`, `SOL_USDT`, `BNB_USDT`, `XRP_USDT`, `AVAX_USDT`, `LINK_USDT`, `DOGE_USDT`, `ADA_USDT`, `LTC_USDT`, `AAVE_USDT`, `SUI_USDT`) |
| Timeframe | 4H |
| Date Range | 2026-04-22T12:00:00Z to 2026-10-06T00:00:00Z |
| Total Candles Evaluated | 12,000 (1,000 candles per asset) |
| Phase 12-13 Data Overlap | YES (Exact historical dataset used in Phase 12.4-12.9 & Phase 13) |
| Genuinely Fresh Data | NO |
| Provenance Classification | `INDEPENDENT_OOS_DATA_UNAVAILABLE` |

### Data Quality Audit Table

| Asset | Candles | Start Timestamp | End Timestamp | Gaps | Duplicates | Valid OHLC | Status |
|---|---|---|---|---|---|---|---|
| `BTC_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `ETH_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `SOL_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `BNB_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `XRP_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `AVAX_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `LINK_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `DOGE_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `ADA_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `LTC_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `AAVE_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |
| `SUI_USDT` | 1000 | 2026-04-22T12:00:00Z | 2026-10-06T00:00:00Z | 0 | 0 | True | PASS |

---

## 4. Paired Observation-by-Observation Benchmark Analysis

Evaluated across **3,923 active signal observations**.

| Metric | Candidate V2 | Always LONG | Always SHORT | Random |
|---|---:|---:|---:|---:|
| Directional Accuracy | 47.62% | 50.58% | 49.42% | 49.63% |
| T+3 Mean Return | **+0.2141%** | +0.2073% | -0.2073% | -0.0761% |
| Median Return | **0.0000%** | +0.0000% | 0.0000% | 0.0000% |
| Profit Factor | **1.30** | 1.29 | 0.77 | 0.91 |

### Paired Bootstrap Statistics (1,000 Resamples, 95% CI)

#### vs Always LONG Benchmark
- **Paired Mean Difference**: **+0.0068%**
- **Paired Median Difference**: **+0.0000%**
- **Standard Error**: **0.0406%**
- **95% Bootstrap Confidence Interval**: **[-0.0693%, +0.0893%]**
- **Bootstrap Probability Diff > 0**: **58.70%**

#### vs Always SHORT Benchmark
- **Paired Mean Difference**: **+0.4214%**
- **Paired Median Difference**: **+0.0000%**
- **Standard Error**: **0.0660%**
- **95% Bootstrap Confidence Interval**: **[+0.2922%, +0.5437%]**
- **Bootstrap Probability Diff > 0**: **100.00%**

> [!CAUTION]
> **Statistical Significance Insight**: While Candidate V2 significantly outperforms `Always SHORT` (+0.4214%, 100% prob > 0), its paired difference over `Always LONG` is only **+0.0068%** with a 95% CI spanning from **-0.0693%** to **+0.0893%**. Candidate V2 does **not** demonstrate a statistically significant paired edge over a simple market-buy baseline on the same observations.

---

## 5. Conflict Directional Audit

| Conflict Type | Expected Direction | N | Sample Label | Accuracy | T+3 Expectancy | PF | Paired Diff vs AL | 95% Bootstrap CI |
|---|---|---:|---|---:|---:|---:|---:|---|
| `MR_SHORT_MOM_LONG` | **FOLLOW_MOMENTUM → LONG** | 847 | STRONG | **50.89%** | **+0.7290%** | **2.00** | +0.0000% | [+0.0000%, +0.0000%] |
| `MR_LONG_MOM_SHORT` | **FOLLOW_MOMENTUM → SHORT** | 774 | STRONG | **42.89%** | **-0.0778%** | **0.90** | -0.1556% | [-0.4351%, +0.1576%] |

> [!NOTE]
> **Conflict Structural Asymmetry**: When Mean-Reversion indicates overbought/SHORT while Momentum remains bullish (`MR_SHORT_MOM_LONG`), following momentum LONG produces strong positive expectancy (+0.7290%, PF 2.00). However, when Mean-Reversion indicates oversold/LONG while Momentum remains bearish (`MR_LONG_MOM_SHORT`), following momentum SHORT yields negative expectancy (-0.0778%, PF 0.90).

---

## 6. Regime Performance Breakdown

| Regime | Active N | Accuracy | T+3 Expectancy | PF | Paired Diff vs AL | 95% Bootstrap CI |
|---|---:|---:|---:|---:|---:|---|
| `BULLISH_TREND` | 2,134 | 48.50% | **+0.3090%** | 1.41 | +0.0746% | [-0.0083%, +0.1598%] |
| `BEARISH_TREND` | 566 | 39.05% | **-0.2146%** | 0.76 | -0.3510% | [-0.6860%, +0.0145%] |
| `CONSOLIDATION` | 1,223 | 49.55% | **+0.2469%** | 1.44 | +0.0543% | [-0.0821%, +0.1958%] |
| `HIGH_VOLATILITY` | 0 | N/A | N/A | N/A | N/A | N/A (Filtered to NEUTRAL) |

---

## 7. Asset-Level Breakdown

Sample size classifications: `N < 30`: INSUFFICIENT, `30-99`: EARLY, `100-299`: DEVELOPING, `300-499`: MEANINGFUL, `>= 500`: STRONG.

| Asset | Active N | Sample Label | Accuracy | T+3 Expectancy | PF | Paired Diff vs AL |
|---|---:|---|---:|---:|---:|---:|
| `BTC_USDT` | 370 | MEANINGFUL | 47.03% | +0.1031% | 1.25 | +0.0568% |
| `ETH_USDT` | 361 | MEANINGFUL | 45.98% | +0.2219% | 1.39 | +0.0433% |
| `SOL_USDT` | 331 | MEANINGFUL | 45.32% | +0.2362% | 1.34 | -0.0553% |
| `BNB_USDT` | 392 | MEANINGFUL | 43.88% | +0.1182% | 1.25 | +0.0766% |
| `XRP_USDT` | 296 | DEVELOPING | 46.28% | +0.1708% | 1.23 | -0.0322% |
| `AVAX_USDT` | 288 | DEVELOPING | 46.18% | +0.0349% | 1.04 | -0.2413% |
| `LINK_USDT` | 348 | MEANINGFUL | 48.56% | +0.1534% | 1.20 | -0.2303% |
| `DOGE_USDT` | 270 | DEVELOPING | 42.22% | +0.0617% | 1.07 | +0.0288% |
| `ADA_USDT` | 317 | MEANINGFUL | 52.37% | +0.3868% | 1.42 | +0.1493% |
| `LTC_USDT` | 368 | MEANINGFUL | 50.27% | +0.2239% | 1.38 | +0.1223% |
| `AAVE_USDT` | 319 | MEANINGFUL | 48.28% | +0.2341% | 1.23 | -0.2100% |
| `SUI_USDT` | 263 | DEVELOPING | **53.99%** | **+0.7108%** | **1.94** | **+0.3974%** |

---

## 8. Temporal Stability Across 4 Windows

The historical timeframe was divided into 4 chronological windows of ~230 steps (~38 days each):

| Window | Active N | Candidate V2 Expectancy | Always LONG Expectancy | Paired Diff vs AL | Directional Accuracy | PF |
|---|---:|---:|---:|---:|---:|---:|
| **Window 1 (Early)** | 938 | +0.1412% | -0.1769% | **+0.3181%** | 45.63% | 1.18 |
| **Window 2 (Mid-Early)** | 1,053 | +0.1060% | +0.0657% | **+0.0404%** | 49.38% | 1.18 |
| **Window 3 (Mid-Late)** | 916 | +0.4953% | +0.7004% | **-0.2051%** | 47.38% | 1.78 |
| **Window 4 (Final)** | 1,016 | +0.1400% | +0.2642% | **-0.1242%** | 47.24% | 1.17 |

> [!WARNING]
> **Temporal Decay Observation**: Candidate V2 outperformed `Always LONG` during Window 1 (+0.3181%) and Window 2 (+0.0404%), but underperformed `Always LONG` during Window 3 (-0.2051%) and Window 4 (-0.1242%). The paired edge is chronologically volatile.

---

## 9. Trading Cost Model & Cost Sensitivity

### Scenario Analysis

| Scenario | Assumptions | Roundtrip Cost | Net Expectancy | Net Win Rate | Net Profit Factor |
|---|---|---:|---:|---:|---:|
| **OPTIMISTIC** | Maker fee 0.02%, Slip/Spread 0.01% per leg | **0.06%** | **+0.1541%** | 45.86% | **1.21** |
| **BASE** | Taker fee 0.05%, Slip/Spread 0.02% per leg | **0.14%** | **+0.0741%** | 44.25% | **1.09** |
| **ADVERSE** | Taker fee 0.075%, Slip/Spread 0.05% per leg | **0.25%** | **-0.0359%** | 41.58% | **0.96** |

### Break-Even Cost Summary

- **Gross Standalone Candidate V2 Expectancy**: **+0.2141%**
- **Maximum Round-Trip Cost for Net Expectancy $\ge 0$**: **0.2141%** round-trip (**0.1071%** per leg).
- **Cost to Erode Paired Edge vs Always LONG to Zero**: **+0.0068%** round-trip.

---

## 10. Execution Safety & Unit Tests

### Execution Safety Audit
- **Mode**: `EXECUTION_MODE = "SHADOW"`
- **Fail-Closed Assertion**: Implemented in `agent/_phase14_oos_validation.py`.
- **API Order Calls**: 0 `GateExecutor.place_order()` or `ExecutionEngine` calls executed.

### Unit Test Suite Results
Unit tests in `agent/test_phase14_validation.py` cover all 13 required test cases:

```text
test_1_frozen_candidate_v2_behavior ... ok
test_2_no_lookahead ... ok
test_3_sample_size_labels ... ok
test_4_duplicate_filtering ... ok
test_5_paired_benchmark_calculation ... ok
test_6_bootstrap_ci ... ok
test_7_conflict_split ... ok
test_8_regime_split ... ok
test_9_asset_split ... ok
test_10_cost_calculation ... ok
test_11_breakeven_cost ... ok
test_12_execution_isolation ... ok
test_13_shadow_fail_closed ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.077s - OK
```

---

## 11. Files Changed

| File | Purpose |
|---|---|
| `agent/_phase14_oos_validation.py` | Isolated Phase 14 quantitative audit & trading cost engine |
| `agent/test_phase14_validation.py` | 13 unit tests covering Candidate V2 audit requirements |
| `phase14_oos_validation_report.md` | Comprehensive Phase 14 audit report |

---

> **Phase 14 is an audit of the frozen Candidate V2, not a strategy optimization phase. No production strategy changes are permitted based solely on this audit.**
