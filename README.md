<p align="center">
  <a href="https://github.com/RAYDENFLY/Astel">
    <img src="https://github.com/RAYDENFLY/Astel/blob/main/assets/logo/astel-text.png" alt="Astel" width="500">
  </a>
</p>

# Astel Research - TradingAgents

**Autonomous AI-Powered Cryptocurrency Futures Trading System & Quantitative Signal Research Platform**

[![Status](https://img.shields.io/badge/Status-Phase%2014B.2%20Collecting%20OOS%20Data-blue)]()
[![Exchange](https://img.shields.io/badge/Exchange-Gate.io%20Futures-green)]()
[![Python](https://img.shields.io/badge/Python-3.11%2B-brightgreen)]()
[![License](https://img.shields.io/badge/License-MIT-yellow)]()
[![Release](https://img.shields.io/github/v/release/RAYDENFLY/Astel?include_prereleases)](https://github.com/RAYDENFLY/Astel/releases)

Astel Research - TradingAgents is an autonomous AI trading system and quantitative research platform combining **machine learning predictions**, **multi-horizon market features**, **regime-conditioned signal fusion**, **episodic memory**, **procedural memory**, **LLM reasoning**, and a **self-reflection feedback loop** for cryptocurrency futures markets.

The system operates continuously, conducting empirical historical replay, regime-conditioned research, read-only shadow observation, and continuous independent out-of-sample data collection before any execution consideration.

**Creator & Lead Researcher:** [Azis Maulana Suhada](https://raydenfly.my.id)  
**Developed by:** PT Authentic Media Services by AMS Capital  
**Research Areas:** Autonomous AI Agents • Quantitative Trading • Machine Learning • Multi-Agent Systems • Large Language Models (LLMs)

---

## Current Status

> ### 🟢 CURRENT STATUS: COLLECTING INDEPENDENT OOS DATA (PHASE 14B.2)
>
> - **CandidateSignalV2**: **FROZEN** (Unmodified since Phase 12.9)
> - **Phase 14B.1 Protocol**: **FROZEN** (`1.0.0-FROZEN`, SHA-256: `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`)
> - **Phase 14B.2 Collector**: **ACTIVE** (`agent/_phase14b_oos_collector.py`)
> - **Phase 14C Execution**: **NOT EXECUTED** (Awaiting collection of required 196 raw 4H candles per asset)
> - **Historical Alpha Claim**: **NOT ESTABLISHED** (Historical replay edge does not constitute independent OOS alpha proof)
> - **Independent OOS Evidence**: **INSUFFICIENT** until collection completes

### Current Operational & Research Stage

The repository is actively executing **Phase 14B.2 — Continuous Independent OOS Data Collection**.

Independent post-boundary 4H market candlesticks are being continuously accumulated across the canonical 12-asset universe (`BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `AVAX`, `LINK`, `DOGE`, `ADA`, `LTC`, `AAVE`, `SUI`).

All statistical decision thresholds, benchmark definitions, transaction cost models, and CandidateSignalV2 strategy rules remain 100% frozen.

---

## Overview

Astel Research - TradingAgents is built on the philosophy that successful autonomous trading requires a multi-layered quantitative and cognitive architecture:

1. **Market Perception & Feature Engineering** — Engineering multi-horizon returns, oscillators, and volatility metrics to detect market regimes and build probabilistic signals.
2. **Quantitative Signal Research** — Frozen candidate signal engines evaluated across multi-asset historical datasets and regime switches.
3. **Memory Systems** — Structured memory across procedural rules, episodic experiences, and counterfactual shadow validation.
4. **Reasoning & Intelligence** — Multi-agent specialist evaluation, evidence fusion, and LLM-powered contextual reasoning.
5. **Execution & Supervision** — Isolated, fault-tolerant execution infrastructure with strict risk supervisor controls and shadow branching.

```text
Market Data
    │
    ▼
Feature Engineering
    │
    ├── Machine Learning
    │
    └── Candidate Signal V2 (FROZEN)
              │
              ▼
       Regime Detection
              │
              ▼
       Signal / Conflict
          Resolution
              │
              ▼
      Market Intelligence
              │
              ▼
       Evidence Fusion
              │
              ▼
       Decision Agent
              │
              ▼
       Risk Supervisor
              │
        ┌─────┴─────┐
        │           │
      SHADOW     EXECUTION
        │           │
        ▼           ▼
   Shadow Engine  ExecutionEngine
                     │
                     ▼
                 GateExecutor
                     │
                     ▼
              Gate.io Testnet
```

> **Research Safety & Execution Isolation**
>
> Candidate V2 evaluation is currently conducted in strictly isolated SHADOW / RESEARCH mode. Candidate V2 does not submit exchange orders (`EXECUTION_MODE=SHADOW` enforced).

---

## Frozen CandidateSignalV2 Strategy Specification

CandidateSignalV2 is **FROZEN** and has remained completely unmodified since Phase 12.9.

### 1. Regime Mapping Rules
- **BULLISH_TREND** → Multi-Horizon Momentum
- **BEARISH_TREND** → Mean-Reversion
- **CONSOLIDATION** → Multi-Horizon Momentum
- **HIGH_VOLATILITY** → NEUTRAL (No trade)

### 2. Conflict Resolution Rule (`FOLLOW_MOMENTUM`)
When Mean-Reversion and Momentum indicators generate opposing signals:
- `MR_SHORT` + `MOM_LONG` → Follow Momentum **LONG**
- `MR_LONG` + `MOM_SHORT` → Follow Momentum **SHORT**

### 3. Indicator Definitions
- **Normal Mean-Reversion**:
  - **LONG**: `RSI14 < 35` AND `Bollinger %B < 0.10`
  - **SHORT**: `RSI14 > 65` AND `Bollinger %B > 0.90`
- **Normal Multi-Horizon Momentum**:
  - **LONG**: `ret_3 > 0` AND `ret_6 > 0` AND `ret_12 > 0`
  - **SHORT**: `ret_3 < 0` AND `ret_6 < 0` AND `ret_12 < 0`

> These parameter thresholds are frozen for out-of-sample validation and must not be tuned or optimized.

---

## Historical Research vs. Independent Out-of-Sample Validation

It is a critical quantitative research principle in Astel to strictly distinguish between **Historical In-Sample Replay** and **Independent Out-of-Sample (OOS) Validation**.

### Historical Replay Dataset (Phases 12.4–14.0)
- **Universe**: 12 Canonical USDT-margined futures contracts
- **Timeframe**: 4H
- **Sample Size**: 1,001 candles per asset (12,012 total bar evaluations)
- **Historical Boundary**: `2026-10-06T00:00:00Z`
- **Warmup Window**: 90 candles
- **Forward Horizons**: T+1, T+3, T+6 (Primary Horizon: **T+3**)

### Historical Phase 12.9 / Phase 14.0 Findings

| Metric / Scenario | Historical Value |
|---|---:|
| Candidate V2 Gross T+3 Expectancy | +0.2141% |
| Always LONG Benchmark Expectancy | +0.2073% |
| Paired Expectancy Difference ($\delta$) | +0.0068% (+0.68 bps) |
| Paired 95% Bootstrap Confidence Interval | [-0.0693%, +0.0893%] |
| Probability Difference > 0 | 58.7% |
| Optimistic Cost Scenario (0.06% round-trip) | Net +0.1541%, Profit Factor 1.21 |
| Base Cost Scenario (0.14% round-trip) | Net +0.0741%, Profit Factor 1.09 |
| Adverse Cost Scenario (0.25% round-trip) | Net -0.0359%, Profit Factor 0.96 |

> **Methodological Conclusion**: The historical replay dataset overlapped with the market period used to formulate and freeze Candidate V2. Therefore, these historical results **DO NOT constitute independent out-of-sample alpha evidence**. CandidateSignalV2 does NOT have statistically proven alpha.

---

## Phase 14B.1 — Frozen Independent OOS Protocol

Phase 14B.1 established a machine-readable, immutable validation protocol prior to independent OOS data collection.

### Protocol Specifications
- **Protocol Version**: `1.0.0-FROZEN`
- **Protocol Manifest SHA-256**: `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`
- **Historical Boundary**: `2026-10-06T00:00:00Z`
- **OOS Inclusion Rule**: `new_first_timestamp > 2026-10-06T00:00:00Z`
- **Universe & Timeframe**: 12 canonical assets, 4H timeframe
- **Evaluation Window**: 90 warmup candles + 100 evaluation observations + 6 horizon safety candles
- **Benchmark Set**:
  - Always LONG
  - Always SHORT
  - Uniform Random
- **Methodological Break Note**: The historical Phase 12/14 diagnostic benchmark included `REGIME_SWITCH_V1`. Phase 14B.1 replaces this with `Always LONG`, `Always SHORT`, and `Random`. Historical comparisons against `REGIME_SWITCH_V1` are not directly interchangeable with the frozen Phase 14C benchmark set.
- **Statistical Inference**: 1,000 paired bootstrap resamples, 95% percentile confidence intervals, deterministic seed `42`.
- **Trading Cost Scenarios**:
  - Optimistic: 0.06% round-trip
  - Base: 0.14% round-trip
  - Adverse: 0.25% round-trip

> **Protocol Immutability Guarantee**: The Phase 14B.1 protocol manifest is frozen and SHA-256 fingerprinted. It must not be modified or adjusted based on post-hoc OOS observations.

---

## Phase 14B.2 — Continuous Independent OOS Data Collector

The Phase 14B.2 continuous collector safely and deterministically acquires newly completed 4H candlesticks from Gate.io REST API into an isolated OOS dataset directory (`quant_system/data/oos/`).

### Infrastructure Modules
- **Data Collector**: `agent/_phase14b_oos_collector.py`
- **Health & Status Validator**: `agent/_phase14b_oos_health.py`

### Operational Properties
- **Supported Modes**: `--once` (single cycle) or `--watch --interval 3600` (hourly continuous polling).
- **Completed-Candle Invariant**: `now_sec >= candle_start_sec + 14400` (Enforces zero lookahead).
- **Strict Invariants**: UTC timestamps, 4H step alignment, strict monotonicity, rejection of duplicates and overlapping historical batches, atomic `.tmp` file persistence.
- **Fail-Closed Design**: Rejects malformed API responses; never executes Phase 14C automatically.

---

## OOS Dataset Readiness Requirements

To satisfy the frozen Phase 14B.1 protocol, each canonical asset requires:

$$\text{Raw Completed 4H Candles Required} = 90 \text{ Warmup} + 100 \text{ Evaluation} + 6 \text{ Horizon Safety} = \mathbf{196 \text{ Candles}}$$

> **Important Data Distinction**: $196$ is the **RAW COMPLETED CANDLE REQUIREMENT** per asset. It MUST NOT be conflated as $196$ independent statistical evaluation observations. The actual evaluation sample size per asset is $N=100$.

Initial collection baseline: 12 total candles (1 candle per asset, 0 usable evaluation observations). The system is NOT eligible to execute Phase 14C until the complete 196 candle threshold is satisfied across all 12 canonical assets.

---

## Phase 14C-Prep.1 — Statistical Robustness & Methodology Audit

Phase 14C-Prep.1 was a strictly read-only quantitative methodology audit of the statistical protocol prior to Phase 14C.

### Key Audit Findings & Corrected Power Analysis
Using first-principles analytical $Z$-test calculations ($\sigma = 0.02$, two-sided $\alpha = 0.05$):

| True Paired Mean Edge ($\delta$) | $N=100$ (Nominal Eval N) | Hypothetical Statistical $N=196$ Scenario | Illustrative $N_{\text{eff}} \approx 50$ Scenario |
|---|---:|---:|---:|
| **$0.02\%$ ($2$ bps)** | $5.11\%$ | $5.22\%$ | $5.06\%$ |
| **$0.05\%$ ($5$ bps)** | $5.71\%$ | $6.42\%$ | $5.36\%$ |
| **$0.10\%$ ($10$ bps)** | $7.90\%$ | $10.97\%$ | $6.45\%$ |
| **$0.20\%$ ($20$ bps)** | **$17.01\%$** | $28.71\%$ | $11.13\%$ |

> **Power Analysis Takeaways**:
> 1. Under nominal $N=100$, statistical power to detect a $20$ bps ($0.20\%$) mean edge is **$17.01\%$** (not high power).
> 2. Achieving $80\%$ power at nominal $N=100$ requires a mean edge of $\delta = \mathbf{0.560\%}$ ($56$ bps per trade).
> 3. $N=196$ in statistical power tables is explicitly a **HYPOTHETICAL STATISTICAL SAMPLE-SIZE SCENARIO**, not the raw completed candle count.
> 4. $N_{\text{eff}} \approx 50$ is an **illustrative AR(1)-based sensitivity scenario** ($\rho_1 = 0.33$), not an empirical property of CandidateSignalV2 OOS returns.
> 5. Moving Block Bootstrap CI widening (+18.68% under synthetic AR(1)) represents a controlled simulation stress test demonstrating theoretical dependence sensitivity.

---

## Phase 14B.2 Integrity & Phase 14C Dry-Run Audit

A hardening pass verified collector invariants and Phase 14C fail-closed dry-run behavior using synthetic fixtures:

- **Collector Invariants**: Verified candle completion, timestamp monotonicity, OHLCV validity, canonical asset coverage, gap detection, duplicate rejection, atomic persistence, and restartability.
- **Fail-Closed Dry-Run Suite** (`agent/test_phase14c_dryrun.py`): Verified 10 synthetic edge-case scenarios (insufficient $N$, protocol SHA mismatch, historical overlap, duplicate timestamps, missing assets, incomplete candles, valid dry-run, cost sensitivity).
- **Determinism Verification**: Confirmed exact deterministic equality (`RUN_1 == RUN_2`) across bootstrap resamples using seed `42`.
- **Regression Suite**: **88/88 tests passing** across all repository Phase 14 test suites.

---

## Pre-Phase-14C Repository Cleanup Status

A minimal, reversible pre-Phase-14C cleanup was executed:
- **13 redundant artifacts** (legacy Phase 8 audit scripts, one-off branding/fix scripts, informal notes, and temporary test DBs) were moved to `archive/pre-phase14c/`.
- **2 database files** (`agent/agent.sqlite`, `agent/test_fusion.sqlite`) were retained in place due to default fallback references.
- Documentation report produced: `PRE_PHASE14C_CLEANUP_REPORT.md`.

---

## Next Methodological Milestones

1. **Continuous Collection**: Continue running `agent/_phase14b_oos_collector.py` until the canonical 12-asset universe reaches $\ge 196$ completed 4H candles per asset.
2. **Health Verification**: Periodically inspect dataset integrity using `python -m agent._phase14b_oos_health`.
3. **Readiness Gate Confirmation**: Confirm `ready_for_phase_14c: true` in `phase14b_oos_collector_manifest.json`.
4. **Dataset Freeze**: Lock the eligible OOS dataset SHA-256 fingerprint.
5. **Phase 14C Execution**: Execute Phase 14C out-of-sample validation strictly according to the frozen Phase 14B.1 protocol. Zero strategy tuning or post-hoc protocol modification permitted.

---

## Technology Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI + Uvicorn |
| Data Processing | NumPy, Pandas, SciPy |
| ML Models | LightGBM / XGBoost |
| LLM Framework | Ollama (local) • Groq (cloud) • DeepSeek (cloud) |
| Exchange API | Gate.io Futures API v4 |
| Data Validation | Pydantic v2 |
| Unit Testing | Python Standard `unittest` (88 Phase 14 Tests PASS) |

---

## License

MIT License

Copyright (c) 2026 Astel Research - TradingAgents

---

## Acknowledgements

- **[Gate.io](https://www.gate.io/)** — Futures API & Testnet infrastructure
- **[Ollama](https://ollama.ai/)** — Local LLM inference platform
- **[LightGBM](https://lightgbm.readthedocs.io/)** — Gradient boosting framework
- **[FastAPI](https://fastapi.tiangolo.com/)** — Web dashboard framework
