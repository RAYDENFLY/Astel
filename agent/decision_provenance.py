"""
agent/decision_provenance.py — Phase 12.2 Decision Provenance Manager

Manages saving, retrieving, and auditing decision proposals, specialist breakdowns,
evidence fusion metrics, and risk supervisor reviews.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.schema import DecisionProposal, RiskSupervisorReview
from agent.storage import AgentStorage

log = logging.getLogger("agent.decision_provenance")


class DecisionProvenanceManager:
    """
    Manages decision provenance storage and audit retrieval.
    """
    def __init__(self, storage: Optional[AgentStorage] = None):
        self.storage = storage

    def record_decision(
        self,
        proposal: DecisionProposal,
        review: Optional[RiskSupervisorReview] = None,
    ) -> None:
        """Persist decision proposal and optional risk review to storage."""
        if not self.storage:
            log.warning("DecisionProvenanceManager: storage not configured — skipping persist")
            return

        try:
            prop_dict = proposal.model_dump()
            self.storage.save_decision_proposal(prop_dict)

            if review:
                rev_dict = review.model_dump()
                self.storage.save_risk_supervisor_review(rev_dict)

            log.info("DecisionProvenanceManager: saved decision provenance for proposal %s (%s)", proposal.decision_id, proposal.asset)
        except Exception as err:
            log.warning("DecisionProvenanceManager: failed to save provenance: %s", err)

    def get_recent_proposals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent stored decision proposals."""
        if not self.storage:
            return []
        return self.storage.get_recent_decision_proposals(limit=limit)

    def get_recent_reviews(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent risk supervisor reviews."""
        if not self.storage:
            return []
        return self.storage.get_recent_risk_supervisor_reviews(limit=limit)
