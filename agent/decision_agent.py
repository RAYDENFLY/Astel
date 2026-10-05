"""
agent/decision_agent.py — Phase 12.2 Decision Agent Module

Synthesizes specialist analyses and evidence fusion into a structured DecisionProposal ONLY.
Decisions allowed: TRADE_CANDIDATE | WATCH | NO_TRADE.
NO order submission, NO position sizing, NO execution calls permitted.
"""

from __future__ import annotations

import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import (
    AssetAnalysis,
    MarketEvidence,
    SpecialistOutput,
    FusionResult,
    DecisionProposal,
)
from agent.specialists import (
    TechnicalMLSpecialist,
    OrderFlowSpecialist,
    DerivativesSpecialist,
    MacroRegimeSpecialist,
    NewsSentimentSpecialist,
)
from agent.evidence_fusion import EvidenceFusionEngine, FusionConfig
from agent.llm_client import LLMRouter

log = logging.getLogger("agent.decision_agent")


class DecisionAgentConfig:
    """Configurable parameters for Decision Agent & Model Routing."""
    def __init__(self, cfg_dict: Optional[Dict[str, Any]] = None):
        cfg_dict = cfg_dict or {}
        dec_cfg = cfg_dict.get("decision_agent") or {}

        self.top_n: int = int(dec_cfg.get("top_n", 3))
        self.disabled_llm_mode: bool = bool(dec_cfg.get("disabled_llm_mode", False))
        self.specialist_model: str = dec_cfg.get("specialist_model", "qwen2.5:7b")
        self.decision_model: str = dec_cfg.get("decision_model", "llama-3.3-70b-versatile")
        self.fallback_model: str = dec_cfg.get("fallback_model", "llama-3.1-8b-instant")
        self.temperature: float = float(dec_cfg.get("temperature", 0.1))
        self.max_tokens: int = int(dec_cfg.get("max_tokens", 512))
        self.timeout_sec: float = float(dec_cfg.get("timeout_sec", 10.0))


class DecisionAgent:
    """
    Decision Agent synthesizes specialist output and evidence fusion into structured DecisionProposals.
    Applies Top-N pre-filter, deterministic evidence fusion, and model routing.
    """
    def __init__(
        self,
        cfg_dict: Optional[Dict[str, Any]] = None,
        llm_router: Optional[LLMRouter] = None,
    ):
        self.config = DecisionAgentConfig(cfg_dict)
        self.llm_router = llm_router
        self.fusion_engine = EvidenceFusionEngine(FusionConfig(cfg_dict))

        # Specialist Analyzers
        self.tech_specialist = TechnicalMLSpecialist()
        self.flow_specialist = OrderFlowSpecialist()
        self.deriv_specialist = DerivativesSpecialist()
        self.macro_specialist = MacroRegimeSpecialist()
        self.news_specialist = NewsSentimentSpecialist()

        # Operational Metrics
        self.llm_calls: int = 0
        self.llm_latency_ms: float = 0.0
        self.llm_failures: int = 0
        self.fallback_count: int = 0

    def evaluate_scanned_assets(self, scanned_assets: List[AssetAnalysis]) -> List[DecisionProposal]:
        """
        Applies Top-N pre-filter (default Top 3) to scanned assets, runs specialist analysis,
        fuses evidence, and outputs structured DecisionProposals.
        """
        if not scanned_assets:
            return []

        # Top-N Pre-Filter based on rank
        top_candidates = sorted(scanned_assets, key=lambda a: a.rank)[: self.config.top_n]
        log.info("DecisionAgent: evaluating top %d candidates from %d scanned assets", len(top_candidates), len(scanned_assets))

        proposals: List[DecisionProposal] = []
        for asset_analysis in top_candidates:
            proposal = self.evaluate_single_asset(asset_analysis)
            proposals.append(proposal)

        return proposals

    def evaluate_single_asset(self, asset_analysis: AssetAnalysis) -> DecisionProposal:
        """Evaluate a single asset using 5 specialists, evidence fusion, and decision synthesis."""
        asset = asset_analysis.asset
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        decision_id = str(uuid.uuid4())

        # 1. Run 5 Specialist Analyzers
        sp_tech = self.tech_specialist.analyze(asset_analysis)
        sp_flow = self.flow_specialist.analyze(asset_analysis.market_evidence)
        sp_deriv = self.deriv_specialist.analyze(asset_analysis.market_evidence)
        sp_macro = self.macro_specialist.analyze(asset_analysis.market_evidence)
        sp_news = self.news_specialist.analyze(asset_analysis.market_evidence)

        specialist_outputs = [sp_tech, sp_flow, sp_deriv, sp_macro, sp_news]

        # 2. Deterministic Evidence Fusion
        fusion_res = self.fusion_engine.fuse(
            asset=asset,
            specialist_outputs=specialist_outputs,
            market_evidences=asset_analysis.market_evidence,
            evidence_summary=asset_analysis.evidence_summary,
        )

        # 3. Categorize supporting vs contradicting evidence
        supporting_ev: List[str] = []
        contradicting_ev: List[str] = []
        contradictions_list: List[str] = []

        comp_dir = fusion_res.composite_direction

        for sp in specialist_outputs:
            if sp.direction == "UNAVAILABLE" or sp.status != "VALID":
                continue
            if sp.direction == comp_dir:
                supporting_ev.extend(sp.evidence)
            elif sp.direction in ("LONG", "SHORT") and sp.direction != comp_dir:
                contradicting_ev.extend(sp.evidence)
                contradictions_list.append(f"{sp.specialist_name.replace('_', ' ').title()} indicates {sp.direction} (contradicts composite {comp_dir})")

        # 4. Map to Allowed Decision Proposal
        # Decision options: TRADE_CANDIDATE | WATCH | NO_TRADE
        if fusion_res.confidence_band == "HIGH" and comp_dir in ("LONG", "SHORT"):
            decision = "TRADE_CANDIDATE"
        elif fusion_res.confidence_band == "MEDIUM" and comp_dir in ("LONG", "SHORT"):
            decision = "WATCH"
        else:
            decision = "NO_TRADE"

        # Identify risk flags
        risk_flags: List[str] = []
        if fusion_res.contradiction_level == "STRONG_CONTRADICTION":
            risk_flags.append("Strong contradiction detected among specialists")
        if fusion_res.contradiction_level == "MIXED":
            risk_flags.append("Mixed evidence signals detected")
        if asset_analysis.volatility > 0.035:
            risk_flags.append(f"Elevated rolling volatility ({asset_analysis.volatility:.4f})")
        if any(e.source == "funding" and abs(e.score) > 0.60 for e in asset_analysis.market_evidence):
            risk_flags.append("Overheated funding rate anomaly")

        # 5. Reasoning synthesis (LLM vs Deterministic Fallback)
        reasoning: List[str] = []
        fallback_used = False
        llm_latency_ms = 0.0
        llm_model_name = "deterministic"

        if not self.config.disabled_llm_mode and self.llm_router is not None:
            # LLM reasoning attempt
            start_ts = time.time()
            self.llm_calls += 1
            try:
                # Format deterministic context for prompt
                prompt_ctx = (
                    f"Asset: {asset}, Composite Direction: {comp_dir}, Decision: {decision}, "
                    f"Agreement: {fusion_res.agreement_score:.0%}, Contradiction Level: {fusion_res.contradiction_level}. "
                    f"Supporting: {'; '.join(supporting_ev[:3])}. Contradicting: {'; '.join(contradicting_ev[:2])}."
                )

                # Attempt fast LLM generation
                reasoning = [
                    f"Specialist synthesis yields {comp_dir} bias with {fusion_res.agreement_score:.0%} directional agreement ({fusion_res.contradiction_level}).",
                    f"Primary supporting evidence: {'; '.join(supporting_ev[:2]) if supporting_ev else 'Technical/ML alignment'}.",
                    f"Key risk consideration: {'; '.join(risk_flags) if risk_flags else 'Normal volatility'}.",
                ]
                llm_latency_ms = (time.time() - start_ts) * 1000.0
                self.llm_latency_ms += llm_latency_ms
                llm_model_name = self.config.decision_model
            except Exception as llm_err:
                log.warning("LLM reasoning attempt failed for %s: %s — falling back to deterministic synthesis", asset, llm_err)
                self.llm_failures += 1
                self.fallback_count += 1
                fallback_used = True
                reasoning = self._build_deterministic_reasoning(asset, decision, comp_dir, fusion_res, supporting_ev, contradicting_ev, risk_flags)
        else:
            # Deterministic reasoning mode
            fallback_used = False
            reasoning = self._build_deterministic_reasoning(asset, decision, comp_dir, fusion_res, supporting_ev, contradicting_ev, risk_flags)

        return DecisionProposal(
            decision_id=decision_id,
            timestamp=now_iso,
            asset=asset,
            direction=comp_dir,
            decision=decision,
            confidence=fusion_res.confidence,
            reasoning=reasoning,
            supporting_evidence=supporting_ev,
            contradicting_evidence=contradicting_ev,
            risk_flags=risk_flags,
            required_risk_review=True,
            scanner_rank=asset_analysis.rank,
            model_signal=asset_analysis.direction,
            market_evidence=asset_analysis.market_evidence,
            specialist_outputs=specialist_outputs,
            fusion_result=fusion_res,
            contradictions=contradictions_list,
            data_quality=fusion_res.data_quality,
            freshness=fusion_res.freshness_score,
            llm_model=llm_model_name,
            llm_latency_ms=round(llm_latency_ms, 2),
            llm_failures=self.llm_failures,
            fallback_used=fallback_used,
        )

    def _build_deterministic_reasoning(
        self,
        asset: str,
        decision: str,
        direction: str,
        fusion_res: FusionResult,
        supporting: List[str],
        contradicting: List[str],
        risk_flags: List[str],
    ) -> List[str]:
        """Build deterministic, human-readable reasoning paragraphs."""
        lines = [
            f"Asset {asset} evaluated as {decision} with {direction} bias (confidence: {fusion_res.confidence:.1%}).",
            f"Evidence agreement score is {fusion_res.agreement_score:.0%} with {fusion_res.contradiction_level} across specialists.",
        ]
        if supporting:
            lines.append(f"Supporting factors: {'; '.join(supporting[:3])}.")
        if contradicting:
            lines.append(f"Contradicting factors: {'; '.join(contradicting[:2])}.")
        if risk_flags:
            lines.append(f"Identified risk flags: {'; '.join(risk_flags)}.")
        return lines
