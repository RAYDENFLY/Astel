# Astel Research Dashboard — UI/UX Redesign Specification

> **Version:** 1.0.0  
> **Status:** Completed Specification / Implementation Guide  
> **Target Audience:** Quantitative Researchers, Algorithmic Traders, System Operators  
> **Design Philosophy:** Anti-Slop, Data-First, High Information Density, Institutional Workstation  

---

## 1. Executive Summary & Design Philosophy

### 1.1 Project Context
Astel is an institutional-grade AI and quantitative research/trading infrastructure project. Its web interfaces serve dual purposes:
1. **Main Dashboard (`/`):** Real-time execution telemetry, account balance metrics, active USDT futures positions, historical performance stats, and trade closure logs.
2. **AI Agent Console (`/agent`):** Deep cognitive observability into autonomous LLM/ML decision loops, market intelligence, multi-analyst consensus, shadow trading calibration, treasury runway, and memory evolution metrics.

### 1.2 Core Design Principles ("Anti-Slop")
The redesign eliminates generic Web2/SaaS visual clichés (smooth pastel cards, excessive padding, ambient blurs, decorative glassmorphism) in favor of a **modern dark quantitative workstation terminal** inspired by Refinitiv Eikon, Bloomberg Terminal, and institutional crypto trading tools (e.g. Bybit/Deribit pro interfaces).

- **Data-First Visual Hierarchy:** Critical metrics (Equity, Unrealized PnL, Drawdown, Survival Mode, Position Risk) occupy dominant visual focal points with high-contrast numerical typography.
- **Monochrome & Purposeful Color Tokens:** Pure dark background (`#0B0E14`), muted grid lines (`#1E2638`), neutral slate text (`#94A3B8`), and strict semantic indicators (Profit: Emerald `#10B981`, Loss: Rose `#EF4444`, Warning: Amber `#F59E0B`, Info/Agent: Cyan `#06B6D4`).
- **High Information Density:** Reduced card margins (4px–8px padding), crisp sub-pixel borders (`1px solid #1E293B`), tabular numbers (`font-variant-numeric: tabular-nums`), and compact micro-charts.
- **Zero Decorative Bloat:** No ambient SVG background glows, no heavy box shadows (`box-shadow: none`), no rounded 2xl corners (max `rounded-sm` / `2px` border radius).
- **Strict API & Logic Preservation:** Zero backend modifications, zero schema changes, zero fake metrics. All components map 1:1 to live FastAPI endpoints (`/api/account`, `/api/open-positions`, `/api/qt-performance-metrics`, `/api/agent/*`, `/ws/positions`).

---

## 2. Comprehensive UI/UX Audit & Pain Point Mapping

### 2.1 Main Dashboard Audit (`index.html`)

| Section / Element | Current Implementation | Identified UX / Visual Defect | Redesign Remedy |
| :--- | :--- | :--- | :--- |
| **Top Header & Navigation** | Generic navbar with simple text title and navigation links. | Wasted vertical space (64px header height); soft font hierarchy. | Compact terminal header bar (36px–40px height) featuring live connection status ticker (WebSocket WS/REST status indicator, server clock, 10s auto-refresh countdown badge). |
| **Account Summary Bar** | 4 equal-width grid cards (Equity, Peak Equity, Total Exposure, Max Drawdown). | Cards look identical; visual weight of Equity is equal to Peak Equity; low metric contrast. | **Primary Hero Telemetry Strip:** Large tabular font for Equity, integrated inline equity curve / drawdown gauge, clear sub-labels for Peak Equity & USDT/IDR conversion. |
| **Performance Metrics Card** | Isolated card with 6 metric boxes (Net PnL, Win Rate, Win/Loss Count, Avg PnL). | Fragmented border layout; standard low-density layout. | **Quant Stats Panel:** Dense 2-column or inline statistical strip with micro-bar visualizers for Win/Loss ratio and color-coded Net PnL. |
| **Open Positions Table** | Full-width table inside rounded white/gray border card with soft padding. | Table cells have generous padding; lack of real-time PnL color flashes; missing compact leverage badges. | **Institutional Order Book / Position Matrix:** Condensed row heights (28px–32px), tabular monospace fonts (`Roboto Mono` / `JetBrains Mono`), color flash on WS updates, inline TP/SL status tags. |
| **Current Open Trades (Replay)** | Separate table duplicates position information with different field names. | Confusing duplication for traders; unclear distinction between live exchange positions and agent replay state. | **Unified Position & Execution Log:** Clear tabbed sub-view ("Exchange Live Positions" vs "Agent Execution Replay") with distinct telemetry badges. |
| **Recent Closed Trades** | Basic data table listing historical closures. | Low density; hard to distinguish exit reasons (TP vs SL vs Manual). | **Trade Closure Audit Log:** Color-coded exit badges (Emerald tag for `TP_HIT`, Rose tag for `SL_HIT`), duration formatters, net PnL chips, and sorting controls. |
| **Performance Charts** | Generic Chart.js canvas containers. | Default Chart.js tooltips and axes look plain; contrast is low against dark card backgrounds. | **High-Density Chart Suites:** Custom dark-themed canvas configurations, thin grid lines (`#1E293B`), synchronized tooltips, crosshair inspection cursor, and compact legend overlays. |

### 2.2 AI Agent Console Audit (`agent.html`)

| Section / Element | Current Implementation | Identified UX / Visual Defect | Redesign Remedy |
| :--- | :--- | :--- | :--- |
| **Console Header & Mode Status** | Standard banner displaying Agent Mode, Survival Mode, Treasury. | Low visual urgency for critical states like `EMERGENCY` or `SURVIVAL`. | **Executive Operational Status Bar:** High-visibility status indicator pill (`NORMAL` = Muted Cyan, `SURVIVAL` = Amber Flashing, `EMERGENCY` = Pulsing Red), Treasury runway progress bar, and mode toggle badge (`OBSERVE` vs `LIVE`). |
| **Analyst Consensus & Debates** | Multiple separate card boxes for Analyst Consensus, Bull/Bear Debate, Risk Reviews. | Information overload; visual scatter across 3 rows of grid containers. | **Integrated Cognitive Radar & Debate Matrix:** Split-panel layout with Analyst Consensus on the left (agreement vs conflict meter) and active Bull/Bear debate side-by-side with clear color-coded arguments. |
| **Cognitive Timeline** | Chronological list of events in a single card. | Text is dense and unformatted; hard to distinguish a plan from an action or shadow observation. | **Multi-Stream Event Telemetry Stream:** Icon-tagged chronological log with category filters (All, Plans, Actions, Shadow, Consensus, Debates), expandable JSON detail drawers, and micro-timestamps. |
| **Shadow Trading & Calibration** | Shadow performance metrics buried near the bottom. | Hard to evaluate model accuracy vs live market conditions at a glance. | **Shadow vs Live Execution Terminal:** Dedicated calibration gauge showing Win Rate delta, cum return sparklines, and decision override audit table. |
| **Evolution & Memory Metrics** | Grid of numeric tiles (Validated Patterns, Active Patterns, Memory Contribution, Self-Reflection). | Numbers displayed as plain text without context or trend indicators. | **Memory System Health Panel:** Compact 4-tier memory health dashboard (Episodic, Semantic, Procedural, Shadow) with trend indicators and dimension contribution distribution bars. |

---

## 3. Core Design System & Tokens

### 3.1 Color Palette (Dark Workstation Token Suite)

```css
:root {
  /* Surface & Background Colors */
  --bg-app: #090C10;
  --bg-surface: #0D1117;
  --bg-surface-elevated: #161B22;
  --bg-surface-hover: #1F242C;
  --border-subtle: #21262D;
  --border-strong: #30363D;
  --border-focus: #58A6FF;

  /* Typography Colors */
  --text-primary: #F0F6FC;
  --text-secondary: #8B949E;
  --text-muted: #484F58;
  --text-disabled: #30363D;

  /* Semantic Financial Indicators */
  --color-profit: #10B981;
  --color-profit-bg: rgba(16, 185, 129, 0.1);
  --color-loss: #EF4444;
  --color-loss-bg: rgba(239, 68, 68, 0.1);
  --color-warning: #F59E0B;
  --color-warning-bg: rgba(245, 158, 11, 0.1);
  --color-agent: #06B6D4;
  --color-agent-bg: rgba(6, 182, 212, 0.1);

  /* Typography Families */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', 'Roboto Mono', monospace;
}
```

### 3.2 Typography & Density Rules
1. **Font Sizes:** Headings max `16px–18px` (`font-semibold`), Subheaders `13px` (`font-medium`), Body `12px`, Table/Monospace data `11px–12px`.
2. **Numeric Representation:** All financial metrics, coordinates, prices, sizes, and PnL values **must** use `--font-mono` with `font-variant-numeric: tabular-nums` to prevent layout shift during live data updates.
3. **Card Padding:** Maximum `12px` padding on containers; compact table cells have `4px 8px` padding.
4. **Border Radii:** Structural panels use `border-radius: 4px` (`rounded-sm`). Badges use `border-radius: 2px`.

---

## 4. Redesign Specification: Main Dashboard (`index.html`)

### 4.1 Grid & Layout Architecture
The main dashboard utilizes a responsive 12-column grid layout:

```
+-----------------------------------------------------------------------------------+
| COMPACT TERMINAL HEADER (Title, Refresh Badge, Server Time, WS Connection State)    |
+-----------------------------------------------------------------------------------+
| HERO TELEMETRY STRIP (12 cols: Equity, Peak Equity, Exposure, Drawdown, Net PnL) |
+-------------------------------------------------------------+---------------------+
| ACTIVE POSITIONS MATRIX (8 cols)                            | PERFORMANCE STATS   |
| Real-time USDT Futures Table (WS streaming, flash effects) | & WIN/LOSS (4 cols) |
+-------------------------------------------------------------+---------------------+
| EQUITY CURVE & DRAWDOWN CHART (8 cols)                      | MONTHLY P&L MATRIX  |
| Intersecting crosshair chart with period selectors           | Heatmap grid (4 col)|
+-------------------------------------------------------------+---------------------+
| HISTORICAL TRADE CLOSURES & AUDIT LOG (12 cols)                                   |
| Filterable, sortable execution log with TP/SL exit tags                           |
+-----------------------------------------------------------------------------------+
```

### 4.2 Key Component Enhancements
- **Live Position Matrix:**
  - Header: `CONTRACT`, `SIDE`, `SIZE`, `ENTRY`, `MARK`, `UNREALIZED PnL`, `TP / SL`, `EST. LIQ`, `ACTIONS`.
  - Side pill: Long (`#10B981` border/bg), Short (`#EF4444` border/bg).
  - PnL column: Flashes green/red border on WebSocket payload reception.
- **Equity & Drawdown Chart:**
  - Dual Y-axis setup (Left: Equity USDT, Right: Drawdown %).
  - Custom dark theme with zero area gradient overflow, clean thin grid lines, and interactive timestamp tooltip.
- **Monthly P&L Heatmap:**
  - Compact calendar-grid visualization showing monthly PnL breakdown with win rate badges.

---

## 5. Redesign Specification: Agent Console (`agent.html`)

### 5.1 Grid & Layout Architecture
The AI Agent Console uses a high-density 3-column split layout optimized for dual 1080p / 4K workstation monitors:

```
+-----------------------------------------------------------------------------------+
| AGENT CONTROL HEADER (Agent Mode, Survival Badge, Treasury Runway, Quick Actions) |
+------------------------------------+-------------------------+--------------------+
| COGNITIVE & DEBATE TERMINAL (5 cols)| REASONING & PLANS (4 col)| SYSTEM HEALTH      |
| - Analyst Consensus Gauge          | - Latest Agent Plan     | & EVOLUTION (3 col)|
| - Bull vs Bear Research Debate     | - Proposed Actions List | - Memory Health    |
| - Market Intelligence Matrix       | - Action Results Audit  | - Shadow Trading   |
+------------------------------------+-------------------------+--------------------+
| UNIFIED CHRONOLOGICAL TELEMETRY STREAM (12 cols)                                  |
| Combined timeline of Plans, Actions, Shadow Observations, & Consensus Events       |
+-----------------------------------------------------------------------------------+
```

### 5.2 Key Component Enhancements
- **Executive Operational Header:**
  - Flashing status indicator for `SURVIVAL` / `EMERGENCY` mode.
  - Interactive runway calculator displaying `Treasury USDT` vs daily burn rate (`$0.63/day`).
- **Analyst Consensus & Debate Matrix:**
  - Consensus agreement score bar (`0.0` to `1.0`).
  - Side-by-side Bull/Bear argument card with conviction percentages and analyst override flags.
- **Cognitive Telemetry Feed:**
  - Category filters: `[ALL]` `[PLANS]` `[ACTIONS]` `[SHADOW]` `[CONSENSUS]` `[DEBATES]`.
  - JSON payload preview modal/drawer for deep inspection without leaving the view.

---

## 6. Technical Implementation Roadmap & Verification Plan

### 6.1 Phase Breakdown
1. **Phase 1: Design Tokens & Base Styles Integration**
   - Define custom CSS variables in template `<style>` blocks.
   - Refactor Tailwind classes to use ultra-compact utilities (`text-xs`, `py-1`, `px-2`, `border-slate-800`).
2. **Phase 2: Main Dashboard Redesign (`index.html`)**
   - Refactor Hero Telemetry Strip, Position Matrix, and Performance Chart views.
   - Update WebSocket listener JS to handle real-time row flash animations.
3. **Phase 3: AI Agent Console Redesign (`agent.html`)**
   - Refactor Operational Header, Consensus/Debate Matrix, and Cognitive Telemetry Feed.
   - Implement expandable JSON detail viewers.
4. **Phase 4: Visual QA & Desktop Verification**
   - Verify layout rendering on standard screen widths (`1280px`, `1920px`, `2560px`).
   - Validate auto-refresh logic and WebSocket reconnect stability.

### 6.2 Verification & Safety Criteria
- **Zero API Breakage:** All `fetch()` and `WebSocket` endpoints retain existing URL structures and JSON data mapping.
- **Zero Data Invalidation:** No calculated metrics (Win Rate, Drawdown, PnL) are modified or omitted.
- **Performance:** CSS bundle size remains minimal; JS update render cycles execute under 16ms to maintain 60fps interaction smoothness.
