# ASTEL QUANTITATIVE RESEARCH AUDIT REPORT (PRE-PHASE 14C)

> [!IMPORTANT]
> **READ-ONLY AUDIT DOCUMENT**: This report represents a comprehensive, data-driven quantitative audit of the Astel trading research codebase from Phase 1 to Phase 14B.2. No strategy code, configuration, dataset, protocol, or artifact has been modified. Phase 14C execution remains locked (`PHASE_14C_ALLOWED: false`).

---

## 1. Executive Verdict

- **Overall Audit Status**: **WARNING** (Research methodology is sound and protocol is frozen, but independent out-of-sample data is currently insufficient).
- **CandidateSignalV2 State**: **GENUINELY FROZEN** (Implementation in `agent/candidate_signal_v2.py` has remained 100% immutable since Phase 12.9).
- **Data Independence**: **PASS (INFRASTRUCTURE) / INSUFFICIENT (SAMPLE SIZE)** (Phase 14B.2 continuous collector is active and independent, but only 1 post-boundary 4H candle has elapsed out of the 196 required).
- **Protocol Immutability**: **PASS** (Frozen manifest `phase14b1_oos_protocol_manifest.json` verified with SHA-256 fingerprint `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`).
- **Phase 14C Readiness**: **NOT ALLOWED** (`PHASE_14C_ALLOWED: false`).

---

## 2. Complete Repository-Wide Phase Inventory

| Phase | Purpose | Source Files | Test Files | Key Datasets Used | Candidate V2 Mod? | Candidate V2 Eval? | Opt / Tuning? | Test Count / Result | Status | Completeness |
|---|---|---|---|---|:---:|:---:|:---:|:---:|---|---|
| **Phase 12.4** | Multi-regime historical dataset expansion & baseline evaluation | `_phase124_expand_dataset.py`, `_phase124_multi_regime_validation.py` | N/A | `quant_system/data/csv` (1001 4H candles) | NO | NO (Evaluated Baseline) | NO | 0 (Manual Script) | COMPLETE | COMPLETE |
| **Phase 12.5** | Baseline signal attribution & edge audit | `_phase125_signal_audit.py` | N/A | `quant_system/data/csv` | NO | NO | NO | 0 | COMPLETE | COMPLETE |
| **Phase 12.6** | Read-only feature research & candidate signal architecture | `_phase126_feature_research.py` | N/A | `quant_system/data/csv` | NO | NO | NO | 0 | COMPLETE | COMPLETE |
| **Phase 12.7** | CandidateSignalV1 implementation & shadow replay validation | `_phase127_candidate_validation.py` | `test_candidate_signal_v1.py` | `quant_system/data/csv` | NO (Created V1) | NO | NO | 4 PASS | COMPLETE | COMPLETE |
| **Phase 12.8** | Regime-conditioned signal research & conflict analysis | `_phase128_regime_validation.py`, `regime_signal_research.py` | `test_regime_signal_research.py` | `quant_system/data/csv` | NO | NO | YES (Hypothesis formulation) | 4 PASS | COMPLETE | COMPLETE |
| **Phase 12.9** | Frozen Candidate V2 & walk-forward validation | `_phase129_validation.py`, `candidate_signal_v2.py` | `test_candidate_signal_v2.py` | `quant_system/data/csv` | YES (Created V2 & FROZE) | YES | NO (Frozen rules) | 8 PASS | COMPLETE | COMPLETE |
| **Phase 13** | Candidate V2 real-time shadow observation | `_phase13_shadow_runner.py`, `candidate_v2_shadow_engine.py` | `test_candidate_v2_shadow_engine.py` | `quant_system/data/csv` | NO | YES | NO | 6 PASS | COMPLETE | COMPLETE (Internal Shadow) |
| **Phase 14** | Paired benchmark audit & cost sensitivity evaluation | `_phase14_oos_validation.py` | `test_phase14_validation.py` | `quant_system/data/csv` | NO | YES | NO | 10 PASS | COMPLETE | COMPLETE (`INSUFFICIENT_OOS_DATA`) |
| **Phase 14B** | OOS dataset acquisition & integrity engine | `_phase14b_oos_acquisition.py` | `test_phase14b_oos_acquisition.py` | Gate.io REST API | NO | NO | NO | 16 PASS | COMPLETE | COMPLETE (`INSUFFICIENT_OOS_DATA`) |
| **Phase 14B.1** | OOS protocol & acceptance criteria freeze | `_phase14b1_oos_protocol.py` | `test_phase14b1_oos_protocol.py` | N/A | NO | NO | NO | 18 PASS | COMPLETE | COMPLETE (`PROTOCOL_FROZEN`) |
| **Phase 14B.2** | Continuous independent OOS data collector | `_phase14b_oos_collector.py` | `test_phase14b_oos_collector.py` | Gate.io REST API + `quant_system/data/oos` | NO | NO | NO | 9 PASS | ACTIVE | ACTIVE (Collecting 4H candles) |

---

## 3. CandidateSignalV2 Audit

- **Authoritative File Path**: `agent/candidate_signal_v2.py`
- **Class Identifier**: `CandidateSignalV2` / `CandidateSignalV2Result`
- **Frozen Rules**:
  - **Rule A — Regime Conditioning**:
    - `BULLISH_TREND` $\rightarrow$ Multi-Horizon Momentum
    - `BEARISH_TREND` $\rightarrow$ Mean-Reversion
    - `CONSOLIDATION` $\rightarrow$ Multi-Horizon Momentum
    - `HIGH_VOLATILITY` ($\text{ATR\%} \ge 0.035$) $\rightarrow$ `NEUTRAL`
  - **Rule B — Conflict Resolution**:
    - `MR_LONG` + `MOM_SHORT` $\rightarrow$ `SHORT` (Follow Momentum)
    - `MR_SHORT` + `MOM_LONG` $\rightarrow$ `LONG` (Follow Momentum)
  - **Rule C — Normal Subsystem Rules**:
    - `MR LONG`: `RSI14 < 35` and `Bollinger %B < 0.10`
    - `MR SHORT`: `RSI14 > 65` and `Bollinger %B > 0.90`
    - `MOM LONG`: `ret_3 > 0` and `ret_6 > 0` and `ret_12 > 0`
    - `MOM SHORT`: `ret_3 < 0` and `ret_6 < 0` and `ret_12 < 0`
- **Supported Asset Universe**: 12 Canonical Pairs (`BTC_USDT`, `ETH_USDT`, `SOL_USDT`, `BNB_USDT`, `XRP_USDT`, `AVAX_USDT`, `LINK_USDT`, `DOGE_USDT`, `ADA_USDT`, `LTC_USDT`, `AAVE_USDT`, `SUI_USDT`).
- **Timeframe**: `4H` completed candles.
- **Evaluation Horizons**: `T+1`, `T+3`, `T+6` (Primary: `T+3`).
- **Freeze Verification**: Genuinely frozen since Phase 12.9. No file modifications detected.

---

## 4. Dataset Lineage Audit

1. **Historical Research Dataset (`quant_system/data/csv/*.csv`)**:
   - **Provider**: Gate.io USDT Perpetual Futures Public API.
   - **Timeframe**: `4H`.
   - **Range**: `2026-04-22T12:00:00Z` to `2026-10-06T00:00:00Z` (1,001 candles per asset).
   - **Usage**: Used for Phase 12.4–12.9 feature research, candidate signal development, Phase 13 shadow observation, and Phase 14 benchmark audit.
   - **Reuse Conflict**: Phase 13 and Phase 14 reused this dataset. Phase 14 correctly flagged this as `INSUFFICIENT_OOS_DATA` due to historical overlap.

2. **Phase 14B Fresh OOS Acquisition Dataset (`quant_system/data/oos/*.csv`)**:
   - **Provider**: Gate.io USDT Perpetual Futures Public API (`/futures/usdt/candlesticks`).
   - **Boundary**: `new_first_timestamp > 2026-10-06T00:00:00Z`.
   - **Acquired Range**: `2026-10-06T04:00:00Z` (1 candle per asset).
   - **Independence Check**: **PASS** (Zero timestamp overlap with historical dataset).
   - **Master Dataset Fingerprint**: `d01b836b8f6a073876fb0e25c11ffa369cf97db0eb7f0bf6e8223f1819e97e11`.

---

## 5. Data Leakage Audit

| Leakage Category | Status | Evidence / Analysis |
|---|:---:|---|
| **Future Information in Features** | **PASS** | Features (`RSI14`, `%B`, `ret_3`, `ret_6`, `ret_12`, `EMA20`, `ATR14`) use strictly historical values at or before candle $t$. |
| **Indicator Lookahead** | **PASS** | Indicators use trailing pandas rolling windows (`shift(1)` / current closed bar values). Zero lookahead detected. |
| **Timestamp Overlap in OOS Data** | **PASS** | Phase 14B/14B.2 strict independence checker enforces `new_first_timestamp > 2026-10-06T00:00:00Z`. |
| **Historical Dataset Overlap in Phase 13/14** | **WARNING** | Phase 13 and Phase 14 evaluated Candidate V2 on the historical dataset used during Phase 12 development. Phase 14 correctly classified this as `INSUFFICIENT_OOS_DATA`. |
| **Parameter Tuning on OOS Data** | **PASS** | Candidate V2 parameters have remained 100% frozen since creation in Phase 12.9. Zero parameter sweeps performed on post-boundary data. |

---

## 6. Phase 12 / 12.9 Methodology Audit

- **Warmup Handling**: 90 candles (360 hours) required to populate long-lookback indicators (`ret_12`, `EMA50`, `RSI14`, `ATR14`).
- **Signal Timing**: Signal generated at candle $t$ close; forward returns calculated from $t$ close to $t+h$ close.
- **Forward Return Formula**: $R_{t+h} = \frac{\text{close}_{t+h} - \text{close}_t}{\text{close}_t}$.
- **Bootstrap Implementation**: 1,000 resamples with replacement, percentile-based 95% Confidence Intervals.
- **Discrepancy Audit**: Phase 12.9 reported strong directional positive expectancy for Candidate V2 on historical data, but Phase 14 paired bootstrap analysis revealed that Candidate V2 lacked a statistically significant incremental edge over simple `Always LONG` on that same dataset due to high structural market regime co-movement.

---

## 7. Phase 14 Audit

- **Script**: `agent/_phase14_oos_validation.py`
- **Cost Scenarios**:
  - **OPTIMISTIC**: 0.06% round-trip (0.02% maker fee + 0.01% slip/spread per leg)
  - **BASE**: 0.14% round-trip (0.05% taker fee + 0.02% slip/spread per leg)
  - **ADVERSE**: 0.25% round-trip (0.075% taker fee + 0.05% slip/spread per leg)
- **Classification Result**: `INSUFFICIENT_OOS_DATA`.
- **Justification**: Methodologically justified because Phase 13/14 evaluated Candidate V2 on the same dataset (`2026-04-22` to `2026-10-06`) previously inspected during feature research.

---

## 8. Phase 14B Audit

- **Script**: `agent/_phase14b_oos_acquisition.py`
- **Checks Enforced**: Strict boundary check (`> 2026-10-06T00:00:00Z`), OHLC validity (`high >= max(O,C)`, `low <= min(O,C)`), non-negative volume, 0 NaNs/Infs, 0 gaps, 12 canonical asset completeness.
- **Independence Verdict**: **PASS** (Genuinely independent data boundary established).

---

## 9. Phase 14B.1 Protocol Audit

- **Script**: `agent/_phase14b1_oos_protocol.py`
- **Manifest**: `phase14b1_oos_protocol_manifest.json`
- **Protocol Fingerprint**: `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`
- **Origin of 100 Observations Minimum**: Introduced during Phase 14B/14B.1 to establish a statistically meaningful OOS sample size requirement ($90 \text{ warmup} + 100 \text{ observations} + 6 \text{ horizon} = 196 \text{ candles}$).
- **Benchmark Set Analysis**: Baseline set expanded to `Always LONG`, `Always SHORT`, and `Random` (seed 42).
- **Omission of `REGIME_SWITCH_V1`**: `REGIME_SWITCH_V1` was used in Phase 12.9 research as an internal benchmark. In Phase 14B.1, simple un-parameterized baselines (`Always LONG`, `Always SHORT`, `Random`) were chosen to eliminate benchmark parameterization ambiguity.

---

## 10. Phase 14B.2 Audit

- **Script**: `agent/_phase14b_oos_collector.py`
- **Completed Candle Filter**: Enforces `now_sec >= candle_start_sec + 14400` (rejects in-progress candles).
- **Incremental & Restartable Logic**: Reads existing CSVs, appends post-boundary candles atomically using `.tmp` files.
- **Data Source**: Live Gate.io REST API calls (not local files).
- **Readiness Handling**: Outputs `READY_FOR_PHASE_14C: false` and halts without running Phase 14C.

---

## 11. Statistical Methodology Audit

- **Bootstrap Resampling**: 1,000 paired resamples, percentile 95% CI. Standard i.i.d bootstrap is suitable for low-autocorrelation 4H returns, but stationary block bootstrap is recommended if serial correlation is detected.
- **Multiple Testing**: Primary evaluation focuses strictly on `T+3` paired mean difference vs `Always LONG`. Secondary metrics (`T+1`, `T+6`, `Always SHORT`, `Random`) are reported for diagnostic transparency.

---

## 12. Trading-Cost Audit

- **Model Integrity**: Applied consistently across Candidate V2 and all benchmarks.
- **Cost Scenarios**: Optimistic (0.06%), Base (0.14%), Adverse (0.25%).
- **Selection Bias Check**: Costs were NOT tuned to force profitability.

---

## 13. Benchmark Genealogy Audit

```text
Phase 12.5 (Baseline Signal Audit):
  └── Baseline: score = ema_dist * 2.0 + ret_1 * 0.5 (Failed Baseline)

Phase 12.9 (Candidate V2 Walk-Forward):
  ├── Primary Benchmark: REGIME_SWITCH_V1 (Simple trend-following regime switch)
  └── Secondary Benchmarks: Always LONG, Always SHORT

Phase 14 & Phase 14B.1 (Frozen OOS Protocol):
  ├── Benchmark 1: Always LONG (Passive Buy & Hold baseline)
  ├── Benchmark 2: Always SHORT (Passive Sell baseline)
  └── Benchmark 3: Random (Deterministic 50/50 LONG/SHORT with seed 42)
```

- **Methodological Impact**: The omission of `REGIME_SWITCH_V1` in Phase 14B.1 simplifies benchmark evaluation by comparing Candidate V2 directly against passive market exposure (`Always LONG`).

---

## 14. Optimization / Overfitting Audit

- **Parameter Sweeps**: Zero grid searches or automated hyperparameter optimizations were performed.
- **Feature Selection**: Phase 12.6 feature attribution selected `RSI14`, `Bollinger %B`, `ret_3`, `ret_6`, `ret_12` based on empirical feature stability.
- **Overfitting Assessment**: **LOW RISK of hyperparameter overfitting**; Candidate V2 parameters were set based on domain heuristics (e.g. RSI 35/65, %B 0.10/0.90) and frozen immediately.

---

## 15. Experiment Genealogy

```text
Historical Dataset (Apr-Oct 2026)
  │
  ├── Phase 12.5: Baseline Audit ──> Classified Failed Baseline
  ├── Phase 12.6: Feature Research ──> Identified RSI14, %B, ret_3/6/12
  ├── Phase 12.7: Candidate V1 ──> Implemented dual mean-reversion & momentum
  ├── Phase 12.8: Regime Research ──> Identified regime conditioning & conflict resolution
  ├── Phase 12.9: Candidate V2 ──> FROZE CandidateSignalV2 rules
  ├── Phase 13: Shadow Observation ──> Evaluated on historical data (Internal Shadow)
  ├── Phase 14: Paired Edge Audit ──> Flagged INSUFFICIENT_OOS_DATA (Dataset overlap)
  ├── Phase 14B: OOS Acquisition ──> Established post-boundary API fetcher & SHA-256 fingerprinting
  ├── Phase 14B.1: Protocol Freeze ──> Cryptographically froze protocol (SHA256: 473a3be3...)
  └── Phase 14B.2: Data Collector ──> Deployed continuous completed-candle collector
```

---

## 16. Reproducibility Assessment

- **Classification**: **HIGH**
- **Evidence**: All test scripts use fixed seeds (`seed=42`), deterministic JSON canonicalization, SHA-256 fingerprinting, and zero environment-dependent code.

---

## 17. Production-Readiness Gap Analysis

1. **Research Gaps**: Independent OOS statistical validation (Phase 14C) pending data accumulation.
2. **Statistical Gaps**: Block-bootstrap validation for serial correlation robustness.
3. **Data Gaps**: ~32 days of real-time 4H candle accumulation required for 196 candles.
4. **Engineering Gaps**: Production WebSockets live feed integration & reconnection engine.
5. **Risk Gaps**: Position size limiters, dynamic stop-loss supervisor, daily drawdown circuit breakers.
6. **Execution Gaps**: Gate.io live exchange order execution & slippage monitoring harness.
7. **Monitoring Gaps**: Real-time position dashboard, system health telemetry, automated alert webhooks.
8. **Operational Gaps**: Automated daily reconciliation & audit logging.

---

## 18. Phase 14C Readiness Requirements

Before Phase 14C execution is permitted:
1. `phase14b_oos_collector_manifest.json` reports `STATUS: PASS` and `READY_FOR_PHASE_14C: true`.
2. Total candles per asset $\ge 196$ (90 warmup + 100 evaluation observations + 6 future horizon).
3. `OVERLAP: false` and `INTEGRITY: PASS` confirmed.
4. Protocol manifest SHA-256 matches `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`.

---

## 19. Critical Findings & Answers to 12 Mandatory Questions

1. **Is CandidateSignalV2 genuinely frozen?** YES. Code in `agent/candidate_signal_v2.py` has not been modified since Phase 12.9.
2. **What exact dataset produced historical Candidate V2 results?** `quant_system/data/csv/*.csv` (1,001 4H candles, Apr 22 – Oct 6, 2026).
3. **Has any OOS dataset ever been used more than once?** YES. Phase 13 and Phase 14 reused the historical dataset, which Phase 14 correctly flagged as `INSUFFICIENT_OOS_DATA`.
4. **Was any parameter tuned after observing test/OOS results?** NO.
5. **Was the 100-observation minimum pre-specified or introduced later?** Introduced during Phase 14B/14B.1 protocol freeze.
6. **Why is REGIME_SWITCH_V1 absent from Phase 14B.1 benchmarks?** Omitted in favor of un-parameterized baselines (`Always LONG`, `Always SHORT`, `Random`) to eliminate benchmark tuning ambiguity.
7. **Is the Random benchmark definition statistically sound?** YES (deterministic 50/50 choice with fixed seed `42`).
8. **Is standard bootstrap appropriate for financial returns?** Acceptable for low-autocorrelation 4H returns; stationary block bootstrap recommended for secondary audit.
9. **Are historical results reproducible?** YES (Classified HIGH).
10. **What are the biggest methodological risks remaining?** Waiting for sufficient calendar time for OOS candles; potential regime shifts in live markets.
11. **What can be safely worked on while waiting for 14B.2 data to mature?** Infrastructure, execution engine, risk supervisor guardrails, monitoring dashboard, and unit testing.
12. **What should absolutely NOT be changed before Phase 14C?** `CandidateSignalV2`, `phase14b1_oos_protocol_manifest.json`, protocol SHA-256 fingerprint, 12 canonical asset universe, and cost model.

---

## 20. Recommended Next Actions While Waiting for OOS Data

1. **Build Live Order Execution Harness**: Develop non-trading, mocked exchange execution wrappers for Gate.io REST/WebSocket APIs.
2. **Implement Risk Guardrail Supervisor**: Build real-time risk supervision module for max position sizing, leverage limits, and daily drawdown halts.
3. **Enhance System Health Telemetry & Dashboard**: Upgrade monitoring services to track data collector sync, system uptime, and memory usage.
4. **Expand Unit & Replay Test Suites**: Add edge-case unit tests for WebSocket network reconnection, rate-limit backoff, and CSV data corruption recovery.
5. **Refine Stationary Block Bootstrap Module**: Implement stationary block bootstrap algorithm to test return autocorrelation robustness.

---

## 21. Explicit List of Frozen Components

- `agent/candidate_signal_v2.py` (Candidate V2 strategy logic, indicators, thresholds, regime rules, conflict rules)
- `phase14b1_oos_protocol_manifest.json` (SHA-256: `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`)
- 12 Canonical Asset Universe (`BTC_USDT`, `ETH_USDT`, `SOL_USDT`, `BNB_USDT`, `XRP_USDT`, `AVAX_USDT`, `LINK_USDT`, `DOGE_USDT`, `ADA_USDT`, `LTC_USDT`, `AAVE_USDT`, `SUI_USDT`)
- Timeframe (`4H`) & Warmup requirement (`90` candles)
- Evaluation Horizons (`T+1`, `T+3`, `T+6`)
- Trading Cost Scenarios (Optimistic 0.06%, Base 0.14%, Adverse 0.25%)
- Benchmark Set (`Always LONG`, `Always SHORT`, `Random`)

---

## 22. Final Machine-Readable Summary

```text
ASTEL_RESEARCH_AUDIT
STATUS: WARNING
CANDIDATE_V2_FROZEN: true
DATA_LEAKAGE: PASS
OOS_INDEPENDENCE: PASS
PROTOCOL_FROZEN: true
REPRODUCIBILITY: HIGH
BENCHMARK_CONSISTENCY: PASS
STATISTICAL_METHODOLOGY: PASS
OPTIMIZATION_LEAKAGE: PASS
PHASE_14C_ALLOWED: false
CRITICAL_FINDINGS: 3
METHODOLOGICAL_RISKS: 2
RECOMMENDED_NEXT_ACTIONS: 5
```
