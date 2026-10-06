"""
agent/test_offline_evidence_integrity.py — Phase 12.3F Offline Evidence Integrity Tests

Verifies that offline historical replay does not introduce synthetic/fabricated bullish orderbook evidence,
that OrderFlowSpecialist outputs UNAVAILABLE when orderbook data is missing,
that EvidenceFusion does not create artificial contradictions for missing orderbook data,
and that execution isolation is strictly preserved.
"""

from unittest.mock import MagicMock
import pytest

from agent.market_intelligence import MarketIntelligence, MarketEvidence, analyze_order_book, analyze_large_flow
from agent.specialists import OrderFlowSpecialist, TechnicalMLSpecialist, SpecialistOutput
from agent.evidence_fusion import EvidenceFusionEngine
from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.market_scanner import MarketScanner


class TestPhase12_3F_OfflineEvidenceIntegrity:

    def test_A_historical_replay_without_orderbook_orderflow_unavailable(self):
        """Test A: Historical replay without orderbook -> OrderFlow = UNAVAILABLE."""
        intel = MarketIntelligence(offline_mode=True)
        evidences, summary = intel.analyze_asset_intelligence(
            asset="BTC_USDT",
            tech_signal="BEARISH",
            tech_score=-0.5,
            ml_signal="SHORT",
            ml_score=-0.02,
            ml_confidence=0.75,
        )

        ob_ev = next((e for e in evidences if e.source == "order_book"), None)
        lf_ev = next((e for e in evidences if e.source == "large_flow"), None)

        assert ob_ev is not None
        assert ob_ev.signal == "UNAVAILABLE"
        assert ob_ev.status == "UNAVAILABLE"

        assert lf_ev is not None
        assert lf_ev.signal == "UNAVAILABLE"
        assert lf_ev.status == "UNAVAILABLE"

        specialist = OrderFlowSpecialist()
        sp_out = specialist.analyze(evidences)
        assert sp_out.direction == "UNAVAILABLE"
        assert sp_out.status == "UNAVAILABLE"
        assert sp_out.confidence == 0.0

    def test_B_no_fabricated_imbalance(self):
        """Test B: Historical replay without orderbook -> no fabricated +0.25 imbalance."""
        intel = MarketIntelligence(offline_mode=True)
        evidences, summary = intel.analyze_asset_intelligence(
            asset="ETH_USDT",
            tech_signal="BEARISH",
            tech_score=-0.5,
            ml_signal="SHORT",
            ml_score=-0.02,
            ml_confidence=0.75,
        )
        ob_ev = next((e for e in evidences if e.source == "order_book"), None)
        assert ob_ev.raw_metrics.get("imbalance") is None or ob_ev.raw_metrics.get("imbalance") == 0.0
        assert ob_ev.raw_metrics.get("imbalance") != 0.25

    def test_C_no_fabricated_flow_imbalance(self):
        """Test C: Historical replay without orderbook -> no fabricated +0.30 flow imbalance."""
        intel = MarketIntelligence(offline_mode=True)
        evidences, summary = intel.analyze_asset_intelligence(
            asset="SOL_USDT",
            tech_signal="BEARISH",
            tech_score=-0.5,
            ml_signal="SHORT",
            ml_score=-0.02,
            ml_confidence=0.75,
        )
        lf_ev = next((e for e in evidences if e.source == "large_flow"), None)
        assert lf_ev.raw_metrics.get("flow_imbalance") is None or lf_ev.raw_metrics.get("flow_imbalance") == 0.0
        assert lf_ev.raw_metrics.get("flow_imbalance") != 0.30

    def test_D_technical_short_orderflow_unavailable_no_artificial_contradiction(self):
        """Test D: TechnicalML SHORT + OrderFlow UNAVAILABLE -> must NOT create artificial MIXED contradiction."""
        tech_sp = SpecialistOutput(
            specialist_name="technical_ml",
            direction="SHORT",
            confidence=0.80,
            evidence=["Strong bearish trend"],
            reasons=["EMA slope < 0"],
            status="VALID",
            metrics={"score": -0.05},
        )
        of_sp = SpecialistOutput(
            specialist_name="order_flow",
            direction="UNAVAILABLE",
            confidence=0.0,
            evidence=["Orderbook data unavailable"],
            reasons=["Offline replay"],
            status="UNAVAILABLE",
            metrics={},
        )
        macro_sp = SpecialistOutput(
            specialist_name="macro_regime",
            direction="NEUTRAL",
            confidence=0.60,
            evidence=["BTC neutral consolidation"],
            reasons=["BTC neutral"],
            status="VALID",
            metrics={},
        )

        fusion_engine = EvidenceFusionEngine()
        result = fusion_engine.fuse("BTC_USDT", [tech_sp, of_sp, macro_sp], [])

        assert result.composite_direction == "SHORT"
        # Since order_flow is UNAVAILABLE, it must NOT trigger STRONG_CONTRADICTION or MIXED
        assert result.contradiction_level in ("STRONG_AGREEMENT", "MODERATE_AGREEMENT")
        assert result.confidence_band != "NO_TRADE"

    def test_E_technical_short_real_bearish_orderflow(self):
        """Test E: TechnicalML SHORT + real bearish orderflow -> remains bearish."""
        tech_sp = SpecialistOutput(
            specialist_name="technical_ml",
            direction="SHORT",
            confidence=0.80,
            evidence=["Bearish trend"],
            reasons=["EMA slope < 0"],
            status="VALID",
            metrics={},
        )
        of_sp = SpecialistOutput(
            specialist_name="order_flow",
            direction="SHORT",
            confidence=0.75,
            evidence=["Ask depth dominates"],
            reasons=["Orderbook imbalance -0.35"],
            status="VALID",
            metrics={"imbalance": -0.35},
        )

        fusion_engine = EvidenceFusionEngine()
        result = fusion_engine.fuse("BTC_USDT", [tech_sp, of_sp], [])

        assert result.composite_direction == "SHORT"
        assert result.contradiction_level == "STRONG_AGREEMENT"

    def test_F_technical_short_real_bullish_orderflow_legitimate_contradiction(self):
        """Test F: TechnicalML SHORT + real bullish orderflow -> legitimate contradiction remains."""
        tech_sp = SpecialistOutput(
            specialist_name="technical_ml",
            direction="SHORT",
            confidence=0.80,
            evidence=["Bearish trend"],
            reasons=["EMA slope < 0"],
            status="VALID",
            metrics={},
        )
        of_sp = SpecialistOutput(
            specialist_name="order_flow",
            direction="LONG",
            confidence=0.75,
            evidence=["Bid depth dominates"],
            reasons=["Orderbook imbalance +0.35"],
            status="VALID",
            metrics={"imbalance": 0.35},
        )

        fusion_engine = EvidenceFusionEngine()
        result = fusion_engine.fuse("BTC_USDT", [tech_sp, of_sp], [])

        assert result.contradiction_level in ("MIXED", "STRONG_CONTRADICTION")

    def test_G_live_scanner_with_real_orderbook_preserved(self):
        """Test G: Live scanner with real orderbook -> existing orderflow behavior preserved."""
        mock_client = MagicMock()
        mock_client.get_order_book.return_value = (
            {"bids": [{"p": "100", "s": "20"}], "asks": [{"p": "101", "s": "5"}]},
            "OK",
            0.05,
        )

        ob_ev = analyze_order_book(mock_client, "BTC_USDT")
        assert ob_ev.signal == "BULLISH"
        assert ob_ev.status == "VALID"
        assert ob_ev.raw_metrics["imbalance"] > 0.20

    def test_H_execution_isolation_audit(self):
        """Test H: Execution isolation remains intact."""
        replay = HistoricalReplayEngine()

        assert hasattr(replay, "risk_supervisor")
        # Ensure zero live order methods were called or initialized
        assert not hasattr(replay, "live_executor")
