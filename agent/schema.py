"""
agent/schema.py — Pydantic models untuk Plan JSON agent.

Schema ini dipakai oleh:
- llm_client.py  → parse & validate output LLM
- agent.py       → type-safe plan handling
- storage        → serialisasi ke DB
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SurvivalMode(str, Enum):
    NORMAL       = "NORMAL"
    CONSERVATIVE = "CONSERVATIVE"
    DEFENSIVE    = "DEFENSIVE"
    HIBERNATE    = "HIBERNATE"


class AgentMode(str, Enum):
    OFF     = "off"
    OBSERVE = "observe"
    EXECUTE = "execute"


class ActionType(str, Enum):
    # Low-risk
    PAUSE_ENTRIES       = "PAUSE_ENTRIES"
    RESUME_ENTRIES      = "RESUME_ENTRIES"
    TIGHTEN_RISK        = "TIGHTEN_RISK"
    ROTATE_LOGS         = "ROTATE_LOGS"
    EXPORT_REPORT       = "EXPORT_REPORT"
    NOTIFY              = "NOTIFY"
    # Medium-risk
    CANCEL_STALE_TPSL   = "CANCEL_STALE_TPSL"
    REPLACE_TPSL        = "REPLACE_TPSL"
    REDUCE_POSITION     = "REDUCE_POSITION"
    # High-risk (emergency only)
    CLOSE_POSITION      = "CLOSE_POSITION"
    REVERSE_POSITION    = "REVERSE_POSITION"
    # Agent self-management
    SET_SURVIVAL_MODE   = "SET_SURVIVAL_MODE"
    UPDATE_CONFIG       = "UPDATE_CONFIG"


HIGH_RISK_ACTIONS = {ActionType.CLOSE_POSITION, ActionType.REVERSE_POSITION}
MEDIUM_RISK_ACTIONS = {ActionType.CANCEL_STALE_TPSL, ActionType.REPLACE_TPSL, ActionType.REDUCE_POSITION}
LOW_RISK_ACTIONS = {
    ActionType.PAUSE_ENTRIES, ActionType.RESUME_ENTRIES, ActionType.TIGHTEN_RISK,
    ActionType.ROTATE_LOGS, ActionType.EXPORT_REPORT, ActionType.NOTIFY,
    ActionType.SET_SURVIVAL_MODE, ActionType.UPDATE_CONFIG,
}


# ---------------------------------------------------------------------------
# Action model
# ---------------------------------------------------------------------------

class ProposedAction(BaseModel):
    type: ActionType
    params: Dict[str, Any] = Field(default_factory=dict)
    why: str = ""
    guardrails: List[str] = Field(default_factory=list)

    @field_validator("type", mode="before")
    @classmethod
    def coerce_type(cls, v: Any) -> ActionType:
        # Already an ActionType → return directly (avoids str() mangling to "ActionType.FOO")
        if isinstance(v, ActionType):
            return v
        # Str → strip "ActionType." prefix if present, then convert
        raw = str(v).upper().removeprefix("ACTIONTYPE.")
        return ActionType(raw)


# ---------------------------------------------------------------------------
# Plan model — output LLM / rule engine
# ---------------------------------------------------------------------------

class AgentPlan(BaseModel):
    ts: datetime
    summary: str
    observations: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    proposed_actions: List[ProposedAction] = Field(default_factory=list)
    needs_human_approval: bool = False

    # Mode C tambahan — wajib ada
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    emergency: bool = False

    @model_validator(mode="after")
    def check_high_risk_needs_emergency(self) -> "AgentPlan":
        for act in self.proposed_actions:
            if act.type in HIGH_RISK_ACTIONS and not self.emergency:
                raise ValueError(
                    f"Action {act.type} is high-risk and requires emergency=True in plan"
                )
        return self

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "AgentPlan":
        return cls.model_validate(json.loads(raw))


# ---------------------------------------------------------------------------
# Snapshot model — input ke LLM
# ---------------------------------------------------------------------------

class MarketEvidence(BaseModel):
    source: str             # "order_book" | "large_flow" | "open_interest" | "funding" | "positioning" | "btc_regime" | "news" | "technical" | "ml"
    signal: str             # "BULLISH" | "BEARISH" | "NEUTRAL" | "UNAVAILABLE" | "STALE" | "ERROR"
    score: float = 0.0      # normalized signal score [-1.0, 1.0]
    confidence: float = 0.0 # confidence [0.0, 1.0]
    timestamp: str = ""
    freshness_seconds: float = 0.0
    status: str = "VALID"   # "VALID" | "STALE" | "UNAVAILABLE" | "ERROR"
    reason: str = ""
    raw_metrics: Dict[str, Any] = Field(default_factory=dict)


class EvidenceSummary(BaseModel):
    agreement: float = 0.0
    contradiction_level: str = "INSUFFICIENT_DATA"  # "STRONG_AGREEMENT" | "MODERATE_AGREEMENT" | "MIXED" | "STRONG_CONTRADICTION" | "INSUFFICIENT_DATA"
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    unavailable_count: int = 0
    evidence_quality: float = 0.0
    weighted_score: float = 0.0
    composite_signal: str = "NEUTRAL"


class AssetAnalysis(BaseModel):
    asset: str
    direction: str             # "LONG" | "SHORT" | "NEUTRAL"
    probability: float
    confidence: float
    prediction: float
    threshold: float
    market_regime: str
    top_features: Dict[str, float] = Field(default_factory=dict)
    volatility: float
    momentum: float
    atr: float
    rsi: float
    ema_trend: str
    rank: int = 0
    close_price: float = 0.0

    # Phase 12.1 — Market Intelligence extension
    market_evidence: List[MarketEvidence] = Field(default_factory=list)
    evidence_summary: Optional[EvidenceSummary] = None
    agreement_score: float = 0.0
    contradiction_level: str = "INSUFFICIENT_DATA"
    evidence_quality: float = 0.0
    data_freshness_sec: float = 0.0


class PositionSnapshot(BaseModel):
    contract: str
    side: str          # LONG | SHORT
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None


class AccountSnapshot(BaseModel):
    equity: float
    available: float
    unrealized_pnl: float
    drawdown_pct: float          # current DD dari peak, sebagai persen (mis. -5.2)
    exposure_x: float            # total notional / equity
    open_positions: int
    order_rate_4h: int           # berapa order dikirim dalam 4H terakhir


class AgentSnapshot(BaseModel):
    ts: datetime
    account: AccountSnapshot
    positions: List[PositionSnapshot] = Field(default_factory=list)
    # market scanner
    market_analysis: List[AssetAnalysis] = Field(default_factory=list)
    # runner health
    last_candle_ts: Dict[str, str] = Field(default_factory=dict)   # asset → ISO ts
    runner_error_count: int = 0
    # survival
    treasury_usdt: float = 0.0
    survival_mode: SurvivalMode = SurvivalMode.NORMAL
    agent_mode: AgentMode = AgentMode.OBSERVE
    # cost
    llm_cost_today_usd: float = 0.0
    # recent perf (simple)
    realized_pnl_7d: float = 0.0
    realized_pnl_30d: float = 0.0
    win_rate_30d: float = 0.0
    # Phase 12.2 decision & risk supervisor outputs
    decision_proposals: List[DecisionProposal] = Field(default_factory=list)
    risk_reviews: List[RiskSupervisorReview] = Field(default_factory=list)

    def to_prompt_text(self) -> str:
        """Format ringkas untuk disisipkan ke prompt LLM — tanpa secret."""
        lines = [
            f"[Snapshot {self.ts.isoformat()}]",
            f"Equity: ${self.account.equity:.2f}  Available: ${self.account.available:.2f}",
            f"Drawdown: {self.account.drawdown_pct:.1f}%  Exposure: {self.account.exposure_x:.2f}x",
            f"Open positions: {self.account.open_positions}  Order rate (4H): {self.account.order_rate_4h}",
            f"Treasury: ${self.treasury_usdt:.2f}  LLM cost today: ${self.llm_cost_today_usd:.4f}",
            f"Survival mode: {self.survival_mode}  Agent mode: {self.agent_mode}",
            f"PnL 7d: ${self.realized_pnl_7d:.2f}  PnL 30d: ${self.realized_pnl_30d:.2f}  WinRate 30d: {self.win_rate_30d:.1%}",
            "",
        ]
        if self.market_analysis:
            lines.append("Market Scanner Summary (Top Assets):")
            for item in self.market_analysis[:5]:
                lines.append(
                    f"  #{item.rank} {item.asset}: {item.direction} | Prob: {item.probability:.0%} | "
                    f"Conf: {item.confidence:.0%} | Trend: {item.ema_trend} | Vol: {item.volatility:.4f} | RSI: {item.rsi:.1f}"
                )
            lines.append("")
        if self.positions:
            lines.append("Positions:")
            for p in self.positions:
                tp_str = f" TP={p.tp_price}" if p.tp_price else ""
                sl_str = f" SL={p.sl_price}" if p.sl_price else ""
                lines.append(
                    f"  {p.contract} {p.side} size={p.size} entry={p.entry_price:.4f}"
                    f" uPnL={p.unrealized_pnl:.2f}{tp_str}{sl_str}"
                )
        if self.runner_error_count > 0:
            lines.append(f"Runner errors (recent): {self.runner_error_count}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Token usage / cost tracking
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    provider: str                       # "ollama" | "deepseek" | "grok"
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_input_tokens: int = 0
    cache_miss_input_tokens: int = 0
    cost_usd: float = 0.0

    @classmethod
    def deepseek_cost(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit_input: int = 0,
    ) -> "TokenUsage":
        cache_miss = max(0, input_tokens - cache_hit_input)
        cost = (cache_hit_input / 1e6) * 0.028 + (cache_miss / 1e6) * 0.28 + (output_tokens / 1e6) * 0.42
        return cls(
            provider="deepseek",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_input_tokens=cache_hit_input,
            cache_miss_input_tokens=cache_miss,
            cost_usd=cost,
        )


# ---------------------------------------------------------------------------
# Phase 12.2 — Multi-Agent Market Decision & Evidence Fusion Schemas
# ---------------------------------------------------------------------------

class SpecialistOutput(BaseModel):
    specialist_name: str       # "technical_ml" | "order_flow" | "derivatives" | "macro_regime" | "news_sentiment"
    direction: str             # "LONG" | "SHORT" | "NEUTRAL" | "UNAVAILABLE"
    confidence: float = 0.0    # [0.0, 1.0]
    evidence: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    status: str = "VALID"      # "VALID" | "UNAVAILABLE" | "STALE" | "ERROR"
    metrics: Dict[str, Any] = Field(default_factory=dict)


class FusionResult(BaseModel):
    directional_score: float = 0.0     # [-1.0, 1.0]
    confidence: float = 0.0            # [0.0, 1.0]
    agreement_score: float = 0.0       # [0.0, 1.0]
    contradiction_level: str = "INSUFFICIENT_DATA" # "STRONG_AGREEMENT" | "MODERATE_AGREEMENT" | "MIXED" | "STRONG_CONTRADICTION" | "INSUFFICIENT_DATA"
    evidence_quality: float = 0.0      # [0.0, 1.0]
    data_quality: float = 0.0          # [0.0, 1.0]
    freshness_score: float = 0.0       # [0.0, 1.0]
    confidence_band: str = "NO_TRADE"  # "HIGH" | "MEDIUM" | "LOW" | "NO_TRADE"
    composite_direction: str = "NEUTRAL" # "LONG" | "SHORT" | "NEUTRAL"
    weighted_weights: Dict[str, float] = Field(default_factory=dict)


class DecisionProposal(BaseModel):
    decision_id: str
    timestamp: str
    asset: str
    direction: str                      # "LONG" | "SHORT" | "NEUTRAL"
    decision: str                       # "TRADE_CANDIDATE" | "WATCH" | "NO_TRADE"
    confidence: float = 0.0
    reasoning: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    contradicting_evidence: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    required_risk_review: bool = True
    # Provenance details
    scanner_rank: int = 0
    model_signal: str = "NEUTRAL"
    market_evidence: List[MarketEvidence] = Field(default_factory=list)
    specialist_outputs: List[SpecialistOutput] = Field(default_factory=list)
    fusion_result: Optional[FusionResult] = None
    contradictions: List[str] = Field(default_factory=list)
    data_quality: float = 0.0
    freshness: float = 0.0
    llm_model: str = "deterministic"
    llm_latency_ms: float = 0.0
    llm_failures: int = 0
    fallback_used: bool = False


class RiskSupervisorReview(BaseModel):
    proposal_id: str
    asset: str
    status: str                         # "APPROVED_FOR_RISK_REVIEW" | "REJECTED" | "WATCH"
    rejection_reasons: List[str] = Field(default_factory=list)
    risk_score: float = 0.0             # [0.0, 1.0]
    timestamp: str
    reviewed_decision: str


# ---------------------------------------------------------------------------
# Phase 12.3 — Decision Calibration, Replay & Shadow Trading Models
# ---------------------------------------------------------------------------

class DecisionOutcome(BaseModel):
    decision_id: str
    asset: str
    timestamp: str
    decision: str                      # "TRADE_CANDIDATE" | "WATCH" | "NO_TRADE"
    direction: str                     # "LONG" | "SHORT" | "NEUTRAL"
    confidence: float
    confidence_band: str               # "HIGH" | "MEDIUM" | "LOW" | "NO_TRADE"
    agreement_score: float
    contradiction_level: str
    evidence_quality: float
    data_quality: float
    data_freshness: float
    scanner_rank: int = 0
    # Forward Returns (evaluating ONLY data AFTER decision timestamp)
    forward_return_1: float = 0.0
    forward_return_3: float = 0.0
    forward_return_6: float = 0.0
    forward_return_12: float = 0.0
    forward_return_24: float = 0.0
    # Outcomes
    direction_correct: bool = False
    outcome_class: str = "NEUTRAL"     # "CORRECT" | "INCORRECT" | "NEUTRAL" | "INSUFFICIENT_DATA"
    # Metadata context
    market_regime: str = "NEUTRAL"
    btc_regime: str = "NEUTRAL"
    specialist_signals: Dict[str, str] = Field(default_factory=dict)
    fusion_score: float = 0.0


class ShadowTrade(BaseModel):
    shadow_id: str
    decision_id: str
    asset: str
    timestamp: str
    direction: str                     # "LONG" | "SHORT" | "NEUTRAL"
    entry_reference_price: float
    current_price: float = 0.0
    decision_confidence: float = 0.0
    confidence_band: str = "NO_TRADE"
    agreement_score: float = 0.0
    contradiction_level: str = "INSUFFICIENT_DATA"
    evidence_quality: float = 0.0
    risk_status: str = "WATCH"          # "APPROVED_FOR_RISK_REVIEW" | "REJECTED" | "WATCH"
    execution_mode: str = "SHADOW"      # Strict enforcement: NEVER real execution
    # Simulated Performance Tracking
    unrealized_return: float = 0.0
    max_favorable_excursion: float = 0.0 # MFE %
    max_adverse_excursion: float = 0.0   # MAE %
    closed_at: Optional[str] = None
    final_return: float = 0.0
    outcome: str = "OPEN"               # "OPEN" | "WIN" | "LOSS" | "EXPIRED" | "CLOSED"


class CalibrationBin(BaseModel):
    bin_min: float
    bin_max: float
    sample_count: int = 0
    predicted_confidence: float = 0.0
    actual_accuracy: float = 0.0
    calibration_error: float = 0.0
    avg_forward_return: float = 0.0
    median_forward_return: float = 0.0


class CalibrationReport(BaseModel):
    timestamp: str
    total_decisions: int = 0
    evaluated_decisions: int = 0
    brier_score: float = 0.0
    expected_calibration_error: float = 0.0
    overall_accuracy: float = 0.0
    positive_return_ratio: float = 0.0
    bins: List[CalibrationBin] = Field(default_factory=list)
    baseline_comparisons: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    asset_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    regime_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    agreement_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    calibration_status: str = "UNCALIBRATED" # "CALIBRATED" | "PARTIALLY_CALIBRATED" | "UNCALIBRATED" | "INSUFFICIENT_SAMPLE"
    performance_status: str = "NO_EDGE"       # "POSITIVE_EDGE" | "POSSIBLE_EDGE" | "NO_EDGE" | "INSUFFICIENT_SAMPLE"

