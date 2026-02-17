"""Trade journal and equity tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import sqlite3

import pandas as pd

from quant_system.database.db import Database


@dataclass
class Journal:
    db: Database

    def log_trade_entry(self, trade: Dict[str, Any]) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trades (
                    timestamp, asset, side, qty,
                    entry_order_id, tp_order_id, sl_order_id,
                    entry_price, entry_fee,
                    stop_price, stop_distance,
                    leverage_implied, prediction, risk_at_stop,
                    tp_price, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pd.Timestamp(trade["timestamp"]).isoformat(),
                    trade["asset"],
                    trade["side"],
                    float(trade["qty"]),
                    trade.get("entry_order_id"),
                    trade.get("tp_order_id"),
                    trade.get("sl_order_id"),
                    float(trade["entry_price"]),
                    float(trade["entry_fee"]) if trade.get("entry_fee") is not None else None,
                    float(trade["stop_price"]),
                    float(trade["stop_distance"]),
                    float(trade["leverage_implied"]),
                    float(trade["prediction"]),
                    float(trade["risk_at_stop"]),
                    float(trade["tp_price"]) if trade.get("tp_price") is not None else None,
                    trade.get("status", "OPEN"),
                ),
            )
            trade_id = int(cur.lastrowid)
            conn.commit()
            trade["trade_id"] = trade_id
            return trade_id

    def log_trade_exit(self, closure: Dict[str, Any]) -> None:
        with self.db.connect() as conn:
            # Prefer explicit linkage when provided.
            trade_id = closure.get("trade_id")
            if trade_id is not None:
                trade_id = int(trade_id)
            else:
                # Try to link to the latest open trade for this asset (simple heuristic).
                cur = conn.execute(
                    """SELECT trade_id FROM trades
                       WHERE asset = ? AND status = 'OPEN'
                       ORDER BY trade_id DESC LIMIT 1""",
                    (closure["asset"],),
                )
                row = cur.fetchone()
                trade_id = int(row["trade_id"]) if row is not None else None

            conn.execute(
                """
                INSERT INTO trade_closures (
                    trade_id, timestamp, asset, side, qty, exit_order_id,
                    entry_price, exit_price, exit_reason,
                    gross_pnl, fees, pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    pd.Timestamp(closure["timestamp"]).isoformat(),
                    closure["asset"],
                    closure["side"],
                    float(closure["qty"]),
                    closure.get("exit_order_id"),
                    float(closure["entry_price"]),
                    float(closure["exit_price"]),
                    closure["exit_reason"],
                    float(closure["gross_pnl"]),
                    float(closure["fees"]),
                    float(closure["pnl"]),
                ),
            )

            if trade_id is not None:
                conn.execute("UPDATE trades SET status='CLOSED' WHERE trade_id=?", (trade_id,))

            conn.commit()

    def get_open_trades(self) -> list[Dict[str, Any]]:
        """Return OPEN trades from the journal for reconciliation with exchange."""
        with self.db.connect() as conn:
            conn.row_factory = sqlite3.Row  # type: ignore[name-defined]
            rows = conn.execute(
                """
                SELECT trade_id, timestamp, asset, side, qty,
                       entry_order_id, tp_order_id, sl_order_id,
                       entry_price, entry_fee, stop_price, tp_price,
                       status
                FROM trades
                WHERE status = 'OPEN'
                ORDER BY trade_id ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def update_equity(self, ts: pd.Timestamp, equity: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO equity_curve (ts, equity) VALUES (?, ?)",
                (pd.Timestamp(ts).isoformat(), float(equity)),
            )
            conn.commit()

    def store_weekly_metrics(self, metrics: Dict[str, Any]) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO weekly_performance (
                    week_id, start_ts, end_ts, trades, win_rate, avg_win, avg_loss,
                    profit_factor, total_pnl, return_pct, max_drawdown, sharpe
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metrics["week_id"],
                    metrics["start_ts"],
                    metrics["end_ts"],
                    int(metrics["trades"]),
                    float(metrics["win_rate"]),
                    float(metrics["avg_win"]),
                    float(metrics["avg_loss"]),
                    float(metrics["profit_factor"]),
                    float(metrics["total_pnl"]),
                    float(metrics["return_pct"]),
                    float(metrics["max_drawdown"]),
                    float(metrics["sharpe"]),
                ),
            )
            conn.commit()

    def get_state_value(self, key: str) -> Optional[str]:
        with self.db.connect() as conn:
            cur = conn.execute("SELECT value FROM runner_state WHERE key = ?", (key,))
            row = cur.fetchone()
            return str(row["value"]) if row is not None else None

    def set_state_value(self, key: str, value: str, ts: pd.Timestamp) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runner_state (key, value, updated_ts) VALUES (?, ?, ?)",
                (key, value, pd.Timestamp(ts).isoformat()),
            )
            conn.commit()
