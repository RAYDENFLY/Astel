"""Risk management.

- Risk per trade = cfg.risk_per_trade * equity
- Stop distance = ATR * atr_multiplier
- Position size in contract units ~= risk / stop_distance
- Enforce max portfolio risk: sum(risk_at_stop)/equity <= max_portfolio_risk

Returns metadata used by execution:
- qty
- stop_price
- stop_distance
- leverage_implied
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from quant_system.model.predict import Signal


@dataclass(frozen=True)
class RiskResult:
    qty: float
    stop_price: float
    stop_distance: float
    leverage_implied: float
    risk_at_stop: float


class RiskManager:
    def __init__(self, cfg: Dict) -> None:
        self.cfg = cfg

    def size_position(
        self,
        signal: Signal,
        bar: pd.Series,
        equity: float,
        open_positions: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, float]]:
        atr_mult = float(self.cfg["risk"]["atr_multiplier"])
        risk_per_trade = float(self.cfg["risk"]["risk_per_trade"]) * equity
        max_portfolio_risk = float(self.cfg["risk"]["max_portfolio_risk"]) * equity

        atr = float(bar["atr"])
        if atr <= 0:
            return None

        stop_distance = atr * atr_mult
        entry_price = float(bar["close"])  # decision at bar close

        if signal.side == "LONG":
            stop_price = entry_price - stop_distance
        else:
            stop_price = entry_price + stop_distance

        qty = risk_per_trade / stop_distance
        if qty <= 0:
            return None

        current_portfolio_risk = sum(float(p.get("risk_at_stop", 0.0)) for p in open_positions.values())
        if current_portfolio_risk + risk_per_trade > max_portfolio_risk:
            return None

        # leverage implied is a rough proxy: notional / equity
        notional = qty * entry_price
        leverage = notional / equity if equity > 0 else 0.0

        return {
            "qty": float(qty),
            "stop_price": float(stop_price),
            "stop_distance": float(stop_distance),
            "leverage_implied": float(leverage),
            "risk_at_stop": float(risk_per_trade),
        }
