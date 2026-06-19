"""
agent/memory.py — Episode resolver for Phase 7B.

Evaluates unresolved episodes after an evaluation window,
computes deltas and decision quality.

No learning, no rule generation, no planner modifications.
Fully observational.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from agent.memory_attribution import MemoryAttributionEngine
from agent.storage import AgentStorage

log = logging.getLogger("agent.memory")

# Default evaluation window: 6 hours
DEFAULT_EVALUATION_WINDOW_HOURS = 6


class EpisodeResolver:
    """
    Resolves pending episodes by comparing current experiment metrics
    against stored episode metrics.

    Decision quality (deterministic, rule-based):
      - positive: survival_score_delta > 0 OR equity_delta_pct > 0
      - negative: survival_score_delta < 0 OR equity_delta_pct < 0
      - neutral:  otherwise
    """

    def __init__(
        self,
        storage: AgentStorage,
        evaluation_window_hours: float = DEFAULT_EVALUATION_WINDOW_HOURS,
        attribution_engine: Optional[MemoryAttributionEngine] = None,
    ) -> None:
        self._storage = storage
        self._attribution = attribution_engine
        self._evaluation_window = timedelta(hours=evaluation_window_hours)

    def resolve_pending_episodes(self) -> int:
        """
        Find all unresolved episodes that have aged past the evaluation window,
        compare with current experiment state, compute deltas, and resolve them.

        Returns: number of episodes resolved.
        """
        unresolved = self._storage.get_unresolved_episodes(limit=100)
        if not unresolved:
            return 0

        now = datetime.now(tz=timezone.utc)
        exp = self._storage.get_active_experiment()
        if not exp:
            log.warning("EpisodeResolver: no active experiment — cannot resolve episodes")
            return 0

        # Current experiment metrics for comparison
        current_survival_score = float(exp.get("survival_score", 0.0))
        current_capital = float(exp.get("current_capital", 0.0))

        resolved_count = 0

        for ep in unresolved:
            try:
                resolved = self._resolve_single(
                    episode=ep,
                    now=now,
                    current_survival_score=current_survival_score,
                    current_capital=current_capital,
                )
                if resolved:
                    resolved_count += 1
            except Exception:
                log.exception("EpisodeResolver: failed to resolve episode %s", ep.get("id"))
                continue

        if resolved_count > 0:
            log.info("EpisodeResolver: resolved %d episodes", resolved_count)

        return resolved_count

    def _resolve_single(
        self,
        episode: Dict[str, Any],
        now: datetime,
        current_survival_score: float,
        current_capital: float,
    ) -> bool:
        """Resolve a single episode. Returns True if resolved."""
        episode_id = episode["id"]
        episode_ts_str = episode.get("ts", "")

        if not episode_ts_str:
            return False

        # Parse episode timestamp
        try:
            episode_ts_str_clean = str(episode_ts_str).replace("Z", "+00:00").replace(" ", "T")
            episode_ts = datetime.fromisoformat(episode_ts_str_clean)
        except Exception:
            log.warning("EpisodeResolver: cannot parse ts=%s for episode %d", episode_ts_str, episode_id)
            return False

        # Check if evaluation window has elapsed
        age = now - episode_ts
        if age < self._evaluation_window:
            return False  # too young, skip

        # Extract episode's stored values
        stored_survival_score = float(episode.get("survival_score", 0.0))
        stored_treasury = float(episode.get("treasury_usdt", 0.0))

        # Parse existing outcome_json to preserve action result
        existing_outcome = {}
        outcome_raw = episode.get("outcome_json", "{}")
        if outcome_raw:
            try:
                if isinstance(outcome_raw, str):
                    existing_outcome = json.loads(outcome_raw)
                elif isinstance(outcome_raw, dict):
                    existing_outcome = outcome_raw
            except Exception:
                existing_outcome = {}

        # Compute deltas
        survival_score_delta = current_survival_score - stored_survival_score
        equity_delta = current_capital - stored_treasury
        equity_delta_pct = (equity_delta / max(0.01, stored_treasury)) * 100.0 if stored_treasury > 0 else 0.0

        # Classify decision quality
        if survival_score_delta > 0 or equity_delta_pct > 0:
            decision_quality = "positive"
        elif survival_score_delta < 0 or equity_delta_pct < 0:
            decision_quality = "negative"
        else:
            decision_quality = "neutral"

        # Build resolved outcome_json
        resolved_outcome = {
            "resolved": True,
            "evaluation_window_hours": self._evaluation_window.total_seconds() / 3600,
            "equity_before": round(stored_treasury, 4),
            "equity_after": round(current_capital, 4),
            "equity_delta_pct": round(equity_delta_pct, 4),
            "survival_score_before": round(stored_survival_score, 4),
            "survival_score_after": round(current_survival_score, 4),
            "survival_score_delta": round(survival_score_delta, 4),
            "decision_quality": decision_quality,
            "age_hours": round(age.total_seconds() / 3600, 2),
            # Preserve original action result
            "action_success": existing_outcome.get("success"),
            "action_result": existing_outcome.get("result"),
            "guardrail_blocked": existing_outcome.get("guardrail_blocked"),
        }

        # Store resolved outcome
        self._storage.resolve_episode(
            episode_id=episode_id,
            outcome_json=json.dumps(resolved_outcome),
        )

        # ── Phase 7D.3: Attribute outcome to memory (if attribution engine is available) ──
        if self._attribution is not None:
            try:
                self._attribution.attribute_outcome(
                    episode_id=episode_id,
                    outcome_quality=decision_quality,
                    survival_score_delta=survival_score_delta,
                    equity_delta_pct=equity_delta_pct,
                )
            except Exception:
                log.exception("Memory attribution failed for episode %d (non-fatal)", episode_id)

        log.info(
            "Episode %d resolved: quality=%s surv_delta=%.2f equity_delta=%.2f%% age=%.1fh",
            episode_id, decision_quality, survival_score_delta, equity_delta_pct,
            age.total_seconds() / 3600,
        )

        return True
