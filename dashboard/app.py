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

# Agent storage for agent decision visibility
from agent.storage import AgentStorage, make_storage as _make_agent_storage

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


@app.get("/agent", response_class=HTMLResponse)
def agent_console() -> HTMLResponse:
    """Dedicated AI Agent Research Console page at /agent."""
    html = (TEMPLATES_DIR / "agent.html").read_text(encoding="utf-8")
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


# ---------------------------------------------------------------------------
# Agent visibility endpoints (read-only, observer phase)
# ---------------------------------------------------------------------------

_agent_storage: AgentStorage = None  # lazy init


def _get_agent_storage() -> AgentStorage:
    """Lazy-init agent storage for dashboard read-only access."""
    global _agent_storage
    if _agent_storage is None:
        _agent_storage = _make_agent_storage()
        # Ensure shadow_observations and other agent tables exist
        # (Postgres may not have them if schema wasn't initialized)
        try:
            _agent_storage.init_schema()
        except Exception:
            pass
    return _agent_storage


@app.get("/api/agent/status")
def api_agent_status() -> Dict[str, Any]:
    """Return agent status metadata.

    This endpoint tells the dashboard:
      - Whether the agent is running (via recent plan activity)
      - What mode the agent is in (observe/off)
      - Latest survival mode
      - Latest treasury snapshot

    Response:
      {
        "running": bool,
        "agent_mode": str,
        "last_plan_ts": str | null,
        "last_plan_summary": str | null,
        "survival_mode": str,
        "treasury_usdt": float,
        "runway_days": float,
        "plans_today": int,
        "actions_today": int,
      }
    """
    try:
        storage = _get_agent_storage()
        plans = storage.get_recent_plans(limit=1)
        actions = storage.get_recent_actions(limit=20)

        # Count actions in the last 24h
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=24)).isoformat()
        actions_today = sum(1 for a in actions if a.get("ts", "") >= cutoff)

        treasury = storage.load_treasury()

        last_plan = plans[0] if plans else None
        plan_json = last_plan.get("plan") if last_plan else None
        plan_summary = plan_json.get("summary") if isinstance(plan_json, dict) else None
        survival_mode = (plan_json or {}).get("survival_mode", "NORMAL")
        if treasury is not None and survival_mode == "NORMAL":
            # Try to get survival_mode from treasury table as fallback
            pass

        return {
            "running": bool(last_plan is not None),
            "agent_mode": os.environ.get("AGENT_MODE", "observe"),
            "last_plan_ts": last_plan.get("ts") if last_plan else None,
            "last_plan_summary": plan_summary,
            "survival_mode": survival_mode,
            "treasury_usdt": float(treasury or 0.0),
            "runway_days": 9999.0 if (treasury or 0) <= 0 else (treasury or 0) / 0.63,
            "plans_today": len(plans),
            "actions_today": actions_today,
        }
    except Exception as e:
        return {
            "running": False,
            "agent_mode": os.environ.get("AGENT_MODE", "observe"),
            "error": str(e),
        }


@app.get("/api/agent/plans")
def api_agent_plans(limit: int = 10) -> Dict[str, Any]:
    """Return recent agent plans.

    Query params:
      limit (int, default=10): number of plans to return

    Response:
      {
        "plans": [
          {
            "id": int,
            "ts": str,
            "plan": { ... AgentPlan JSON ... },
            "status": str,
            "action_count": int
          }
        ]
      }
    """
    try:
        storage = _get_agent_storage()
        plans = storage.get_recent_plans(limit=min(limit, 50))
        result = []
        for p in plans:
            plan_data = p.get("plan", {}) or {}
            if isinstance(plan_data, dict):
                actions = plan_data.get("proposed_actions", []) or []
                action_count = len(actions)
            elif isinstance(plan_data, str):
                import json
                try:
                    plan_data = json.loads(plan_data)
                    actions = plan_data.get("proposed_actions", []) or []
                    action_count = len(actions)
                except Exception:
                    action_count = 0
            else:
                action_count = 0
            result.append({
                "id": p.get("id"),
                "ts": p.get("ts"),
                "plan": plan_data if isinstance(plan_data, dict) else {},
                "status": p.get("status"),
                "action_count": action_count,
            })
        return {"plans": result}
    except Exception as e:
        return {"plans": [], "error": str(e)}


@app.get("/api/agent/actions")
def api_agent_actions(limit: int = 20) -> Dict[str, Any]:
    """Return recent agent actions.

    Query params:
      limit (int, default=20): number of actions to return

    Response:
      {
        "actions": [
          {
            "id": int,
            "plan_id": int,
            "ts": str,
            "action_type": str,
            "action_params": { ... },
            "result": { ... },
            "success": bool
          }
        ]
      }
    """
    try:
        storage = _get_agent_storage()
        actions = storage.get_recent_actions(limit=min(limit, 100))
        return {"actions": actions}
    except Exception as e:
        return {"actions": [], "error": str(e)}


@app.get("/api/agent/analysts")
def api_agent_analysts(limit: int = 10) -> Dict[str, Any]:
    """Return recent analyst reports.

    Query params:
      limit (int, default=10): number of reports

    Response:
      {
        "reports": [
          {
            "id": int,
            "plan_id": int,
            "ts": str,
            "reports": [{agent, verdict, confidence, reasons}],
            "consensus": str,
            "confidence": float,
            "breakdown": {bullish, bearish, conservative, neutral}
          }
        ]
      }
    """
    try:
        storage = _get_agent_storage()
        rows = storage.get_recent_analyst_reports(limit=min(limit, 50))
        result = []
        for r in rows:
            import json
            reports = json.loads(r.get("reports_json", "[]") or "[]")
            breakdown = json.loads(r.get("breakdown_json", "{}") or "{}")
            result.append({
                "id": r.get("id"),
                "plan_id": r.get("plan_id"),
                "ts": r.get("ts"),
                "reports": reports,
                "consensus": r.get("consensus"),
                "confidence": r.get("confidence"),
                "breakdown": breakdown,
            })
        return {"reports": result}
    except Exception as e:
        return {"reports": [], "error": str(e)}


@app.get("/api/agent/analyst-consensus")
def api_agent_analyst_consensus(limit: int = 1) -> Dict[str, Any]:
    """Return analyst consensus with agreement/conflict scores.

    Query params:
      limit (int, default=1): number of recent consensus snapshots

    Response:
      {
        "consensus": str,
        "agreement_score": float,
        "conflict_score": float,
        "analyst_count": int,
        "analysts": [{agent, verdict, confidence}],
        "ts": str
      }
    """
    try:
        storage = _get_agent_storage()
        rows = storage.get_recent_analyst_reports(limit=min(limit, 10))
        if not rows:
            return {"consensus": "unknown", "agreement_score": 0.0, "conflict_score": 0.0, "analyst_count": 0, "analysts": []}

        r = rows[0]
        import json
        reports = json.loads(r.get("reports_json", "[]") or "[]")
        consensus = r.get("consensus", "neutral")
        analyst_count = len(reports)

        # Count how many analysts match consensus
        matching = sum(1 for rep in reports if rep.get("verdict") == consensus)
        agreement_score = round(matching / max(analyst_count, 1), 2)
        conflict_score = round(1.0 - agreement_score, 2)

        analysts_out = [
            {"agent": rep.get("agent"), "verdict": rep.get("verdict"), "confidence": rep.get("confidence")}
            for rep in reports
        ]

        return {
            "consensus": consensus,
            "agreement_score": agreement_score,
            "conflict_score": conflict_score,
            "analyst_count": analyst_count,
            "analysts": analysts_out,
            "ts": r.get("ts"),
        }
    except Exception as e:
        return {"consensus": "error", "agreement_score": 0.0, "conflict_score": 0.0, "analyst_count": 0, "analysts": [], "error": str(e)}


@app.get("/api/agent/bullbear")
def api_agent_bullbear(limit: int = 5) -> Dict[str, Any]:
    """Return recent Bull/Bear research debates.

    Query params:
      limit (int, default=5): number of debates

    Response:
      {
        "debates": [{
          "id": int, "plan_id": int, "ts": str,
          "bull": {overall_verdict, overall_confidence, signals_found, reasons},
          "bear": {overall_verdict, overall_confidence, risks_found, reasons},
          "verdict": {final_verdict, final_conviction, net_bias, override_by_analysts, reasons}
        }]
      }
    """
    try:
        storage = _get_agent_storage()
        rows = storage.get_recent_bullbear_debates(limit=min(limit, 20))
        result = []
        import json
        for r in rows:
            bull = json.loads(r.get("bull_json", "{}") or "{}")
            bear = json.loads(r.get("bear_json", "{}") or "{}")
            verdict = json.loads(r.get("verdict_json", "{}") or "{}")
            result.append({
                "id": r.get("id"), "plan_id": r.get("plan_id"), "ts": r.get("ts"),
                "bull": {"overall_verdict": bull.get("overall_verdict"), "overall_confidence": bull.get("overall_confidence"),
                         "signals_found": bull.get("signals_found"), "reasons": bull.get("reasons", [])},
                "bear": {"overall_verdict": bear.get("overall_verdict"), "overall_confidence": bear.get("overall_confidence"),
                         "risks_found": bear.get("risks_found"), "reasons": bear.get("reasons", [])},
                "verdict": {"final_verdict": verdict.get("final_verdict"), "final_conviction": verdict.get("final_conviction"),
                            "net_bias": verdict.get("net_bias"), "override_by_analysts": verdict.get("override_by_analysts"),
                            "reasons": verdict.get("reasons", [])},
            })
        return {"debates": result}
    except Exception as e:
        return {"debates": [], "error": str(e)}


@app.get("/api/agent/reasoning")
def api_agent_reasoning(plan_id: int = None) -> Dict[str, Any]:
    """Return full reasoning for a specific plan.

    Query params:
      plan_id (int, required): the plan to fetch

    Response:
      {
        "plan_id": int,
        "ts": str,
        "summary": str,
        "observations": [str],
        "risks": [str],
        "proposed_actions": [{type, params, why, guardrails}],
        "confidence": float,
        "emergency": bool,
        "input_snapshot_summary": {equity, drawdown_pct, ...} | null
      }
    """
    try:
        if plan_id is None:
            # Return most recent plan
            storage = _get_agent_storage()
            plans = storage.get_recent_plans(limit=1)
            if not plans:
                return {"plan_id": None, "error": "No plans found"}
            plan_id = plans[0].get("id")
            plan_json = plans[0].get("plan", {})
            input_snapshot_raw = plans[0].get("input_snapshot", {})
        else:
            # Fetch all plans and find matching id (no direct id query available)
            storage = _get_agent_storage()
            all_plans = storage.get_recent_plans(limit=100)
            target = None
            for p in all_plans:
                if p.get("id") == plan_id:
                    target = p
                    break
            if not target:
                return {"plan_id": plan_id, "error": f"Plan {plan_id} not found"}
            plan_json = target.get("plan", {})
            input_snapshot_raw = target.get("input_snapshot", {})

        # Extract snapshot summary
        snapshot_summary = None
        if isinstance(input_snapshot_raw, dict):
            acct = input_snapshot_raw.get("account", {})
            snapshot_summary = {
                "equity": acct.get("equity"),
                "available": acct.get("available"),
                "drawdown_pct": acct.get("drawdown_pct"),
                "unrealized_pnl": acct.get("unrealized_pnl"),
                "open_positions": acct.get("open_positions"),
                "exposure_x": acct.get("exposure_x"),
                "survival_mode": input_snapshot_raw.get("survival_mode"),
                "treasury_usdt": input_snapshot_raw.get("treasury_usdt"),
            }

        return {
            "plan_id": plan_id,
            "ts": plan_json.get("ts") if isinstance(plan_json, dict) else None,
            "summary": plan_json.get("summary") if isinstance(plan_json, dict) else None,
            "observations": plan_json.get("observations", []) if isinstance(plan_json, dict) else [],
            "risks": plan_json.get("risks", []) if isinstance(plan_json, dict) else [],
            "proposed_actions": plan_json.get("proposed_actions", []) if isinstance(plan_json, dict) else [],
            "confidence": plan_json.get("confidence") if isinstance(plan_json, dict) else None,
            "emergency": plan_json.get("emergency") if isinstance(plan_json, dict) else None,
            "input_snapshot_summary": snapshot_summary,
        }
    except Exception as e:
        return {"plan_id": plan_id, "error": str(e)}


@app.get("/api/agent/treasury")
def api_agent_treasury() -> Dict[str, Any]:
    """Return treasury current state + history.

    Response:
      {
        "current": {treasury_usdt, runway_days},
        "history": [{ts, treasury_usdt, survival_mode}]
      }
    """
    try:
        storage = _get_agent_storage()
        treasury = storage.load_treasury()

        # Extract treasury history from plan snapshots (works with both SQLite and Postgres)
        plans = storage.get_recent_plans(limit=100)
        history = []
        for p in plans:
            snapshot = p.get("input_snapshot", {}) or {}
            if isinstance(snapshot, str):
                import json
                try:
                    snapshot = json.loads(snapshot)
                except Exception:
                    snapshot = {}
            treasury_val = snapshot.get("treasury_usdt", 0.0) if isinstance(snapshot, dict) else 0.0
            survival_val = snapshot.get("survival_mode", "NORMAL") if isinstance(snapshot, dict) else "NORMAL"
            if treasury_val > 0:
                history.append({
                    "ts": p.get("ts", ""),
                    "treasury_usdt": float(treasury_val),
                    "survival_mode": str(survival_val),
                })

        return {
            "current": {
                "treasury_usdt": float(treasury or 0.0),
                "runway_days": 9999.0 if (treasury or 0) <= 0 else (treasury or 0) / 0.63,
            },
            "history": history,
        }
    except Exception as e:
        return {"current": {}, "history": [], "error": str(e)}


@app.get("/api/agent/timeline")
def api_agent_timeline(limit: int = 20) -> Dict[str, Any]:
    """Unified chronological feed of all agent activity.

    Merges plans, actions, shadow observations, and survival changes
    into a single sorted timeline.

    Query params:
      limit (int, default=20): max entries

    Response:
      {
        "entries": [{ts, type, ...description fields}]
      }
    """
    try:
        storage = _get_agent_storage()
        entries = []

        # Plans
        plans = storage.get_recent_plans(limit=limit)
        for p in plans:
            plan_data = p.get("plan", {}) or {}
            if isinstance(plan_data, str):
                import json
                try:
                    plan_data = json.loads(plan_data)
                except Exception:
                    plan_data = {}
            entries.append({
                "ts": p.get("ts"),
                "type": "plan",
                "plan_id": p.get("id"),
                "summary": plan_data.get("summary", "") if isinstance(plan_data, dict) else "",
                "action_count": len(plan_data.get("proposed_actions", [])) if isinstance(plan_data, dict) else 0,
                "status": p.get("status"),
            })

        # Actions
        actions = storage.get_recent_actions(limit=limit)
        for a in actions:
            entries.append({
                "ts": a.get("ts"),
                "type": "action",
                "plan_id": a.get("plan_id"),
                "action_type": a.get("action_type"),
                "success": a.get("success"),
                "detail": (a.get("result") or {}).get("detail", "") if isinstance(a.get("result"), dict) else "",
            })

        # Shadow observations
        shadows = storage.get_shadow_observations(limit=limit)
        for s in shadows:
            entries.append({
                "ts": s.get("ts"),
                "type": "shadow",
                "observation_id": s.get("id"),
                "agreement": s.get("agreement"),
                "recommended_action": s.get("recommended_action"),
                "system_action": s.get("system_action"),
            })

        # Analyst reports + consensus events
        analysts = storage.get_recent_analyst_reports(limit=limit)
        for ar in analysts:
            import json
            try:
                reports_list = json.loads(ar.get("reports_json", "[]") or "[]")
                consensus = ar.get("consensus", "?")
                matching = sum(1 for r in reports_list if r.get("verdict") == consensus)
                total = max(len(reports_list), 1)
                agreement_pct = round(matching / total * 100)
                summary_text = f"Analyst consensus: {consensus}"
                if reports_list:
                    parts = [f"{r.get('agent','?')}={r.get('verdict','?')}" for r in reports_list[:3]]
                    summary_text += f" ({', '.join(parts)})"
            except Exception:
                summary_text = f"Analyst reports (plan #{ar.get('plan_id')})"
                agreement_pct = 0
            entries.append({
                "ts": ar.get("ts"), "type": "analyst", "plan_id": ar.get("plan_id"),
                "consensus": ar.get("consensus"), "confidence": ar.get("confidence"),
                "agreement_pct": agreement_pct, "summary": summary_text,
            })
            entries.append({
                "ts": ar.get("ts"), "type": "consensus",
                "consensus": ar.get("consensus"), "agreement_pct": agreement_pct,
                "summary": f"Consensus: {ar.get('consensus')} (agreement {agreement_pct}%)",
            })

        # Bull/Bear debate events
        debates = storage.get_recent_bullbear_debates(limit=limit)
        for d in debates:
            import json as _json_db
            bull = _json_db.loads(d.get("bull_json", "{}") or "{}")
            bear = _json_db.loads(d.get("bear_json", "{}") or "{}")
            verdict = _json_db.loads(d.get("verdict_json", "{}") or "{}")
            bv = bull.get("overall_verdict", "?")
            bc = bull.get("overall_confidence", 0)
            be = bear.get("overall_verdict", "?")
            bd = bear.get("overall_confidence", 0)
            fv = verdict.get("final_verdict", "?")
            entries.append({
                "ts": d.get("ts"), "type": "debate", "plan_id": d.get("plan_id"),
                "bull_verdict": bv, "bull_confidence": bc,
                "bear_verdict": be, "bear_confidence": bd,
                "final_verdict": fv,
                "summary": f"Debate: {bv} {bc:.2f} vs {be} {bd:.2f} → {fv}",
            })

        # Sort by timestamp descending
        entries.sort(key=lambda e: str(e.get("ts", "")), reverse=True)

        return {"entries": entries[:limit]}
    except Exception as e:
        return {"entries": [], "error": str(e)}


@app.get("/api/agent/health")
def api_agent_health() -> Dict[str, Any]:
    """Computed health metrics for the agent.

    Response:
      {
        "status": "HEALTHY" | "DEGRADED" | "CRITICAL",
        "survival_mode": str,
        "plans_24h": int,
        "actions_24h": int,
        "agreement_rate_24h": float | null,
        "treasury_usdt": float,
        "runway_days": float,
        "error_count_24h": int,
        "circuit_breaker_state": str,
        "seconds_since_last_tick": float | null,
        "last_tick_ts": str | null,
      }
    """
    try:
        storage = _get_agent_storage()
        from datetime import datetime, timedelta, timezone

        now = datetime.now(tz=timezone.utc)
        cutoff_24h = (now - timedelta(hours=24)).isoformat()

        plans = storage.get_recent_plans(limit=50)
        actions = storage.get_recent_actions(limit=100)

        plans_24h = [p for p in plans if str(p.get("ts", "")) >= cutoff_24h]
        actions_24h = [a for a in actions if str(a.get("ts", "")) >= cutoff_24h]

        # Last tick = most recent plan ts
        last_plan = plans[0] if plans else None
        last_tick_ts = last_plan.get("ts") if last_plan else None
        seconds_since_last_tick = None
        if last_tick_ts:
            try:
                last_ts = datetime.fromisoformat(last_tick_ts)
                seconds_since_last_tick = (now - last_ts).total_seconds()
            except Exception:
                pass

        # Shadow agreement rate (24h)
        shadows = storage.get_shadow_observations(limit=100)
        shadows_24h = [s for s in shadows if str(s.get("ts", "")) >= cutoff_24h]
        agreements_24h = sum(1 for s in shadows_24h if s.get("agreement") == "AGREE")
        disagreements_24h = sum(1 for s in shadows_24h if s.get("agreement") == "DISAGREE")
        agreement_rate = round(agreements_24h / max(1, agreements_24h + disagreements_24h), 4) if (agreements_24h + disagreements_24h) > 0 else None

        # Treasury
        treasury = storage.load_treasury()
        treasury_usdt = float(treasury or 0.0)
        runway_days = 9999.0 if treasury_usdt <= 0 else treasury_usdt / 0.63

        # Error count = failed actions in 24h
        error_count_24h = sum(1 for a in actions_24h if not a.get("success"))

        # Survival mode = from latest plan
        survival_mode = "NORMAL"
        if last_plan:
            plan_data = last_plan.get("plan", {}) or {}
            if isinstance(plan_data, dict):
                survival_mode = plan_data.get("survival_mode", "NORMAL")

        # Time-based health classification (Issue A)
        HEALTHY_MAX_SEC = 600      # 10 minutes
        DEGRADED_MAX_SEC = 3600    # 1 hour
        if seconds_since_last_tick is None:
            agent_health = "UNKNOWN"
        elif seconds_since_last_tick <= HEALTHY_MAX_SEC:
            agent_health = "HEALTHY"
        elif seconds_since_last_tick <= DEGRADED_MAX_SEC:
            agent_health = "DEGRADED"
        else:
            agent_health = "OFFLINE"

        # Stale data detection (Issue B)
        stale_data = False
        if last_tick_ts:
            if seconds_since_last_tick is not None and seconds_since_last_tick > 86400:
                stale_data = True

        return {
            "status": agent_health,
            "survival_mode": survival_mode,
            "plans_24h": len(plans_24h),
            "actions_24h": len(actions_24h),
            "agreement_rate_24h": agreement_rate,
            "treasury_usdt": treasury_usdt,
            "runway_days": runway_days,
            "error_count_24h": error_count_24h,
            "circuit_breaker_state": "CLOSED",
            "seconds_since_last_tick": seconds_since_last_tick,
            "last_tick_ts": last_tick_ts,
            "stale_data": stale_data,
        }
    except Exception as e:
        return {"status": "UNKNOWN", "error": str(e)}


@app.get("/api/agent/survival")
def api_agent_survival() -> Dict[str, Any]:
    """Survival metrics KPI panel.

    Core KPIs for the "100 USDT survive or die" research experiment.
    Single source of truth: experiment_runs table.

    Response:
      {
        "age_seconds": float,
        "initial_capital": float,
        "current_capital": float,
        "peak_capital": float,
        "max_drawdown": float,
        "current_survival_mode": str,
        "mode_history": [{ts, mode}]
      }
    """
    try:
        storage = _get_agent_storage()
        from datetime import datetime, timezone

        now = datetime.now(tz=timezone.utc)

        # ── Primary: read capital values from experiment_runs (single source of truth) ──
        exp = storage.get_active_experiment()
        if exp:
            initial_capital = float(exp.get("initial_capital", 0.0))
            current_capital = float(exp.get("current_capital", 0.0))
            peak_capital    = float(exp.get("peak_capital", 0.0))
            total_return_pct = float(exp.get("total_return_pct", 0.0))
            age_days        = float(exp.get("days_alive", 0.0))
            age_seconds     = age_days * 86400
            survival_score  = float(exp.get("survival_score", 0.0))
            max_drawdown    = float(exp.get("max_drawdown", 0.0))
            runway_days     = float(exp.get("runway_days", 0.0))
        else:
            # ── Fallback: no experiment → use plan snapshots ──
            plans = storage.get_recent_plans(limit=100)
            treasury_history = []
            for p in plans:
                snapshot = p.get("input_snapshot", {}) or {}
                if isinstance(snapshot, str):
                    import json
                    try:
                        snapshot = json.loads(snapshot)
                    except Exception:
                        snapshot = {}
                treasury_val = snapshot.get("treasury_usdt", 0.0) if isinstance(snapshot, dict) else 0.0
                survival_val = snapshot.get("survival_mode", "NORMAL") if isinstance(snapshot, dict) else "NORMAL"
                if treasury_val > 0:
                    treasury_history.append({
                        "ts": p.get("ts", ""),
                        "treasury_usdt": float(treasury_val),
                        "survival_mode": str(survival_val),
                    })

            if not treasury_history:
                current_treasury = float(storage.load_treasury() or 0.0)
            else:
                current_treasury = treasury_history[-1]["treasury_usdt"]

            first_entry = treasury_history[0] if treasury_history else None
            age_seconds = 0.0
            if first_entry and first_entry.get("ts"):
                try:
                    first_ts_str = str(first_entry["ts"]).replace("Z", "+00:00").replace(" ", "T")
                    first_ts = datetime.fromisoformat(first_ts_str)
                    age_seconds = max(0.0, (now - first_ts).total_seconds())
                except Exception:
                    pass

            initial_capital = float(first_entry["treasury_usdt"]) if first_entry else current_treasury
            current_capital = current_treasury
            peak_capital = max(float(r["treasury_usdt"]) for r in treasury_history) if treasury_history else current_treasury
            total_return_pct = round(((current_capital - initial_capital) / max(0.01, initial_capital)) * 100.0, 2) if initial_capital > 0 else 0.0

            # Max drawdown from plan snapshots
            max_drawdown = 0.0
            rolling_peak = 0.0
            for r in treasury_history:
                val = float(r["treasury_usdt"])
                if val > rolling_peak:
                    rolling_peak = val
                dd = (rolling_peak - val) / rolling_peak * 100.0 if rolling_peak > 0 else 0.0
                if dd > max_drawdown:
                    max_drawdown = dd

            runway_days = 0.0
            survival_score = 0.0
            age_days = round(age_seconds / 86400, 2)

        # ── Survival mode + mode history from plan snapshots (same for both paths) ──
        plans = storage.get_recent_plans(limit=100)
        treasury_history = []
        for p in plans:
            snapshot = p.get("input_snapshot", {}) or {}
            if isinstance(snapshot, str):
                import json
                try:
                    snapshot = json.loads(snapshot)
                except Exception:
                    snapshot = {}
            treasury_val = snapshot.get("treasury_usdt", 0.0) if isinstance(snapshot, dict) else 0.0
            survival_val = snapshot.get("survival_mode", "NORMAL") if isinstance(snapshot, dict) else "NORMAL"
            treasury_history.append({
                "ts": p.get("ts", ""),
                "treasury_usdt": float(treasury_val),
                "survival_mode": str(survival_val),
            })

        current_mode = treasury_history[-1]["survival_mode"] if treasury_history else "NORMAL"

        mode_history = []
        prev_mode = None
        for r in treasury_history:
            if r["survival_mode"] != prev_mode:
                mode_history.append({"ts": r["ts"], "mode": r["survival_mode"]})
                prev_mode = r["survival_mode"]

        # ── Compute change_pct from experiment_runs values for consistency ──
        capital_change_pct = round(((current_capital - initial_capital) / max(0.01, initial_capital)) * 100.0, 2) if initial_capital > 0 else 0.0

        return {
            "age_seconds": round(age_seconds, 1),
            "age_days": round(age_seconds / 86400, 2),
            "initial_capital": round(initial_capital, 2),
            "current_capital": round(current_capital, 2),
            "peak_capital": round(peak_capital, 2),
            "capital_change_pct": capital_change_pct,
            "max_drawdown": round(max_drawdown, 2),
            "current_survival_mode": current_mode,
            "mode_history": mode_history,
            "survival_score": round(survival_score, 1),
            "runway_days": round(runway_days, 1),
            "_source": "experiment_runs" if exp else "plan_snapshots",
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/agent/shadow")
def api_agent_shadow(limit: int = 20, status: str = None, agreement: str = None) -> Dict[str, Any]:
    """Return shadow observations and dynamic metrics.

    Query params:
      limit (int, default=20): number of observations
      status (str, optional): filter by status ("PENDING_24H" | "RESOLVED")
      agreement (str, optional): filter by agreement ("AGREE" | "DISAGREE" | ...)

    Response:
      {
        "observations": [ ... ],
        "metrics": {
          "total_observations": int,
          "pending_count": int,
          "resolved_count": int,
          "agreements": int,
          "disagreements": int,
          "agreement_rate": float,
          "avg_equity_change": float | null,
          "avg_agreement_pnl": float | null,
          "avg_disagreement_pnl": float | null,
        }
      }
    """
    try:
        storage = _get_agent_storage()
        observations = storage.get_shadow_observations(
            limit=min(limit, 100),
            status=status,
            agreement=agreement,
        )

        # Compute dynamic metrics from raw observations
        total = len(observations)
        pending = sum(1 for o in observations if o.get("status") == "PENDING_24H")
        resolved = sum(1 for o in observations if o.get("status") == "RESOLVED")
        agreements = sum(1 for o in observations if o.get("agreement") == "AGREE")
        disagreements = sum(1 for o in observations if o.get("agreement") == "DISAGREE")

        # Resolved observations with equity_change_24h
        resolved_with_pnl = [
            o for o in observations
            if o.get("status") == "RESOLVED" and o.get("equity_change_24h") is not None
        ]
        agreement_pnls = [
            float(o["equity_change_24h"])
            for o in resolved_with_pnl if o.get("agreement") == "AGREE"
        ]
        disagreement_pnls = [
            float(o["equity_change_24h"])
            for o in resolved_with_pnl if o.get("agreement") == "DISAGREE"
        ]
        all_pnls = [
            float(o["equity_change_24h"])
            for o in resolved_with_pnl
        ]

        metrics = {
            "total_observations": total,
            "pending_count": pending,
            "resolved_count": resolved,
            "agreements": agreements,
            "disagreements": disagreements,
            "agreement_rate": round(agreements / max(1, agreements + disagreements), 4),
            "avg_equity_change": round(sum(all_pnls) / max(1, len(all_pnls)), 4) if all_pnls else None,
            "avg_agreement_pnl": round(sum(agreement_pnls) / max(1, len(agreement_pnls)), 4) if agreement_pnls else None,
            "avg_disagreement_pnl": round(sum(disagreement_pnls) / max(1, len(disagreement_pnls)), 4) if disagreement_pnls else None,
        }

        return {"observations": observations, "metrics": metrics}
    except Exception as e:
        return {"observations": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/experiment")
def api_agent_experiment() -> Dict[str, Any]:
    """Return active experiment data with survival score.

    Response: {status, age_days, initial_capital, current_capital, peak_capital,
               max_drawdown, survival_score, plans_generated, debates_generated,
               agreement_rate, ...}
    """
    try:
        storage = _get_agent_storage()
        exp = storage.get_active_experiment()
        if not exp:
            return {"status": "NO_ACTIVE_EXPERIMENT"}
        return {
            "status": exp.get("status", "RUNNING"),
            "age_days": round(float(exp.get("days_alive", 0)), 2),
            "initial_capital": float(exp.get("initial_capital", 0)),
            "current_capital": float(exp.get("current_capital", 0)),
            "peak_capital": float(exp.get("peak_capital", 0)),
            "max_drawdown": float(exp.get("max_drawdown", 0)),
            "survival_score": float(exp.get("survival_score", 0)),
            "plans_generated": int(exp.get("plans_generated", 0)),
            "debates_generated": int(exp.get("debates_generated", 0)),
            "agreement_rate": float(exp.get("agreement_rate", 0)),
            "total_return_pct": float(exp.get("total_return_pct", 0)),
            "runway_days": float(exp.get("runway_days", 0)),
            "best_survival_score": float(exp.get("best_survival_score", 0)),
            "worst_survival_score": float(exp.get("worst_survival_score", 0)),
            "highest_runway_days": float(exp.get("highest_runway_days", 0)),
            "lowest_runway_days": float(exp.get("lowest_runway_days", 0)),
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


@app.get("/api/agent/experiment/history")
def api_agent_experiment_history(limit: int = 10) -> Dict[str, Any]:
    """Return all past experiment runs."""
    try:
        storage = _get_agent_storage()
        rows = storage.get_experiment_history(limit=min(limit, 50))
        return {"experiments": rows}
    except Exception as e:
        return {"experiments": [], "error": str(e)}


@app.get("/api/agent/episodes")
def api_agent_episodes(limit: int = 20) -> Dict[str, Any]:
    """Return recent episodic memory entries.

    Query params:
      limit (int, default=20): number of episodes to return

    Response:
      {
        "episodes": [{
          "id": int,
          "ts": str,
          "plan_id": int,
          "action_type": str,
          "survival_mode": str,
          "treasury_usdt": float,
          "survival_score": float,
          "analyst_consensus": str,
          "debate_verdict": str,
          "importance_score": float,
          "resolved": bool,
          "created_at": str
        }]
      }
    """
    try:
        storage = _get_agent_storage()
        episodes = storage.get_recent_episodes(limit=min(limit, 100))
        return {"episodes": episodes}
    except Exception as e:
        return {"episodes": [], "error": str(e)}


@app.get("/api/agent/episodes/unresolved")
def api_agent_episodes_unresolved(limit: int = 50) -> Dict[str, Any]:
    """Return unresolved (pending evaluation) episodes.

    Query params:
      limit (int, default=50): max episodes

    Response:
      {
        "episodes": [{episode fields...}],
        "count": int
      }
    """
    try:
        storage = _get_agent_storage()
        episodes = storage.get_unresolved_episodes(limit=min(limit, 200))
        return {"episodes": episodes, "count": len(episodes)}
    except Exception as e:
        return {"episodes": [], "count": 0, "error": str(e)}


@app.get("/api/agent/episodes/resolved")
def api_agent_episodes_resolved(limit: int = 50) -> Dict[str, Any]:
    """Return resolved episodes with decision quality metrics.

    Query params:
      limit (int, default=50): max episodes

    Response:
      {
        "episodes": [{episode fields with outcome_json parsed...}],
        "metrics": {
          "resolved_count": int,
          "positive_decisions": int,
          "negative_decisions": int,
          "neutral_decisions": int,
          "decision_accuracy": float
        }
      }
    """
    try:
        storage = _get_agent_storage()
        # Get from episode endpoint and filter resolved
        all_eps = storage.get_recent_episodes(limit=min(limit * 2, 200))
        resolved = [ep for ep in all_eps if ep.get("resolved") is True or ep.get("resolved") == 1]
        resolved = resolved[:limit]

        # Compute metrics from outcome_json
        positive = 0
        negative = 0
        neutral = 0
        for ep in resolved:
            outcome = ep.get("outcome_json", "{}")
            if isinstance(outcome, str):
                import json
                try:
                    outcome = json.loads(outcome)
                except Exception:
                    outcome = {}
            if isinstance(outcome, dict):
                q = outcome.get("decision_quality", "")
                if q == "positive":
                    positive += 1
                elif q == "negative":
                    negative += 1
                else:
                    neutral += 1

        total_resolved = len(resolved)
        accuracy = round(positive / max(1, total_resolved), 4)

        metrics = {
            "resolved_count": total_resolved,
            "positive_decisions": positive,
            "negative_decisions": negative,
            "neutral_decisions": neutral,
            "decision_accuracy": accuracy,
        }

        return {"episodes": resolved, "metrics": metrics}
    except Exception as e:
        return {"episodes": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/patterns")
def api_agent_patterns(limit: int = 20) -> Dict[str, Any]:
    """Return learned semantic patterns from resolved episodes.

    Query params:
      limit (int, default=20): number of patterns to return

    Response:
      {
        "patterns": [{pattern fields...}],
        "metrics": {
          "total_patterns": int,
          "strongest_positive_pattern": dict | null,
          "strongest_negative_pattern": dict | null,
          "average_confidence": float
        }
      }
    """
    try:
        storage = _get_agent_storage()
        patterns = storage.get_patterns(limit=min(limit, 100))

        total = len(patterns)
        avg_conf = 0.0
        strongest_positive = None
        strongest_negative = None

        if patterns:
            avg_conf = round(sum(float(p.get("confidence_score", 0)) for p in patterns) / max(1, total), 4)
            # Find strongest positive (high success rate) and negative (low success rate)
            pos_candidates = [p for p in patterns if float(p.get("success_rate", 0)) >= 0.7]
            neg_candidates = [p for p in patterns if float(p.get("success_rate", 0)) <= 0.3]
            if pos_candidates:
                pos_candidates.sort(key=lambda p: float(p.get("confidence_score", 0)), reverse=True)
                strongest_positive = pos_candidates[0]
            if neg_candidates:
                neg_candidates.sort(key=lambda p: float(p.get("confidence_score", 0)), reverse=True)
                strongest_negative = neg_candidates[0]

        metrics = {
            "total_patterns": total,
            "strongest_positive_pattern": strongest_positive,
            "strongest_negative_pattern": strongest_negative,
            "average_confidence": avg_conf,
        }

        return {"patterns": patterns, "metrics": metrics}
    except Exception as e:
        return {"patterns": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/patterns/validated")
def api_agent_patterns_validated(limit: int = 50) -> Dict[str, Any]:
    """Return validated patterns with summary.

    Query params:
      limit (int, default=50): max patterns

    Response:
      {
        "validated_patterns": [{pattern...}],
        "rejected_patterns": [{pattern...}],
        "metrics": {total_patterns, validated, rejected, validation_rate}
      }
    """
    try:
        storage = _get_agent_storage()
        from agent.pattern_validator import PatternValidator
        validator = PatternValidator(storage)

        all_patterns = storage.get_patterns(limit=min(limit * 2, 200))
        validated_patterns = []
        rejected_patterns = []

        for p in all_patterns:
            if p.get("validated") is True or p.get("validated") == 1:
                validated_patterns.append(p)
            else:
                rejected_patterns.append(p)

        metrics = validator.get_validation_summary()

        return {
            "validated_patterns": validated_patterns[:limit],
            "rejected_patterns": rejected_patterns[:limit],
            "metrics": metrics,
        }
    except Exception as e:
        return {"validated_patterns": [], "rejected_patterns": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/memory-attribution")
def api_agent_memory_attribution(limit: int = 20) -> Dict[str, Any]:
    """Return memory attribution records.

    Query params:
      limit (int, default=20): number of records

    Response:
      {
        "records": [{ts, plan_id, episode_id, outcome_quality, memory_contribution_score, ...}],
        "metrics": {total_attributions, average_contribution_score, memory_alignment_rate, memory_success_rate}
      }
    """
    try:
        storage = _get_agent_storage()
        from agent.memory_attribution import MemoryAttributionEngine
        engine = MemoryAttributionEngine(storage)
        result = engine.get_attribution_metrics()
        result["records"] = result.get("records", [])[:min(limit, 100)]
        return result
    except Exception as e:
        return {"records": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/memory-context")
def api_agent_memory_context(limit: int = 10) -> Dict[str, Any]:
    """Return procedural memory injection records.

    Query params:
      limit (int, default=10): number of records

    Response:
      {
        "injections": [{ts, plan_id, rule_count, rules_json, planner_used_memory}],
        "metrics": {injection_count, avg_rules_per_plan, validated_patterns_available}
      }
    """
    try:
        storage = _get_agent_storage()
        from agent.procedural_memory import ProceduralMemory
        pm = ProceduralMemory(storage)
        summary = pm.get_memory_summary(limit=min(limit, 100))
        return {"injections": summary.get("injections", []), "metrics": summary.get("stats", {})}
    except Exception as e:
        return {"injections": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/memory-advice")
def api_agent_memory_advice(limit: int = 20) -> Dict[str, Any]:
    """Return memory sandbox advice records.

    Query params:
      limit (int, default=20): number of records

    Response:
      {
        "advice": [{plan_id, planner_decision, memory_decision, difference_detected, confidence, reason_json, ts}],
        "metrics": {advice_count, agreement_rate, disagreement_rate, avg_confidence}
      }
    """
    try:
        storage = _get_agent_storage()
        from agent.memory_sandbox import CounterfactualEngine
        engine = CounterfactualEngine(storage)
        history = engine.get_history(limit=min(limit, 100))
        stats = engine.get_stats()
        return {"advice": history, "metrics": stats}
    except Exception as e:
        return {"advice": [], "metrics": {}, "error": str(e)}


@app.get("/api/agent/patterns/audit")
def api_agent_patterns_audit() -> Dict[str, Any]:
    """Return memory integrity audit data.

    Verifies pattern statistics are not inflated by double-counting.

    Response:
      {
        "total_patterns": int,
        "total_resolved_episodes": int,
        "total_sample_count_all_patterns": int,
        "episode_coverage_ratio": float,
        "duplicate_risk": str,
        "integrity_status": str,
        "patterns_with_checkpoints": int,
        "total_positive_across_patterns": int,
        "total_negative_across_patterns": int
      }
    """
    try:
        from agent.memory_miner import MemoryMiner
        storage = _get_agent_storage()
        miner = MemoryMiner(storage)
        audit = miner.get_audit()
        return audit
    except Exception as e:
        return {"error": str(e), "integrity_status": "unknown"}


# Update API docs summary to include agent endpoints
@app.get("/api/docs/summary")
def api_docs_summary_v2() -> Dict[str, Any]:
    """Quick index of dashboard APIs (v2 with agent endpoints)."""
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
            "agent": {
                "status": "/api/agent/status",
                "plans": "/api/agent/plans?limit=10",
                "actions": "/api/agent/actions?limit=20",
            },
        },
    }
