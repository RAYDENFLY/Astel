"""
agent/test_candidate_v2_shadow_engine.py — Unit Tests for Phase 13 Real-Time Shadow Engine
"""

import unittest
import os
import tempfile
import pandas as pd
import agent.candidate_v2_shadow_engine as shadow_module
from agent.candidate_v2_shadow_engine import CandidateV2ShadowEngine, EXECUTION_MODE


class TestCandidateV2ShadowEngine(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.persist_file = os.path.join(self.tmp_dir.name, "shadow_test.json")
        self.engine = CandidateV2ShadowEngine(persistence_path=self.persist_file)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_1_completed_candle_requirement(self):
        row = pd.Series({
            "timestamp": "2026-10-06 00:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="BTC_USDT", is_completed_candle=True)
        self.assertIsNotNone(rec)

    def test_2_incomplete_candle_rejection(self):
        row = pd.Series({
            "timestamp": "2026-10-06 00:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="BTC_USDT", is_completed_candle=False)
        self.assertIsNone(rec)

    def test_3_correct_candidate_v2_invocation(self):
        row = pd.Series({
            "timestamp": "2026-10-06 04:00:00", "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BEARISH_TREND", asset="BTC_USDT")
        self.assertEqual(rec.direction, "SHORT")
        self.assertTrue(rec.follow_momentum_used)

    def test_4_deterministic_signal_generation(self):
        row = pd.Series({
            "timestamp": "2026-10-06 08:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec1 = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="ETH_USDT")
        self.assertEqual(rec1.direction, "LONG")

    def test_5_duplicate_observation_prevention_idempotency(self):
        row = pd.Series({
            "timestamp": "2026-10-06 12:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec1 = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="SOL_USDT")
        rec2 = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="SOL_USDT")
        self.assertIsNotNone(rec1)
        self.assertIsNone(rec2)

    def test_6_t1_t3_t6_outcome_tracking(self):
        row = pd.Series({
            "timestamp": "2026-10-06 16:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="BNB_USDT")
        fut = pd.DataFrame([
            {"close": 101.0, "high": 102.0, "low": 99.0},
            {"close": 102.0, "high": 103.0, "low": 100.0},
            {"close": 103.0, "high": 104.0, "low": 101.0},
            {"close": 104.0, "high": 105.0, "low": 102.0},
            {"close": 105.0, "high": 106.0, "low": 103.0},
            {"close": 106.0, "high": 107.0, "low": 104.0},
        ])
        self.engine.update_outcomes(rec.shadow_trade_id, fut)
        self.assertTrue(rec.is_completed_t1)
        self.assertTrue(rec.is_completed_t3)
        self.assertTrue(rec.is_completed_t6)
        self.assertAlmostEqual(rec.ret_3_fwd, 0.03, places=4)

    def test_7_mfe_mae_tracking(self):
        row = pd.Series({
            "timestamp": "2026-10-06 20:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="XRP_USDT")
        fut = pd.DataFrame([
            {"close": 105.0, "high": 110.0, "low": 95.0},
        ])
        self.engine.update_outcomes(rec.shadow_trade_id, fut)
        self.assertAlmostEqual(rec.mfe, 0.10, places=4)
        self.assertAlmostEqual(rec.mae, -0.05, places=4)

    def test_8_conflict_classification(self):
        row = pd.Series({
            "timestamp": "2026-10-07 00:00:00", "rsi14": 30.0, "bollinger_pct_b": 0.05,
            "ret_3": -0.01, "ret_6": -0.02, "ret_12": -0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="AVAX_USDT")
        self.assertTrue(rec.is_conflict)
        self.assertEqual(rec.conflict_type, "MR_LONG_MOM_SHORT")

    def test_9_regime_classification(self):
        row = pd.Series({
            "timestamp": "2026-10-07 04:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="CONSOLIDATION", asset="LINK_USDT")
        self.assertEqual(rec.regime, "CONSOLIDATION")

    def test_10_missing_data_handling(self):
        row = pd.Series({
            "timestamp": "2026-10-07 08:00:00", "rsi14": None, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "close": 100.0
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="DOGE_USDT")
        self.assertIsNone(rec)

    def test_11_shadow_persistence(self):
        row = pd.Series({
            "timestamp": "2026-10-07 12:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="ADA_USDT")
        self.engine.save_records()
        self.assertTrue(os.path.exists(self.persist_file))

        engine2 = CandidateV2ShadowEngine(persistence_path=self.persist_file)
        self.assertIn(rec.shadow_trade_id, engine2.records)

    def test_12_execution_isolation(self):
        self.assertFalse(hasattr(self.engine, "place_order"))
        self.assertFalse(hasattr(self.engine, "execute_trade"))

    def test_13_fail_closed_execution_mode(self):
        original_mode = shadow_module.EXECUTION_MODE
        try:
            shadow_module.EXECUTION_MODE = "LIVE"
            with self.assertRaises(RuntimeError):
                CandidateV2ShadowEngine(persistence_path=self.persist_file)
        finally:
            shadow_module.EXECUTION_MODE = original_mode

    def test_14_historical_record_immutability(self):
        row = pd.Series({
            "timestamp": "2026-10-07 16:00:00", "rsi14": 50.0, "bollinger_pct_b": 0.5,
            "ret_3": 0.01, "ret_6": 0.02, "ret_12": 0.04, "close": 100.0, "atr_pct": 0.01
        })
        rec = self.engine.process_completed_candle(row, regime="BULLISH_TREND", asset="LTC_USDT")
        original_entry = rec.entry_price
        rec2 = self.engine.process_completed_candle(row, regime="BEARISH_TREND", asset="LTC_USDT")
        self.assertIsNone(rec2)
        self.assertEqual(self.engine.records[rec.shadow_trade_id].entry_price, original_entry)


if __name__ == "__main__":
    unittest.main()
