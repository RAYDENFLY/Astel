# ASTEL RESEARCH REPOSITORY ARTIFACT INVENTORY

> [!IMPORTANT]
> **READ-ONLY ARTIFACT INVENTORY**: This document provides a static inventory and classification of repository artifacts, reports, manifests, scripts, and test suites. No files have been deleted, moved, renamed, or modified.

---

## 1. Executive Summary & Classification Overview

All repository artifacts are classified into four distinct categories based on their operational, audit, and historical role:

1. **ACTIVE**: Core code, active data collection pipeline scripts, monitoring utilities, and active test suites required for live operation and OOS dataset accumulation.
2. **FROZEN**: Frozen strategy implementations, authoritative manifests, protocol specifications, mathematical reviews, and audit reports that must remain 100% immutable.
3. **HISTORICAL**: Prior research phase artifacts, superseded dataset manifests, and diagnostic reports retained for audit provenance and research history.
4. **REDUNDANT / POSSIBLY OBSOLETE**: One-off diagnostic scripts, temporary notes, and generated SQLite databases that are no longer referenced in current workflows.

---

## 2. Detailed Inventory of Relevant Artifacts

### A. Core Protocol, Manifests & Audit Reports

| Path | Purpose | Status | Referenced By | Safe to Archive Later | Preserve for Audit Provenance |
|---|---|---|---|---|---|
| `phase14b1_oos_protocol_manifest.json` | Authoritative frozen protocol SHA-256 (`473a3be3...`) manifest | **FROZEN** | Collector, Health engine, Protocol tests | **No** | **Yes** |
| `PHASE_14B1_REPORT.md` | Specification report for Phase 14B.1 frozen protocol and criteria | **FROZEN** | Pre-14C Audit, Statistical Audit | **No** | **Yes** |
| `PHASE_14C_PREP_STATISTICAL_AUDIT.md` | Statistical methodology audit (power analysis, $N_{\text{eff}}$, dependence) | **FROZEN** | Pre-14C Audit, Audit Review | **No** | **Yes** |
| `PHASE_14C_PREP_STATISTICAL_AUDIT_REVIEW.md` | Mathematical review verifying power formulas and bps labels | **FROZEN** | Pre-14C Audit, Dry-Run Audit | **No** | **Yes** |
| `PHASE_14B2_INTEGRITY_PHASE14C_DRYRUN_AUDIT.md` | Hardening, collector invariants & synthetic dry-run audit report | **FROZEN** | Phase 14C Readiness Verification | **No** | **Yes** |
| `ASTEL_RESEARCH_AUDIT_PRE_PHASE14C.md` | Master repository-wide research evolution audit (Phases 1–14B.2) | **FROZEN** | Master Architecture Docs | **No** | **Yes** |
| `phase14b_oos_collector_manifest.json` | Dynamic manifest tracking OOS candle counts and dataset SHA-256 | **ACTIVE** | Collector, Health engine, Pre-14C Audit | **No** | **Yes** |
| `phase14b_oos_manifest.json` | Initial Phase 14B dataset acquisition manifest | **HISTORICAL** | `_phase14b_oos_acquisition.py`, Phase 14B report | **Yes** | **Yes** |
| `PHASE_14B_REPORT.md` | Documentation report of Phase 14B dataset preparation pass | **HISTORICAL** | Pre-14C Audit Report | **Yes** | **Yes** |
| `PHASE_14B2_REPORT.md` | Documentation report of Phase 14B.2 continuous collector pass | **HISTORICAL** | Pre-14C Audit Report | **Yes** | **Yes** |
| `phase14_oos_validation_report.md` | Diagnostic audit report for Phase 14.0 historical data audit | **HISTORICAL** | `_phase14_oos_validation.py` | **Yes** | **Yes** |
| `fix-close trade.md` | Informal notes snippet regarding trade closure fix | **REDUNDANT** | None | **Yes** | **No** |
| `place-order.md` | Informal notes snippet regarding order placement | **REDUNDANT** | None | **Yes** | **No** |

---

### B. Python Execution Modules (`agent/` and Root)

| Path | Purpose | Status | Referenced By | Safe to Archive Later | Preserve for Audit Provenance |
|---|---|---|---|---|---|
| `agent/candidate_signal_v2.py` | Authoritative frozen CandidateSignalV2 strategy module | **FROZEN** | Shadow engine, `_phase14_oos_validation.py`, tests | **No** | **Yes** |
| `agent/_phase14b1_oos_protocol.py` | Protocol definition and manifest generation script | **FROZEN** | `test_phase14b1_oos_protocol.py` | **No** | **Yes** |
| `agent/_phase14c_prep_statistical_audit.py` | Statistical methodology audit engine | **FROZEN** | Statistical audit tests, Dry-run test harness | **No** | **Yes** |
| `agent/_phase14b_oos_collector.py` | Phase 14B.2 continuous OOS data collector engine | **ACTIVE** | Collector CLI (`--watch`, `--once`), collector tests | **No** | **Yes** |
| `agent/_phase14b_oos_health.py` | Read-only OOS dataset health and status validator | **ACTIVE** | Health CLI, dry-run test harness | **No** | **Yes** |
| `agent/_phase14b_oos_acquisition.py` | Dataset fetcher and validation logic routines | **ACTIVE** | Collector, Health engine, acquisition tests | **No** | **Yes** |
| `agent/candidate_v2_shadow_engine.py` | Execution engine for Candidate V2 in shadow mode | **ACTIVE** | Replay engine, shadow tests | **No** | **Yes** |
| `live_runner.py` | Live/paper trading loop execution script | **ACTIVE** | Live runner workflows | **No** | **Yes** |
| `agent/candidate_signal.py` | CandidateSignal V1 strategy module | **HISTORICAL** | `candidate_signal_v2.py`, V1 tests | **Yes** | **Yes** |
| `agent/_phase14_oos_validation.py` | Phase 14.0 diagnostic validation & bootstrap audit engine | **HISTORICAL** | Validation tests, dry-run test harness | **Yes** | **Yes** |
| `agent/_phase123d_eval.py` ... `_phase129_validation.py` (12 files) | Historical Phase 12 research and feature evaluation scripts | **HISTORICAL** | Research history, feature research | **Yes** | **Yes** |
| `agent/_phase8210_audit.py` ... `_phase84_audit.py` (17 files) | Historical Phase 8 memory influence layer audit scripts | **HISTORICAL** | Memory layer research | **Yes** | **Yes** |
| `agent/_audit_evolution.py`, `_audit_fields.py`, `_audit_js_sim.py` | One-off audit utility scripts | **REDUNDANT** | None | **Yes** | **No** |
| `agent/_fix_storage_methods.py`, `_inject_storage_methods.py`, `_monitor.py` | Memory storage fix/monitor helper scripts | **REDUNDANT** | None | **Yes** | **No** |
| `agent/_quick_diag.py`, `find_branding.py`, `rebrand.py`, `verify_data.py` | One-off diagnostic and branding utility scripts | **REDUNDANT** | None | **Yes** | **No** |

---

### C. Accumulating OOS Dataset (`quant_system/data/oos/`)

| Path | Purpose | Status | Referenced By | Safe to Archive Later | Preserve for Audit Provenance |
|---|---|---|---|---|---|
| `quant_system/data/oos/*_4H_oos.csv` (12 assets) | Accumulating independent 4H completed candle datasets | **ACTIVE** | Collector, Health engine, Validator, Phase 14C | **No** | **Yes** |

---

### D. Test Suite Files (`agent/`)

| Path | Purpose | Status | Referenced By | Safe to Archive Later | Preserve for Audit Provenance |
|---|---|---|---|---|---|
| `agent/test_phase14b1_oos_protocol.py` | Tests for protocol SHA-256 fingerprint & immutability | **FROZEN** | Unittest runner | **No** | **Yes** |
| `agent/test_phase14c_prep_statistical_audit.py` | Tests for statistical audit calculations and bootstrap logic | **FROZEN** | Unittest runner | **No** | **Yes** |
| `agent/test_phase14c_prep_statistical_audit_review.py` | Tests for analytical Z-test power and sample size scoping | **FROZEN** | Unittest runner | **No** | **Yes** |
| `agent/test_candidate_signal_v2.py` | Tests for frozen CandidateSignalV2 logic and signal generation | **FROZEN** | Unittest runner | **No** | **Yes** |
| `agent/test_candidate_v2_shadow_engine.py` | Tests for Candidate V2 shadow engine execution | **FROZEN** | Unittest runner | **No** | **Yes** |
| `agent/test_phase14b_oos_collector.py` | Tests for collector incremental append and atomic persistence | **ACTIVE** | Unittest runner | **No** | **Yes** |
| `agent/test_phase14b_oos_acquisition.py` | Tests for dataset validator, gap detection, and OHLC checks | **ACTIVE** | Unittest runner | **No** | **Yes** |
| `agent/test_phase14c_dryrun.py` | Synthetic dry-run test harness for Phase 14C fail-closed cases | **ACTIVE** | Unittest runner | **No** | **Yes** |
| `agent/test_phase14_validation.py` | Diagnostic tests for Phase 14.0 validation engine | **HISTORICAL** | Unittest runner | **Yes** | **Yes** |
| `agent/test_candidate_signal_v1.py` | Legacy tests for CandidateSignal V1 | **HISTORICAL** | Unittest runner | **Yes** | **Yes** |

---

## 3. Summary Counts

```text
ACTIVE_FILES: 41
FROZEN_FILES: 14
HISTORICAL_FILES: 47
POSSIBLY_REDUNDANT_FILES: 15

SAFE_TO_ARCHIVE_LATER: 62
REQUIRES_MANUAL_REVIEW: 55
```
