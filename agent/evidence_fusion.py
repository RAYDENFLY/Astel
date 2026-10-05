"""
agent/evidence_fusion.py — Phase 12.2 Deterministic Evidence Fusion Engine

Fuses evidence from Specialist outputs, MarketEvidence, and EvidenceSummary using
configurable, deterministic weights and explicit contradiction handling.
LLMs do NOT invent weights or confidence band thresholds.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import AssetAnalysis, MarketEvidence, EvidenceSummary, SpecialistOutput, FusionResult

log = logging.getLogger("agent.evidence_fusion")


class FusionConfig:
    """Configurable weights & thresholds for EvidenceFusion."""
    def __init__(self, cfg_dict: Optional[Dict[str, Any]] = None):
        cfg_dict = cfg_dict or {}
        fusion_cfg = cfg_dict.get("evidence_fusion") or {}
        weights = fusion_cfg.get("weights") or {}

        # Configurable weights (default sum to 1.0)
        self.technical_weight: float = float(weights.get("technical_ml", 0.35))
        self.order_flow_weight: float = float(weights.get("order_flow", 0.20))
        self.derivatives_weight: float = float(weights.get("derivatives", 0.25))
        self.macro_weight: float = float(weights.get("macro_regime", 0.15))
        self.news_weight: float = float(weights.get("news_sentiment", 0.05))

        # Confidence band thresholds
        bands = fusion_cfg.get("confidence_bands") or {}
        self.high_agreement_min: float = float(bands.get("high_agreement_min", 0.75))
        self.high_quality_min: float = float(bands.get("high_quality_min", 0.65))
        self.medium_agreement_min: float = float(bands.get("medium_agreement_min", 0.55))
        self.medium_quality_min: float = float(bands.get("medium_quality_min", 0.45))


class EvidenceFusionEngine:
    """
    Deterministic Evidence Fusion Engine.
    Combines specialist outputs into a unified FusionResult with explicit contradiction classification
    and deterministic confidence bands.
    """
    def __init__(self, config: Optional[FusionConfig] = None):
        self.config = config or FusionConfig()

    def fuse(
        self,
        asset: str,
        specialist_outputs: List[SpecialistOutput],
        market_evidences: List[MarketEvidence],
        evidence_summary: Optional[EvidenceSummary] = None,
    ) -> FusionResult:
        """Fuse specialist outputs deterministically."""
        weight_map = {
            "technical_ml": self.config.technical_weight,
            "order_flow": self.config.order_flow_weight,
            "derivatives": self.config.derivatives_weight,
            "macro_regime": self.config.macro_weight,
            "news_sentiment": self.config.news_weight,
        }

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        unavailable_count = 0

        weighted_score_sum = 0.0
        active_weight_sum = 0.0
        active_weights: Dict[str, float] = {}

        valid_specialists_count = 0
        total_confidence_sum = 0.0

        for sp in specialist_outputs:
            w = weight_map.get(sp.specialist_name, 0.15)
            direction = sp.direction.upper()

            if direction == "UNAVAILABLE" or sp.status in ("UNAVAILABLE", "STALE", "ERROR"):
                unavailable_count += 1
                continue

            valid_specialists_count += 1
            total_confidence_sum += sp.confidence

            # Convert direction to numerical score in [-1.0, 1.0]
            if direction in ("LONG", "BULLISH"):
                bullish_count += 1
                score = sp.confidence
                weighted_score_sum += w * score
                active_weight_sum += w
                active_weights[sp.specialist_name] = round(w, 4)
            elif direction in ("SHORT", "BEARISH"):
                bearish_count += 1
                score = -sp.confidence
                weighted_score_sum += w * score
                active_weight_sum += w
                active_weights[sp.specialist_name] = round(w, 4)
            else:  # NEUTRAL
                neutral_count += 1
                score = 0.0
                weighted_score_sum += w * score
                active_weight_sum += w
                active_weights[sp.specialist_name] = round(w, 4)

        # Directional Score
        directional_score = weighted_score_sum / active_weight_sum if active_weight_sum > 0 else 0.0

        # Composite Direction
        if directional_score >= 0.18:
            composite_direction = "LONG"
        elif directional_score <= -0.18:
            composite_direction = "SHORT"
        else:
            composite_direction = "NEUTRAL"

        # Agreement Score
        directional_sources = bullish_count + bearish_count
        if directional_sources > 0:
            agreement_score = max(bullish_count, bearish_count) / float(directional_sources)
        else:
            agreement_score = 0.0

        # Contradiction Level Classification
        if valid_specialists_count < 2:
            contradiction_level = "INSUFFICIENT_DATA"
        elif bullish_count == 0 or bearish_count == 0:
            if agreement_score >= 0.75:
                contradiction_level = "STRONG_AGREEMENT"
            else:
                contradiction_level = "MODERATE_AGREEMENT"
        else:
            # Both bullish and bearish signals exist
            if min(bullish_count, bearish_count) >= 2 or agreement_score < 0.60:
                contradiction_level = "STRONG_CONTRADICTION"
            else:
                contradiction_level = "MIXED"

        # Quality & Freshness metrics
        data_quality = (valid_specialists_count / max(1, len(specialist_outputs)))
        avg_confidence = total_confidence_sum / max(1, valid_specialists_count)
        evidence_quality = avg_confidence * (0.60 + 0.40 * data_quality)
        freshness_score = 0.95  # Live scanner data freshness

        # Confidence Band Determination
        if contradiction_level in ("STRONG_CONTRADICTION", "INSUFFICIENT_DATA") or composite_direction == "NEUTRAL":
            confidence_band = "NO_TRADE"
        elif (
            agreement_score >= self.config.high_agreement_min
            and evidence_quality >= self.config.high_quality_min
            and contradiction_level in ("STRONG_AGREEMENT", "MODERATE_AGREEMENT")
        ):
            confidence_band = "HIGH"
        elif (
            agreement_score >= self.config.medium_agreement_min
            and evidence_quality >= self.config.medium_quality_min
            and contradiction_level != "STRONG_CONTRADICTION"
        ):
            confidence_band = "MEDIUM"
        else:
            confidence_band = "LOW"

        final_confidence = avg_confidence * (0.50 + 0.50 * agreement_score)

        return FusionResult(
            directional_score=round(directional_score, 4),
            confidence=round(final_confidence, 4),
            agreement_score=round(agreement_score, 4),
            contradiction_level=contradiction_level,
            evidence_quality=round(evidence_quality, 4),
            data_quality=round(data_quality, 4),
            freshness_score=round(freshness_score, 4),
            confidence_band=confidence_band,
            composite_direction=composite_direction,
            weighted_weights=active_weights,
        )
