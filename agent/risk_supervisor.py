"""
agent/risk_supervisor.py — Phase 12.2 Risk Supervisor Module

Independent supervisor review layer that reviews DecisionProposals.
Outputs ONLY RiskSupervisorReview status: APPROVED_FOR_RISK_REVIEW | REJECTED | WATCH.

CRITICAL SAFETY BOUNDARY:
- NO order submission
- NO position sizing
- NO leverage calculation
- NO live execution calls allowed
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.schema import DecisionProposal, RiskSupervisorReview, AgentSnapshot

log = logging.getLogger("agent.risk_supervisor")


class RiskSupervisor:
    """
    Independent Risk Supervisor review layer.
    Performs deterministic risk filtering on DecisionProposals without placing orders.
    """

    def review_proposal(
        self,
        proposal: DecisionProposal,
        snapshot: Optional[AgentSnapshot] = None,
    ) -> RiskSupervisorReview:
        """
        Reviews a DecisionProposal against risk rules and portfolio constraints.
        Returns RiskSupervisorReview.
        """
        asset = proposal.asset
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        rejection_reasons: List[str] = []
        risk_score = 0.20  # Base low risk

        fusion = proposal.fusion_result

        # 1. Reject if Decision is NO_TRADE
        if proposal.decision == "NO_TRADE":
            rejection_reasons.append("Decision proposal is NO_TRADE")
            return RiskSupervisorReview(
                proposal_id=proposal.decision_id,
                asset=asset,
                status="REJECTED",
                rejection_reasons=rejection_reasons,
                risk_score=1.0,
                timestamp=now_iso,
                reviewed_decision=proposal.decision,
            )

        # 2. Check Contradiction Level
        if fusion and fusion.contradiction_level == "STRONG_CONTRADICTION":
            rejection_reasons.append("Rejected due to STRONG_CONTRADICTION among specialist evidence")
            risk_score += 0.40

        # 3. Check Confidence Band
        if fusion and fusion.confidence_band not in ("HIGH", "MEDIUM"):
            rejection_reasons.append(f"Rejected due to insufficient confidence band ({fusion.confidence_band})")
            risk_score += 0.30

        # 4. Check Data Freshness & Quality
        if proposal.data_quality < 0.40:
            rejection_reasons.append(f"Rejected due to low evidence data quality ({proposal.data_quality:.2f})")
            risk_score += 0.30

        # 5. Check Portfolio Drawdown (from snapshot if provided)
        if snapshot and hasattr(snapshot, "account"):
            dd = snapshot.account.drawdown_pct
            if dd > 15.0:
                rejection_reasons.append(f"Rejected due to high portfolio drawdown ({dd:.1f}% > 15.0%)")
                risk_score += 0.50

        # Determine Final Status
        if proposal.decision == "WATCH":
            status = "WATCH"
            if not rejection_reasons:
                rejection_reasons.append("Placed on WATCH list pending market confirmation")
        elif rejection_reasons:
            status = "REJECTED"
        else:
            status = "APPROVED_FOR_RISK_REVIEW"

        log.info("RiskSupervisor: proposal %s for %s reviewed -> status: %s (risk_score: %.2f)",
                 proposal.decision_id, asset, status, risk_score)

        return RiskSupervisorReview(
            proposal_id=proposal.decision_id,
            asset=asset,
            status=status,
            rejection_reasons=rejection_reasons,
            risk_score=min(1.0, round(risk_score, 2)),
            timestamp=now_iso,
            reviewed_decision=proposal.decision,
        )
