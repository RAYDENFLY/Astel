"""
agent/shadow_trading.py — Phase 12.3 Live Read-Only Shadow Trading Engine

Simulates live trades without order submission or exchange interaction.

CRITICAL EXECUTION SAFETY BOUNDARY:
- EXECUTION_MODE = "SHADOW"
- ZERO live order placement
- ZERO exchange API order submission
- Simulated tracking ONLY
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

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
        self._recorded_decision_ids: Set[str] = set()

        # Hydrate active trades and recorded decision IDs from storage if available
        if self.storage:
            try:
                recent_trades = self.storage.get_recent_shadow_trades(limit=200)
                for t_dict in recent_trades:
                    dec_id = t_dict.get("decision_id")
                    if dec_id:
                        self._recorded_decision_ids.add(dec_id)
                    if t_dict.get("outcome") == "OPEN":
                        st = ShadowTrade(**t_dict)
                        self._active_shadow_trades[st.shadow_id] = st
                log.info("ShadowTradingEngine initialized with %d active trades and %d decision records from DB",
                         len(self._active_shadow_trades), len(self._recorded_decision_ids))
            except Exception as e:
                log.warning("ShadowTradingEngine: error loading state from storage: %s", e)

    def record_decision(
        self,
        proposal: DecisionProposal,
        review: RiskSupervisorReview,
        reference_price: float,
    ) -> Optional[ShadowTrade]:
        """Alias for process_decision_review to match API context."""
        return self.process_decision_review(proposal, review, reference_price)

    def process_decision_review(
        self,
        proposal: DecisionProposal,
        review: RiskSupervisorReview,
        reference_price: float,
    ) -> Optional[ShadowTrade]:
        """
        Creates a simulated ShadowTrade if proposal is APPROVED_FOR_RISK_REVIEW and TRADE_CANDIDATE.
        Enforces strict idempotency and structured read-only logging.
        """
        # Idempotency Guard 1: Duplicate decision_id check
        if proposal.decision_id in self._recorded_decision_ids:
            log.info("[SHADOW] decision skipped asset=%s reason=DUPLICATE decision_id=%s",
                     proposal.asset, proposal.decision_id)
            return None

        # Idempotency Guard 2: Active open trade on same asset and direction check
        if any(t.asset == proposal.asset and t.outcome == "OPEN" and t.direction == proposal.direction
               for t in self._active_shadow_trades.values()):
            log.info("[SHADOW] decision skipped asset=%s reason=ACTIVE_TRADE_EXISTS decision_id=%s",
                     proposal.asset, proposal.decision_id)
            self._recorded_decision_ids.add(proposal.decision_id)
            return None

        # Eligibility Check: Only approved TRADE_CANDIDATE proposals become shadow trades
        if review.status != "APPROVED_FOR_RISK_REVIEW" or proposal.decision != "TRADE_CANDIDATE":
            skip_reason = review.status if review.status != "APPROVED_FOR_RISK_REVIEW" else proposal.decision
            log.info("[SHADOW] decision skipped asset=%s reason=%s decision_id=%s",
                     proposal.asset, skip_reason, proposal.decision_id)
            self._recorded_decision_ids.add(proposal.decision_id)
            return None

        # Reference Price Check
        if reference_price <= 0:
            log.warning("[SHADOW] decision skipped asset=%s reason=INVALID_PRICE decision_id=%s",
                        proposal.asset, proposal.decision_id)
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

        self._recorded_decision_ids.add(proposal.decision_id)
        self._active_shadow_trades[shadow_id] = shadow_trade

        if self.storage:
            try:
                self.storage.save_shadow_trade(shadow_trade.model_dump())
            except Exception as err:
                log.warning("ShadowTradingEngine: failed persisting shadow trade %s: %s", shadow_id, err)

        log.info("[SHADOW] decision recorded asset=%s direction=%s confidence=%.2f risk_status=%s decision_id=%s",
                 proposal.asset, proposal.direction, proposal.confidence, review.status, proposal.decision_id)

        return shadow_trade

    def update_prices(self, current_prices: Dict[str, float]) -> List[ShadowTrade]:
        """
        Updates unrealized return, MFE (Max Favorable Excursion), and MAE (Max Adverse Excursion)
        for all open shadow trades using live price updates.
        Also evaluates trade lifecycle (expiry / TP / SL).
        """
        updated_trades: List[ShadowTrade] = []
        now_dt = datetime.now(tz=timezone.utc)

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

            # Check Lifecycle Expiry (12 Hours Horizon or TP/SL)
            try:
                ts_dt = datetime.fromisoformat(trade.timestamp.replace("Z", "+00:00"))
                age_hours = (now_dt - ts_dt).total_seconds() / 3600.0

                if age_hours >= 12.0:
                    self.close_shadow_trade(shadow_id, price, reason="HORIZON_REACHED")
                elif ret >= 0.03:
                    self.close_shadow_trade(shadow_id, price, reason="TAKE_PROFIT")
                elif ret <= -0.02:
                    self.close_shadow_trade(shadow_id, price, reason="STOP_LOSS")
            except Exception as exp_err:
                log.warning("ShadowTradingEngine: error evaluating lifecycle for %s: %s", shadow_id, exp_err)

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
