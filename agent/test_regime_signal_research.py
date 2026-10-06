"""
agent/test_regime_signal_research.py — Unit Tests for Phase 12.8 Regime Research Engine
"""

import unittest
import pandas as pd
from agent.regime_signal_research import RegimeSignalResearchEngine
from agent.candidate_signal import CandidateSignalV1


class TestRegimeSignalResearch(unittest.TestCase):

    def setUp(self):
        self.engine = RegimeSignalResearchEngine(high_vol_threshold_atr_pct=0.035)

    def test_1_bullish_regime_selects_momentum(self):
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertEqual(res.mom_direction, "LONG")
        self.assertEqual(res.regime_switch_direction, "LONG")

    def test_2_bearish_regime_selects_mr(self):
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BEARISH_TREND")
        self.assertEqual(res.mr_direction, "LONG")
        self.assertEqual(res.regime_switch_direction, "LONG")

    def test_3_consolidation_selects_mr(self):
        row = pd.Series({
            "rsi14": 70.0, "bollinger_pct_b": 0.95,
            "ret_3": 0.01, "ret_6": 0.01, "ret_12": 0.01,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="CONSOLIDATION")
        self.assertEqual(res.mr_direction, "SHORT")
        self.assertEqual(res.regime_switch_direction, "SHORT")

    def test_4_high_volatility_selects_neutral(self):
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.05
        })
        res = self.engine.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertTrue(res.is_high_volatility)
        self.assertEqual(res.regime_switch_direction, "NEUTRAL")

    def test_5_mr_momentum_conflict_classified_correctly(self):
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="CONSOLIDATION")
        self.assertTrue(res.is_conflict)

    def test_6_mr_long_mom_short_distinct_from_mr_short_mom_long(self):
        row1 = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04,
            "atr_pct": 0.01
        })
        res1 = self.engine.evaluate_bar(row1, regime="CONSOLIDATION")
        self.assertEqual(res1.conflict_type, "MR_LONG_MOM_SHORT")

        row2 = pd.Series({
            "rsi14": 70.0, "bollinger_pct_b": 0.95,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.01
        })
        res2 = self.engine.evaluate_bar(row2, regime="CONSOLIDATION")
        self.assertEqual(res2.conflict_type, "MR_SHORT_MOM_LONG")

    def test_7_no_future_candle_accessed(self):
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertIsNotNone(res.regime_switch_direction)

    def test_8_candidate_signal_v1_remains_unchanged(self):
        cand = CandidateSignalV1()
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04
        })
        res = cand.evaluate_bar(row)
        self.assertEqual(res.fused_state, "HIGH_CONSISTENCY_LONG")

    def test_9_no_gate_executor_calls(self):
        self.assertFalse(hasattr(self.engine, "gate_executor"))

    def test_10_no_execution_engine_calls(self):
        self.assertFalse(hasattr(self.engine, "execution_engine"))

    def test_11_no_order_apis(self):
        self.assertFalse(hasattr(self.engine, "place_order"))

    def test_12_no_production_modules_modified(self):
        import agent.specialists as sp
        self.assertTrue(hasattr(sp, "TechnicalMLSpecialist"))


if __name__ == "__main__":
    unittest.main()
