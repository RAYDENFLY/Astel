"""
agent/researcher.py — Bull/Bear Researcher + Debate Engine.

Phase 5: Survival-focused deterministic researchers.

Primary question: "Can the agent survive and grow its treasury?"

BullResearcher: find evidence the agent is healthy and can survive.
BearResearcher: find evidence the agent is at risk of decline/failure.
DebateEngine: determine if current operating mode should remain or become more defensive.

No LLM dependency. No market data dependency. Deterministic only.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import AgentSnapshot, SurvivalMode

log = logging.getLogger("agent.researcher")


# ---------------------------------------------------------------------------
# Bull Researcher
# ---------------------------------------------------------------------------

class BullResearcher:
    """
    Looks for evidence the agent is healthy and can continue operating.

    Bullish signals:
    - Treasury >= initial capital (capital preservation)
    - Runway > 14 days (long survival horizon)
    - Positive 7d PnL (recent profitability)
    - Win rate > 50% (edge exists)
    - Drawdown < 3% (low stress)
    - Exposure < 3x (safe positioning)
    - No high-risk positions (leverage < 5x)
    - Low LLM costs (cost efficiency)
    - Conservative or NORMAL survival mode (calm state)
    """

    def __init__(self) -> None:
        self.name = "BullResearcher"

    def analyze(self, snapshot: AgentSnapshot) -> Dict[str, Any]:
        """Build bullish case for agent survival."""
        acct = snapshot.account
        reasons: List[str] = []
        signals_found = 0
        total_signals = 9  # total checks below
        confidence = 0.5  # base

        # 1. Treasury health
        if snapshot.treasury_usdt >= 10:
            reasons.append(f"Treasury healthy: ${snapshot.treasury_usdt:.2f}")
            signals_found += 1
            confidence += 0.05

        # 2. Runway
        runway = snapshot.treasury_usdt / 0.63 if snapshot.treasury_usdt > 0 else 0
        if runway > 14:
            reasons.append(f"Runway sufficient: {runway:.0f} days")
            signals_found += 1
            confidence += 0.05
        elif runway > 7:
            reasons.append(f"Runway adequate: {runway:.0f} days")
            signals_found += 1

        # 3. Recent PnL
        if snapshot.realized_pnl_7d > 0:
            reasons.append(f"Positive 7d PnL: ${snapshot.realized_pnl_7d:.2f}")
            signals_found += 1
            confidence += 0.08
        elif snapshot.realized_pnl_7d > -10:
            reasons.append(f"7d PnL neutral: ${snapshot.realized_pnl_7d:.2f}")
            signals_found += 1

        # 4. Win rate
        wr = snapshot.win_rate_30d
        if wr > 0.55:
            reasons.append(f"Strong win rate: {wr:.0%}")
            signals_found += 1
            confidence += 0.08
        elif wr >= 0.45:
            reasons.append(f"Win rate near breakeven: {wr:.0%}")
            signals_found += 1

        # 5. Drawdown
        dd = abs(acct.drawdown_pct)
        if dd < 3:
            reasons.append(f"Low drawdown: {acct.drawdown_pct:.1f}%")
            signals_found += 1
            confidence += 0.05
        elif dd < 8:
            reasons.append(f"Manageable drawdown: {acct.drawdown_pct:.1f}%")
            signals_found += 1

        # 6. Exposure
        if acct.exposure_x < 3:
            reasons.append(f"Safe exposure: {acct.exposure_x:.1f}x")
            signals_found += 1
            confidence += 0.05
        elif acct.exposure_x < 5:
            reasons.append(f"Moderate exposure: {acct.exposure_x:.1f}x")
            signals_found += 1

        # 7. Leverage (check positions)
        high_lev = sum(1 for p in snapshot.positions if p.leverage > 5)
        if high_lev == 0:
            reasons.append("No high-leverage positions")
            signals_found += 1
            confidence += 0.04

        # 8. LLM cost
        if snapshot.llm_cost_today_usd < 0.05:
            reasons.append(f"Low LLM cost today: ${snapshot.llm_cost_today_usd:.4f}")
            signals_found += 1
            confidence += 0.03

        # 9. Survival mode
        mode_str = snapshot.survival_mode.value if hasattr(snapshot.survival_mode, 'value') else str(snapshot.survival_mode)
        if mode_str in ("NORMAL", "CONSERVATIVE"):
            reasons.append(f"Survival mode: {mode_str}")
            signals_found += 1
            confidence += 0.05

        # Calculate verdict
        health_ratio = signals_found / max(total_signals, 1)
        confidence = min(confidence, 0.95)

        if health_ratio >= 0.6:
            verdict = "bullish"
        elif health_ratio >= 0.3:
            verdict = "neutral"
        else:
            verdict = "bearish"

        if not reasons:
            reasons.append("No bullish signals detected")
            verdict = "bearish"
            confidence = 0.3

        return {
            "researcher": self.name,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "overall_verdict": verdict,
            "overall_confidence": round(confidence, 2),
            "signals_found": signals_found,
            "total_signals": total_signals,
            "health_ratio": round(health_ratio, 2),
            "reasons": reasons,
            "summary": self._summarize(verdict, reasons[:3]),
        }

    def _summarize(self, verdict: str, top_reasons: List[str]) -> str:
        if verdict == "bullish":
            base = "Agent appears healthy"
        elif verdict == "neutral":
            base = "Agent condition is mixed"
        else:
            base = "Agent shows signs of stress"
        if top_reasons:
            base += ": " + "; ".join(top_reasons)
        return base


# ---------------------------------------------------------------------------
# Bear Researcher
# ---------------------------------------------------------------------------

class BearResearcher:
    """
    Looks for evidence the agent is at risk of decline or failure.

    Bearish signals:
    - Treasury low or declining
    - Runway < 7 days (critical)
    - Negative 7d PnL (recent losses)
    - Win rate < 40% (no edge)
    - Drawdown > 8% (high stress)
    - Exposure > 5x (overextended)
    - High-leverage positions (> 5x)
    - Runner errors
    - HIBERNATE or DEFENSIVE mode
    - High LLM costs eating treasury
    """

    def __init__(self) -> None:
        self.name = "BearResearcher"

    def analyze(self, snapshot: AgentSnapshot) -> Dict[str, Any]:
        """Build bearish case for agent survival risk."""
        acct = snapshot.account
        reasons: List[str] = []
        risks_found = 0
        total_checks = 10
        confidence = 0.5

        # 1. Treasury critical
        if snapshot.treasury_usdt <= 0:
            reasons.append("Treasury DEPLETED: $0.00")
            risks_found += 2  # double weight
            confidence += 0.2
        elif snapshot.treasury_usdt < 5:
            reasons.append(f"Treasury critically low: ${snapshot.treasury_usdt:.2f}")
            risks_found += 1
            confidence += 0.15
        elif snapshot.treasury_usdt < 10:
            reasons.append(f"Treasury low: ${snapshot.treasury_usdt:.2f}")
            risks_found += 1
            confidence += 0.08

        # 2. Runway critical
        runway = snapshot.treasury_usdt / 0.63 if snapshot.treasury_usdt > 0 else 0
        if runway <= 3:
            reasons.append(f"Runway CRITICAL: {runway:.0f} days")
            risks_found += 2
            confidence += 0.2
        elif runway <= 7:
            reasons.append(f"Runway short: {runway:.0f} days")
            risks_found += 1
            confidence += 0.1
        elif runway <= 14:
            reasons.append(f"Runway limited: {runway:.0f} days")
            risks_found += 1

        # 3. Negative PnL
        if snapshot.realized_pnl_7d < -20:
            reasons.append(f"Large negative 7d PnL: ${snapshot.realized_pnl_7d:.2f}")
            risks_found += 1
            confidence += 0.1
        elif snapshot.realized_pnl_7d < 0:
            reasons.append(f"Negative 7d PnL: ${snapshot.realized_pnl_7d:.2f}")
            risks_found += 1
            confidence += 0.05

        # 4. Low win rate
        wr = snapshot.win_rate_30d
        if wr > 0 and wr < 0.4:
            reasons.append(f"Low win rate: {wr:.0%}")
            risks_found += 1
            confidence += 0.08

        # 5. High drawdown
        dd = abs(acct.drawdown_pct)
        if dd > 12:
            reasons.append(f"Severe drawdown: {acct.drawdown_pct:.1f}%")
            risks_found += 2
            confidence += 0.15
        elif dd > 8:
            reasons.append(f"High drawdown: {acct.drawdown_pct:.1f}%")
            risks_found += 1
            confidence += 0.08
        elif dd > 5:
            reasons.append(f"Elevated drawdown: {acct.drawdown_pct:.1f}%")
            risks_found += 1

        # 6. High exposure
        if acct.exposure_x > 8:
            reasons.append(f"Extreme exposure: {acct.exposure_x:.1f}x")
            risks_found += 2
            confidence += 0.15
        elif acct.exposure_x > 5:
            reasons.append(f"High exposure: {acct.exposure_x:.1f}x")
            risks_found += 1
            confidence += 0.08

        # 7. High leverage positions
        high_lev = sum(1 for p in snapshot.positions if p.leverage > 5)
        if high_lev > 0:
            reasons.append(f"{high_lev} position(s) with leverage > 5x")
            risks_found += 1
            confidence += 0.05

        # 8. Runner errors
        if snapshot.runner_error_count > 10:
            reasons.append(f"Runner errors: {snapshot.runner_error_count}")
            risks_found += 1
            confidence += 0.08

        # 9. Survival mode
        mode_str = snapshot.survival_mode.value if hasattr(snapshot.survival_mode, 'value') else str(snapshot.survival_mode)
        if mode_str == "HIBERNATE":
            reasons.append("System in HIBERNATE mode")
            risks_found += 2
            confidence += 0.15
        elif mode_str == "DEFENSIVE":
            reasons.append("System in DEFENSIVE mode")
            risks_found += 1
            confidence += 0.08

        # 10. LLM costs
        if snapshot.llm_cost_today_usd > 0.1:
            reasons.append(f"LLM cost high today: ${snapshot.llm_cost_today_usd:.4f}")
            risks_found += 1
            confidence += 0.05

        # Calculate verdict
        risk_ratio = risks_found / max(total_checks, 1)
        confidence = min(confidence, 0.95)

        if risk_ratio >= 0.6:
            verdict = "bearish"
        elif risk_ratio >= 0.3:
            verdict = "neutral"
        else:
            verdict = "bullish"

        if not reasons:
            reasons.append("No bearish signals detected")
            verdict = "bullish"
            confidence = 0.3

        return {
            "researcher": self.name,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "overall_verdict": verdict,
            "overall_confidence": round(confidence, 2),
            "risks_found": risks_found,
            "total_checks": total_checks,
            "risk_ratio": round(risk_ratio, 2),
            "reasons": reasons,
            "summary": self._summarize(verdict, reasons[:3]),
        }

    def _summarize(self, verdict: str, top_reasons: List[str]) -> str:
        if verdict == "bearish":
            base = "Agent is at risk"
        elif verdict == "neutral":
            base = "Agent has some risk factors"
        else:
            base = "Agent risks are manageable"
        if top_reasons:
            base += ": " + "; ".join(top_reasons)
        return base


# ---------------------------------------------------------------------------
# Debate Engine
# ---------------------------------------------------------------------------

class DebateEngine:
    """
    Determines whether current operating mode should remain or become more defensive.

    Input: BullCase + BearCase + current survival mode + analyst consensus
    Output: Action recommendation + reasoning

    Logic:
    - If bear confidence > bull confidence by 0.15+ → recommend DEFENSIVE escalation
    - If runway < 7 days → recommend HIBERNATE escalation
    - If analyst consensus is bearish AND bear agrees → escalate
    - If bull and bear agree (same verdict) → strong signal
    - Otherwise → no change needed
    """

    def __init__(self) -> None:
        self.name = "DebateEngine"

    def debate(
        self,
        bull_result: Dict[str, Any],
        bear_result: Dict[str, Any],
        snapshot: AgentSnapshot,
        analyst_consensus: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run debate and produce final verdict."""
        bull_verdict = bull_result.get("overall_verdict", "neutral")
        bull_conf = bull_result.get("overall_confidence", 0.5)
        bear_verdict = bear_result.get("overall_verdict", "neutral")
        bear_conf = bear_result.get("overall_confidence", 0.5)

        reasons: List[str] = []
        override = False
        final_verdict = "neutral"
        final_conviction = 0.5

        # Net confidence calculation
        net_bias_confidence = bull_conf - bear_conf

        # Determine net bias
        if net_bias_confidence > 0.1:
            net_bias = "bullish"
        elif net_bias_confidence < -0.1:
            net_bias = "bearish"
        else:
            net_bias = "neutral"

        # Agreement check
        agreement = (bull_verdict == bear_verdict)
        if agreement:
            reasons.append(f"Bull and Bear agree: {bull_verdict}")
            final_conviction = max(bull_conf, bear_conf) + 0.1
        else:
            reasons.append(f"Bull says {bull_verdict} ({bull_conf:.2f}), Bear says {bear_verdict} ({bear_conf:.2f})")

        # Survival mode escalation check
        mode_str = snapshot.survival_mode.value if hasattr(snapshot.survival_mode, 'value') else str(snapshot.survival_mode)

        # If runway < 7 days → recommend more defensive
        runway = snapshot.treasury_usdt / 0.63 if snapshot.treasury_usdt > 0 else 0
        if runway < 7 and snapshot.treasury_usdt > 0:
            reasons.append(f"Runway critical ({runway:.0f}d) → defensive stance required")
            if final_verdict == "neutral":
                final_verdict = "conservative"
            override = True

        # If bear wins by a lot → escalate
        if net_bias_confidence < -0.15:
            reasons.append("Bear case significantly stronger than bull case")
            final_verdict = "conservative"

        # Analyst override: if analysts say bearish AND bear agrees
        if analyst_consensus == "bearish" and bear_verdict == "bearish":
            reasons.append("Analyst consensus aligns with bear case — DEFENSIVE mode warranted")
            final_verdict = "conservative"
            override = True

        # If bull wins clearly → no change needed
        if net_bias_confidence > 0.2 and final_verdict == "neutral":
            reasons.append("Bull case clearly stronger — current mode acceptable")
            final_verdict = "maintain"
            final_conviction = min(bull_conf + 0.05, 0.95)

        # Default to maintain if nothing triggered
        if final_verdict == "neutral":
            if net_bias_confidence > 0:
                reasons.append("Slight bull edge — maintaining current stance")
                final_verdict = "maintain"
            else:
                reasons.append("Slight bear edge — maintaining vigilance")
                final_verdict = "maintain"
            final_conviction = max(bull_conf, bear_conf)

        final_conviction = min(final_conviction, 0.95)

        return {
            "debate_ts": datetime.now(tz=timezone.utc).isoformat(),
            "bull_verdict": bull_verdict,
            "bull_confidence": round(bull_conf, 2),
            "bear_verdict": bear_verdict,
            "bear_confidence": round(bear_conf, 2),
            "net_bias": net_bias,
            "net_bias_confidence": round(net_bias_confidence, 2),
            "final_verdict": final_verdict,
            "final_conviction": round(final_conviction, 2),
            "override_by_analysts": override,
            "reasons": reasons,
            "summary": self._build_summary(final_verdict, reasons[:2]),
        }

    def _build_summary(self, verdict: str, top_reasons: List[str]) -> str:
        labels = {
            "maintain": "Maintain current operating mode",
            "conservative": "Consider more defensive operating mode",
            "bearish": "Agent survival risk detected",
            "bullish": "Agent operating conditions favorable",
        }
        base = labels.get(verdict, f"Verdict: {verdict}")
        if top_reasons:
            base += " | " + " | ".join(top_reasons)
        return base


# ---------------------------------------------------------------------------
# Research Team — combined runner
# ---------------------------------------------------------------------------

class ResearchTeam:
    """Runs Bull + Bear researchers + Debate Engine."""

    def __init__(self) -> None:
        self.bull = BullResearcher()
        self.bear = BearResearcher()
        self.debate = DebateEngine()

    def run(
        self,
        snapshot: AgentSnapshot,
        analyst_consensus: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """
        Run full research pipeline.
        Returns (bull_result, bear_result, debate_verdict).
        """
        bull_result = self.bull.analyze(snapshot)
        bear_result = self.bear.analyze(snapshot)
        debate_verdict = self.debate.debate(bull_result, bear_result, snapshot, analyst_consensus)

        log.info(
            "Bull=%s(%.2f) Bear=%s(%.2f) Debate=%s(%.2f)",
            bull_result["overall_verdict"], bull_result["overall_confidence"],
            bear_result["overall_verdict"], bear_result["overall_confidence"],
            debate_verdict["final_verdict"], debate_verdict["final_conviction"],
        )

        return bull_result, bear_result, debate_verdict