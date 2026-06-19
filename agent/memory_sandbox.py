"""
agent/memory_sandbox.py — Phase 7D.0: Memory Sandbox & Counterfactual Decision Engine.

Evaluates how validated memory patterns would influence decisions
WITHOUT changing live trading behavior.

Read-only advisory layer. No planner, policy, or execution modifications.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.storage import AgentStorage

log = logging.getLogger("agent.memory_sandbox")


class MemoryAdvisor:
    """
    Evaluates current state against validated memory patterns
    and produces a counterfactual recommendation.

    Sandbox only — never modifies planner/policy/risk.
    """

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage

    def advise(
        self,
        plan_id: int,
        planner_decision: str,
        survival_mode: str,
        analyst_consensus: str,
        debate_verdict: str,
        treasury_usdt: float,
        drawdown_pct: float,
    ) -> Dict[str, Any]:
        """
        Produce a memory-based recommendation for the current plan.

        Returns:
        {
            "memory_recommendation": str,
            "confidence": float,
            "supporting_patterns": [...],
            "counterfactual_difference": bool,
            "reason": str
        }
        """
        # Get validated patterns
        validated = self._storage.get_validated_patterns(limit=50)

        if not validated:
            result = {
                "memory_recommendation": planner_decision,
                "confidence": 0.0,
                "supporting_patterns": [],
                "counterfactual_difference": False,
                "reason": "No validated patterns available",
            }
            self._save_advice(plan_id, planner_decision, result)
            return result

        # Find patterns matching current conditions
        matching = []
        for p in validated:
            try:
                cond = p.get("condition_json", "{}")
                if isinstance(cond, str):
                    cond = json.loads(cond)
            except Exception:
                continue

            p_action = str(p.get("action_type", ""))
            p_mode = cond.get("survival_mode", "")
            p_analyst = cond.get("analyst_consensus", "")
            p_debate = cond.get("debate_verdict", "")

            score = 0
            # Match survival mode
            if p_mode and p_mode == survival_mode:
                score += 3
            # Match analyst consensus
            if p_analyst and p_analyst == analyst_consensus:
                score += 2
            # Match debate
            if p_debate and p_debate == debate_verdict:
                score += 1
            # Action type relevance
            if p_action == "PAUSE_ENTRIES" or p_action == "TIGHTEN_RISK":
                score += 1

            if score >= 3:  # significant match
                matching.append({
                    "pattern_key": p.get("pattern_key"),
                    "action_type": p_action,
                    "success_rate": p.get("success_rate"),
                    "confidence_score": p.get("confidence_score"),
                    "validation_score": p.get("validation_score"),
                    "match_score": score,
                })

        # Determine recommendation from matching patterns
        if not matching:
            result = {
                "memory_recommendation": planner_decision,
                "confidence": 0.3,
                "supporting_patterns": [],
                "counterfactual_difference": False,
                "reason": "No patterns match current conditions",
            }
            self._save_advice(plan_id, planner_decision, result)
            return result

        # Sort by match score then validation score
        matching.sort(key=lambda m: (m["match_score"], float(m.get("validation_score", 0) or 0)), reverse=True)

        # Determine what patterns suggest
        pause_count = sum(1 for m in matching if m["action_type"] == "PAUSE_ENTRIES")
        tighten_count = sum(1 for m in matching if m["action_type"] == "TIGHTEN_RISK")
        reduce_count = sum(1 for m in matching if m["action_type"] in ("REDUCE_POSITION", "CLOSE_POSITION"))
        maintain_count = sum(1 for m in matching if m["action_type"] in ("RESUME_ENTRIES", "NOTIFY"))

        total = len(matching)
        avg_conf = sum(float(m.get("validation_score", 0) or 0) for m in matching) / max(1, total)

        # Decide recommendation
        if pause_count > total * 0.4:
            memory_rec = "pause"
        elif tighten_count > total * 0.3:
            memory_rec = "conservative"
        elif reduce_count > total * 0.3:
            memory_rec = "defensive"
        elif maintain_count > total * 0.5:
            memory_rec = "maintain"
        else:
            memory_rec = "maintain"

        # Map planner decision to comparison
        planner_map = {
            "maintain": "maintain",
            "pause": "pause",
            "conservative": "conservative",
            "defensive": "defensive",
            "PAUSE_ENTRIES": "pause",
            "TIGHTEN_RISK": "conservative",
            "REDUCE_POSITION": "defensive",
        }
        planner_norm = planner_map.get(planner_decision, "maintain")

        difference = memory_rec != planner_norm

        top_patterns = [m["pattern_key"] for m in matching[:3]]

        result = {
            "memory_recommendation": memory_rec,
            "confidence": round(min(avg_conf, 0.95), 4),
            "supporting_patterns": top_patterns,
            "counterfactual_difference": difference,
            "reason": (
                f"Memory suggests '{memory_rec}' vs planner '{planner_norm}'"
                f" ({len(matching)} matching patterns, avg_conf={avg_conf:.2f})"
            ),
        }

        self._save_advice(plan_id, planner_decision, result)
        return result

    def _save_advice(self, plan_id: int, planner_decision: str, result: Dict[str, Any]) -> None:
        """Store advice record in memory_advice table."""
        try:
            self._storage.save_memory_advice(
                ts=datetime.now(tz=timezone.utc),
                plan_id=plan_id,
                planner_decision=planner_decision,
                memory_decision=result["memory_recommendation"],
                difference_detected=result["counterfactual_difference"],
                confidence=result["confidence"],
                reason_json=json.dumps({
                    "reason": result["reason"],
                    "supporting_patterns": result["supporting_patterns"],
                }),
            )
        except Exception:
            log.exception("Failed to save memory advice (non-fatal)")


class CounterfactualEngine:
    """
    Quantifies how often memory disagrees with the planner.
    """

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage

    def get_stats(self) -> Dict[str, Any]:
        """Return counterfactual statistics from memory_advice."""
        return self._storage.get_memory_advice_stats()

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent memory advice records."""
        return self._storage.get_recent_memory_advice(limit=limit)