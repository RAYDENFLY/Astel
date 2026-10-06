# Astel Web Dashboard Architecture & Hardening Audit Report

**Date:** October 6, 2026  
**Status:** Complete Analysis & Baseline Audit (Read-Only)  
**Scope:** Dashboard Architecture, Data Flow, Components, API Endpoints, Visual/Structural Anomalies, and Safety Constraints  

---

## Executive Summary

This audit provides a comprehensive, read-only analysis of the Astel Web Dashboard. The dashboard serves as an observer and monitoring layer for the Astel quantitative trading and AI research pipeline. It consists of a FastAPI backend (`dashboard/app.py` and `dashboard/data_service.py`) serving two client-side single-page applications (`index.html` and `agent.html`).

The analysis identified key visual anomalies (such as duplicate position tables and broken HTML headers), API endpoint redundancies (legacy SQLite journal vs. new agent replay event storage), and data flow patterns. Crucially, all read-only safety constraints have been preserved—no source code, execution logic, or frozen research artifacts were modified.

---

## 1. Dashboard Overview & Architecture

The Astel Web Dashboard is a strictly **read-only, observer-focused** monitoring suite. It provides real-time visibility into live exchange state (via Gate.io), risk and account metrics, ML configuration, trade execution history, and AI agent cognitive evolution.

### Key Architectural Layers

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND TEMPLATES                               │
│  index.html (Trading Monitor)           agent.html (AI Research Console)   │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ REST (10s polling) & WebSocket (/ws/positions)
┌─────────────────────────────────────▼───────────────────────────────────────┐
│                            FASTAPI BACKEND                                  │
│                             dashboard/app.py                                │
└───────────────┬─────────────────────┬───────────────────────┬───────────────┘
                │                     │                       │
┌───────────────▼───────────┐ ┌───────▼─────────────┐ ┌───────▼───────────────┐
│       GATE EXECUTOR       │ │   AGENT STORAGE     │ │    SQLITE DATABASE    │
│ (Gate.io Live Read API)   │ │ (Postgres / SQLite) │ │ (quant_system.sqlite) │
└───────────────────────────┘ └─────────────────────┘ └───────────────────────┘
```

---

## 2. Directory & Component Structure

- **`dashboard/app.py`**: Main FastAPI application instance. Defines REST endpoints, mounts static assets, initializes WebSocket handlers, and coordinates data fetching from `GateExecutor`, `AgentStorage`, and SQLite.
- **`dashboard/data_service.py`**: Read-only data access layer encapsulating helper functions for equity parsing, drawdown calculation, position notional computation, and legacy SQLite database reads.
- **`dashboard/templates/index.html`**: Primary trading monitor dashboard built with TailwindCSS, Chart.js, and FontAwesome.
- **`dashboard/templates/agent.html`**: AI Agent Research Console tracking survival metrics, analyst consensus, memory attributions, semantic patterns, and performance trends.

---

## 3. Route & Endpoint Catalog

### HTML Page Routes
- `GET /`: Serves `index.html` (Trading Monitor).
- `GET /agent`: Serves `agent.html` (AI Agent Research Console).

### REST API Endpoints

| Category | Endpoint | Data Source | Notes / Status |
| :--- | :--- | :--- | :--- |
| **Account & Equity** | `/api/account` | `GateExecutor` + SQLite `equity_curve` | Active; includes USDT to IDR conversion |
| **Positions** | `/api/positions` | `GateExecutor` | Active; raw live exchange positions + triggers |
| **Current Positions** | `/api/current-positions` | `AgentStorage.agent_trade_replay_events` + Gate | Active; execution-engine open positions |
| **Performance Stats** | `/api/stats` | SQLite `trade_closures` | Active; win rate, net PnL, monthly stats |
| **Weekly Stats** | `/api/weekly` | SQLite `weekly_performance` | Active; weekly return % & Sharpe ratio |
| **ML Configuration** | `/api/ml_config` | `configs/ml_config.json` | Active; LightGBM parameters & training rules |
| **API Index** | `/api/docs/summary` | Hardcoded metadata | Active |
| **Legacy Trades** | `/api/trades` | SQLite `trades` | **DEPRECATED**; tagged for removal/migration |
| **Legacy Closures** | `/api/closures` | SQLite `trade_closures` | **DEPRECATED**; tagged for removal/migration |
| **Replay Closures** | `/api/replay/closures` | `AgentStorage.agent_trade_replay_events` | Active; agent replay realized exits |
| **Agent Status** | `/api/agent/status` | `AgentStorage` | Active; status, mode, circuit breaker |
| **Agent Health** | `/api/agent/health` | `AgentStorage` | Active; health status, 24h agreement rate |
| **Agent Survival** | `/api/agent/survival` | `AgentStorage` | Active; capital history & drawdown |
| **Agent Treasury** | `/api/agent/treasury` | `AgentStorage` | Active; runway days & treasury log |
| **Agent Timeline** | `/api/agent/timeline` | `AgentStorage` | Active; chronological activity feed |
| **Agent Reasoning** | `/api/agent/reasoning` | `AgentStorage.agent_plans` | Active; latest plan observations & risks |
| **Agent Shadow** | `/api/agent/shadow` | `AgentStorage.shadow_observations` | Active; shadow trade agreement log |
| **Agent Analysts** | `/api/agent/analysts` | `AgentStorage.analyst_reports` | Active; multi-agent consensus reports |
| **Analyst Consensus**| `/api/agent/analyst-consensus`| `AgentStorage` | Active; agreement vs conflict score |
| **Agent Evolution** | `/api/agent/evolution` | `AgentStorage` | Active; pattern health, memory influence |
| **AI Performance** | `/api/agent/performance-over-time` | `AgentStorage` | Active; learning curve & AI score |

### WebSocket Endpoints
- `/ws/positions`: Pushes real-time open position updates to `index.html`. Falls back to 2-second HTTP polling if WS connection fails.

---

## 4. Detailed Visual & Structural Anomalies List

The audit identified several anomalies in `index.html` and `app.py`:

| # | Anomaly Location | Description | Category | Impact |
| :---: | :--- | :--- | :---: | :--- |
| **1** | `index.html:1` | Accidental leading `x` before `<!doctype html>` (starts with `x<!doctype html>`). | Cosmetic | Minor HTML parsing glitch in strict browsers |
| **2** | `index.html:272-300` vs `310-374` | **Duplicate Position Tables**: Two separate sections ("Open Positions" and "Current Positions") display open position data fetched from different endpoints (`/api/positions` vs `/api/current-positions`). | Structural / UX | Confusing layout; redundant data display |
| **3** | `index.html:283-295` | **Duplicate Table Column Header**: The table in section 1 lists `ENTRY PRICE` twice (columns 4 and 8). | Cosmetic | Misaligned table headers |
| **4** | `index.html:97-142` | **Redundant Metrics Display**: "QT PERFORMANCE METRICS" duplicates Win Rate displays (`dex_avg_win_rate` and `dex_avg_win_rate_2`) and hardcodes `Avg. APY` to `"—"`. | Cosmetic / UI | Cluttered UI |
| **5** | `app.py:1571` & `1604` | **Active Deprecated Endpoints**: `/api/trades` and `/api/closures` are marked `(DEPRECATED)` in docstrings but remain active routes in `app.py`. | Architectural | Potential maintenance debt |
| **6** | Data Source Discrepancy | "Closed Trades Stats" computes PnL from SQLite `trade_closures`, while "Recent Closures" fetches from `AgentStorage.agent_trade_replay_events`. | Functional | Discrepancy if journal DB is not synced with replay events |

---

## 5. Issue Classification Matrix

### A. Cosmetic Issues
1. Malformed DOCTYPE header in `index.html` (`x<!doctype html>`).
2. Duplicate `ENTRY PRICE` table header in `index.html` line 287 & 291.
3. Hardcoded `Avg. APY` field displaying `"—"`.
4. Duplicated Win Rate values in the QT Performance card.

### B. Functional Issues
1. Coexistence of two open position tables rendering near-identical datasets with different schemas.
2. Divergence between legacy SQLite journal metrics and AgentStorage event replay metrics.

### C. Architectural Issues
1. Transition phase between legacy journal database (`quant_system.sqlite`) and AgentStorage replay system (`agent_trade_replay_events`).

---

## 6. Critical Safety Constraints & Immutable Boundaries

To safeguard ongoing OOS collection (Phase 14B.2) and frozen protocols (Phase 14B.1), the following components **MUST NOT** be modified during any future UI/dashboard cleanup:

1. **CandidateSignalV2 Implementation & Thresholds**: Strictly frozen.
2. **Phase 14B.1 Frozen Protocol & SHA-256 Manifest**: Protocol hash `473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36` is immutable.
3. **ExecutionEngine & GateExecutor Write Interface**: Dashboard must remain strictly read-only; no trade placement or order modification logic should ever be added.
4. **AgentStorage Database Schema**: Core tables (`agent_trade_replay_events`, `semantic_patterns`, `shadow_observations`) must not be altered or purged.

---

## 7. Strategic Recommendations for Future Maintenance

1. **Unify Open Positions Panel**: Remove the legacy raw `Open Positions` section (lines 272-300) in `index.html` and rely exclusively on the feature-rich `Current Positions` section powered by `/api/current-positions`.
2. **Fix HTML Syntax**: Correct `x<!doctype html>` on line 1 of `index.html`.
3. **Standardize Data Sources**: Ensure summary performance metrics prioritize `AgentStorage.agent_trade_replay_events` with SQLite journal fallback.
4. **Deprecate Legacy Routes**: Plan a clean deprecation strategy for `/api/trades` and `/api/closures`.
