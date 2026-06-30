"""Data access layer for the monitoring dashboard (read-only).

Contract:
- Uses GateExecutor for live exchange reads (equity, positions).
- Uses SQLite for historical/derived reads (peak equity, weekly stats).
- Uses AgentStorage for replay-based trade closures.
- No exchange write calls.

All functions here are side-effect free aside from network/DB reads.
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from quant_system.execution.gate_executor import GateExecutor


def fetch_equity(executor: GateExecutor) -> float:
    """Return current account equity from Gate (strict parser in GateExecutor)."""
    return float(executor.get_account_equity())


def fetch_open_positions(executor: GateExecutor) -> List[Dict[str, Any]]:
    """Return raw open positions from Gate."""
    positions = executor.get_open_positions()
    return positions or []


def get_open_trades_by_asset(db_path: str) -> Dict[str, Dict[str, Any]]:
        """Return latest OPEN trade per asset from SQLite.

        Purpose:
            - Fallback for showing intended TP/SL when exchange trigger orders aren't present.
            - Provides entry_price/tp_price/stop_price even if exchange doesn't expose them.

        Returns:
            {"ADA_USDT": {row}, ...}
        """

        def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
                rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
                return any(r[1] == column for r in rows)

        with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Some older DBs may not have tp_price.
                tp_expr = "tp_price" if _has_column(conn, "trades", "tp_price") else "NULL AS tp_price"

                rows = conn.execute(
                        f"""
                        SELECT asset, side, qty, entry_price, stop_price, {tp_expr}, timestamp
                        FROM trades
                        WHERE status='OPEN'
                        ORDER BY trade_id DESC
                        """
                ).fetchall()

                out: Dict[str, Dict[str, Any]] = {}
                for r in rows:
                        a = str(r["asset"])
                        if a and a not in out:
                                out[a] = dict(r)
                return out


def fetch_open_trigger_orders(executor: GateExecutor, *, contract: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return open trigger (plan) orders from Gate.

    These are used to display current TP/SL that are actually placed on the exchange.
    """
    orders = executor.get_open_trigger_orders(contract=contract)
    return orders or []


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def compute_exposure(positions: List[Dict[str, Any]], *, equity: float) -> float:
    """Compute total exposure as abs(position notional)/equity.

    Gate position payloads typically include a `value` field (USDT notional).
    If missing, we try `notional` as a fallback.

    Returns a fraction (e.g., 1.25 = 125%).
    """
    if equity <= 0:
        return 0.0

    total_abs_value = 0.0
    for p in positions:
        value = _safe_float(p.get("value"))
        if value is None:
            value = _safe_float(p.get("notional"))
        if value is None:
            # As a last resort, approximate: abs(size) * mark_price
            size = _safe_float(p.get("size"))
            mark = _safe_float(p.get("mark_price"))
            if size is not None and mark is not None:
                value = abs(size) * mark
        if value is None:
            continue
        total_abs_value += abs(value)

    return float(total_abs_value / equity)


def get_peak_equity_from_sqlite(db_path: str) -> Optional[float]:
    """Peak equity derived from equity_curve table (max equity)."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT MAX(equity) AS peak_equity FROM equity_curve").fetchone()
        if not row:
            return None
        val = row["peak_equity"]
        return float(val) if val is not None else None


def compute_drawdown(*, equity: float, peak_equity: Optional[float]) -> float:
    """Return drawdown fraction in [0, 1] based on current equity vs peak.

    drawdown = (peak - equity) / peak
    """
    if peak_equity is None or peak_equity <= 0:
        return 0.0
    dd = (float(peak_equity) - float(equity)) / float(peak_equity)
    return float(max(0.0, min(1.0, dd)))


def get_weekly_stats(db_path: str) -> Optional[Dict[str, Any]]:
    """Fetch latest weekly performance row."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM weekly_performance ORDER BY end_ts DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_recent_trades(db_path: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent trades from SQLite journal.

    Includes SL (`stop_price`) and optional TP (`tp_price`) if present.
    """
    def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(r[1] == column for r in rows)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # Backwards compatibility: older journal DBs may not have newer columns.
        base_cols = [
            "trade_id",
            "timestamp",
            "asset",
            "side",
            "qty",
            "entry_price",
            "stop_price",
            "status",
            "leverage_implied",
            "prediction",
        ]

        optional_cols = [
            "entry_fee",
            "tp_price",
            "entry_order_id",
            "tp_order_id",
            "sl_order_id",
        ]

        select_exprs: List[str] = []
        for c in base_cols:
            select_exprs.append(c)
        for c in optional_cols:
            if _has_column(conn, "trades", c):
                select_exprs.append(c)
            else:
                select_exprs.append(f"NULL AS {c}")

        sql = (
            "SELECT "
            + ", ".join(select_exprs)
            + " FROM trades ORDER BY trade_id DESC LIMIT ?"
        )
        rows = conn.execute(sql, (int(limit),)).fetchall()
        return [dict(r) for r in rows]


def get_closed_trade_stats(db_path: str, *, lookback: int = 200) -> Dict[str, Any]:
    """Compute simple stats from most recent closed trades.

    We use `trade_closures` because it has realized PnL.

    Returns:
      - closed_trades: number of closures considered
      - wins: pnl > 0
      - losses: pnl < 0
      - winrate: wins / max(1, wins+losses) (pushes excluded)
      - total_pnl: sum(pnl)
      - avg_pnl: total_pnl / max(1, wins+losses)
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT pnl
            FROM trade_closures
            ORDER BY closure_id DESC
            LIMIT ?
            """,
            (int(lookback),),
        ).fetchall()

    pnls: List[float] = []
    for r in rows:
        v = _safe_float(r["pnl"])
        if v is None:
            continue
        pnls.append(float(v))

    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    considered = wins + losses
    winrate = (wins / considered) if considered > 0 else None
    total_pnl = float(sum(pnls)) if pnls else 0.0
    avg_pnl = (total_pnl / considered) if considered > 0 else None

    return {
        "closed_trades": int(len(pnls)),
        "wins": int(wins),
        "losses": int(losses),
        "winrate": float(winrate) if winrate is not None else None,
        "total_pnl": float(total_pnl),
        "avg_pnl": float(avg_pnl) if avg_pnl is not None else None,
    }


def get_recent_closures(db_path: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent trade closures (realized exits) from SQLite."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT closure_id, trade_id, timestamp, asset, side, qty,
                   exit_order_id, exit_reason,
                   entry_price, exit_price,
                   gross_pnl, fees, pnl
            FROM trade_closures
            ORDER BY closure_id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_alltime_winrate(db_path: str) -> Optional[float]:
    """All-time winrate computed from trade_closures (pnl > 0 vs pnl < 0).

    Returns None if no wins/losses.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses
            FROM trade_closures
            """
        ).fetchone()
        if not row:
            return None
        wins = int(row["wins"] or 0)
        losses = int(row["losses"] or 0)
        denom = wins + losses
        if denom <= 0:
            return None
        return float(wins / denom)


def get_monthly_pnl_and_wl(db_path: str, *, months: int = 12) -> List[Dict[str, Any]]:
    """Monthly aggregates from trade_closures.

    Returns rows ordered ascending by month:
      {month: 'YYYY-MM', net_pnl: float, wins: int, losses: int}
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
              substr(timestamp, 1, 7) AS month,
              SUM(COALESCE(pnl, 0)) AS net_pnl,
              SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses
            FROM trade_closures
            GROUP BY substr(timestamp, 1, 7)
            ORDER BY month DESC
            LIMIT ?
            """,
            (int(months),),
        ).fetchall()

        out = [dict(r) for r in rows]
        out.reverse()  # oldest -> newest for charting
        # Ensure basic typing.
        for r in out:
            r["net_pnl"] = float(r.get("net_pnl") or 0.0)
            r["wins"] = int(r.get("wins") or 0)
            r["losses"] = int(r.get("losses") or 0)
        return out
