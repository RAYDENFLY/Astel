# PHASE 14B.1 — OOS PROTOCOL & ACCEPTANCE CRITERIA FREEZE REPORT

> [!IMPORTANT]
> **Phase 14B.1 is a protocol-freeze and audit phase only. CandidateSignalV2 strategy rules remain 100% frozen and unmodified. Zero evaluation of strategy returns or parameter tuning on OOS data was performed.**

---

## 1. Objective

Phase 14B.1 established and cryptographically froze the complete evaluation protocol, benchmark methodologies, trading-cost models, outcome definitions, statistical requirements, and multi-tiered decision criteria for **Phase 14C Fresh Independent OOS Validation** before sufficient independent OOS data becomes available.

---

## 2. Pre-existing Boundaries & Canonical Specs

| Protocol Component | Value | Source / Rule |
|---|---|---|
| Historical Dataset Boundary | `2026-10-06T00:00:00Z` | Frozen dataset boundary from Phase 12.4–14 |
| OOS Start Rule | `new_first_timestamp > 2026-10-06T00:00:00Z` | Must satisfy zero timestamp overlap (`OVERLAP = false`) |
| Canonical Timeframe | `4H` | Canonical timeframe used across Phase 12–14 |
| Canonical Asset Universe | 12 Assets (`BTC_USDT`, `ETH_USDT`, `SOL_USDT`, `BNB_USDT`, `XRP_USDT`, `AVAX_USDT`, `LINK_USDT`, `DOGE_USDT`, `ADA_USDT`, `LTC_USDT`, `AAVE_USDT`, `SUI_USDT`) | Authoritative asset list |
| Warmup Candles Required | 90 candles | Indicator lookback requirement (RSI14, Bollinger %B, ret_12, etc.) |
| Evaluation Horizons | `T+1`, `T+3`, `T+6` (Primary: `T+3`) | Close-to-close forward return based on completed candles |
| Minimum Evaluation Observations | 100 observations | Protocol requirement before Phase 14C execution |
| Horizon Safety Margin | 6 candles | Horizon safety margin for T+6 without lookahead |

---

## 3. Benchmarks & Paired Statistical Comparison

- **Benchmark Set**:
  - `Always LONG`: Market buy on every active candidate evaluation timestamp.
  - `Always SHORT`: Market short on every active candidate evaluation timestamp.
  - `Random`: Random direction selection per timestamp (seed 42).
- **Paired Comparison Methodology**:
  - Paired return difference: $R_{\text{candidate, } t} - R_{\text{benchmark, } t}$ on exact matching asset and timestamp observations.
- **Bootstrap Resampling**:
  - 1,000 paired bootstrap resamples.
  - 95% Confidence Interval (2-tailed, percentile method).
  - Deterministic RNG seed `42`.

---

## 4. Frozen Trading Cost Scenarios

| Cost Scenario | Round-Trip Fee | Slippage / Spread | Total Round-Trip Cost |
|---|---:|---:|---:|
| **OPTIMISTIC** | 0.04% (0.02% maker fee per leg) | 0.02% (0.01% per leg) | **0.06%** |
| **BASE** | 0.10% (0.05% taker fee per leg) | 0.04% (0.02% per leg) | **0.14%** |
| **ADVERSE** | 0.15% (0.075% taker fee per leg) | 0.10% (0.05% per leg) | **0.25%** |

---

## 5. Multi-Tiered Decision Criteria Matrix

| Final Classification | Primary Condition | Statistical / Cost Threshold | Action / Conclusion |
|---|---|---|---|
| `STATISTICALLY_SUPPORTED_EDGE` | Paired diff vs Always LONG > 0 | 95% Bootstrap CI lower bound > 0 AND Net Expectancy > 0 under BASE cost | Candidate V2 exhibits genuine, cost-resistant, statistically significant OOS edge |
| `OOS_POSITIVE_BUT_NOT_SIGNIFICANT` | Paired diff vs Always LONG > 0 | 95% Bootstrap CI spans 0 | Directionally positive, but statistical edge is unproven |
| `NO_INCREMENTAL_EDGE` | Paired diff vs Always LONG $\le$ 0 | Paired difference $\le 0$ | Strategy fails to outperform simple market buy baseline |
| `COST_SENSITIVE` | Gross paired diff > 0 | Net Expectancy $\le 0$ under BASE cost (0.14%) | Strategy edge is completely eroded by trading costs |
| `INSUFFICIENT_OOS_EVIDENCE` | Usable observations < 100 | Usable OOS sample size below protocol threshold | Fail closed; require more calendar data before Phase 14C |
| `DATA_INTEGRITY_FAILURE` | Gaps > 4H, duplicate timestamps, invalid OHLC | Fail-closed integrity rule | Require clean data re-acquisition |
| `PROTOCOL_VIOLATION` | Parameter mutation, lookahead, or protocol hash mismatch | Strict anti-tamper rule | Halt execution immediately |

---

## 6. Failure Conditions

Phase 14C will fail closed under any of the following conditions:
1. `DATA_OVERLAP`: Any timestamp $\le \text{2026-10-06T00:00:00Z}$.
2. `UNAUTHORIZED_STRATEGY_MUTATION`: Any edit to `agent/candidate_signal_v2.py`.
3. `PROTOCOL_SHA256_MISMATCH`: Any modification to `phase14b1_oos_protocol_manifest.json`.
4. `INSUFFICIENT_WARMUP`: Total candles $< 90$.
5. `LOOKAHEAD_LEAKAGE`: Signal generation using future candle data.
6. `MISSING_CANONICAL_ASSET`: Any missing asset from the 12 canonical pairs.

---

## 7. Machine-Readable Summary

```text
PHASE: 14B.1
STATUS: PASS
CLASSIFICATION: PROTOCOL_FROZEN
PROTOCOL_VERSION: 1.0.0-FROZEN
HISTORICAL_BOUNDARY: 2026-10-06T00:00:00Z
OOS_START_RULE: new_first_timestamp > 2026-10-06T00:00:00Z
TIMEFRAME: 4H
ASSETS: 12
WARMUP: 90
HORIZONS: T+1,T+3,T+6
MIN_EVALUATION_OBSERVATIONS: 100
COST_MODEL: FROZEN
BENCHMARKS: FROZEN
OUTCOME_DEFINITION: FROZEN
STATISTICAL_METHOD: FROZEN
DECISION_CRITERIA: FROZEN
PROTOCOL_FROZEN: true
PROTOCOL_SHA256: 473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36
TESTS: 18/18
PHASE_14C_ALLOWED: false
```

---

## 8. Anti-Goalpost Policy & Next Steps

> **Strict Anti-Goalpost Rule**: Once Phase 14B.1 returns `PROTOCOL_FROZEN`, the protocol fingerprint `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36` is permanently locked. No post-hoc changes to thresholds, benchmarks, statistical methods, cost models, or decision boundaries are permitted regardless of Phase 14C evaluation outcomes.

- **Phase 14C Status**: **NOT ALLOWED** (`PHASE_14C_ALLOWED: false`).
- **Prerequisite**: Phase 14C requires explicit subsequent instructions and sufficient calendar time (~32.6 days post Oct 6, 2026) for independent OOS observations to accumulate.
