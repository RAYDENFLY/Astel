"""
agent/memory_miner.py — Phase 7C: Semantic Memory & Pattern Mining.

Discovers recurring patterns from resolved episodes.
Idempotent: re-running with no new episodes produces identical statistics.

Observational only. No planner modifications, no action overrides.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.storage import AgentStorage

log = logging.getLogger("agent.memory_miner")

# Minimum samples to form a pattern
MIN_SAMPLE_SIZE = 5

# Thresholds for pattern significance
HIGH_SUCCESS_RATE = 0.70
LOW_SUCCESS_RATE = 0.30


class MemoryMiner:
    """
    Mines resolved episodes for recurring patterns.

    Groups by: action_type, survival_mode, analyst_consensus, debate_verdict
    Only creates patterns meeting significance thresholds.

    Idempotency: tracks the max episode_id processed per pattern.
    On re-run, only processes episodes with id > checkpoint.
    """

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage

    def mine_patterns(self) -> int:
        """
        Scan resolved episodes, group by context conditions,
        compute success rates, save significant patterns.

        Idempotent: re-running with no new episodes produces
        identical sample_size, success_rate, and confidence_score.

        Returns: number of patterns created or updated.
        """
        # Get ALL resolved episodes (up to 500)
        all_eps = self._storage.get_recent_episodes(limit=500)
        resolved = [ep for ep in all_eps if ep.get("resolved") is True or ep.get("resolved") == 1]

        if not resolved:
            return 0

        # Get existing patterns to check their checkpoints
        existing_patterns = self._storage.get_patterns(limit=200)
        checkpoints: Dict[str, int] = {}
        for p in existing_patterns:
            key = p.get("pattern_key", "")
            cid = p.get("last_episode_id_processed", 0)
            checkpoints[key] = int(cid) if cid else 0

        # Determine which episodes are NEW (never processed before)
        # For each pattern, we only count episodes whose id > its checkpoint
        # Since patterns group by conditions, we need to filter globally:
        # min_checkpoint = min of all checkpoints (or 0 if no patterns exist)
        # We'll process ALL episodes but only ADD the ones past each pattern's checkpoint

        # Group episodes by (action_type, survival_mode, analyst_consensus, debate_verdict)
        groups: Dict[str, Dict[str, Any]] = {}

        for ep in resolved:
            episode_id = int(ep.get("id", 0))
            action_type = str(ep.get("action_type", "unknown"))
            survival_mode = str(ep.get("survival_mode", "unknown"))
            analyst_consensus = str(ep.get("analyst_consensus", "unknown"))
            debate_verdict = str(ep.get("debate_verdict", "unknown"))

            condition = {
                "survival_mode": survival_mode,
                "analyst_consensus": analyst_consensus,
                "debate_verdict": debate_verdict,
            }
            pattern_key = f"{action_type}|{survival_mode}|{analyst_consensus}|{debate_verdict}"

            if pattern_key not in groups:
                groups[pattern_key] = {
                    "pattern_key": pattern_key,
                    "action_type": action_type,
                    "condition_json": json.dumps(condition),
                    "sample_size": 0,           # NEW episodes count only
                    "positive_count": 0,         # NEW episodes count only
                    "negative_count": 0,
                    "neutral_count": 0,
                    "all_sample_size": 0,        # ALL episodes in group (for checkpoint calc)
                    "max_episode_id": 0,         # max episode id seen in this group
                    "episode_ids": set(),        # track unique episode IDs
                }

            g = groups[pattern_key]
            g["all_sample_size"] += 1
            g["episode_ids"].add(episode_id)
            if episode_id > g["max_episode_id"]:
                g["max_episode_id"] = episode_id

            # Is this episode NEW (past the checkpoint for this pattern)?
            checkpoint = checkpoints.get(pattern_key, 0)
            if episode_id <= checkpoint:
                continue  # already counted in previous runs

            g["sample_size"] += 1

            # Extract decision quality from outcome_json
            outcome = ep.get("outcome_json", "{}")
            if isinstance(outcome, str):
                try:
                    outcome = json.loads(outcome)
                except Exception:
                    outcome = {}
            if isinstance(outcome, dict):
                quality = outcome.get("decision_quality", "neutral")
                if quality == "positive":
                    g["positive_count"] += 1
                elif quality == "negative":
                    g["negative_count"] += 1
                else:
                    g["neutral_count"] += 1

        # Process each group
        patterns_created = 0

        for pattern_key, g in groups.items():
            checkpoint = checkpoints.get(pattern_key, 0)
            new_count = g["sample_size"]  # NEW episodes this run
            total_all = g["all_sample_size"]  # ALL episodes ever seen
            max_ep_id = g["max_episode_id"]

            # ---- Load existing counts from DB ----
            existing = self._storage.get_pattern_by_key(pattern_key)

            if existing:
                base_sample = int(existing.get("sample_size", 0))
                base_positive = int(existing.get("positive_count", 0))
                base_negative = int(existing.get("negative_count", 0))
                base_neutral = int(existing.get("neutral_count", 0))
            else:
                base_sample = 0
                base_positive = 0
                base_negative = 0
                base_neutral = 0

            # ---- Total = base (from previous runs) + new (this run) ----
            total_sample = base_sample + new_count
            total_positive = base_positive + g["positive_count"]
            total_negative = base_negative + g["negative_count"]
            total_neutral = base_neutral + g["neutral_count"]

            # ---- Skip if total sample below minimum ----
            if total_sample < MIN_SAMPLE_SIZE:
                continue

            # ---- Compute success_rate ----
            total_non_neutral = total_positive + total_negative
            success_rate = total_positive / max(1, total_non_neutral) if total_non_neutral > 0 else 0.5

            # ---- Only save if significant ----
            if success_rate < HIGH_SUCCESS_RATE and success_rate > LOW_SUCCESS_RATE:
                continue

            # ---- Compute confidence score ----
            sample_weight = 1.0 - math.exp(-total_sample / 10.0)
            distance_from_random = abs(success_rate - 0.5) * 2.0
            confidence_score = round(sample_weight * distance_from_random, 4)

            # ---- Check for duplication risk ----
            # If no new episodes were added, the pattern should be identical
            duplicate_risk = "none"
            if new_count == 0 and existing:
                duplicate_risk = "reprocess_no_new_data"

            # ---- Determine the checkpoint to store ----
            # Store the max episode_id processed so far
            # We need to know the overall max from ALL episodes in this group
            all_ep_ids = g["episode_ids"]
            max_ep_processed = max(all_ep_ids) if all_ep_ids else 0

            # ---- Save pattern ----
            self._storage.save_pattern(
                pattern_key=g["pattern_key"],
                action_type=g["action_type"],
                condition_json=g["condition_json"],
                sample_size=total_sample,
                positive_count=total_positive,
                negative_count=total_negative,
                neutral_count=total_neutral,
                success_rate=round(success_rate, 4),
                confidence_score=confidence_score,
                last_episode_id_processed=max_ep_processed,
            )
            patterns_created += 1

        total_unique = sum(len(g["episode_ids"]) for g in groups.values())
        log.info(
            "MemoryMiner: processed %d patterns from %d unique episode IDs (%d new, %d total resolved)",
            patterns_created, total_unique,
            sum(g["sample_size"] for g in groups.values()),
            len(resolved),
        )

        return patterns_created

    def get_top_patterns(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return top patterns sorted by confidence_score."""
        patterns = self._storage.get_patterns(limit=limit * 2)
        patterns.sort(key=lambda p: float(p.get("confidence_score", 0)), reverse=True)
        return patterns[:limit]

    def get_audit(self) -> Dict[str, Any]:
        """Return memory integrity audit data."""
        patterns = self._storage.get_patterns(limit=200)
        all_eps = self._storage.get_recent_episodes(limit=500)
        resolved = [ep for ep in all_eps if ep.get("resolved") is True or ep.get("resolved") == 1]
        resolved_ids = set(int(ep.get("id", 0)) for ep in resolved)

        total_resolved = len(resolved_ids)
        total_patterns = len(patterns)

        # Check duplication risk: sum of all sample_sizes vs total resolved episodes
        total_sample = sum(int(p.get("sample_size", 0)) for p in patterns)
        total_p_positive = sum(int(p.get("positive_count", 0)) for p in patterns)
        total_p_negative = sum(int(p.get("negative_count", 0)) for p in patterns)

        # An episode can belong to only ONE pattern (one action per episode)
        # So total_sample should be <= total_resolved
        duplicate_risk = "none"
        if total_sample > total_resolved and total_resolved > 0:
            ratio = total_sample / total_resolved
            if ratio > 1.5:
                duplicate_risk = "high"
            elif ratio > 1.0:
                duplicate_risk = "medium"
            else:
                duplicate_risk = "low"

        # Check all patterns have checkpoints
        patterns_with_checkpoints = sum(1 for p in patterns if p.get("last_episode_id_processed", 0) > 0)

        integrity_status = "healthy"
        if duplicate_risk == "high":
            integrity_status = "degraded"
        elif duplicate_risk == "medium":
            integrity_status = "warning"

        return {
            "total_patterns": total_patterns,
            "total_resolved_episodes": total_resolved,
            "total_sample_count_all_patterns": total_sample,
            "total_positive_across_patterns": total_p_positive,
            "total_negative_across_patterns": total_p_negative,
            "patterns_with_checkpoints": patterns_with_checkpoints,
            "duplicate_risk": duplicate_risk,
            "integrity_status": integrity_status,
            "episode_coverage_ratio": round(total_sample / max(1, total_resolved), 4) if total_resolved > 0 else 0.0,
        }