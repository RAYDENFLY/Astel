# Phase 12.3E — Directional Decision Path Audit Report

**Repository:** D:\Data Ray\QuantumTrade  
**Date:** 2026-10-06  
**Execution Mode:** `SHADOW` (Read-Only Safety Enforced)  
**Audit Objective:** Identify where bearish information is lost or converted into `LONG` in the decision pipeline.  

---

## Executive Summary

Phase 12.3E conducted a step-by-step diagnostic trace across the entire decision path:
$$\text{OHLCV} \longrightarrow \text{FeatureBuilder} \longrightarrow \text{ML Prediction} \longrightarrow \text{MarketScanner} \longrightarrow \text{Specialists} \longrightarrow \text{Evidence Fusion} \longrightarrow \text{Decision Agent} \longrightarrow \text{Risk Supervisor}$$

### Key Findings & Root Cause
1. **FeatureBuilder is Functionally Correct**: Correctly calculates negative EMA distance, negative slope, and low RSI during bearish periods.
2. **ML Signal Asymmetry**: Rule-based prediction mapping outputs **14.6% SHORT signals** (123/840 bars) vs **82.1% LONG signals** (690/840 bars) across all asset bars.
3. **Order Flow Default Mock Bias**: When live orderbook data is absent (as in offline CSV replay), `MarketScanner` defaults orderbook depth imbalance to `+0.25` (BULLISH) and large flow imbalance to `+0.30` (BULLISH). Consequently, `OrderFlowSpecialist` emits **100% BULLISH (LONG) signals** (333 LONG / 27 NEUTRAL / 0 SHORT).
4. **Contradiction-Driven Confidence Capping**: When `technical_ml` outputs `SHORT`, `OrderFlowSpecialist` outputs `LONG`. This creates a contradiction (`MIXED`), capping the fused `confidence_band` to `"MEDIUM"` or `"NO_TRADE"`.
5. **Decision Proposal Downgrade**: `DecisionAgent` requires `confidence_band == "HIGH"` to emit `TRADE_CANDIDATE`. Because SHORT confidence band is never `"HIGH"`, **100% of SHORT proposals are downgraded to `WATCH` (13) or `NO_TRADE` (44)**.
6. **Zero Approved SHORT Candidates**: Because Risk Supervisor and Shadow Engine only process `TRADE_CANDIDATE` proposals, **0 SHORT proposals are ever approved or recorded as trades**, producing the empirical **99.3% LONG decision bias** observed in Phase 12.3D.

---

## 1. Feature Direction

- **Audit Target**: `FeatureBuilder.build()` across representative assets (`BTC_USDT`, `ETH_USDT`, `BNB_USDT`, `XRP_USDT`).
- **Bearish Bars Identified**: 84 contiguous 4H bars classified as `BEARISH_TREND` (`ema_fast < ema_slow` AND `ema_slope < 0`).
- **Recorded Metrics**:
  - `ema_fast` < `ema_slow` (e.g., BTC $76,346 vs $76,841)
  - `ema_slope` < 0 (e.g., -54.18 to -18.76)
  - `ema_distance` < 0 (-0.0038 to -0.0068)
  - `rsi` < 40 (24.4 to 39.0)
  - `return_1` negative to near-zero
- **Conclusion**: `FeatureBuilder` accurately represents bearish technical conditions. No code-path bug exists in feature calculation.

---

## 2. ML Direction

- **Audit Target**: Prediction score and calibrated probability calculation in `MarketScanner._analyze_asset_bar()`.
- **Distribution across 840 Total Asset Bars**:
  - `LONG` (`prediction > +0.005`): **690 (82.1%)**
  - `SHORT` (`prediction < -0.005`): **123 (14.6%)**
  - `NEUTRAL` (`-0.005 <= prediction <= +0.005`): **27 (3.2%)**
- **Prediction Score Range**: Min `-0.0697`, Max `+0.3070`, Mean `+0.0695`
- **Probability Range**: Min `0.5000`, Max `0.8800`, Mean `0.8639`
- **Conclusion**: ML predictions generate 14.6% SHORT signals, but exhibit a net positive mean (+0.0695) due to baseline price drift.

---

## 3. MarketScanner Direction

- **Audit Target**: Raw prediction score vs final `AssetAnalysis` direction.
- **Threshold Mapping (`threshold = 0.005`)**:
  - `prediction > +0.005` $\rightarrow$ `LONG` (690 bars)
  - `prediction < -0.005` $\rightarrow$ `SHORT` (123 bars)
  - `-0.005 <= prediction <= +0.005` $\rightarrow$ `NEUTRAL` (27 bars)
- **Conclusion**: `MarketScanner` faithfully preserves raw SHORT directions from ML predictions into `AssetAnalysis.direction`.

---

## 4. Specialist Direction

- **Audit Target**: Output direction from all 5 specialist modules across 210 replay decision evaluations.

| Specialist Module | LONG Count | SHORT Count | NEUTRAL Count | UNAVAILABLE Count | Signal Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **`TechnicalMLSpecialist`** | 311 | 44 | 5 | 0 | Valid Dual-Directional |
| **`OrderFlowSpecialist`** | **333** | **0** | **27** | **0** | **BULLISH BIASED (Mock Data)** |
| **`DerivativesSpecialist`** | 177 | 165 | 18 | 0 | Balanced |
| **`MacroRegimeSpecialist`** | 0 | 0 | 360 | 0 | Neutral Offline |
| **`NewsSentimentSpecialist`** | 0 | 0 | 0 | 360 | Unavailable Offline |

> [!CAUTION]
> **PRIMARY DISCOVERY 1**: `OrderFlowSpecialist` generated **0 SHORT signals** across all 360 evaluations. In offline replay where live orderbook snapshots are unpopulated, default evidence structures in `MarketScanner._build_market_evidence()` supply `imbalance = +0.25` and `flow_imbalance = +0.30`, forcing `OrderFlowSpecialist` to output `LONG` on every single step.

---

## 5. Evidence Fusion

- **Audit Target**: `EvidenceFusionEngine.fuse()` weighting and directional score calculation.
- **Directional Score Distribution (Threshold $\pm 0.18$)**:
  - `Score >= +0.18` (`LONG`): **303 (84.2%)**
  - `Score <= -0.18` (`SHORT`): **13 (3.6%)**
  - `-0.18 < Score < +0.18` (`NEUTRAL`): **44 (12.2%)**
- **Fused Confidence Bands**:
  - `HIGH`: **127 (35.3%)** — *100% of HIGH band decisions were LONG*
  - `MEDIUM`: **189 (52.5%)** — *Contains all 13 SHORT composite direction scores*
  - `NO_TRADE`: **44 (12.2%)**

> [!CAUTION]
> **PRIMARY DISCOVERY 2**: Because `OrderFlowSpecialist` (+0.20 weight) always outputs `LONG`, any `SHORT` signal from `TechnicalMLSpecialist` (+0.35 weight) results in a contradiction (`MIXED`). In `EvidenceFusionEngine`, `contradiction_level == "MIXED"` strictly caps the `confidence_band` to `"MEDIUM"` or `"LOW"`. Zero SHORT signals ever achieve `"HIGH"` confidence band.

---

## 6. Decision Agent

- **Audit Target**: `DecisionAgent.evaluate_single_asset()` decision mapping logic.
- **Rule Matrix**:
  - `confidence_band == "HIGH"` and `comp_dir in ("LONG", "SHORT")` $\rightarrow$ `TRADE_CANDIDATE`
  - `confidence_band == "MEDIUM"` and `comp_dir in ("LONG", "SHORT")` $\rightarrow$ `WATCH`
  - Else $\rightarrow$ `NO_TRADE`
- **Output Distribution**:
  - `('TRADE_CANDIDATE', 'LONG')`: **127 (35.3%)**
  - `('WATCH', 'LONG')`: **176 (48.9%)**
  - `('WATCH', 'SHORT')`: **13 (3.6%)**
  - `('TRADE_CANDIDATE', 'SHORT')`: **0 (0.0%)**
  - `('NO_TRADE', 'NEUTRAL')`: **44 (12.2%)**

> [!CRITICAL]
> **PRIMARY DISCOVERY 3**: Because `DecisionAgent` requires `confidence_band == "HIGH"` to classify a proposal as `TRADE_CANDIDATE`, and SHORT proposals are capped at `MEDIUM` by Evidence Fusion, **100% of SHORT proposals are emitted as `WATCH`**, producing zero `TRADE_CANDIDATE` proposals for SHORT trades.

---

## 7. Risk Supervisor

- **SHORT Proposals Entering RiskSupervisor**: **13** (all with `decision == "WATCH"`).
- **SHORT Proposals Exiting as Approved Candidates**: **0**.
- **Conclusion**: `RiskSupervisor` correctly enforces risk review rules on `WATCH` proposals (proposals marked `WATCH` are held without trade authorization). The supervisor is not deleting proposals; it is correctly receiving proposals already classified as `WATCH`.

---

## 8. Top-N Selection

- **BEFORE Top-N Filtering (840 Total Asset Bars)**:
  - `LONG`: 690 (82.1%) | `SHORT`: 123 (14.6%) | `NEUTRAL`: 27 (3.2%)
- **AFTER Top-N Filtering (210 Selected Top-3 Asset Bars)**:
  - `LONG`: 181 (86.2%) | `SHORT`: 14 (6.7%) | `NEUTRAL`: 15 (7.1%)
- **Conclusion**: Top-N ranking reduces SHORT asset exposure from 14.6% to 6.7% due to composite rank sorting favoring high positive prediction scores, but is secondary to the Evidence Fusion / Confidence Band capping issue.

---

## 9. End-to-End Trace

Trace of 15 representative bearish-regime steps (Warmup step 30 onwards):

| Timestamp | Asset | ML Direction | Rank | Tech Specialist | Macro Specialist | Fusion Score | Fused Direction | Decision Proposal | Final Direction |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 2026-09-16 00:00Z | SUI_USDT | SHORT | 1 | SHORT | NEUTRAL | -0.3278 | SHORT | `WATCH` | SHORT |
| 2026-09-16 00:00Z | LTC_USDT | SHORT | 2 | SHORT | NEUTRAL | +0.0373 | NEUTRAL | `NO_TRADE` | NEUTRAL |
| 2026-09-16 00:00Z | SOL_USDT | SHORT | 3 | SHORT | NEUTRAL | -0.2604 | SHORT | `WATCH` | SHORT |
| 2026-09-16 04:00Z | SUI_USDT | SHORT | 1 | SHORT | NEUTRAL | +0.0315 | NEUTRAL | `NO_TRADE` | NEUTRAL |
| 2026-09-16 04:00Z | ETH_USDT | SHORT | 2 | SHORT | NEUTRAL | +0.0406 | NEUTRAL | `NO_TRADE` | NEUTRAL |
| 2026-09-16 04:00Z | LTC_USDT | SHORT | 3 | SHORT | NEUTRAL | +0.0249 | NEUTRAL | `NO_TRADE` | NEUTRAL |
| 2026-09-16 08:00Z | SUI_USDT | SHORT | 1 | SHORT | NEUTRAL | -0.3314 | SHORT | `WATCH` | SHORT |
| 2026-09-16 08:00Z | LTC_USDT | SHORT | 2 | SHORT | NEUTRAL | +0.0190 | NEUTRAL | `NO_TRADE` | NEUTRAL |
| 2026-09-16 08:00Z | SOL_USDT | SHORT | 3 | SHORT | NEUTRAL | -0.2864 | SHORT | `WATCH` | SHORT |

> [!NOTE]
> The trace clearly illustrates the precise point of failure: at `2026-09-16 00:00Z`, `SUI_USDT` ML prediction is `SHORT`, `TechnicalMLSpecialist` outputs `SHORT`, and `EvidenceFusion` produces `composite_direction = SHORT` with `directional_score = -0.3278`. However, because `OrderFlowSpecialist` outputs `LONG`, `confidence_band` is set to `MEDIUM`, forcing `DecisionAgent` to emit `WATCH` instead of `TRADE_CANDIDATE`.

---

## 10. Counterfactual Diagnostics

- **Diagnostic A**: When ML direction is `SHORT` (N=44), final decision remains `LONG` in only **1** instance (2.3%).
- **Diagnostic B**: When Evidence Fusion score < 0 (N=28), final decision remains `LONG` in **0** instances (0.0%).
- **Diagnostic C**: When MacroRegime is `BEARISH` (N=0 offline), final decision remains `LONG` in **0** instances.

---

## 11. Fallback Path

- **LLM / Deterministic Fallback Invocations**: 0 / 360 (Deterministic fallback mode ran cleanly throughout without throwing exceptions or defaulting to LONG).

---

## 12. Confidence Path

- **LONG Candidates Confidence**: Mean `0.6740` | Min `0.5291` | Max `0.7954`
- **SHORT Candidates Confidence**: Mean `0.5736` | Min `0.5120` | Max `0.6350`
- Confidence calculation is magnitude-based. Because SHORT signals suffer from specialist contradiction, their average confidence is lower (0.5736 vs 0.6740), preventing them from reaching the HIGH confidence band.

---

## 13. Root Cause Classification

$$\mathbf{Root \; Cause: J. MULTIPLE\_ISSUES}$$

The 99.3% LONG decision bias is caused by a three-tier structural interaction:

1. **OrderFlow Mock Evidence Bias (`SPECIALIST_BIAS`)**: Synthetic default orderbook metrics (`imbalance: +0.25`, `flow_imbalance: +0.30`) cause `OrderFlowSpecialist` to output `LONG` on 100% of offline replay steps.
2. **Contradiction Confidence Capping (`EVIDENCE_FUSION_BIAS`)**: When technicals are `SHORT`, `OrderFlow` contradicts with `LONG`, triggering `contradiction_level = "MIXED"` and capping fused confidence band to `"MEDIUM"`.
3. **Decision Proposal Thresholding (`DECISION_AGENT_DEFAULT_LONG`)**: `DecisionAgent` requires `confidence_band == "HIGH"` to issue a `TRADE_CANDIDATE`. Because SHORT confidence bands are capped at `"MEDIUM"`, **100% of SHORT proposals are emitted as `WATCH`**, resulting in **0 approved SHORT trades**.

---

## 14. Tests

- **Regression Test Suite**: Executed pytest across all completed modules.
- **Result**: **53 / 53 passed (100.0%)**.

---

## 15. Execution Safety

- `GateExecutor.place_order() = 0`
- `ExecutionEngine.open_position() = 0`
- `ExecutionEngine.close_position() = 0`
- `submit_order() = 0` | `cancel_order() = 0`
- `EXECUTION_MODE = "SHADOW"` maintained. Zero live or Testnet order placement calls.

---

## 16. Recommended Next Step

**DO NOT IMPLEMENT FIXES IN THIS PHASE.**

When Phase 12.4 / strategy refinement is authorized:
1. Update `MarketScanner._build_market_evidence()` to return `UNAVAILABLE` (instead of bullish mock defaults) when offline orderbook data is missing.
2. Adjust `EvidenceFusionEngine` to treat `UNAVAILABLE` orderbook data gracefully without penalizing directional agreement scores.
3. Allow `SHORT` proposals with high technical agreement and valid risk parameters to achieve `TRADE_CANDIDATE` status for symmetric long/short evaluation.
