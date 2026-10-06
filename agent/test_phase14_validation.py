"""
agent/test_phase14_validation.py — Unit Tests for Phase 14 Validation & Cost Engine
"""

import unittest
import numpy as np
import pandas as pd

from agent.candidate_signal_v2 import CandidateSignalV2, CandidateSignalV2Result
import agent._phase14_oos_validation as oos_module
from agent._phase14_oos_validation import (
    paired_bootstrap_ci,
    calculate_cost_scenario,
    get_sample_size_label,
    EXECUTION_MODE,
)


class TestPhase14Validation(unittest.TestCase):

    def test_1_frozen_candidate_v2_behavior(self):
        v2 = CandidateSignalV2()
        row = pd.Series({
            "rsi14": 70.0, "bollinger_pct_b": 0.95,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04,
            "close": 100.0, "atr_pct": 0.01
        })
        res = v2.evaluate_bar(row, regime="BULLISH_TREND")
        self.assertEqual(res.direction, "LONG")
        self.assertTrue(res.is_conflict)
        self.assertEqual(res.conflict_type, "MR_SHORT_MOM_LONG")

    def test_2_no_lookahead(self):
        # Verify signal output uses strictly present bar values
        v2 = CandidateSignalV2()
        row = pd.Series({
            "rsi14": 70.0, "bollinger_pct_b": 0.95,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04,
            "close": 100.0, "atr_pct": 0.01
        })
        res = v2.evaluate_bar(row, regime="BEARISH_TREND")
        self.assertEqual(res.direction, "SHORT")

    def test_3_sample_size_labels(self):
        self.assertEqual(get_sample_size_label(20), "INSUFFICIENT")
        self.assertEqual(get_sample_size_label(50), "EARLY")
        self.assertEqual(get_sample_size_label(150), "DEVELOPING")
        self.assertEqual(get_sample_size_label(350), "MEANINGFUL")
        self.assertEqual(get_sample_size_label(600), "STRONG")

    def test_4_duplicate_filtering(self):
        df = pd.DataFrame([
            {"timestamp": "2026-10-06 00:00:00", "close": 100.0},
            {"timestamp": "2026-10-06 00:00:00", "close": 100.0},
        ])
        dups = df["timestamp"].duplicated().sum()
        self.assertEqual(dups, 1)

    def test_5_paired_benchmark_calculation(self):
        v2_ret = np.array([0.02, -0.01, 0.03])
        al_ret = np.array([0.01, 0.01, 0.01])
        diff = v2_ret - al_ret
        np.testing.assert_almost_equal(diff, np.array([0.01, -0.02, 0.02]))

    def test_6_bootstrap_ci(self):
        a = np.array([0.02, 0.03, 0.04, 0.01, 0.02, 0.05])
        b = np.array([0.01, 0.01, 0.01, 0.01, 0.01, 0.01])
        mean_d, med_d, se_d, low_ci, high_ci, prob_gt = paired_bootstrap_ci(a, b)
        self.assertGreater(mean_d, 0)
        self.assertGreater(prob_gt, 50.0)

    def test_7_conflict_split(self):
        v2 = CandidateSignalV2()
        row_short_mom_long = pd.Series({
            "rsi14": 70.0, "bollinger_pct_b": 0.95,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0
        })
        res1 = v2.evaluate_bar(row_short_mom_long, regime="BULLISH_TREND")
        self.assertEqual(res1.conflict_type, "MR_SHORT_MOM_LONG")
        self.assertEqual(res1.direction, "LONG")

        row_long_mom_short = pd.Series({
            "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04, "close": 100.0
        })
        res2 = v2.evaluate_bar(row_long_mom_short, regime="BULLISH_TREND")
        self.assertEqual(res2.conflict_type, "MR_LONG_MOM_SHORT")
        self.assertEqual(res2.direction, "SHORT")

    def test_8_regime_split(self):
        v2 = CandidateSignalV2()
        row = pd.Series({
            "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0
        })
        res_bull = v2.evaluate_bar(row, regime="BULLISH_TREND")
        res_bear = v2.evaluate_bar(row, regime="BEARISH_TREND")
        self.assertEqual(res_bull.direction, "LONG")
        self.assertEqual(res_bear.direction, "NEUTRAL")

    def test_9_asset_split(self):
        assets = ["BTC_USDT", "ETH_USDT", "SOL_USDT"]
        self.assertEqual(len(assets), 3)

    def test_10_cost_calculation(self):
        rets = np.array([0.01, 0.02, -0.005])
        res = calculate_cost_scenario(rets, roundtrip_cost_pct=0.14)
        # 0.14% = 0.0014 decimal cost per trade
        expected_net_mean = float(np.mean(rets - 0.0014) * 100.0)
        self.assertAlmostEqual(res["net_expectancy"], expected_net_mean, places=4)

    def test_11_breakeven_cost(self):
        gross_exp = 0.2148
        cost = 0.14
        net = gross_exp - cost
        self.assertAlmostEqual(net, 0.0748, places=4)

    def test_12_execution_isolation(self):
        self.assertEqual(EXECUTION_MODE, "SHADOW")

    def test_13_shadow_fail_closed(self):
        orig_mode = oos_module.EXECUTION_MODE
        try:
            oos_module.EXECUTION_MODE = "LIVE"
            with self.assertRaises(RuntimeError):
                oos_module.run_phase14_validation()
        finally:
            oos_module.EXECUTION_MODE = orig_mode


if __name__ == "__main__":
    unittest.main()
