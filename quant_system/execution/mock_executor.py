"""Mock execution layer.

Simulates:
- entry at close +/- slippage
- exit at stop price if penetrated intrabar, else a time-exit at next bar close
- fees and slippage

Assumptions:
- One-bar holding period unless stopped earlier.
- Uses the bar's OHLC to determine if stop was hit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from quant_system.model.predict import Signal


class MockExecutor:
    def __init__(self, cfg: Dict) -> None:
        self.cfg = cfg
        self.slippage_bps = float(cfg["execution"]["slippage_bps"])
        self.fee_rate = float(cfg["execution"]["fee_rate"])

    def _apply_slippage(self, price: float, side: str, is_entry: bool) -> float:
        bps = self.slippage_bps / 10000.0
        if side == "LONG":
            return price * (1.0 + bps) if is_entry else price * (1.0 - bps)
        return price * (1.0 - bps) if is_entry else price * (1.0 + bps)

    def enter_trade(self, signal: Signal, bar: pd.Series, risk_meta: Dict[str, float]) -> Optional[Dict[str, Any]]:
        entry_px = float(bar["close"])
        entry_px = self._apply_slippage(entry_px, side=signal.side, is_entry=True)
        qty = float(risk_meta["qty"])

        trade = {
            "timestamp": pd.Timestamp(bar["timestamp"]),
            "asset": str(signal.asset),
            "side": str(signal.side),
            "qty": qty,
            "entry_price": entry_px,
            "stop_price": float(risk_meta["stop_price"]),
            "stop_distance": float(risk_meta["stop_distance"]),
            "leverage_implied": float(risk_meta["leverage_implied"]),
            "prediction": float(signal.prediction),
            "risk_at_stop": float(risk_meta["risk_at_stop"]),
            "status": "OPEN",
        }
        return trade

    def check_exit(self, position: Dict[str, Any], bar: pd.Series) -> Optional[Dict[str, Any]]:
        """Check exit conditions for an open position using the current bar."""
        side = str(position["side"])
        qty = float(position["qty"])
        entry_price = float(position["entry_price"])
        stop_price = float(position["stop_price"])

        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        stopped = False
        if side == "LONG" and low <= stop_price:
            exit_price = stop_price
            stopped = True
        elif side == "SHORT" and high >= stop_price:
            exit_price = stop_price
            stopped = True
        else:
            # Time exit at this bar close (one-bar hold in this engine)
            exit_price = close

        exit_price = self._apply_slippage(exit_price, side=side, is_entry=False)

        # PnL: (exit-entry)*qty with sign
        if side == "LONG":
            gross_pnl = (exit_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - exit_price) * qty

        # Fees: charged on notional both entry and exit
        entry_fee = abs(entry_price * qty) * self.fee_rate
        exit_fee = abs(exit_price * qty) * self.fee_rate
        pnl = gross_pnl - entry_fee - exit_fee

        return {
            "timestamp": pd.Timestamp(bar["timestamp"]),
            "asset": str(position["asset"]),
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "exit_price": float(exit_price),
            "stop_price": stop_price,
            "exit_reason": "STOP" if stopped else "TIME",
            "gross_pnl": float(gross_pnl),
            "fees": float(entry_fee + exit_fee),
            "pnl": float(pnl),
        }
