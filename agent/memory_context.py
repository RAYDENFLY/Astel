"""
Phase 9.1 — MemoryContextBuilder: Rich context aggregator for Groq reasoning.

Aggregates ALL internal state before the LLM call so Groq can reason
like an AI Portfolio Manager instead of a chatbot.

Sources:
- ML prediction
- Procedural/validated patterns
- Episodic memory (recent outcomes)
- Shadow memory influence
- Portfolio state
- Risk metrics
- Market conditions

All data is sourced from existing AgentStorage queries.
No new storage schema required.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agent.memory import EpisodeResolver
from agent.memory_attribution import MemoryAttributionEngine
from agent.memory_shadow import ShadowMemoryInfluence
from agent.procedural_memory import ProceduralMemory
from agent.schema import AgentSnapshot
from agent.storage import AgentStorage

log = logging.getLogger("agent.memory_context")


class MemoryContextBuilder:
    """
    Aggregates every meaningful state dimension into a structured context dict
    that feeds into the LLM prompt for high-quality reasoning.
    """

    def __init__(
        self,
        storage: AgentStorage,
        procedural_memory: ProceduralMemory,
        shadow_influence: ShadowMemoryInfluence,
        attribution_engine: MemoryAttributionEngine,
        episode_resolver: EpisodeResolver,
    ) -> None:
        self._storage = storage
        self._procedural_memory = procedural_memory
        self._shadow_influence = shadow_influence
        self._attribution_engine = attribution_engine
        self._episode_resolver = episode_resolver

    def build_context(
        self,
        snapshot: AgentSnapshot,
        survival_mode: str = "NORMAL",
        analyst_consensus: str = "neutral",
        debate_verdict: str = "neutral",
        planner_confidence: float = 0.5,
        planner_action: str = "HOLD",
        ml_prediction: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build a comprehensive context string for the LLM prompt.

        This is the single aggregation point for ALL internal state.
        """
        sections = []

        # ── 1. Market Prediction Context ──
        sections.append(self._build_prediction_context(ml_prediction))

        # ── 2. Procedural Memory (Validated Patterns) ──
        sections.append(self._build_procedural_context(survival_mode, analyst_consensus, debate_verdict))

        # ── 3. Episodic Memory (Recent Outcomes) ──
        sections.append(self._build_episodic_context())

        # ── 4. Shadow Memory Influence ──
        sections.append(self._build_shadow_context(
            planner_action, planner_confidence, survival_mode,
            analyst_consensus, debate_verdict, snapshot,
        ))

        # ── 5. Portfolio State ──
        sections.append(self._build_portfolio_context(snapshot))

        # ── 6. Risk Metrics ──
        sections.append(self._build_risk_context(snapshot, survival_mode))

        # ── 7. Memory Attribution (learning signal) ──
        sections.append(self._build_attribution_context())

        # Join all sections with clear separators
        return "\n\n".join(s for s in sections if s)

    def _build_prediction_context(self, ml_prediction: Optional[Dict[str, Any]]) -> str:
        """ML model output context."""
        if not ml_prediction:
            return "=== ML PREDICTION ===\nNo prediction available."

        direction = str(ml_prediction.get("direction", "HOLD"))
        probability = ml_prediction.get("probability", 0.0)
        confidence = ml_prediction.get("confidence", 0.0)
        top_features = ml_prediction.get("top_features", [])
        regime = ml_prediction.get("market_regime", "unknown")
        volatility = ml_prediction.get("volatility", "unknown")

        lines = [
            "=== ML PREDICTION ===",
            f"Direction: {direction}",
            f"Probability: {probability:.2%}",
            f"Model Confidence: {confidence:.2%}",
            f"Market Regime: {regime}",
            f"Volatility: {volatility}",
        ]
        if top_features:
            lines.append("Top Features:")
            for feat in top_features[:5]:
                name = feat.get("name", "?")
                imp = feat.get("importance", 0)
                value = feat.get("value", "?")
                lines.append(f"  - {name}: importance={imp:.4f}, value={value}")

        return "\n".join(lines)

    def _build_procedural_context(
        self,
        survival_mode: str,
        analyst_consensus: str,
        debate_verdict: str,
    ) -> str:
        """Validated procedural patterns from memory."""
        patterns = self._procedural_memory.get_relevant_rules(
            survival_mode=survival_mode,
            analyst_consensus=analyst_consensus,
            debate_verdict=debate_verdict,
        )

        if not patterns:
            return "=== VALIDATED PATTERNS ===\nNo validated patterns available."

        lines = ["=== VALIDATED PATTERNS (Procedural Memory) ==="]
        for p in patterns[:5]:
            lines.append(
                f"  Pattern: {p.get('pattern_key', '?')} | "
                f"Action: {p.get('action_type', '?')} | "
                f"Confidence: {float(p.get('confidence_score', 0)):.2f} | "
                f"Success Rate: {float(p.get('success_rate', 0)):.1%} | "
                f"Samples: {p.get('sample_size', 0)}"
            )

        # Count pattern statistics
        total = len(patterns)
        high_conf = sum(1 for p in patterns if float(p.get('confidence_score', 0)) >= 0.7)
        lines.append(f"\nSummary: {total} relevant patterns found, {high_conf} high-confidence.")

        return "\n".join(lines)

    def _build_episodic_context(self) -> str:
        """Recent resolved episodes with outcomes."""
        episodes = self._storage.get_recent_episodes(limit=20)
        resolved = [ep for ep in episodes if ep.get("resolved")]

        if not resolved:
            return "=== EPISODIC MEMORY ===\nNo resolved episodes yet."

        # Get attribution metrics for learning signals
        attribution_metrics = self._attribution_engine.get_attribution_metrics()

        lines = ["=== EPISODIC MEMORY (Last 10 Resolved) ==="]

        # Show last 10 resolved episodes
        for ep in resolved[:10]:
            outcome = ep.get("outcome_json", {})
            if isinstance(outcome, str):
                import json
                try:
                    outcome = json.loads(outcome)
                except Exception:
                    outcome = {}
            quality = outcome.get("decision_quality", "unknown")
            pnl = outcome.get("pnl_delta", 0)
            drawdown = outcome.get("drawdown_change", 0)

            lines.append(
                f"  Action: {ep.get('action_type', '?')} | "
                f"Quality: {quality} | "
                f"PnL Delta: {pnl:+.2f} | "
                f"DD Change: {drawdown:+.1f}% | "
                f"Mode: {ep.get('survival_mode', '?')}"
            )

        # Attribution summary
        lines.append("\n=== MEMORY ATTRIBUTION ===")
        lines.append(f"  Total Attributions: {attribution_metrics.get('total_attributions', 0)}")
        lines.append(f"  Avg Contribution: {attribution_metrics.get('average_contribution_score', 0):.4f}")
        lines.append(f"  Success Rate: {attribution_metrics.get('memory_success_rate', 0):.1%}")
        lines.append(f"  Alignment Rate: {attribution_metrics.get('memory_alignment_rate', 0):.1%}")

        return "\n".join(lines)

    def _build_shadow_context(
        self,
        planner_action: str,
        planner_confidence: float,
        survival_mode: str,
        analyst_consensus: str,
        debate_verdict: str,
        snapshot: AgentSnapshot,
    ) -> str:
        """Shadow memory influence metrics."""
        try:
            metrics = self._storage.get_shadow_memory_influence_metrics()
        except Exception:
            metrics = {}

        lines = ["=== SHADOW MEMORY INFLUENCE ==="]

        if metrics:
            total = metrics.get("total_evaluations", 0)
            agree = metrics.get("agreement_count", 0)
            disagree = metrics.get("disagreement_count", 0)
            avg_influence = metrics.get("avg_shadow_influence_score", 0)
            avg_mem_conf = metrics.get("avg_memory_confidence", 0)

            lines.append(f"  Total Evaluations: {total}")
            lines.append(f"  Agree: {agree} | Disagree: {disagree}")
            lines.append(f"  Agreement Rate: {agree / max(1, total):.1%}")
            lines.append(f"  Avg Shadow Score: {avg_influence:.4f}")
            lines.append(f"  Avg Memory Confidence: {avg_mem_conf:.4f}")
        else:
            lines.append("No shadow influence data yet.")

        # Recent influence disagreements (overrides worth considering)
        try:
            recent = self._storage.get_recent_shadow_memory_influence(limit=5)
            if recent:
                lines.append("\nRecent Memory Disagreements:")
                for inf in recent:
                    if inf.get("agreement") == "DISAGREE":
                        lines.append(
                            f"  Planner: {inf.get('planner_action', '?')} vs "
                            f"Memory: {inf.get('memory_action', '?')} | "
                            f"Conf Δ: {float(inf.get('memory_confidence', 0)) - float(inf.get('planner_confidence', 0)):+.2f}"
                        )
        except Exception:
            pass

        return "\n".join(lines)

    def _build_portfolio_context(self, snapshot: AgentSnapshot) -> str:
        """Current portfolio and position state."""
        lines = ["=== PORTFOLIO STATE ==="]
        lines.append(f"  Equity: ${snapshot.account.equity:.2f}")
        lines.append(f"  Available: ${snapshot.account.available:.2f}")
        lines.append(f"  Drawdown: {snapshot.account.drawdown_pct:.1f}%")
        lines.append(f"  Exposure: {snapshot.account.exposure_x:.2f}x")
        lines.append(f"  Open Positions: {snapshot.account.open_positions}")
        lines.append(f"  Unrealized PnL: ${snapshot.account.unrealized_pnl:.2f}")
        lines.append(f"  Treasury: ${snapshot.treasury_usdt:.2f}")
        lines.append(f"  Survival Mode: {snapshot.survival_mode}")

        # Positions detail
        if snapshot.positions:
            lines.append("\nPositions:")
            for p in snapshot.positions:
                lines.append(
                    f"  {p.contract} {p.side} | "
                    f"Size: {p.size} | "
                    f"Entry: {p.entry_price} | "
                    f"uPnL: ${p.unrealized_pnl:.2f}"
                )

        # Recent realized PnL
        lines.append(f"\n  Realized PnL 7d: ${snapshot.realized_pnl_7d:.2f}")
        lines.append(f"  Realized PnL 30d: ${snapshot.realized_pnl_30d:.2f}")
        lines.append(f"  Win Rate 30d: {snapshot.win_rate_30d:.1%}")

        return "\n".join(lines)

    def _build_risk_context(self, snapshot: AgentSnapshot, survival_mode: str) -> str:
        """Current risk state and constraints."""
        lines = ["=== RISK STATE ==="]
        lines.append(f"  Survival Mode: {survival_mode}")
        lines.append(f"  Agent Mode: {snapshot.agent_mode.value}")
        lines.append(f"  Drawdown: {snapshot.account.drawdown_pct:.1f}%")
        lines.append(f"  Exposure: {snapshot.account.exposure_x:.2f}x")
        lines.append(f"  Order Rate 4h: {snapshot.account.order_rate_4h}")
        lines.append(f"  Runner Errors: {snapshot.runner_error_count}")
        lines.append(f"  LLM Cost Today: ${snapshot.llm_cost_today_usd:.4f}")

        # Risk level classification
        dd = snapshot.account.drawdown_pct
        if dd > -5:
            risk_level = "LOW"
        elif dd > -12:
            risk_level = "MEDIUM"
        elif dd > -20:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"
        lines.append(f"  Risk Level: {risk_level}")

        return "\n".join(lines)

    def _build_attribution_context(self) -> str:
        """Memory learning attribution summary."""
        try:
            metrics = self._attribution_engine.get_attribution_metrics()
        except Exception:
            return ""

        lines = ["=== MEMORY LEARNING ==="]
        lines.append(f"  Memory Success Rate: {metrics.get('memory_success_rate', 0):.1%}")
        lines.append(f"  Memory Alignment: {metrics.get('memory_alignment_rate', 0):.1%}")
        lines.append(f"  Avg Contribution Score: {metrics.get('average_contribution_score', 0):.4f}")
        lines.append(f"  Positive Outcomes: {metrics.get('memory_success_count', 0)}")
        lines.append(f"  Negative Outcomes: {metrics.get('memory_failure_count', 0)}")

        return "\n".join(lines)