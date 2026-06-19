"""
agent/analysts.py — Independent analyst modules that generate reports before plan generation.

Each analyst:
  - Receives the current AgentSnapshot
  - Returns an AnalystReport with verdict, confidence, and reasons
  - Operates independently (no cross-analyst dependencies)

Analysts:
  1. TechnicalAnalyst   — Evaluates position PnL, leverage, TP/SL distances
  2. MarketAnalyst      — Evaluates drawdown, exposure, order rate, win rate
  3. SurvivalAnalyst    — Evaluates treasury, runway, survival mode, error rate

All reports are stored in analyst_reports table and consumed by plan generation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import AgentSnapshot

log = logging.getLogger("agent.analysts")

# ---------------------------------------------------------------------------
# Report model
# ---------------------------------------------------------------------------

class AnalystReport:
    """Output of a single analyst module."""

    def __init__(
        self,
        agent: str,
        verdict: str,
        confidence: float,
        reasons: List[str],
        ts: Optional[datetime] = None,
    ) -> None:
        self.agent = agent
        self.verdict = verdict      # "bullish" | "bearish" | "neutral" | "conservative"
        self.confidence = confidence  # 0.0 to 1.0
        self.reasons = reasons
        self.ts = ts or datetime.now(tz=timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "ts": self.ts.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnalystReport":
        return cls(
            agent=str(d.get("agent", "")),
            verdict=str(d.get("verdict", "neutral")),
            confidence=float(d.get("confidence", 0.5)),
            reasons=list(d.get("reasons", [])),
            ts=datetime.fromisoformat(str(d.get("ts", datetime.now(tz=timezone.utc).isoformat()))),
        )


# ---------------------------------------------------------------------------
# Base analyst
# ---------------------------------------------------------------------------

class BaseAnalyst:
    """Base class for all analysts."""

    def __init__(self, name: str) -> None:
        self.name = name

    def analyze(self, snapshot: AgentSnapshot) -> AnalystReport:
        """Override in subclass. Returns AnalystReport."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Technical Analyst — position-level analysis
# ---------------------------------------------------------------------------

class TechnicalAnalyst(BaseAnalyst):
    """
    Evaluates each open position for:
    - Unrealized PnL (large negative = bearish)
    - Leverage (high = risky)
    - TP/SL distance (tight = expected move)
    
    Verdict:
      - "bearish" if any position has large negative uPnL or high leverage
      - "bullish" if positions are profitable and within safe leverage
      - "neutral" otherwise
    """

    def __init__(self) -> None:
        super().__init__("TechnicalAnalyst")

    def analyze(self, snapshot: AgentSnapshot) -> AnalystReport:
        reasons: List[str] = []
        total_upnl = 0.0
        high_risk_positions = 0
        total_exposure_lev = 0.0

        for pos in snapshot.positions:
            total_upnl += pos.unrealized_pnl
            total_exposure_lev += abs(pos.size * pos.entry_price * pos.leverage)

            if pos.unrealized_pnl < -50:
                high_risk_positions += 1
                reasons.append(f"{pos.contract}: large negative uPnL=${pos.unrealized_pnl:.2f}")

            if pos.leverage > 10:
                high_risk_positions += 1
                reasons.append(f"{pos.contract}: high leverage={pos.leverage}x")

        if not snapshot.positions:
            return AnalystReport(
                agent=self.name,
                verdict="neutral",
                confidence=0.9,
                reasons=["No open positions to analyze"],
            )

        if high_risk_positions > 0:
            return AnalystReport(
                agent=self.name,
                verdict="bearish",
                confidence=min(0.5 + 0.1 * high_risk_positions, 0.95),
                reasons=reasons or ["High-risk positions detected"],
            )

        if total_upnl > 0:
            return AnalystReport(
                agent=self.name,
                verdict="bullish",
                confidence=min(0.5 + (total_upnl / 500.0), 0.9),
                reasons=[f"Total unrealized PnL positive: ${total_upnl:.2f}"],
            )

        return AnalystReport(
            agent=self.name,
            verdict="neutral",
            confidence=0.6,
            reasons=[f"Total unrealized PnL: ${total_upnl:.1f}, {len(snapshot.positions)} positions"],
        )


# ---------------------------------------------------------------------------
# Market Analyst — aggregate market conditions
# ---------------------------------------------------------------------------

class MarketAnalyst(BaseAnalyst):
    """
    Evaluates market conditions from the account snapshot:
    - Drawdown severity
    - Exposure ratio
    - Order rate (high = panicking)
    - Recent performance (win rate, PnL)
    
    Verdict:
      - "bearish" if drawdown > 5%, exposure high, or PnL negative
      - "conservative" if drawdown > 2% or win rate low
      - "bullish" if all metrics positive
      - "neutral" otherwise
    """

    def __init__(self) -> None:
        super().__init__("MarketAnalyst")

    def analyze(self, snapshot: AgentSnapshot) -> AnalystReport:
        reasons: List[str] = []
        acct = snapshot.account
        verdict = "neutral"
        confidence = 0.6

        # Drawdown check
        dd = abs(acct.drawdown_pct)
        if dd > 10:
            reasons.append(f"Severe drawdown: {acct.drawdown_pct:.1f}%")
            verdict = "bearish"
            confidence = 0.85
        elif dd > 5:
            reasons.append(f"Significant drawdown: {acct.drawdown_pct:.1f}%")
            verdict = "conservative"
            confidence = 0.7
        elif dd > 2:
            reasons.append(f"Mild drawdown: {acct.drawdown_pct:.1f}%")
            verdict = "conservative"
            confidence = 0.55

        # Exposure check
        if acct.exposure_x > 6:
            reasons.append(f"High exposure: {acct.exposure_x:.1f}x")
            if verdict == "neutral":
                verdict = "conservative"
            confidence = min(confidence + 0.1, 0.95)
        elif acct.exposure_x < 1 and acct.open_positions > 0:
            reasons.append(f"Low exposure: {acct.exposure_x:.1f}x with {acct.open_positions} positions")

        # Order rate
        if acct.order_rate_4h > 10:
            reasons.append(f"High order rate: {acct.order_rate_4h}/4h")
            if verdict == "neutral":
                verdict = "conservative"

        # Recent performance
        wr = snapshot.win_rate_30d
        if wr > 0.6:
            reasons.append(f"Strong win rate: {wr:.0%}")
            if verdict == "neutral":
                verdict = "bullish"
                confidence = 0.65
        elif 0 < wr < 0.4:
            reasons.append(f"Low win rate: {wr:.0%}")

        pnl_7d = snapshot.realized_pnl_7d
        if pnl_7d < 0:
            reasons.append(f"Negative 7d PnL: ${pnl_7d:.2f}")
            if verdict == "neutral":
                verdict = "conservative"
        elif pnl_7d > 0:
            reasons.append(f"Positive 7d PnL: ${pnl_7d:.2f}")
            if verdict == "neutral":
                verdict = "bullish"
                confidence = 0.55

        if not reasons:
            reasons.append("All market metrics within normal range")

        return AnalystReport(
            agent=self.name,
            verdict=verdict,
            confidence=round(confidence, 2),
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Survival Analyst — treasury & system health
# ---------------------------------------------------------------------------

class SurvivalAnalyst(BaseAnalyst):
    """
    Evaluates the agent's own survival capacity:
    - Treasury balance
    - Runway (days until treasury exhausted)
    - Survival mode escalation
    - LLM cost tracking
    - Runner error count
    
    Verdict:
      - "bearish" if treasury low, runway short, or in HIBERNATE
      - "conservative" if runway < 7 days or in DEFENSIVE/CONSERVATIVE mode
      - "neutral" if all survival metrics healthy
      - Never returns "bullish" (survival is defensive by nature)
    """

    def __init__(self) -> None:
        super().__init__("SurvivalAnalyst")

    def analyze(self, snapshot: AgentSnapshot) -> AnalystReport:
        reasons: List[str] = []
        verdict = "neutral"
        confidence = 0.7

        # Treasury check
        treasury = snapshot.treasury_usdt
        if treasury <= 0:
            reasons.append("Treasury depleted: $0.00")
            verdict = "bearish"
            confidence = 0.95
        elif treasury < 5:
            reasons.append(f"Treasury critically low: ${treasury:.2f}")
            verdict = "bearish"
            confidence = 0.9
        elif treasury < 10:
            reasons.append(f"Treasury low: ${treasury:.2f}")
            verdict = "conservative"
            confidence = 0.75

        # Survival mode
        mode = snapshot.survival_mode.value if hasattr(snapshot.survival_mode, 'value') else str(snapshot.survival_mode)
        if mode == "HIBERNATE":
            reasons.append("System in HIBERNATE mode")
            verdict = "bearish"
            confidence = 0.95
        elif mode == "DEFENSIVE":
            reasons.append("System in DEFENSIVE mode")
            if verdict != "bearish":
                verdict = "conservative"
            confidence = max(confidence, 0.85)
        elif mode == "CONSERVATIVE":
            reasons.append("System in CONSERVATIVE mode")
            if verdict == "neutral":
                verdict = "conservative"
            confidence = max(confidence, 0.7)

        # LLM cost
        llm_cost = snapshot.llm_cost_today_usd
        if llm_cost > 0.1:
            reasons.append(f"LLM cost today: ${llm_cost:.4f}")
            confidence = min(confidence + 0.05, 0.95)

        # Runner errors
        if snapshot.runner_error_count > 10:
            reasons.append(f"Runner errors: {snapshot.runner_error_count}")
            if verdict == "neutral":
                verdict = "conservative"
            confidence = min(confidence + 0.1, 0.95)

        # Treasury (if not already added)
        if treasury >= 10:
            try:
                runway = treasury / 0.63  # approximate daily cost
                reasons.append(f"Treasury healthy: ${treasury:.2f} (~{runway:.0f}d runway)")
            except Exception:
                pass

        if not reasons:
            reasons.append("Survival metrics nominal")

        return AnalystReport(
            agent=self.name,
            verdict=verdict,
            confidence=round(confidence, 2),
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Analyst team — runs all analysts and aggregates reports
# ---------------------------------------------------------------------------

class AnalystTeam:
    """Runs all analysts and produces a consolidated report summary."""

    def __init__(self) -> None:
        self._analysts: List[BaseAnalyst] = [
            TechnicalAnalyst(),
            MarketAnalyst(),
            SurvivalAnalyst(),
        ]

    @property
    def analyst_names(self) -> List[str]:
        return [a.name for a in self._analysts]

    def analyze(self, snapshot: AgentSnapshot) -> List[AnalystReport]:
        """Run all analysts and return their reports."""
        reports: List[AnalystReport] = []
        for analyst in self._analysts:
            try:
                report = analyst.analyze(snapshot)
                reports.append(report)
                log.info(
                    "Analyst %s: verdict=%s confidence=%.2f reasons=%d",
                    report.agent, report.verdict, report.confidence, len(report.reasons),
                )
            except Exception as e:
                log.exception("Analyst %s failed: %s", analyst.name, e)
                reports.append(AnalystReport(
                    agent=analyst.name,
                    verdict="neutral",
                    confidence=0.0,
                    reasons=[f"Analysis error: {e}"],
                ))

        return reports

    def summarize(self, reports: List[AnalystReport]) -> Dict[str, Any]:
        """Produce a consensus summary from all reports."""
        verdicts = [r.verdict for r in reports]
        avg_confidence = sum(r.confidence for r in reports) / max(len(reports), 1)

        # Count verdicts
        bullish = verdicts.count("bullish")
        bearish = verdicts.count("bearish")
        conservative = verdicts.count("conservative")
        neutral = verdicts.count("neutral")

        # Consensus: most conservative wins (safety first)
        if bearish > 0:
            consensus = "bearish"
        elif conservative > 0:
            consensus = "conservative"
        elif bullish > neutral:
            consensus = "bullish"
        else:
            consensus = "neutral"

        return {
            "consensus": consensus,
            "confidence": round(avg_confidence, 2),
            "breakdown": {
                "bullish": bullish,
                "bearish": bearish,
                "conservative": conservative,
                "neutral": neutral,
            },
            "analyst_count": len(reports),
        }