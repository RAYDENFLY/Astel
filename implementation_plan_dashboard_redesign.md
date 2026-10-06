# Revised Implementation Plan – Astel Main Dashboard UI Redesign

> **Target File:** `dashboard/templates/index.html` ONLY  
> **Status:** Revised & Awaiting Implementation Approval  
> **Design Philosophy:** Anti-Slop, Data-First, High Information Density, Institutional Terminal  

---

## Explicit Declarations & Boundary Constraints

```yaml
FILES_TO_MODIFY:
  - dashboard/templates/index.html ONLY

NEW_API_ENDPOINTS:
  - NONE

NEW_DATA_SOURCES:
  - NONE

NEW_FINANCIAL_METRICS:
  - NONE

TRADING_LOGIC_CHANGES:
  - NONE

CANDIDATE_V2_CHANGES:
  - NONE

PROTOCOL_CHANGES:
  - NONE

OOS_CHANGES:
  - NONE

BACKEND_CHANGES:
  - NONE
```

---

## 1. Summary of Scope & Key Corrections

This is a surgical, frontend-only visual and layout refactor of `dashboard/templates/index.html`. It transforms the existing dashboard into a high-density, dark institutional quantitative workstation while maintaining 100% data contract compatibility with the existing backend endpoints (`/api/account`, `/api/positions`, `/api/current-positions`, `/api/ml-config`, `/api/weekly-summary`, `/api/qt-performance-metrics`, `/api/replay/closures`, `/ws/positions`).

### Key Plan Corrections Applied:
1. **NO Liquidation Price Column:** Removed any mention of "Est. LIQ". The table columns remain strictly backed by verified fields in the existing data contract (`Time`, `Contract`, `Side`, `Size (USDT)`, `Entry`, `Mark Price`, `Unrealized PnL`, `SL`, `TP`, `Order ID`, `Status`, `Mode`).
2. **NO IDR Conversion:** Removed all IDR conversion tags and FX formatting elements. Currency semantics remain strictly USDT as returned by the API.
3. **Purely Presentational Refresh Badge:** The top header refresh badge indicates the existing 10s auto-refresh interval purely visually. Polling timers, fetch logic, and execution schedules are untouched.
4. **Purely Presentational WebSocket Status Indicator:** The connection status badge (`#status` / `#ws_status`) visually reflects the existing WebSocket lifecycle without modifying WS URL, reconnect loops, or message handlers.
5. **Neutral Equity Color:** Equity is styled as a neutral account/capital metric (`#F0F6FC` / `--text-primary`). Directional colors (Emerald green / Rose red) are reserved exclusively for PnL and Win/Loss metrics.
6. **Chart.js Visual Refinements Only:** Styling for canvas charts (`#chart_alltime_winrate`, `#chart_monthly_netpnl`, `#chart_monthly_wl`) is limited to dark backgrounds, gridline opacity (`rgba(148,163,184,0.08)`), fonts, and tooltip formatting. Datasets, calculations, and financial semantics are strictly unchanged.
7. **Realistic UI Performance Verification:** Replaced hardcoded timing targets with empirical UI health criteria (zero UI freezes, zero DOM churn, zero JS console errors, uninterrupted 10s polling, smooth WebSocket updates).
8. **Preservation of Previous Dashboard Remediation:** Retains corrected DOCTYPE, clean win-rate layout (no duplicates), removal of APY placeholders, single unified position matrix, pagination, filter controls, and WebSocket listeners.

---

## 2. Component Layout & Structural Specification

### 2.1 Compact Terminal Header (Height: ~36px–40px)
- **Container:** `bg-[#0D1117]`, `border-[#21262D]`, `rounded`, compact padding (`px-3 py-2`).
- **Brand / Mode Indicator:** Green pulse dot + `ASTEL | QUANTITATIVE RESEARCH WORKSTATION` + direct cyan link to `/agent` console.
- **Exchange Telemetry Badge:** `GATE.IO (FUTURES)` exchange tag.
- **Auto-Refresh Indicator:** `AUTO-REFRESH: 10S` (purely presentational badge).
- **WS Connection Badge:** Existing `<div id="status">` presenting `LIVE` / `DISCONNECTED` state.

### 2.2 Hero Telemetry Strip (5 Columns Grid)
- **Total Equity (`#equity`):** Neutral text color (`#F0F6FC`), font size `text-lg font-bold font-mono-num`. No IDR conversion, no forced green text.
- **Peak Equity (`#peak_equity`):** Neutral text color (`#F0F6FC`), font size `text-lg font-bold font-mono-num`. Hidden starting capital container preserved (`#starting_capital`).
- **Unrealized PnL (`#unreal_pnl`):** Directional color formatting (`text-emerald-400` for >= 0, `text-rose-400` for < 0) + open position count (`#unreal_pos_count`).
- **Risk & Exposure:** Drawdown (`#drawdown` in amber `text-amber-400`), Total Exposure (`#exposure` in slate `text-slate-200`).
- **Quant Engine Status:** Engine Net PnL (`#dex_total_net_pnl`), Win Rate (`#dex_avg_win_rate`), Engine Status badge (`#dex_status`).

### 2.3 Live Futures Positions Matrix (8-Column Panel)
- **Header & Filter Controls:**
  - Title: `Live Futures Positions Matrix` + row counter badge (`#cur_pos_count`).
  - Search input: `#cur_pos_filter_contract` (`oninput="applyCurPosFilters()"`).
  - Side selector: `#cur_pos_filter_side` (`onchange="applyCurPosFilters()"`).
  - Mode selector: `#cur_pos_filter_mode` (`onchange="applyCurPosFilters()"`).
- **Table Columns (Strict Existing Contract):**
  1. `Time`
  2. `Contract`
  3. `Side` (Badge: BUY/LONG emerald, SELL/SHORT rose)
  4. `Size (USDT)`
  5. `Entry`
  6. `Mark Price`
  7. `Unrealized PnL` (Colored)
  8. `SL`
  9. `TP`
  10. `Order ID` (Truncated font-mono with full title hover)
  11. `Status` (Badge)
  12. `Mode` (Badge: TESTNET / LIVE)
- **Pagination Controls:** `#cur_pos_page_size`, `#cur_pos_showing`, `#cur_pos_prev`, `#cur_pos_page_info`, `#cur_pos_next`.
- **WS Flash Effects:** `.qt-flash-green` / `.qt-flash-red` animations trigger on real-time WebSocket position updates.

### 2.4 Performance & Model Telemetry Panel (4-Column Panel)
- **Historical Closed Trades Summary Card:**
  - Metric tiles: `#winrate`, `#closed_trades`, `#total_pnl`, `#avg_pnl`.
  - Detailed counts: `#dex_total_win`, `#dex_total_loss`, `#dex_avg_total_pnl`.
- **ML Model Telemetry Card:**
  - Model info: `#ml_model`, `#ml_timeframe`, `#ml_min_rows`, `#ml_data_source`.
  - Pre-formatted parameters block: `#ml_params`.

### 2.5 High-Density Charts Section (3 Columns)
- **Chart 1:** All-Time Win Rate Distribution (`#chart_alltime_winrate` doughnut chart).
- **Chart 2:** Monthly Net P&L Breakdown (`#chart_monthly_netpnl` bar chart).
- **Chart 3:** Monthly Win / Loss Count (`#chart_monthly_wl` stacked bar chart).
- **Visual Improvements:** Dark slate gridlines (`rgba(148,163,184,0.08)`), crisp monospace tick labels (`#94a3b8`), compact heights (`h-36`).

### 2.6 Weekly Telemetry & Replay Trade Closure Audit Log
- **Weekly Performance Grid:** `#weekly` grid layout for weekly summary cards.
- **Replay Closures Table & Pagination:**
  - Filters: `#closures_filter_contract`, `#closures_filter_side`, `#closures_filter_pnl`.
  - Table body: `#closures_tbody` displaying closed trades with exit reason badges (`TP_HIT`, `SL_HIT`, `MANUAL`).
  - Pagination controls: `#closures_page_size`, `#closures_showing`, `#closures_prev`, `#closures_page_info`, `#closures_next`.

---

## 3. JavaScript & DOM Contract Mapping

All existing JavaScript functions, variables, polling timers, and WebSocket handlers remain completely untouched functionally:

| Data Binding Target / Function | API / WS Source | Preservation Status |
| :--- | :--- | :--- |
| `loadAccount()` | `/api/account` | Preserved (`#equity`, `#peak_equity`, `#starting_capital`) |
| `loadUnrealizedPnL()` | `/api/positions` | Preserved (`#unreal_pnl`, `#unreal_pos_count`) |
| `loadMlConfig()` | `/api/ml-config` | Preserved (`#ml_model`, `#ml_timeframe`, etc.) |
| `loadWeekly()` | `/api/weekly-summary` | Preserved (`#weekly`) |
| `loadStats()` | `/api/qt-performance-metrics` | Preserved (`#winrate`, `#closed_trades`, `#total_pnl`, etc.) |
| `loadCurrentPositions()`, `renderCurPosPage()` | `/api/current-positions` | Preserved (`#cur_pos_tbody`, pagination, filters) |
| `loadClosures()`, `renderClosuresPage()` | `/api/replay/closures` | Preserved (`#closures_tbody`, pagination, filters) |
| `startPositionsWebSocket()` | `ws://.../ws/positions` | Preserved (updates `_allCurPos`, triggers flash animation) |
| `setInterval(refresh, 10000)` | Auto Polling Loop | Preserved (10s interval) |

---

## 4. Verification & Acceptance Criteria

Upon receiving approval to execute, verification will confirm:
1. **Zero Console Errors:** Page loads cleanly without JS errors or unhandled promise rejections.
2. **Data Parity:** Every numeric field matches the exact payload values returned by backend REST endpoints.
3. **Smooth WS Telemetry:** Real-time WebSocket messages parse correctly, update open positions, and trigger subtle green/red row flash animations.
4. **Responsive Layout:** Workstation renders cleanly on standard desktop widths (`1280px`, `1920px`, `2560px`).
5. **No Interrupted Polling:** 10s auto-refresh loop runs continuously without UI lockup or DOM instability.

---

*This plan is ready for implementation upon user approval.*
