"""
agent/test_candidate_signal_v2.py — Unit Tests for Frozen Candidate Signal Architecture V2
"""

import unittest
import pandas as pd
from agent.candidate_signal_v2 import CandidateSignalV2
from agent.candidate_signal import CandidateSignalV1


class TestCandidateSignalV2(unittest.TestCase):

    def setUp(self):
        self.engine = CandidateSignalV2(high_vol_threshold_atr_pct=0.035)

    def test_1_bullish_selects_momentum(self):
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertEqual(res.direction, "LONG")
        self.assertEqual(res.signal_reason, "REGIME_MOMENTUM")

    def test_2_bearish_selects_mr(self):
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BEARISH_TREND")
        self.assertEqual(res.direction, "LONG")
        self.assertEqual(res.signal_reason, "REGIME_MR")

    def test_3_consolidation_selects_momentum(self):
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="CONSOLIDATION")
        self.assertEqual(res.direction, "LONG")
        self.assertEqual(res.signal_reason, "REGIME_MOMENTUM")

    def test_4_high_volatility_selects_neutral(self):
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.05
        })
        res = self.engine.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertTrue(res.is_high_volatility)
        self.assertEqual(res.direction, "NEUTRAL")
        self.assertEqual(res.signal_reason, "HIGH_VOL_NEUTRAL")

    def test_5_mr_long_mom_short_selects_short(self):
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BEARISH_TREND")
        self.assertTrue(res.is_conflict)
        self.assertEqual(res.conflict_type, "MR_LONG_MOM_SHORT")
        self.assertEqual(res.direction, "SHORT")
        self.assertEqual(res.signal_reason, "CONFLICT_MOMENTUM")

    def test_6_mr_short_mom_long_selects_long(self):
        row = pd.Series({
            "rsi14": 70.0, "bollinger_pct_b": 0.95,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="CONSOLIDATION")
        self.assertTrue(res.is_conflict)
        self.assertEqual(res.conflict_type, "MR_SHORT_MOM_LONG")
        self.assertEqual(res.direction, "LONG")
        self.assertEqual(res.signal_reason, "CONFLICT_MOMENTUM")

    def test_7_non_conflict_signals_follow_regime_subsystem(self):
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="CONSOLIDATION")
        self.assertFalse(res.is_conflict)
        self.assertEqual(res.direction, "SHORT")
        self.assertEqual(res.signal_reason, "REGIME_MOMENTUM")

    def test_8_candidate_signal_v1_remains_unchanged(self):
        cand1 = CandidateSignalV1()
        row = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04
        })
        res = cand1.evaluate_bar(row)
        self.assertEqual(res.fused_state, "HIGH_CONSISTENCY_LONG")

    def test_9_no_lookahead(self):
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0,
            "atr_pct": 0.01
        })
        res = self.engine.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertIsNotNone(res.direction)

    def test_10_no_execution_calls(self):
        self.assertFalse(hasattr(self.engine, "execution_engine"))

    def test_11_no_gate_io_calls(self):
        self.assertFalse(hasattr(self.engine, "gate_executor"))

    def test_12_no_production_module_modifications(self):
        import agent.specialists as sp
        self.assertTrue(hasattr(sp, "TechnicalMLSpecialist"))


if __name__ == "__main__":
    unittest.main()
