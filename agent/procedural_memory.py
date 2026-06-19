"""
agent/procedural_memory.py — Phase 7D.1: Procedural Memory Context Injection.

Injects validated memory patterns into planning context.
Memory is advisory only — planner authority remains unchanged.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.storage import AgentStorage

log = logging.getLogger("agent.procedural_memory")

TOP_K = 5


class ProceduralMemory:
    """
    Selects relevant validated patterns and builds memory context
    for planner consumption. Advisory only.
    """

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage

    def get_relevant_rules(
        self,
        survival_mode: str,
        analyst_consensus: str,
        debate_verdict: str,
    ) -> List[Dict[str, Any]]:
        """
        Find validated patterns matching current conditions.
        Sorted by validation_score DESC, confidence_score DESC.
        Returns top 5.
        """
        patterns = self._storage.get_validated_patterns(limit=100)
        if not patterns:
            return []

        scored = []
        for p in patterns:
            try:
                cond = p.get("condition_json", "{}")
                if isinstance(cond, str):
                    cond = json.loads(cond)
            except Exception:
                continue

            score = 0
            p_action = str(p.get("action_type", ""))
            p_mode = cond.get("survival_mode", "")
            p_analyst = cond.get("analyst_consensus", "")
            p_debate = cond.get("debate_verdict", "")

            if p_mode and p_mode == survival_mode:
                score += 10
            if p_analyst and p_analyst == analyst_consensus:
                score += 5
            if p_debate and p_debate == debate_verdict:
                score += 3

            if p_action in ("PAUSE_ENTRIES", "TIGHTEN_RISK", "REDUCE_POSITION"):
                score += 2

            if score > 0:
                scored.append((score, p))

        # Sort by match score, then validation_score
        scored.sort(key=lambda x: (x[0], float(x[1].get("validation_score", 0) or 0)), reverse=True)
        return [p for _, p in scored[:TOP_K]]

    def build_memory_context(
        self,
        survival_mode: str,
        analyst_consensus: str,
        debate_verdict: str,
        treasury_usdt: float,
        drawdown_pct: float,
    ) -> Dict[str, Any]:
        """
        Build structured memory context for planner.

        Returns:
        {
            "memory_context": [
                {
                    "pattern_key": "...",
                    "success_rate": 0.84,
                    "sample_size": 37,
                    "validation_score": 0.88,
                    "recommendation": "..."
                }
            ],
            "rule_count": 3
        }
        """
        rules = self.get_relevant_rules(survival_mode, analyst_consensus, debate_verdict)

        memory_context = []
        for r in rules:
            action = str(r.get("action_type", ""))
            success_rate = float(r.get("success_rate", 0))
            sample_size = int(r.get("sample_size", 0))
            val_score = float(r.get("validation_score", 0) or 0)

            # Build human-readable recommendation
            if success_rate >= 0.7 and action in ("PAUSE_ENTRIES", "TIGHTEN_RISK", "REDUCE_POSITION"):
                rec = f"Historically {action} performed well (success_rate={success_rate:.0%}) during {survival_mode} mode."
            else:
                rec = f"Pattern suggests {action} with {success_rate:.0%} historical success."

            memory_context.append({
                "pattern_key": r.get("pattern_key", ""),
                "success_rate": success_rate,
                "sample_size": sample_size,
                "validation_score": val_score,
                "recommendation": rec,
            })

        return {
            "memory_context": memory_context,
            "rule_count": len(memory_context),
        }

    def inject_for_plan(
        self,
        plan_id: int,
        survival_mode: str,
        analyst_consensus: str,
        debate_verdict: str,
        treasury_usdt: float,
        drawdown_pct: float,
    ) -> Dict[str, Any]:
        """
        Create memory context and store injection record.
        Returns context dict. Advisory only — planner is unchanged.
        """
        context = self.build_memory_context(
            survival_mode=survival_mode,
            analyst_consensus=analyst_consensus,
            debate_verdict=debate_verdict,
            treasury_usdt=treasury_usdt,
            drawdown_pct=drawdown_pct,
        )

        # Store injection record
        try:
            self._storage.save_memory_injection(
                ts=datetime.now(tz=timezone.utc),
                plan_id=plan_id,
                rule_count=context["rule_count"],
                rules_json=json.dumps(context["memory_context"]),
            )
        except Exception:
            log.exception("Failed to save memory injection record (non-fatal)")

        return context

    def get_memory_summary(self, limit: int = 5) -> Dict[str, Any]:
        """Return recent injections + stats."""
        injections = self._storage.get_recent_memory_injections(limit=limit)
        stats = self._storage.get_memory_injection_stats()
        return {"injections": injections, "stats": stats}