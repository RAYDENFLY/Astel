# PHASE 14B.2 — CONTINUOUS INDEPENDENT OOS DATA COLLECTOR REPORT

> [!IMPORTANT]
> **Phase 14B.2 is a continuous data collector and persistence engine only. CandidateSignalV2 strategy rules remain 100% frozen and unmodified. Zero evaluation of strategy returns or parameter tuning was conducted.**

---

## 1. Objective

Phase 14B.2 extended the Phase 14B acquisition pipeline into a safe, restartable, fail-closed continuous market data collector (`agent/_phase14b_oos_collector.py`) that incrementally acquires newly completed 4H candles for the 12 canonical assets while enforcing the frozen Phase 14B.1 protocol fingerprint `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36`.

---

## 2. Architecture & Key Collector Components

| Feature | Implementation / Constraint |
|---|---|
| Execution Modes | `--once` (one-shot cycle) & `--watch` (continuous schedule until readiness) |
| Protocol Verification | Verifies `phase14b1_oos_protocol_manifest.json` SHA-256 before every cycle |
| Completed Candle Enforcement | `now_sec >= candle_start_sec + 14,400` (strictly completed 4H candles) |
| Incremental Storage | Appends newly acquired post-boundary candles to `quant_system/data/oos/{asset}_4H_oos.csv` |
| Atomic Persistence | Writes to `.tmp` file first before replacing target file to prevent corruption |
| Data Independence Check | `candle_timestamp > 2026-10-06T00:00:00Z` and `candle_timestamp > last_stored_timestamp` |
| Verification & Quality | Monotonicity, 0 duplicates, valid OHLC relations, volume $\ge 0$, 0 NaNs/Infs |
| Fingerprinting & Manifest | Generates asset SHA-256 hashes and master dataset SHA-256 fingerprint in `phase14b_oos_collector_manifest.json` |

---

## 3. Current Dataset State & Collection Metrics

- **Acquisitions Completed**: Initial post-boundary candle acquired per asset (`2026-10-06T04:00:00Z`).
- **Total Candles Stored**: 12 candles (1 candle per asset across 12 canonical pairs).
- **Usable Evaluation Observations**: **0** (Required: 100 evaluation observations; Total required candles = $90 + 100 + 6 = 196$).
- **Data Independence & Integrity**: **PASS** (100% clean, 0 overlap, 0 duplicate, 0 invalid OHLC).
- **Current Status**: `INSUFFICIENT_OOS_DATA` (`READY_FOR_PHASE_14C: false`).

---

## 4. Machine-Readable Summary

```text
PHASE: 14B.2
STATUS: FAIL
CLASSIFICATION: INSUFFICIENT_OOS_DATA
PROTOCOL_SHA256: 473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36
TIMEFRAME: 4H
ASSETS: 12
TOTAL_CANDLES: 12
USABLE_OBSERVATIONS: 0
REQUIRED_OBSERVATIONS: 100
INDEPENDENT: true
OVERLAP: false
INTEGRITY: PASS
COMPLETENESS: PASS
FROZEN: false
READY_FOR_PHASE_14C: false
```

---

## 5. Usage & Continuous Operation Instructions

### Running a One-Shot Cycle:
```bash
python -m agent._phase14b_oos_collector --once
```

### Running Continuous Watch Mode:
To run the collector continuously in background watch mode (polling every 3600s until 196 completed candles accumulate):
```bash
python -m agent._phase14b_oos_collector --watch --interval 3600
```

> **Automatic Stop Guarantee**: When all readiness conditions are satisfied, the collector automatically performs final fingerprinting, marks the dataset as frozen, outputs `READY_FOR_PHASE_14C: true`, and exits without launching Phase 14C.
