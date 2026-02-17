"""FastAPI monitoring dashboard (read-only).

Run:
  uvicorn dashboard.app:app --reload --port 8000

Notes:
- No authentication (for now).
- No exchange write calls.
- Reads:
  - GateExecutor: equity + open positions
  - SQLite: peak equity (from equity_curve) + latest weekly stats
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import os

# Load .env for local development convenience (no-op if missing).
try:
    from quant_system.utils.env import load_dotenv

    load_dotenv(".env", override=False)
except Exception:
    pass

import yaml
from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from dashboard.data_service import (
    compute_drawdown,
    compute_exposure,
    fetch_equity,
    fetch_open_positions,
    fetch_open_trigger_orders,
    get_open_trades_by_asset,
    get_closed_trade_stats,
    get_alltime_winrate,
    get_monthly_pnl_and_wl,
    get_recent_closures,
    get_peak_equity_from_sqlite,
    get_recent_trades,
    get_weekly_stats,
)
from quant_system.execution.gate_executor import GateExecutor

import asyncio


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_config() -> Dict[str, Any]:
    cfg_path = ROOT / "quant_system" / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid config.yaml")
    return data


def _mk_executor(cfg: Dict[str, Any]) -> GateExecutor:
    gate = cfg.get("gate") or {}
    execution = cfg.get("execution") or {}

    api_key = os.environ.get("GATE_API_KEY")
    api_secret = os.environ.get("GATE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            "Missing Gate credentials. Set environment variables GATE_API_KEY and GATE_API_SECRET."
        )

    return GateExecutor(
    api_key=str(api_key),
    api_secret=str(api_secret),
        base_url=str(gate.get("base_url", "https://api.gateio.ws/api/v4")),
        fee_rate=float(execution.get("fee_rate", 0.0)),
        slippage=float(execution.get("slippage_bps", 0.0)) / 10000.0,
    )


def _db_path(cfg: Dict[str, Any]) -> str:
    paths = cfg.get("paths") or {}
    rel = str(paths.get("db_path", "quant_system/database/quant_system.sqlite"))
    return str((ROOT / rel).resolve())


app = FastAPI(title="QuantumTrade Dashboard", version="0.1.0")


@app.get("/api/docs/summary")
def api_docs_summary() -> Dict[str, Any]:
    """Quick index of dashboard APIs.

    Note: Full interactive docs are available at /docs (Swagger UI) and /redoc.
    """
    return {
        "openapi": "/openapi.json",
        "swagger": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "open_positions": {
                "rest": "/api/open-positions",
                "ws": "/ws/positions",
            },
            "qt_performance_metrics": "/api/qt-performance-metrics",
        },
    }

# Optional static mount (not strictly needed since we serve HTML file).
if TEMPLATES_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(TEMPLATES_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/api/account")
def api_account() -> Dict[str, Any]:
    cfg = _load_config()
    executor = _mk_executor(cfg)
    db_path = _db_path(cfg)

    equity = fetch_equity(executor)
    positions = fetch_open_positions(executor)
    exposure = compute_exposure(positions, equity=equity)

    peak_equity = get_peak_equity_from_sqlite(db_path)
    # If equity_curve is empty, fall back to current equity.
    if peak_equity is None:
        peak_equity = equity

    drawdown = compute_drawdown(equity=equity, peak_equity=peak_equity)
    # Optional display FX rate (USDT -> IDR). If missing, frontend will hide conversion.
    display_cfg = (cfg.get("display") or {})
    usdt_to_idr = display_cfg.get("usdt_to_idr")

    # Optional: starting capital / initial deposit to display on the dashboard and expose via API.
    # If not configured, frontend can hide it.
    starting_capital_usdt = (cfg.get("display") or {}).get("starting_capital_usdt")

    return {
        "equity": equity,
        "peak_equity": peak_equity,
        "drawdown": drawdown,
        "total_exposure": exposure,
        "usdt_to_idr": usdt_to_idr,
        "starting_capital_usdt": starting_capital_usdt,
    }


@app.get("/api/positions")
def api_positions() -> Dict[str, Any]:
    cfg = _load_config()
    executor = _mk_executor(cfg)
    db_path = _db_path(cfg)
    positions = fetch_open_positions(executor)

    # Fetch open trigger orders once and merge TP/SL into the position objects.
    trigger_orders = fetch_open_trigger_orders(executor)
    tp_by_contract: Dict[str, float] = {}
    sl_by_contract: Dict[str, float] = {}
    for o in trigger_orders:
        try:
            c = str(o.get("contract", ""))
            if not c:
                continue
            trig = o.get("trigger") or {}
            px_raw = trig.get("price")
            px = float(px_raw) if px_raw is not None else None
            if px is None:
                continue

            # Deterministic mapping by our own tags.
            # Gate fields vary; the tag can appear in different places.
            tag = str(o.get("text") or o.get("order", {}).get("text") or "")
            if tag == "t-qt-tp":
                tp_by_contract[c] = px
            elif tag == "t-qt-sl":
                sl_by_contract[c] = px
        except Exception:
            continue

    # Filter to open positions (size != 0) but keep original payload.
    open_only = []
    for p in positions:
        try:
            size = float(p.get("size", 0))
        except Exception:
            size = 0.0
        if size != 0.0:
            c = str(p.get("contract", ""))
            if c:
                # Attach guessed TP/SL prices from trigger orders.
                if c in tp_by_contract:
                    p["tp_price"] = tp_by_contract[c]
                if c in sl_by_contract:
                    p["sl_price"] = sl_by_contract[c]

                # Fallback: if exchange trigger orders aren't visible, use journal OPEN trade.
                # This helps keep the dashboard informative even when Gate doesn't return
                # open plan orders (or they weren't placed).
                if "tp_price" not in p or p.get("tp_price") is None or "sl_price" not in p or p.get("sl_price") is None:
                    try:
                        open_by_asset = get_open_trades_by_asset(db_path)
                        jt = open_by_asset.get(c)
                        if jt:
                            if p.get("tp_price") is None and jt.get("tp_price") is not None:
                                p["tp_price"] = float(jt.get("tp_price"))
                            if p.get("sl_price") is None and jt.get("stop_price") is not None:
                                p["sl_price"] = float(jt.get("stop_price"))
                    except Exception:
                        pass
            open_only.append(p)

    return {"positions": open_only}


@app.get("/api/open-positions")
def api_open_positions() -> Dict[str, Any]:
        """Open Positions API.

        This is the official API used by the Open Positions table.

        Data source:
            - Gate.io USDT futures positions (via GateExecutor)
            - Optional merge TP/SL from open trigger orders
            - Optional fallback TP/SL from SQLite journal (OPEN trade)

        Response shape:
            {
                "positions": [ ... ]
            }

        Notes:
            - Payload is "best-effort" and mostly mirrors Gate fields.
            - We attach extra fields when available:
                    - tp_price: float
                    - sl_price: float
        """
        return api_positions()


@app.get("/api/qt-performance-metrics")
def api_qt_performance_metrics() -> Dict[str, Any]:
        """QT PERFORMANCE METRICS API.

        This serves the "QT PERFORMANCE METRICS" card.

        Data source:
            - SQLite `trade_closures` via `get_closed_trade_stats()`

        Returns:
            - total_net_pnl (all time)
            - avg_win_rate (all time)
            - total_win (count)
            - total_loss (count)
            - avg_total_pnl (avg pnl per non-push closure)
            - avg_apy: currently null/placeholder
        """
        cfg = _load_config()
        db_path = _db_path(cfg)
        s = get_closed_trade_stats(db_path, lookback=500)

        # Prefer all-time winrate computation (wins/losses) for consistency with charts.
        alltime_winrate = get_alltime_winrate(db_path)

        return {
                "total_net_pnl": s.get("total_pnl"),
                "avg_win_rate": alltime_winrate,
                "total_win": s.get("wins"),
                "total_loss": s.get("losses"),
                "avg_total_pnl": s.get("avg_pnl"),
                "avg_apy": None,
                "source": "sqlite.trade_closures",
        }


@app.websocket("/ws/positions")
async def ws_positions(ws: WebSocket) -> None:
    """Push open positions snapshots over WebSocket.

    Contract:
      - Sends JSON messages: {"type": "positions", "positions": [...], "ts": <unix_ms>}
      - Snapshot-based (not deltas) to keep frontend simple.

    Notes:
      - We intentionally poll Gate on an interval (default 2s) and push.
      - This gives a "realtime" UI feel while staying robust.
    """
    await ws.accept()

    # Small keepalive loop.
    try:
        while True:
            try:
                # Reuse the same logic as the REST endpoint so the UI stays consistent.
                payload = api_positions()
                positions = payload.get("positions", []) or []

                # Derive Unrealized PnL from the same exchange snapshot so the card can be realtime.
                sum_unreal = 0.0
                for p in positions:
                    try:
                        v = p.get("unrealised_pnl", p.get("unrealized_pnl", p.get("pnl")))
                        if v is None:
                            continue
                        sum_unreal += float(v)
                    except Exception:
                        continue

                await ws.send_json(
                    {
                        "type": "positions",
                        "positions": positions,
                        "unreal_pnl": float(sum_unreal),
                        "pos_count": int(len(positions)),
                        "ts": int(asyncio.get_event_loop().time() * 1000),
                    }
                )
            except Exception as e:
                # Send an error message but keep the socket open; frontend can fallback.
                try:
                    await ws.send_json({"type": "error", "message": str(e)})
                except Exception:
                    pass

            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        return


@app.get("/api/weekly")
def api_weekly() -> Dict[str, Any]:
    cfg = _load_config()
    db_path = _db_path(cfg)
    row = get_weekly_stats(db_path)
    return {"weekly": row}


@app.get("/api/trades")
def api_trades() -> Dict[str, Any]:
    cfg = _load_config()
    db_path = _db_path(cfg)
    trades = get_recent_trades(db_path, limit=50)
    return {"trades": trades}


@app.get("/api/closures")
def api_closures() -> Dict[str, Any]:
    cfg = _load_config()
    db_path = _db_path(cfg)
    rows = get_recent_closures(db_path, limit=50)
    return {"closures": rows}


@app.get("/api/stats")
def api_stats() -> Dict[str, Any]:
    cfg = _load_config()
    db_path = _db_path(cfg)
    stats = get_closed_trade_stats(db_path, lookback=500)

    alltime_winrate = get_alltime_winrate(db_path)
    monthly = get_monthly_pnl_and_wl(db_path, months=12)
    return {
        "stats": stats,
        "alltime_winrate": alltime_winrate,
        "monthly": monthly,
    }


@app.get("/api/ml_config")
def api_ml_config() -> Dict[str, Any]:
    """Expose ML/model config for monitoring/debugging (read-only)."""
    cfg = _load_config()
    system_cfg = cfg.get("system") or {}
    data_cfg = cfg.get("data") or {}
    feat_cfg = cfg.get("features") or {}
    model_cfg = cfg.get("model") or {}

    # Keep this intentionally small and JSON-friendly.
    return {
        "system": system_cfg,
        "data": {
            "source": data_cfg.get("source"),
            "timezone": data_cfg.get("timezone"),
            "gate": (data_cfg.get("gate") or {}),
        },
        "features": feat_cfg,
        "model": {
            "model_type": model_cfg.get("model_type"),
            "min_train_rows": model_cfg.get("min_train_rows"),
            "categorical_features": model_cfg.get("categorical_features"),
            "params": (model_cfg.get("params") or {}),
        },
    }
