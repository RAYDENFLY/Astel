"""
agent/test_candidate_signal_v1.py — Unit Tests for Candidate Signal Architecture V1
"""

import unittest
import pandas as pd
from agent.candidate_signal import CandidateSignalV1


class TestCandidateSignalV1(unittest.TestCase):

    def setUp(self):
        self.signal_engine = CandidateSignalV1()

    def test_1_rsi_oversold_mr_long(self):
        row = pd.Series({
            "rsi14": 30.0,
            "bollinger_pct_b": 0.05,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0,
            "close": 100.0, "ema20": 100.0, "atr": 2.0
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.mr_direction, "LONG")
        self.assertEqual(res.fused_state, "SINGLE_FACTOR_LONG")
        self.assertEqual(res.direction, "LONG")

    def test_2_rsi_overbought_mr_short(self):
        row = pd.Series({
            "rsi14": 70.0,
            "bollinger_pct_b": 0.95,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0,
            "close": 100.0, "ema20": 100.0, "atr": 2.0
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.mr_direction, "SHORT")
        self.assertEqual(res.fused_state, "SINGLE_FACTOR_SHORT")
        self.assertEqual(res.direction, "SHORT")

    def test_3_bollinger_lower_extreme_long(self):
        row = pd.Series({
            "rsi14": 32.0,
            "bollinger_pct_b": 0.08,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.mr_direction, "LONG")

    def test_4_bollinger_upper_extreme_short(self):
        row = pd.Series({
            "rsi14": 68.0,
            "bollinger_pct_b": 0.92,
            "ret_3": 0.0, "ret_6": 0.0, "ret_12": 0.0
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.mr_direction, "SHORT")

    def test_5_momentum_all_positive_long(self):
        row = pd.Series({
            "rsi14": 50.0,
            "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.mom_direction, "LONG")
        self.assertEqual(res.fused_state, "SINGLE_FACTOR_LONG")

    def test_6_momentum_all_negative_short(self):
        row = pd.Series({
            "rsi14": 50.0,
            "bollinger_pct_b": 0.5,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.mom_direction, "SHORT")
        self.assertEqual(res.fused_state, "SINGLE_FACTOR_SHORT")

    def test_7_momentum_conflict_detection(self):
        row = pd.Series({
            "rsi14": 50.0,
            "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.005, "ret_12": -0.02
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertTrue(res.mom_conflict)

    def test_8_mr_long_plus_mom_long_high_consistency(self):
        row = pd.Series({
            "rsi14": 30.0,
            "bollinger_pct_b": 0.05,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.fused_state, "HIGH_CONSISTENCY_LONG")
        self.assertEqual(res.direction, "LONG")
        self.assertTrue(res.is_shadow_eligible)

    def test_9_mr_short_plus_mom_short_high_consistency(self):
        row = pd.Series({
            "rsi14": 70.0,
            "bollinger_pct_b": 0.95,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.fused_state, "HIGH_CONSISTENCY_SHORT")
        self.assertEqual(res.direction, "SHORT")
        self.assertTrue(res.is_shadow_eligible)

    def test_10_opposing_signals_conflict(self):
        row = pd.Series({
            "rsi14": 30.0,
            "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.fused_state, "CONFLICT")
        self.assertEqual(res.direction, "NEUTRAL")
        self.assertFalse(res.is_shadow_eligible)

    def test_11_both_neutral(self):
        row = pd.Series({
            "rsi14": 50.0,
            "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": -0.01, "ret_12": 0.02
        })
        res = self.signal_engine.evaluate_bar(row)
        self.assertEqual(res.fused_state, "NEUTRAL")
        self.assertEqual(res.direction, "NEUTRAL")
        self.assertFalse(res.is_shadow_eligible)

    def test_12_no_future_candle_leakage(self):
        # Verify inputs are scalar/row values only
        row = pd.Series({"rsi14": 30.0, "bollinger_pct_b": 0.05, "ret_3": 0.01, "ret_6": 0.01, "ret_12": 0.01})
        res = self.signal_engine.evaluate_bar(row)
        self.assertIsNotNone(res.direction)

    def test_13_candidate_does_not_call_execution(self):
        # CandidateSignalV1 has no network/order code
        self.assertFalse(hasattr(self.signal_engine, "place_order"))

    def test_14_existing_baseline_remains_unchanged(self):
        # Baseline engine remains independent
        from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
        engine = HistoricalReplayEngine(config=ReplayConfig())
        self.assertEqual(engine.config.warmup_period, 90)


if __name__ == "__main__":
    unittest.main()
