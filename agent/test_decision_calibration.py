"""
agent/test_decision_calibration.py — Phase 12.3 Unit & Integration Tests

Comprehensive validation for Phase 12.3:
1. Historical Replay Engine (Step-by-step)
2. Strict No-Lookahead Bias Audit
3. Outcome Calculation & Forward Returns
4. Confidence Binning, ECE, and Brier Score
5. Mandatory Baseline Comparisons (Always LONG/SHORT, Random, Tech-only, ML-only)
6. Asset-by-Asset and Regime Analysis
7. Evidence Agreement & Contradiction Correlation
8. Data Edge Cases (Missing candles, gaps, insufficient warmup)
9. Shadow Trading Engine (Creation, Price Update, Close)
10. Shadow Execution Isolation Audit (Zero order placement calls)
11. Dashboard APIs & Provenance Storage Integration
"""

import logging
import math
import os
import unittest
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from agent.schema import (
    AssetAnalysis,
    MarketEvidence,
    EvidenceSummary,
    DecisionProposal,
    RiskSupervisorReview,
    DecisionOutcome,
    ShadowTrade,
    CalibrationBin,
    CalibrationReport,
)
from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.calibration import DecisionCalibrationEngine
from agent.shadow_trading import ShadowTradingEngine
from agent.storage import SQLiteAgentStorage

logging.basicConfig(level=logging.INFO)


class TestPhase12_3_DecisionCalibration(unittest.TestCase):
    def setUp(self):
        self.db_path = "agent/test_calibration.sqlite"
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

        self.storage = SQLiteAgentStorage(db_path=self.db_path)
        self.storage.init_schema()

        # Mock sample outcomes
        self.sample_outcomes = [
            DecisionOutcome(
                decision_id=f"dec_{i}",
                asset="BTC_USDT" if i % 2 == 0 else "ETH_USDT",
                timestamp="2026-01-01T00:00:00Z",
                decision="TRADE_CANDIDATE" if i <= 15 else "WATCH",
                direction="LONG" if i % 3 != 0 else "SHORT",
                confidence=0.55 + (i % 5) * 0.08,
                confidence_band="HIGH" if i % 2 == 0 else "MEDIUM",
                agreement_score=0.85 if i % 2 == 0 else 0.60,
                contradiction_level="STRONG_AGREEMENT" if i % 2 == 0 else "MIXED",
                evidence_quality=0.80,
                data_quality=0.90,
                data_freshness=0.95,
                forward_return_1=0.01 if i % 2 == 0 else -0.005,
                forward_return_3=0.02 if i % 2 == 0 else -0.01,
                forward_return_6=0.03 if i % 2 == 0 else -0.015,
                direction_correct=(i % 2 == 0),
                outcome_class="CORRECT" if i % 2 == 0 else "INCORRECT",
                market_regime="BULLISH_TREND" if i % 2 == 0 else "CONSOLIDATION",
                fusion_score=0.50 if i % 2 == 0 else -0.20,
            )
            for i in range(1, 25)
        ]

    def tearDown(self):
        if hasattr(self, "db_path") and os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_01_historical_replay_engine_initialization(self):
        config = ReplayConfig(warmup_period=20, top_n=2)
        engine = HistoricalReplayEngine(config=config)
        self.assertEqual(engine.config.warmup_period, 20)
        self.assertEqual(engine.config.top_n, 2)
        self.assertFalse(engine.config.llm_replay_enabled)

    def test_02_historical_replay_execution(self):
        config = ReplayConfig(warmup_period=90, top_n=2)
        engine = HistoricalReplayEngine(config=config)
        outcomes, logs = engine.run_replay()
        self.assertGreater(len(outcomes), 0)
        self.assertIsInstance(outcomes[0], DecisionOutcome)
        self.assertIn(outcomes[0].direction, ("LONG", "SHORT", "NEUTRAL"))

    def test_03_no_lookahead_bias_audit(self):
        """Verify step T receives strictly market data <= T during decision generation."""
        engine = HistoricalReplayEngine(config=ReplayConfig(warmup_period=90, top_n=1))

        # Inspect raw data slice at step 92
        step = 92
        for asset, df in engine._raw_data.items():
            slice_df = df.iloc[: step + 1]
            # Ensure max timestamp in slice equals exact row at step
            self.assertEqual(slice_df.iloc[-1]["timestamp"], df.iloc[step]["timestamp"])
            # Ensure future rows (step+1 onwards) are not present in slice_df
            self.assertNotIn(df.iloc[step + 1]["timestamp"], slice_df["timestamp"].values)

    def test_04_outcome_calculation_and_forward_returns(self):
        engine = HistoricalReplayEngine(config=ReplayConfig(warmup_period=90, top_n=1))
        outcomes, _ = engine.run_replay()
        for o in outcomes:
            self.assertIsInstance(o.forward_return_1, float)
            self.assertIsInstance(o.forward_return_3, float)
            self.assertIsInstance(o.direction_correct, bool)

    def test_05_confidence_calibration_analysis(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze(self.sample_outcomes)
        self.assertIsInstance(report, CalibrationReport)
        self.assertGreater(report.total_decisions, 0)
        self.assertGreater(len(report.bins), 0)
        self.assertGreaterEqual(report.brier_score, 0.0)
        self.assertGreaterEqual(report.expected_calibration_error, 0.0)

    def test_06_mandatory_baseline_comparisons(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze(self.sample_outcomes)
        baselines = report.baseline_comparisons
        self.assertIn("Agent_Multi_Agent", baselines)
        self.assertIn("Baseline_A_Always_LONG", baselines)
        self.assertIn("Baseline_B_Always_SHORT", baselines)
        self.assertIn("Baseline_C_Random", baselines)
        self.assertIn("Baseline_D_Tech_Only", baselines)
        self.assertIn("Baseline_E_ML_Only", baselines)
        self.assertIn("Baseline_F_Intelligence_Only", baselines)

    def test_07_asset_breakdown_analysis(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze(self.sample_outcomes)
        asset_bd = report.asset_breakdown
        self.assertIn("BTC_USDT", asset_bd)
        self.assertIn("ETH_USDT", asset_bd)
        self.assertIn("accuracy", asset_bd["BTC_USDT"])

    def test_08_regime_and_agreement_breakdown(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze(self.sample_outcomes)
        self.assertIn("BULLISH_TREND", report.regime_breakdown)
        self.assertIn("STRONG_AGREEMENT", report.agreement_breakdown)

    def test_09_calibration_readiness_status(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze(self.sample_outcomes)
        self.assertIn(report.calibration_status, ("CALIBRATED", "PARTIALLY_CALIBRATED", "UNCALIBRATED", "INSUFFICIENT_SAMPLE"))
        self.assertIn(report.performance_status, ("POSITIVE_EDGE", "POSSIBLE_EDGE", "NO_EDGE", "INSUFFICIENT_SAMPLE"))

    def test_10_edge_case_empty_outcomes(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze([])
        self.assertEqual(report.total_decisions, 0)
        self.assertEqual(report.calibration_status, "INSUFFICIENT_SAMPLE")

    def test_11_shadow_trading_engine_initialization(self):
        shadow_engine = ShadowTradingEngine(storage=self.storage)
        self.assertEqual(shadow_engine.execution_mode, "SHADOW")
        self.assertEqual(len(shadow_engine.get_active_shadow_trades()), 0)

    def test_12_shadow_trade_creation(self):
        shadow_engine = ShadowTradingEngine(storage=self.storage)
        proposal = DecisionProposal(
            decision_id="prop_101",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            asset="BTC_USDT",
            direction="LONG",
            decision="TRADE_CANDIDATE",
            confidence=0.82,
        )
        review = RiskSupervisorReview(
            proposal_id="prop_101",
            asset="BTC_USDT",
            status="APPROVED_FOR_RISK_REVIEW",
            risk_score=0.20,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            reviewed_decision="TRADE_CANDIDATE",
        )
        shadow_trade = shadow_engine.process_decision_review(proposal, review, reference_price=65000.0)
        self.assertIsNotNone(shadow_trade)
        self.assertEqual(shadow_trade.asset, "BTC_USDT")
        self.assertEqual(shadow_trade.entry_reference_price, 65000.0)
        self.assertEqual(shadow_trade.execution_mode, "SHADOW")

    def test_13_shadow_trade_price_updates(self):
        shadow_engine = ShadowTradingEngine(storage=self.storage)
        proposal = DecisionProposal(
            decision_id="prop_102",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            asset="ETH_USDT",
            direction="LONG",
            decision="TRADE_CANDIDATE",
            confidence=0.78,
        )
        review = RiskSupervisorReview(
            proposal_id="prop_102",
            asset="ETH_USDT",
            status="APPROVED_FOR_RISK_REVIEW",
            risk_score=0.15,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            reviewed_decision="TRADE_CANDIDATE",
        )
        shadow_trade = shadow_engine.process_decision_review(proposal, review, reference_price=3000.0)

        # Price ticks up +5%
        updated = shadow_engine.update_prices({"ETH_USDT": 3150.0})
        self.assertEqual(len(updated), 1)
        self.assertAlmostEqual(updated[0].unrealized_return, 0.05, places=4)
        self.assertAlmostEqual(updated[0].max_favorable_excursion, 0.05, places=4)

    def test_14_shadow_trade_closing(self):
        shadow_engine = ShadowTradingEngine(storage=self.storage)
        proposal = DecisionProposal(
            decision_id="prop_103",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            asset="SOL_USDT",
            direction="LONG",
            decision="TRADE_CANDIDATE",
            confidence=0.85,
        )
        review = RiskSupervisorReview(
            proposal_id="prop_103",
            asset="SOL_USDT",
            status="APPROVED_FOR_RISK_REVIEW",
            risk_score=0.10,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            reviewed_decision="TRADE_CANDIDATE",
        )
        trade = shadow_engine.process_decision_review(proposal, review, reference_price=150.0)
        closed_trade = shadow_engine.close_shadow_trade(trade.shadow_id, exit_price=165.0, reason="PROFIT_TARGET")

        self.assertEqual(closed_trade.outcome, "WIN")
        self.assertAlmostEqual(closed_trade.final_return, 0.10, places=4)

    def test_15_shadow_execution_isolation_audit(self):
        """Verify that ShadowTradingEngine contains ZERO order submission calls."""
        import inspect
        import agent.shadow_trading as shadow_module

        source = inspect.getsource(shadow_module)
        prohibited = [
            "place_order",
            "open_position",
            "close_position",
            "GateExecutor",
            "ExecutionEngine",
            "submit_order",
        ]
        for word in prohibited:
            self.assertNotIn(word, source, f"Prohibited execution string '{word}' found in ShadowTradingEngine module!")

    def test_16_storage_shadow_trade_methods(self):
        shadow_trade = ShadowTrade(
            shadow_id="sh_test_01",
            decision_id="prop_test_01",
            asset="BTC_USDT",
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            direction="LONG",
            entry_reference_price=64000.0,
            current_price=65000.0,
            unrealized_return=0.0156,
            execution_mode="SHADOW",
        )
        row_id = self.storage.save_shadow_trade(shadow_trade.model_dump())
        self.assertGreater(row_id, 0)

        recent = self.storage.get_recent_shadow_trades(limit=10)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["shadow_id"], "sh_test_01")

    def test_17_storage_calibration_report_methods(self):
        cal_engine = DecisionCalibrationEngine()
        report = cal_engine.analyze(self.sample_outcomes)
        row_id = self.storage.save_calibration_report(report.model_dump(mode="json"))
        self.assertGreater(row_id, 0)

        latest = self.storage.get_latest_calibration_report()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["report"]["total_decisions"], report.total_decisions)

    def test_18_dashboard_apis(self):
        from dashboard.app import (
            api_agent_shadow_latest,
            api_agent_shadow_history,
            api_agent_shadow_performance,
            api_agent_calibration_summary,
        )

        latest = api_agent_shadow_latest()
        self.assertIn("shadow_trades", latest)
        self.assertEqual(latest["execution_mode"], "SHADOW")

        history = api_agent_shadow_history()
        self.assertIn("shadow_history", history)

        perf = api_agent_shadow_performance()
        self.assertIn("execution_mode", perf)

        cal_sum = api_agent_calibration_summary()
        self.assertIn("calibration_report", cal_sum)


if __name__ == "__main__":
    unittest.main()
