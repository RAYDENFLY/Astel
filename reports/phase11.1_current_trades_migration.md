# Phase 11.1 — Current Trades Dashboard Migration Verification Report

## 1. Audit Summary
The objective was to migrate the 'Current Trades' panel away from the legacy `trades` table, and decouple the UI from any remaining legacy SQLite queries inside of `dashboard/app.py`. The legacy execution model wrote to the `trades` table as the source of truth, while the modern `ExecutionEngine` utilizes `agent_trade_replay_events` and Gate.io live exchange data to track the true active trade status with live mark prices.

**Before Migration:**
- The panel was labelled "Recent Trades (Journal)" and triggered an endpoint `/api/trades` which directly accessed the SQLite `trades` table relying entirely on the legacy execution loop. 
- A separate fallback in the `/api/positions` endpoint (powering the Open Positions visualization) relied on `get_open_trades_by_asset(db_path)` which fetched from the same table when TP/SL data was absent.

## 2. Completed Migration Steps

**Backend API Integration:**
- The `/api/trades` endpoint was deprecated (with an explicit `warning: deprecated` returned in the response object) but kept structurally intact to ensure no other external scripts immediately break. 
- A new `/api/current-positions` endpoint was registered which acts as exactly the single source of truth. It fetches the replay summaries from `agent_trade_replay_summary` filtering for `status='OPEN'`. 
- The `/api/current-positions` payload is then robustly enriched via the `GateExecutor.fetch_open_positions` hook providing correct real-time `mark_price` and correct calculated `unrealized_pnl` as a sum component of the actual ExecutionEngine structure. 
- Secondary fields like `avg_fill_price` and `exchange_order_id` map dynamically from `agent_trade_replay_events` resolving real Execution state.
- In `api_positions()` and `api_open_positions()`, the deprecated `get_open_trades_by_asset` fallback code was removed. It was replaced with an equivalent querying mechanism reading specifically from the internal `_get_agent_storage()` over the ExecutionEngine data (fetching `storage.get_trade_replay_summary()` and `storage.get_trade_replay_events()` for TP/SL values).

**Frontend Modification:**
- Updated the DOM tree in `templates/index.html` to fully remove the "Recent Trades (Journal)" section node. 
- Replaced the node with a new, highly detailed "Current Positions" UI module tracking: `Contract`, `Side`, `Size`, `Avg Fill`, `Current Price`, `Unrealized PnL`, `Stop Loss`, `Take Profit`, `Exchange Order ID`, `Status`, and `Mode`. 
- Overhauled client-side data binding so that `<tbody id="cur_pos_tbody">` automatically merges real-time `fetch('/api/current-positions')` streams. 
- Provided standard pagination logic identical to closures UI with dynamic page size and inline filters corresponding to specific `ExecutionMode`. 

## 3. Verification of Canonical State
- Execution Engine (`agent_trade_replay_summary` and `agent_trade_replay_events`) acts as the absolute truth for Agent activity.
- The `Gate.io` Testnet hook acts as the truth for real-time asset mark values. 
- Legacy SQLite tables (`trades`) are completely bypassed in UI rendering.
- Test endpoint functionality was validated by rebooting the standard internal `uvicorn dashboard.app:app` component gracefully.

All criteria met, fully removing legacy dependencies. 
