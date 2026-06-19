"""
agent/pattern_validator.py — Phase 7C.2: Pattern Validation & Historical Replay.

Validates semantic patterns against historical episode data.
Only patterns meeting strict criteria become validated=True.

Observational only. No planner integration.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.storage import AgentStorage

log = logging.getLogger("agent.pattern_validator")

# Validation thresholds
MIN_SAMPLE_SIZE = 10
MIN_CONFIDENCE_SCORE = 0.60
MIN_SUCCESS_RATE = 0.70


class PatternValidator:
    """
    Validates semantic patterns by replaying historical episodes.

    A pattern is VALID only if ALL of:
      - sample_size >= 10
      - confidence_score >= 0.60
      - success_rate >= 0.70
      - average_survival_score_delta > 0

    Invalid patterns are deactivated (active=false).
    """

    def __init__(self, storage: AgentStorage) -> None:
        self._storage = storage

    def validate_patterns(self) -> Dict[str, Any]:
        """
        Validate all active patterns. Returns summary of results.
        """
        patterns = self._storage.get_patterns(limit=200)
        if not patterns:
            return {"total": 0, "validated": 0, "rejected": 0, "validation_rate": 0.0}

        validated_count = 0
        rejected_count = 0
        results = []

        for p in patterns:
            result = self._validate_single(p)
            results.append(result)
            if result["validated"]:
                validated_count += 1
            else:
                rejected_count += 1

        total = len(patterns)
        rate = round(validated_count / max(1, total), 4)

        log.info(
            "PatternValidator: validated=%d rejected=%d total=%d rate=%.2f",
            validated_count, rejected_count, total, rate,
        )

        return {
            "total_patterns": total,
            "validated": validated_count,
            "rejected": rejected_count,
            "validation_rate": rate,
        }

    def validate_pattern(self, pattern_key: str) -> Dict[str, Any]:
        """Validate a single pattern by key."""
        pattern = self._storage.get_pattern_by_key(pattern_key)
        if not pattern:
            return {"pattern_key": pattern_key, "error": "not_found", "validated": False}
        return self._validate_single(pattern)

    def _validate_single(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single pattern. Measures historical outcome metrics
        and applies qualification rules.
        """
        pattern_key = str(pattern.get("pattern_key", ""))
        action_type = str(pattern.get("action_type", ""))
        sample_size = int(pattern.get("sample_size", 0))
        success_rate = float(pattern.get("success_rate", 0.0))
        confidence_score = float(pattern.get("confidence_score", 0.0))

        # Extract condition from condition_json
        condition_json = pattern.get("condition_json", "{}")
        if isinstance(condition_json, str):
            try:
                condition = json.loads(condition_json)
            except Exception:
                condition = {}
        elif isinstance(condition_json, dict):
            condition = condition_json
        else:
            condition = {}

        survival_mode = condition.get("survival_mode", "")
        analyst_consensus = condition.get("analyst_consensus", "")
        debate_verdict = condition.get("debate_verdict", "")

        # ── Replay: find episodes matching this pattern ──
        all_eps = self._storage.get_recent_episodes(limit=500)
        matching = []
        for ep in all_eps:
            if ep.get("action_type") != action_type:
                continue
            if survival_mode and ep.get("survival_mode") != survival_mode:
                continue
            if analyst_consensus and ep.get("analyst_consensus") != analyst_consensus:
                continue
            if debate_verdict and ep.get("debate_verdict") != debate_verdict:
                continue
            matching.append(ep)

        replay_count = len(matching)

        # ── Compute validation metrics from matched episodes ──
        total_survival_delta = 0.0
        total_equity_delta = 0.0
        total_runway_delta = 0.0
        positive_count = 0
        negative_count = 0
        neutral_count = 0
        measured_count = 0

        for ep in matching:
            outcome = ep.get("outcome_json", "{}")
            if isinstance(outcome, str):
                try:
                    outcome = json.loads(outcome)
                except Exception:
                    outcome = {}

            if isinstance(outcome, dict):
                quality = outcome.get("decision_quality", "")
                if quality == "positive":
                    positive_count += 1
                elif quality == "negative":
                    negative_count += 1
                else:
                    neutral_count += 1

                # Deltas from resolved outcome
                surv_delta = outcome.get("survival_score_delta")
                equity_delta = outcome.get("equity_delta_pct")
                if surv_delta is not None:
                    total_survival_delta += float(surv_delta)
                    measured_count += 1
                if equity_delta is not None:
                    total_equity_delta += float(equity_delta)

        avg_survival_delta = round(total_survival_delta / max(1, measured_count), 4) if measured_count > 0 else 0.0
        avg_equity_delta = round(total_equity_delta / max(1, measured_count), 4) if measured_count > 0 else 0.0

        # ── Qualification Rules ──
        checks = {
            "sample_size_ok": sample_size >= MIN_SAMPLE_SIZE,
            "confidence_ok": confidence_score >= MIN_CONFIDENCE_SCORE,
            "success_rate_ok": success_rate >= MIN_SUCCESS_RATE,
            "survival_delta_positive": avg_survival_delta > 0,
        }
        validated = all(checks.values())

        # Compute validation_score = how strongly this passes
        # Range 0.0 to 1.0
        score_parts = []
        score_parts.append(min(1.0, sample_size / 50.0))
        score_parts.append(confidence_score)
        score_parts.append(success_rate)
        score_parts.append(min(1.0, max(0.0, avg_survival_delta / 10.0)))
        validation_score = round(sum(score_parts) / len(score_parts), 4)

        # Store validation result
        self._storage.validate_pattern(
            pattern_key=pattern_key,
            validated=validated,
            validation_score=validation_score,
        )

        result = {
            "pattern_key": pattern_key,
            "action_type": action_type,
            "sample_size": sample_size,
            "replay_episodes_found": replay_count,
            "success_rate": success_rate,
            "confidence_score": confidence_score,
            "avg_survival_score_delta": avg_survival_delta,
            "avg_equity_delta_pct": avg_equity_delta,
            "positive_count": positive_count,
            "negative_count": negative_count,
            "neutral_count": neutral_count,
            "checks": checks,
            "validated": validated,
            "validation_score": validation_score,
            "is_active": validated,  # deactivate if invalid
        }

        return result

    def get_validation_summary(self) -> Dict[str, Any]:
        """Return summary of all pattern validation states."""
        patterns = self._storage.get_patterns(limit=200)
        validated = self._storage.get_validated_patterns(limit=200)

        total = len(patterns)
        v_count = len(validated)
        r_count = total - v_count

        avg_score = 0.0
        if validated:
            avg_score = round(
                sum(float(p.get("validation_score", 0)) for p in validated) / max(1, len(validated)),
                4,
            )

        return {
            "total_patterns": total,
            "validated": v_count,
            "rejected": r_count,
            "validation_rate": round(v_count / max(1, total), 4),
            "average_validation_score": avg_score,
        }