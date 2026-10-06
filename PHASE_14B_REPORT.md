# PHASE 14B — INDEPENDENT DATASET ACQUISITION & OOS PREPARATION REPORT

> [!IMPORTANT]
> **Phase 14B is a data acquisition and OOS preparation phase only. CandidateSignalV2 strategy rules remain 100% frozen and unmodified. No strategy performance evaluation or parameter tuning was conducted.**

---

## 1. Objective

Phase 14B established an isolated, machine-readable pipeline to acquire, validate, fingerprint, freeze, and document a genuinely independent out-of-sample (OOS) dataset for future **Phase 14C Fresh Independent OOS Validation**.

---

## 2. Previous vs New Dataset Boundaries

| Asset | Previous Last Timestamp (Phase 12.4–14) | New First Timestamp (Acquired OOS) | New Last Timestamp | Post-Boundary Candles Acquired | Independence Status |
|---|---|---|---|---:|---|
| `BTC_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `ETH_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `SOL_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `BNB_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `XRP_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `AVAX_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `LINK_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `DOGE_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `ADA_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `LTC_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `AAVE_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |
| `SUI_USDT` | `2026-10-06T00:00:00Z` | `2026-10-06T04:00:00Z` | `2026-10-06T04:00:00Z` | 1 | **INDEPENDENT (PASS)** |

---

## 3. Data Integrity & Completeness Audit

- **Canonical Asset Completeness**: 12/12 canonical assets present.
- **Chronology & Monotonicity**: Timestamps strictly increasing, 0 backwards timestamps, 0 duplicates.
- **OHLC Relation Checks**: `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`, `volume >= 0` — 100% PASS.
- **NaN / Inf Checks**: 0 NaN / Inf values across all acquired fields.
- **Gap Analysis**: 0 unexpected gaps > 4H detected in newly fetched OOS candles.

---

## 4. Warmup & Horizon Safety Analysis

- **Warmup Required**: 90 candles (360 hours) required to populate `RSI14`, `Bollinger %B`, `ret_3`, `ret_6`, `ret_12`, `ema20`, `ema50`, `atr14`.
- **Future Horizon Safety Required**: 6 candles (24 hours) required to compute forward returns for T+1, T+3, and T+6 without lookahead.
- **Acquired Post-Boundary Candles**: 1 candle per asset (12 total candles).
- **Usable Evaluation Observations**: **0** (Required: $\ge 100$ observations).

---

## 5. Provenance & Cryptographic Freeze

- **Provider**: Gate.io USDT Perpetual Futures Public REST API (`/futures/usdt/candlesticks`).
- **Acquisition Timestamp**: `2026-10-06T07:32:16Z`.
- **Manifest Location**: `phase14b_oos_manifest.json`.
- **Master Manifest SHA-256 Fingerprint**: `d01b836b8f6a073876fb0e25c11ffa369cf97db0eb7f0bf6e8223f1819e97e11`.
- **Freeze Status**: `UNFROZEN` (Status = `FAIL` due to insufficient OOS sample size).

---

## 6. Final Classification & Fail-Closed Logic

```text
INSUFFICIENT_OOS_DATA
```

**Reason**: Only 1 completed 4H candle has elapsed since the previous dataset boundary (`2026-10-06T00:00:00Z`). Candidate V2 feature calculation requires 90 warmup candles and 6 future horizon candles.

### Final Summary Block

```text
PHASE: 14B
STATUS: FAIL
CLASSIFICATION: INSUFFICIENT_OOS_DATA
DATASET_ID: OOS_4H_20261006_073216
TIMEFRAME: 4h
ASSETS: 12
INDEPENDENT: true
OVERLAP: false
INTEGRITY: PASS
COMPLETENESS: PASS
FROZEN: false
HASH_VERIFIED: true
```

---

## 7. Prerequisites for Phase 14C

To proceed to **Phase 14C Fresh Independent OOS Validation**, the following exact prerequisites must be met:

1. **Chronological Elapsed Time**: At least **196 completed 4H candles** (~32.6 days) must elapse after `2026-10-06T00:00:00Z` (providing 90 warmup + 100 evaluation observations + 6 future horizon safety candles).
2. **Re-run Acquisition Engine**: Run `python -c "import sys; sys.path.insert(0, '.'); from agent._phase14b_oos_acquisition import acquire_and_freeze_oos_dataset; acquire_and_freeze_oos_dataset()"` when sufficient real-time calendar hours have passed.
3. **Manifest Status PASS**: `phase14b_oos_manifest.json` must report `STATUS: PASS` and `CLASSIFICATION: READY_FOR_PHASE_14C`.
