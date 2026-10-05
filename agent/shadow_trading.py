"""
agent/shadow_trading.py — Phase 12.3 Live Read-Only Shadow Trading Engine

Simulates live trades without order submission or exchange interaction.

CRITICAL EXECUTION SAFETY BOUNDARY:
- EXECUTION_MODE = "SHADOW"
- ZERO order placement calls
- ZERO Gate.io API order submission
- ZERO ExecutionEngine or GateExecutor calls
- Simulated tracking ONLY
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.schema import (
    DecisionProposal,
    RiskSupervisorReview,
    ShadowTrade,
)
from agent.storage import AgentStorage

log = logging.getLogger("agent.shadow_trading")

# Strict enforcement of execution mode
EXECUTION_MODE = "SHADOW"


class ShadowTradingEngine:
    """
    Simulated live read-only shadow trading engine.
    Track simulated performance without executing exchange orders.
    """

    def __init__(self, storage: Optional[AgentStorage] = None) -> None:
        self.storage = storage
        self.execution_mode = EXECUTION_MODE

        # Verify safety boundary at initialization
        if self.execution_mode != "SHADOW":
            raise RuntimeError("CRITICAL ERROR: ShadowTradingEngine must be run in SHADOW execution mode!")

        self._active_shadow_trades: Dict[str, ShadowTrade] = {}

    def process_decision_review(
        self,
        proposal: DecisionProposal,
        review: RiskSupervisorReview,
        reference_price: float,
    ) -> Optional[ShadowTrade]:
        """
        Creates a simulated ShadowTrade if proposal is APPROVED_FOR_RISK_REVIEW or TRADE_CANDIDATE.
        """
        if reference_price <= 0:
            log.warning("ShadowTradingEngine: invalid reference price %.2f for %s", reference_price, proposal.asset)
            return None

        # Create shadow trade ONLY for candidates or approved proposals
        if review.status != "APPROVED_FOR_RISK_REVIEW" and proposal.decision != "TRADE_CANDIDATE":
            log.info("ShadowTradingEngine: skipping shadow trade creation for %s (status=%s, decision=%s)",
                     proposal.asset, review.status, proposal.decision)
            return None

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        shadow_id = f"shadow_{uuid.uuid4().hex[:8]}"

        fusion = proposal.fusion_result
        shadow_trade = ShadowTrade(
            shadow_id=shadow_id,
            decision_id=proposal.decision_id,
            asset=proposal.asset,
            timestamp=now_iso,
            direction=proposal.direction,
            entry_reference_price=reference_price,
            current_price=reference_price,
            decision_confidence=proposal.confidence,
            confidence_band=fusion.confidence_band if fusion else "NO_TRADE",
            agreement_score=fusion.agreement_score if fusion else 0.0,
            contradiction_level=fusion.contradiction_level if fusion else "INSUFFICIENT_DATA",
            evidence_quality=fusion.evidence_quality if fusion else 0.0,
            risk_status=review.status,
            execution_mode="SHADOW",
            unrealized_return=0.0,
            max_favorable_excursion=0.0,
            max_adverse_excursion=0.0,
            outcome="OPEN",
        )

        self._active_shadow_trades[shadow_id] = shadow_trade

        if self.storage:
            try:
                self.storage.save_shadow_trade(shadow_trade.model_dump())
            except Exception as err:
                log.warning("ShadowTradingEngine: failed persisting shadow trade %s: %s", shadow_id, err)

        log.info("ShadowTradingEngine: created SHADOW TRADE %s for %s at ref price $%.4f (Direction=%s, Mode=SHADOW, NO_ORDERS_SENT)",
                 shadow_id, proposal.asset, reference_price, proposal.direction)

        return shadow_trade

    def update_prices(self, current_prices: Dict[str, float]) -> List[ShadowTrade]:
        """
        Updates unrealized return, MFE (Max Favorable Excursion), and MAE (Max Adverse Excursion)
        for all open shadow trades using live price updates.
        """
        updated_trades: List[ShadowTrade] = []

        for shadow_id, trade in list(self._active_shadow_trades.items()):
            if trade.outcome != "OPEN":
                continue

            price = current_prices.get(trade.asset)
            if price is None or price <= 0:
                continue

            trade.current_price = price
            entry = trade.entry_reference_price

            # Calculate return depending on direction
            if trade.direction == "LONG":
                ret = (price - entry) / entry
            elif trade.direction == "SHORT":
                ret = (entry - price) / entry
            else:
                ret = 0.0

            trade.unrealized_return = round(ret, 6)

            # Update MFE and MAE
            if ret > trade.max_favorable_excursion:
                trade.max_favorable_excursion = round(ret, 6)
            if ret < trade.max_adverse_excursion:
                trade.max_adverse_excursion = round(ret, 6)

            updated_trades.append(trade)

            if self.storage:
                try:
                    self.storage.update_shadow_trade(trade.model_dump())
                except Exception as err:
                    log.warning("ShadowTradingEngine: failed updating shadow trade %s: %s", shadow_id, err)

        return updated_trades

    def close_shadow_trade(
        self,
        shadow_id: str,
        exit_price: float,
        reason: str = "EXPIRED",
    ) -> Optional[ShadowTrade]:
        """Simulates closing a shadow trade without touching exchange."""
        trade = self._active_shadow_trades.get(shadow_id)
        if not trade:
            return None

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        trade.current_price = exit_price
        entry = trade.entry_reference_price

        if trade.direction == "LONG":
            final_ret = (exit_price - entry) / entry
        elif trade.direction == "SHORT":
            final_ret = (entry - exit_price) / entry
        else:
            final_ret = 0.0

        trade.final_return = round(final_ret, 6)
        trade.closed_at = now_iso

        if final_ret > 0:
            trade.outcome = "WIN"
        elif final_ret < 0:
            trade.outcome = "LOSS"
        else:
            trade.outcome = "CLOSED"

        if self.storage:
            try:
                self.storage.update_shadow_trade(trade.model_dump())
            except Exception as err:
                log.warning("ShadowTradingEngine: failed closing shadow trade %s: %s", shadow_id, err)

        log.info("ShadowTradingEngine: CLOSED SHADOW TRADE %s for %s (Final Return: %.2f%%, Outcome: %s, Reason: %s)",
                 shadow_id, trade.asset, final_ret * 100, trade.outcome, reason)

        return trade

    def get_active_shadow_trades(self) -> List[ShadowTrade]:
        """Return active open shadow trades."""
        return [t for t in self._active_shadow_trades.values() if t.outcome == "OPEN"]
