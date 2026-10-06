<p align="center">
  <a href="https://github.com/RAYDENFLY/Astel">
    <img src="https://github.com/RAYDENFLY/Astel/blob/main/assets/logo/astel-text.png" alt="Astel" width="500">
  </a>
</p>

# Astel Research - TradingAgents

**Autonomous AI-Powered Cryptocurrency Futures Trading System & Quantitative Signal Research Platform**

[![Status](https://img.shields.io/badge/Status-Phase%2013%20Shadow%20Observation-blue)]()
[![Exchange](https://img.shields.io/badge/Exchange-Gate.io%20Futures-green)]()
[![Python](https://img.shields.io/badge/Python-3.11%2B-brightgreen)]()
[![License](https://img.shields.io/badge/License-MIT-yellow)]()
[![Release](https://img.shields.io/github/v/release/RAYDENFLY/Astel?include_prereleases)](https://github.com/RAYDENFLY/Astel/releases)

Astel Research - TradingAgents is an autonomous AI trading system and quantitative research platform combining **machine learning predictions**, **multi-horizon market features**, **regime-conditioned signal fusion**, **episodic memory**, **procedural memory**, **LLM reasoning**, and a **self-reflection feedback loop** for cryptocurrency futures markets.

The system operates continuously, conducting empirical historical replay, regime-conditioned research, and read-only shadow observation to evaluate candidate signal architectures before any execution consideration.

**Creator & Lead Researcher:** [Azis Maulana Suhada](https://raydenfly.my.id)  
**Developed by:** PT Authentic Media Servicex  
**Research Areas:** Autonomous AI Agents • Quantitative Trading • Machine Learning • Multi-Agent Systems • Large Language Models (LLMs)

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
    └── Candidate Signal V2
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

> **Current Research Safety State**
>
> Candidate V2 validation is currently conducted in strictly isolated SHADOW mode. Phase 13 does not submit exchange orders. Production/Testnet execution is not enabled by the Candidate V2 research pipeline.

---

## Current Status

### Current Research Phase

**Phase 13 — Candidate V2 Real-Time Shadow Observation**

Status: **✅ Complete — Internal Shadow Validation**

Candidate V2 has been evaluated in a strictly isolated, read-only shadow framework using completed 4H candle observations across 12 assets.

**Important Operational Status**:
- Strategy rules remain completely frozen.
- Shadow execution only (`EXECUTION_MODE=SHADOW` enforced).
- No exchange orders submitted (0 GateExecutor / ExecutionEngine order calls).
- Candidate V2 is **NOT** production-ready.
- Candidate V2 is **NOT** independently out-of-sample validated yet.

### Phase 13 Headline Metrics

| Metric | Value |
|---|---:|
| Observed Assets | 12 |
| Timeframe | 4H |
| Historical Bar Evaluations | 10,920 |
| Active Candidate V2 Observations | 3,910 |
| Candidate V2 Coverage | 35.92% |
| Candidate V2 T+3 Expectancy | +0.2148% |
| Candidate V2 Directional Accuracy | 47.62% |
| Candidate V2 Profit Factor | 1.30 |
| Candidate V2 Payoff Ratio | 1.42 |
| Conflict FOLLOW_MOMENTUM Observations | 1,620 |
| Conflict FOLLOW_MOMENTUM T+3 Expectancy | +0.3440% |
| Conflict FOLLOW_MOMENTUM Profit Factor | 1.45 |
| MR_SHORT_MOM_LONG T+3 Expectancy / PF | +0.7299% / 2.00 |
| MR_LONG_MOM_SHORT T+3 Expectancy / PF | -0.0778% / 0.90 |
| Execution Safety Audit | PASS |
| Unit Test Suite | 14/14 PASS |

### Research Interpretation

> Phase 13 produced encouraging positive shadow/historical results, particularly for the conflict resolution path where momentum overrides mean-reversion signals. However, these results are not yet sufficient to establish independent statistical alpha because the observation dataset overlaps with the historical dataset used during Candidate V2 development and rule freezing.

---

## Research & Validation Status

The project follows a rigorous, multi-stage quantitative validation pipeline:

```text
Historical Research
      ↓
Signal Research
      ↓
Candidate V1
      ↓
Regime-Conditioned Research
      ↓
Candidate V2
      ↓
Internal Walk-Forward Validation
      ↓
Phase 13 Shadow Observation
      ↓
Phase 14 Independent OOS + Cost Audit
      ↓
Future Testnet Readiness Audit
```

The system strictly separates:
1. **Signal Discovery** — Identifying candidate market features without lookahead.
2. **Historical Validation** — Multi-regime historical replay across multi-month datasets.
3. **Shadow Observation** — Read-only, real-time observation of frozen candidate rules.
4. **Independent Out-of-Sample Validation** — Testing frozen rules on chronologically un-seen market periods.
5. **Transaction-Cost Validation** — Modeling fees, slippage, and spread drag.
6. **Testnet Readiness** — Verifying API connection stability and risk guards under zero live capital.
7. **Live Deployment Readiness** — Strict decision gates required before any live capital allocation.

Positive historical expectancy alone does not qualify the system for live execution.

---

## Quantitative Research Progress

Phase 12 transitioned Astel from a general autonomous trading architecture into a measurable, data-driven quantitative research pipeline.

### Phase 12-13 Key Findings

- **Multi-Asset Replay**: Expanded historical dataset to 12 assets, 4H timeframe, 12,000 candles total (~5.5 months), covering 43.11% Bullish, 44.62% Bearish, and 12.26% Consolidation regimes.
- **Directional Bias Audit**: Proved that initial 100% LONG bias in early phases was caused by short bullish sample windows rather than pipeline flaws.
- **Baseline Feature Audit**: Audited the initial heuristic formula (`ema_dist * 2.0 + ret_1 * 0.5`) and classified it as `NO_SIGNAL` / `MISLEADING_SIGNAL` due to unstable predictive relationships.
- **Candidate V1 Architecture**: Implemented `CandidateSignalV1` combining Mean-Reversion (`RSI14`, `Bollinger %B`) and Multi-Horizon Momentum (`ret_3`, `ret_6`, `ret_12`). Showed that requiring simultaneous agreement produced 0 high-consistency signals due to structural indicator contradiction (deep oversold dips naturally coincide with negative recent returns).
- **Regime-Conditioned Switching**: Identified that Mean-Reversion performs best in Bearish trends (60.25% accuracy), while Multi-Horizon Momentum excels in Bullish trends and Consolidation.
- **Frozen Candidate V2**: Developed `CandidateSignalV2` based on regime-conditioned switching and explicit conflict resolution (`FOLLOW_MOMENTUM`).

### Frozen Candidate V2 Architecture

**Regime Mapping**:
- **Bullish Trend** → Multi-Horizon Momentum
- **Bearish Trend** → Mean Reversion
- **Consolidation** → Multi-Horizon Momentum
- **High Volatility** → Neutral

**Conflict Resolution Rule**:
When Mean-Reversion and Momentum conflict:
- `MR_SHORT` + `MOM_LONG` → follow momentum **LONG**
- `MR_LONG` + `MOM_SHORT` → follow momentum **SHORT**

**Signal Definitions**:
- **Mean Reversion**: `RSI14 < 35 & %B < 0.10` → LONG; `RSI14 > 65 & %B > 0.90` → SHORT.
- **Momentum**: `ret_3 > 0 & ret_6 > 0 & ret_12 > 0` → LONG; `ret_3 < 0 & ret_6 < 0 & ret_12 < 0` → SHORT.

> These rules are frozen for validation and should not be interpreted as proven optimal parameters.

---

## Phase 13 — Candidate V2 Shadow Observation

| Metric | Result |
|---|---:|
| Assets | 12 |
| Timeframe | 4H |
| Historical evaluations | 10,920 |
| Active observations | 3,910 |
| Coverage | 35.92% |
| Accuracy | 47.62% |
| T+3 expectancy | +0.2148% |
| Profit Factor | 1.30 |
| Payoff Ratio | 1.42 |
| Conflict observations | 1,620 |
| Conflict expectancy | +0.3440% |
| Conflict PF | 1.45 |
| Execution mode | SHADOW |
| Order calls | 0 |
| Tests | 14/14 |

> The strongest conflict asymmetry was observed when the mean-reversion layer indicated overbought/SHORT while multi-horizon momentum remained bullish. `MR_SHORT_MOM_LONG` produced +0.7299% mean T+3 return with PF 2.00 in the internal observation dataset. The opposite conflict direction (`MR_LONG_MOM_SHORT`) produced -0.0778% with PF 0.90.

> **Disclaimer**: These results are research observations, not proof of independent trading alpha. The Phase 13 dataset overlaps with data used during Candidate V2 development and freezing.

---

## Core Components

### AutonomousAgent

The central orchestrator that runs a continuous loop (default: every 300 seconds). Each tick performs market snapshot, analyst evaluation, plan generation (rule-based + LLM), guardrail checking, execution, memory recording, and reflection.

- **Mode**: `observe` (monitor only) or `execute` (submit orders)
- **Survival Mode**: NORMAL → CONSERVATIVE → DEFENSIVE → HIBERNATE
- **Treasury Management**: Tracks capital, deducts operational costs, manages runway

### ExecutionEngine

A unified, fault-tolerant order execution wrapper that delegates to GateExecutor. Every order passes through:

1. **Dedup Cache** — 5-second TTL prevents duplicate order submission
2. **Risk Callback** — Pre-execution validation via Guardrails
3. **Rate Limiter** — Maximum 5 requests/second
4. **Retry with Backoff** — Up to 3 attempts with exponential backoff
5. **Storage Callback** — Every order stored in `agent_orders` table

Supports SIMULATION, TESTNET, and LIVE modes with identical code paths.

### GateExecutor

Direct Gate.io Futures API client supporting:

- Market orders (BUY/SELL)
- Limit orders
- TP/SL trigger orders (reduce-only)
- Position queries and reconciliation
- Leverage management
- Candlestick data fetching
- Account equity queries

### MemoryContextBuilder

**Phase 9.1** — Builds rich context for LLM reasoning by aggregating:

- Current market snapshot
- Survival mode and treasury state
- Procedural memory rules
- Shadow memory influence scores
- Recent episode outcomes
- Memory attribution data

### ReasoningValidator

**Phase 9.2** — Audits every LLM plan for:

- Memory usage score (did the LLM consider memory?)
- Context size and latency
- Which memory dimensions were used (procedural, episodic, shadow, ML, portfolio, risk, treasury)
- Raw reasoning content analysis

### ReasoningFeedbackEngine

**Phase 9.3** — Stores feedback from reasoning audits and builds a feedback prompt that is injected into the next LLM call. Creates a continuous self-reflection loop.

### TradeRecorder

**Phase 10.5** — The AI Flight Recorder. Records every stage of every trade as a structured timeline with standard metadata. Thread-safe with per-trade locks.

---

## AI Memory Architecture

Astel Research - TradingAgents implements a multi-layered memory system inspired by cognitive architectures:

### Procedural Memory (Phase 7D.1)
Stores validated trading rules extracted from successful patterns. Rules are injected as context into LLM prompts.

### Episodic Memory (Phase 7A)
Records every action as an episode with full context: market state, decision, outcome, and importance score.

### Shadow Memory (Phase 2 + 8.1)
A read-only comparator that observes agent decisions without interference. Influence scores measure alignment with memory recommendations.

### Memory Mining & Pattern Validation (Phase 7C)
`MemoryMiner` extracts recurring patterns from resolved episodes; `PatternValidator` scores statistical significance.

### Memory Attribution (Phase 7D.2)
Tracks which memory rules influenced decisions and whether those decisions led to positive or negative outcomes.

---

## Roadmap

### Completed Phases

| Phase | Description |
|---|---|
| Phase 1-4 | Base agent loop, Shadow comparator, Analyst team, Bull/Bear research |
| Phase 5 | ML model integration, feature engineering, prediction pipeline |
| Phase 6 | Experiment tracking, survival mode, treasury management |
| Phase 7A-7D | Episodic memory, memory mining, pattern validation, memory attribution |
| Phase 8 | Shadow memory influence |
| Phase 9.1-9.3 | Memory context builder, reasoning validator, reasoning feedback |
| Phase 10 | ExecutionEngine, GateExecutor, order management |
| Phase 10.5 | Trade Replay / AI Flight Recorder |
| Phase 10.5B-10.5C | Replay storage and runtime integration |
| Phase 10.6 | Operational validation, smoke test, execution audit |
| Phase 10.6C | Execution unification / single execution owner |
| Phase 10.6D | Gate.io Testnet readiness audit |
| Phase 10.7 | Launch package and observation infrastructure |
| Phase 10.7B | Replay-backed dashboard closures and recent closure analysis |
| Phase 11 | Market pipeline tracing and current-position migration |
| Phase 12.0 | Multi-asset live market scanner |
| Phase 12.1 | Market Intelligence Layer |
| Phase 12.2 | Multi-Agent Market Decision & Evidence Fusion |
| Phase 12.3 | Decision Calibration, Historical Replay & Shadow Validation |
| Phase 12.3A-12.3G | Historical validation, evidence integrity, directional bias audits |
| Phase 12.4 | Historical Dataset Expansion & Multi-Regime Validation |
| Phase 12.4A | Edge Attribution & Regime Performance Analysis |
| Phase 12.5 | Signal Predictive Value & Calibration Readiness |
| Phase 12.6 | Feature Research & Candidate Signal Architecture |
| Phase 12.7 | Candidate Signal V1 Implementation & Shadow Replay |
| Phase 12.8 | Regime-Conditioned Signal Research |
| Phase 12.9 | Candidate V2 Frozen Rules & Walk-Forward Validation |
| Phase 13 | Candidate V2 Real-Time Shadow Observation |

### Upcoming Research Phases

| Phase | Description |
|---|---|
| Phase 14 | Independent OOS Validation, Paired Edge Analysis & Trading-Cost Audit |
| Phase 15 | Production Readiness / Risk Guard Audit |
| Future | Gate.io Testnet Controlled Execution |
| Future | Live Deployment — only after independent validation and readiness gates |

---

## Project Structure

```text
Astel Research - TradingAgents/
│
├── live_runner.py              # Runtime launcher (single entry point)
├── requirements.txt            # Python dependencies
├── .env                        # Environment configuration
├── README.md                   # System documentation
│
├── agent/                      # AI Agent & Research subsystem
│   ├── agent.py                # AutonomousAgent main loop
│   ├── candidate_signal.py     # CandidateSignalV1 engine (Phase 12.7)
│   ├── candidate_signal_v2.py  # Frozen CandidateSignalV2 engine (Phase 12.9)
│   ├── candidate_v2_shadow_engine.py # Phase 13 Real-Time Shadow Engine
│   ├── regime_signal_research.py     # Regime research engine (Phase 12.8)
│   ├── historical_replay.py    # Historical replay engine
│   ├── market_intelligence.py  # Market intelligence layer
│   ├── market_scanner.py       # Multi-asset scanner
│   ├── specialists.py          # Technical, ML & OrderFlow specialists
│   ├── evidence_fusion.py      # Multi-agent decision fusion engine
│   ├── calibration.py          # Signal calibration engine
│   ├── guardrails.py           # Guardrails, rate limiter, circuit breaker
│   ├── llm_client.py           # LLM Router (Groq/Ollama/DeepSeek)
│   ├── memory.py               # Episode resolver
│   ├── memory_miner.py         # Pattern mining
│   ├── memory_context.py       # Memory context builder
│   ├── trade_replay.py         # TradeRecorder / AI Flight Recorder
│   └── ...
│
├── quant_system/               # Quantitative subsystem
│   ├── config.yaml             # Main configuration
│   ├── execution/
│   │   ├── execution_engine.py # Fault-tolerant execution wrapper
│   │   └── gate_executor.py    # Gate.io API client
│   ├── features/
│   │   └── build_features.py   # Feature engineering pipeline
│   ├── model/
│   │   └── predict.py          # ML prediction model
│   └── risk/
│       └── risk_manager.py     # Position sizing and risk
│
├── dashboard/                  # Web dashboard
│   ├── app.py                  # FastAPI application
│   └── ...
│
└── reports/                    # Generated research reports
```

---

## Installation & Setup

### Prerequisites

- **Python 3.11+**
- **Ollama** (for local LLM inference)
- **PostgreSQL** (optional, SQLite fallback available)
- **Gate.io Testnet account**

### Dependencies

```bash
pip install -r requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```env
GATE_API_KEY=your_testnet_api_key
GATE_API_SECRET=your_testnet_api_secret
AGENT_MODE=observe
AGENT_STORAGE=sqlite
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PRIMARY_MODEL=qwen2.5:7b
```

---

## Running Research Validation Scripts

```bash
# Run Phase 13 Real-Time Shadow Observation Harness:
python -c "import sys; sys.path.insert(0, '.'); from agent._phase13_shadow_runner import run_phase13_shadow_observation; run_phase13_shadow_observation()"

# Run Unit Tests for Shadow Observation Engine:
python -m unittest agent/test_candidate_v2_shadow_engine.py

# Run Unit Tests for Candidate V2 Logic:
python -m unittest agent/test_candidate_signal_v2.py
```

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
| Unit Testing | Python Standard `unittest` |

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
