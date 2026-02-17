"""Weekly performance reporting.

Computes weekly metrics from SQLite and prints a formatted report.
Also writes a CSV report to /reports.

Sharpe annualization:
- 4H bars => 6 bars/day
- ~365 days/year => 2190 bars/year
- Sharpe = mean(ret) / std(ret) * sqrt(2190)

Returns are computed from the equity curve (preferred), falling back to summed PnL.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from quant_system.database.db import Database


@dataclass
class WeeklyReporter:
    cfg: Dict
    reports_dir: Path

    def __post_init__(self) -> None:
        self.log = logging.getLogger(self.__class__.__name__)

    def compute_weekly_metrics(self, db: Database, week_id: str) -> Optional[Dict[str, Any]]:
        """Compute metrics for a given ISO week id like '2026-W07'."""
        with db.connect() as conn:
            closures = pd.read_sql_query(
                "SELECT * FROM trade_closures", conn, parse_dates=["timestamp"]
            )
            equity = pd.read_sql_query("SELECT * FROM equity_curve", conn, parse_dates=["ts"])

        if closures.empty and equity.empty:
            return None

        # Filter week by ISO calendar.
        def iso_week(s: pd.Series) -> pd.Series:
            t = pd.to_datetime(s, utc=True)
            return t.dt.strftime("%G-W%V")

        week_closures = closures.copy()
        if not week_closures.empty:
            week_closures["week_id"] = iso_week(week_closures["timestamp"])
            week_closures = week_closures[week_closures["week_id"] == week_id]

        week_equity = equity.copy()
        if not week_equity.empty:
            week_equity["week_id"] = iso_week(week_equity["ts"])
            week_equity = week_equity[week_equity["week_id"] == week_id].sort_values("ts")

        if week_closures.empty and week_equity.empty:
            return None

        trades = int(len(week_closures))
        pnl_series = week_closures["pnl"].astype(float) if trades > 0 else pd.Series(dtype=float)

        wins = pnl_series[pnl_series > 0]
        losses = pnl_series[pnl_series < 0]

        win_rate = float((len(wins) / trades) * 100.0) if trades > 0 else 0.0
        avg_win = float(wins.mean()) if len(wins) else 0.0
        avg_loss = float(losses.mean()) if len(losses) else 0.0

        gross_win = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(losses.abs().sum()) if len(losses) else 0.0
        profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")

        total_pnl = float(pnl_series.sum()) if trades > 0 else 0.0

        if not week_equity.empty:
            start_equity = float(week_equity["equity"].iloc[0])
            end_equity = float(week_equity["equity"].iloc[-1])
            return_pct = (end_equity / start_equity - 1.0) * 100.0 if start_equity > 0 else 0.0

            rets = week_equity["equity"].pct_change().dropna()
            max_dd = float(self._max_drawdown(week_equity["equity"].astype(float)))
            sharpe = float(self._annualized_sharpe(rets)) if len(rets) > 3 else 0.0

            start_ts = pd.Timestamp(week_equity["ts"].iloc[0]).isoformat()
            end_ts = pd.Timestamp(week_equity["ts"].iloc[-1]).isoformat()
        else:
            return_pct = 0.0
            max_dd = 0.0
            sharpe = 0.0
            start_ts = pd.Timestamp(week_closures["timestamp"].min()).isoformat() if trades else ""
            end_ts = pd.Timestamp(week_closures["timestamp"].max()).isoformat() if trades else ""

        return {
            "week_id": week_id,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "trades": trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_pnl": total_pnl,
            "return_pct": float(return_pct),
            "max_drawdown": max_dd,
            "sharpe": sharpe,
        }

    @staticmethod
    def _max_drawdown(equity: pd.Series) -> float:
        cum_max = equity.cummax()
        dd = equity / cum_max - 1.0
        return float(dd.min() * 100.0)  # percent

    @staticmethod
    def _annualized_sharpe(rets: pd.Series) -> float:
        rets = rets.astype(float)
        mu = rets.mean()
        sigma = rets.std(ddof=0)
        if sigma == 0 or np.isnan(sigma):
            return 0.0
        bars_per_year = 6 * 365
        return float(mu / sigma * math.sqrt(bars_per_year))

    def print_report(self, m: Dict[str, Any]) -> None:
        lines = [
            "WEEKLY PERFORMANCE REPORT",
            f"Week: {m['week_id']}",
            f"Trades: {m['trades']}",
            f"Win Rate: {m['win_rate']:.1f}%",
            f"Return: {m['return_pct']:+.2f}%",
            f"Max DD: {m['max_drawdown']:+.2f}%",
            f"Sharpe: {m['sharpe']:.2f}",
            f"Profit Factor: {m['profit_factor']:.2f}" if np.isfinite(m["profit_factor"]) else "Profit Factor: inf",
            f"Total PnL: {m['total_pnl']:+.2f}",
        ]
        for ln in lines:
            self.log.info(ln)

    def save_csv(self, m: Dict[str, Any]) -> Path:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        fp = self.reports_dir / f"weekly_report_{m['week_id']}.csv"
        with fp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(m.keys()))
            writer.writeheader()
            writer.writerow(m)
        return fp
