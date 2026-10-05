"""
agent/test_decision_fusion.py — Phase 12.2 Unit & Integration Tests

Comprehensive validation for Phase 12.2 Multi-Agent Market Decision & Evidence Fusion:
1. Specialist Analyzers (5 specialists)
2. Evidence Fusion Engine & Contradiction Classification
3. Decision Agent Top-N Filtering & Proposal Synthesis
4. Model Routing & Deterministic Fallback Mode
5. Risk Supervisor Review & Boundary Rules
6. Decision Provenance & Replay Integration
7. Execution Isolation Audit (Zero execution calls)
"""

import logging
import unittest
import math
import os
from datetime import datetime, timezone

from agent.schema import (
    AssetAnalysis,
    MarketEvidence,
    EvidenceSummary,
    SpecialistOutput,
    FusionResult,
    DecisionProposal,
    RiskSupervisorReview,
)
from agent.specialists import (
    TechnicalMLSpecialist,
    OrderFlowSpecialist,
    DerivativesSpecialist,
    MacroRegimeSpecialist,
    NewsSentimentSpecialist,
)
from agent.evidence_fusion import EvidenceFusionEngine, FusionConfig
from agent.decision_agent import DecisionAgent, DecisionAgentConfig
from agent.risk_supervisor import RiskSupervisor
from agent.decision_provenance import DecisionProvenanceManager
from agent.storage import SQLiteAgentStorage
from agent.trade_replay import TradeRecorder
from agent.market_scanner import MarketScanner

logging.basicConfig(level=logging.INFO)


class TestPhase12_2_DecisionFusion(unittest.TestCase):
    def setUp(self):
        self.db_path = "agent/test_fusion.sqlite"
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

        # Sample AssetAnalysis
        self.sample_evidence = [
            MarketEvidence(source="order_book", signal="BULLISH", score=0.65, confidence=0.80, reason="Bid depth exceeds ask depth (+32%)", raw_metrics={"imbalance": 0.32, "spread_pct": 0.0002}),
            MarketEvidence(source="large_flow", signal="BULLISH", score=0.70, confidence=0.85, reason="Net buyer volume flow +45%", raw_metrics={"flow_imbalance": 0.45, "large_trade_count": 12}),
            MarketEvidence(source="open_interest", signal="BULLISH", score=0.60, confidence=0.75, reason="OI expansion (+8.5%)", raw_metrics={"oi_change_pct": 0.085}),
            MarketEvidence(source="funding", signal="NEUTRAL", score=0.05, confidence=0.70, reason="Funding rate normal (+0.0100%/8h)", raw_metrics={"funding_rate": 0.0001}),
            MarketEvidence(source="positioning", signal="BULLISH", score=0.55, confidence=0.70, reason="Taker buy ratio > 1.20", raw_metrics={"lsr_account": 1.45, "lsr_taker": 1.28}),
            MarketEvidence(source="btc_regime", signal="BULLISH", score=0.50, confidence=0.80, reason="BTC bullish trend", raw_metrics={"btc_regime": "BULLISH_TREND", "btc_trend": "BULLISH"}),
            MarketEvidence(source="news", signal="UNAVAILABLE", score=0.0, confidence=0.0, status="UNAVAILABLE", reason="External news feed unconfigured"),
        ]

        self.sample_asset_analysis = AssetAnalysis(
            asset="BTC_USDT",
            direction="LONG",
            probability=0.78,
            confidence=0.82,
            prediction=0.0145,
            threshold=0.0050,
            market_regime="BULLISH_TREND",
            volatility=0.0180,
            momentum=0.0120,
            atr=450.0,
            rsi=58.5,
            ema_trend="BULLISH",
            rank=1,
            market_evidence=self.sample_evidence,
            evidence_summary=EvidenceSummary(
                agreement=0.85,
                contradiction_level="STRONG_AGREEMENT",
                bullish_count=5,
                bearish_count=0,
                neutral_count=1,
                unavailable_count=1,
                evidence_quality=0.78,
                weighted_score=0.62,
                composite_signal="BULLISH",
            ),
            agreement_score=0.85,
            contradiction_level="STRONG_AGREEMENT",
            evidence_quality=0.78,
            data_freshness_sec=1.5,
        )

    def test_01_technical_ml_specialist(self):
        specialist = TechnicalMLSpecialist()
        out = specialist.analyze(self.sample_asset_analysis)
        self.assertEqual(out.specialist_name, "technical_ml")
        self.assertEqual(out.direction, "LONG")
        self.assertGreater(out.confidence, 0.50)
        self.assertEqual(out.status, "VALID")
        self.assertTrue(any("prediction" in r for r in out.reasons))

    def test_02_order_flow_specialist(self):
        specialist = OrderFlowSpecialist()
        out = specialist.analyze(self.sample_evidence)
        self.assertEqual(out.specialist_name, "order_flow")
        self.assertEqual(out.direction, "LONG")
        self.assertGreaterEqual(out.confidence, 0.80)
        self.assertTrue(any("Bid depth" in e or "volume flow" in e for e in out.evidence))

    def test_03_derivatives_specialist(self):
        specialist = DerivativesSpecialist()
        out = specialist.analyze(self.sample_evidence)
        self.assertEqual(out.specialist_name, "derivatives")
        self.assertEqual(out.direction, "LONG")
        self.assertGreater(out.confidence, 0.60)
        self.assertTrue(any("Open interest" in r or "Funding rate" in r for r in out.reasons))

    def test_04_macro_regime_specialist(self):
        specialist = MacroRegimeSpecialist()
        out = specialist.analyze(self.sample_evidence)
        self.assertEqual(out.specialist_name, "macro_regime")
        self.assertEqual(out.direction, "LONG")
        self.assertEqual(out.status, "VALID")

    def test_05_news_sentiment_specialist_unavailable(self):
        specialist = NewsSentimentSpecialist()
        out = specialist.analyze(self.sample_evidence)
        self.assertEqual(out.specialist_name, "news_sentiment")
        self.assertEqual(out.status, "UNAVAILABLE")
        self.assertEqual(out.direction, "UNAVAILABLE")
        self.assertEqual(out.confidence, 0.0)

    def test_06_evidence_fusion_engine_strong_agreement(self):
        fusion_engine = EvidenceFusionEngine()
        specialists = [
            TechnicalMLSpecialist().analyze(self.sample_asset_analysis),
            OrderFlowSpecialist().analyze(self.sample_evidence),
            DerivativesSpecialist().analyze(self.sample_evidence),
            MacroRegimeSpecialist().analyze(self.sample_evidence),
            NewsSentimentSpecialist().analyze(self.sample_evidence),
        ]
        res = fusion_engine.fuse("BTC_USDT", specialists, self.sample_evidence)
        self.assertEqual(res.composite_direction, "LONG")
        self.assertEqual(res.contradiction_level, "STRONG_AGREEMENT")
        self.assertEqual(res.confidence_band, "HIGH")
        self.assertGreaterEqual(res.agreement_score, 0.80)

    def test_07_evidence_fusion_engine_strong_contradiction(self):
        fusion_engine = EvidenceFusionEngine()
        # Create contradicting specialist outputs
        sp1 = SpecialistOutput(specialist_name="technical_ml", direction="LONG", confidence=0.85, status="VALID")
        sp2 = SpecialistOutput(specialist_name="order_flow", direction="SHORT", confidence=0.85, status="VALID")
        sp3 = SpecialistOutput(specialist_name="derivatives", direction="SHORT", confidence=0.80, status="VALID")
        sp4 = SpecialistOutput(specialist_name="macro_regime", direction="LONG", confidence=0.75, status="VALID")
        sp5 = SpecialistOutput(specialist_name="news_sentiment", direction="UNAVAILABLE", confidence=0.0, status="UNAVAILABLE")

        res = fusion_engine.fuse("SOL_USDT", [sp1, sp2, sp3, sp4, sp5], [])
        self.assertEqual(res.contradiction_level, "STRONG_CONTRADICTION")
        self.assertEqual(res.confidence_band, "NO_TRADE")

    def test_08_decision_agent_top_n_filtering(self):
        agent = DecisionAgent(cfg_dict={"decision_agent": {"top_n": 3, "disabled_llm_mode": True}})
        # Generate 6 mock scanned assets
        scanned = []
        for i, asset in enumerate(["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT", "AVAX_USDT"], start=1):
            scanned.append(AssetAnalysis(
                asset=asset,
                direction="LONG" if i <= 3 else "NEUTRAL",
                probability=0.80 - i * 0.05,
                confidence=0.85 - i * 0.05,
                prediction=0.02 - i * 0.003,
                threshold=0.005,
                market_regime="BULLISH_TREND",
                volatility=0.02,
                momentum=0.01,
                atr=10.0,
                rsi=55.0,
                ema_trend="BULLISH",
                rank=i,
                market_evidence=self.sample_evidence,
            ))

        proposals = agent.evaluate_scanned_assets(scanned)
        # Should only evaluate Top 3 assets
        self.assertEqual(len(proposals), 3)
        self.assertEqual([p.asset for p in proposals], ["BTC_USDT", "ETH_USDT", "SOL_USDT"])
        self.assertIn(proposals[0].decision, ("TRADE_CANDIDATE", "WATCH", "NO_TRADE"))

    def test_09_decision_agent_fallback_mode(self):
        agent = DecisionAgent(cfg_dict={"decision_agent": {"disabled_llm_mode": True}})
        proposal = agent.evaluate_single_asset(self.sample_asset_analysis)
        self.assertIsInstance(proposal, DecisionProposal)
        self.assertFalse(proposal.fallback_used)  # disabled LLM mode directly builds deterministic reasoning
        self.assertEqual(proposal.llm_model, "deterministic")
        self.assertGreater(len(proposal.reasoning), 0)

    def test_10_risk_supervisor_approval(self):
        agent = DecisionAgent(cfg_dict={"decision_agent": {"disabled_llm_mode": True}})
        proposal = agent.evaluate_single_asset(self.sample_asset_analysis)

        supervisor = RiskSupervisor()
        review = supervisor.review_proposal(proposal)

        self.assertIsInstance(review, RiskSupervisorReview)
        self.assertIn(review.status, ("APPROVED_FOR_RISK_REVIEW", "WATCH"))
        self.assertLessEqual(review.risk_score, 0.50)

    def test_11_risk_supervisor_rejection_on_strong_contradiction(self):
        supervisor = RiskSupervisor()
        contradicting_proposal = DecisionProposal(
            decision_id="test_001",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            asset="ETH_USDT",
            direction="SHORT",
            decision="TRADE_CANDIDATE",
            confidence=0.60,
            fusion_result=FusionResult(
                directional_score=-0.20,
                confidence=0.60,
                agreement_score=0.50,
                contradiction_level="STRONG_CONTRADICTION",
                evidence_quality=0.50,
                data_quality=0.80,
                freshness_score=0.95,
                confidence_band="NO_TRADE",
                composite_direction="SHORT",
            ),
        )
        review = supervisor.review_proposal(contradicting_proposal)
        self.assertEqual(review.status, "REJECTED")
        self.assertIn("STRONG_CONTRADICTION", review.rejection_reasons[0])

    def tearDown(self):
        if hasattr(self, "db_path") and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_12_decision_provenance_storage(self):
        storage = SQLiteAgentStorage(db_path=self.db_path)
        storage.init_schema()

        manager = DecisionProvenanceManager(storage=storage)
        agent = DecisionAgent(cfg_dict={"decision_agent": {"disabled_llm_mode": True}})
        proposal = agent.evaluate_single_asset(self.sample_asset_analysis)

        supervisor = RiskSupervisor()
        review = supervisor.review_proposal(proposal)

        manager.record_decision(proposal, review)

        stored_props = manager.get_recent_proposals(limit=10)
        stored_revs = manager.get_recent_reviews(limit=10)

        self.assertEqual(len(stored_props), 1)
        self.assertEqual(len(stored_revs), 1)
        self.assertEqual(stored_props[0]["asset"], "BTC_USDT")
        self.assertEqual(stored_revs[0]["asset"], "BTC_USDT")

    def test_13_trade_replay_integration(self):
        storage = SQLiteAgentStorage(db_path=self.db_path)
        storage.init_schema()

        recorder = TradeRecorder(storage=storage)
        trade_id = recorder.create_trade("BTC_USDT", "LONG", plan_id=101)

        recorder.record_specialist_analysis(trade_id, "BTC_USDT", {"technical_ml": "LONG", "order_flow": "LONG"})
        recorder.record_evidence_fused(trade_id, "BTC_USDT", {"directional_score": 0.65, "confidence": 0.82})
        recorder.record_decision_created(trade_id, "BTC_USDT", {"decision": "TRADE_CANDIDATE", "direction": "LONG", "confidence": 0.82})
        recorder.record_decision_reviewed(trade_id, "BTC_USDT", {"status": "APPROVED_FOR_RISK_REVIEW", "risk_score": 0.20})

        timeline = recorder.get_trade_timeline(trade_id)
        event_types = [e["event_type"] for e in timeline]

        self.assertIn("specialist_analysis", event_types)
        self.assertIn("evidence_fused", event_types)
        self.assertIn("decision_created", event_types)
        self.assertIn("decision_reviewed", event_types)

    def test_14_execution_isolation_audit(self):
        """Verify that Phase 12.2 decision agent & risk supervisor make ZERO execution calls."""
        import inspect
        import agent.decision_agent as da_module
        import agent.risk_supervisor as rs_module

        da_source = inspect.getsource(da_module)
        rs_source = inspect.getsource(rs_module)

        # Prohibited execution strings
        prohibited = [
            "place_order",
            "open_position",
            "close_position",
            "GateExecutor.place_order",
            "ExecutionEngine",
        ]

        for word in prohibited:
            self.assertNotIn(word, da_source, f"Forbidden execution call '{word}' found in DecisionAgent module!")
            self.assertNotIn(word, rs_source, f"Forbidden execution call '{word}' found in RiskSupervisor module!")


if __name__ == "__main__":
    unittest.main()
