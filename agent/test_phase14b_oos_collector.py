"""
agent/test_phase14b_oos_collector.py — Unit Tests for Phase 14B.2 Continuous OOS Data Collector Engine
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
import numpy as np

from agent._phase14b_oos_collector import (
    OOSCollectorConfig,
    OOSDataCollector,
    is_completed_4h_candle,
    REQUIRED_PROTOCOL_SHA256,
    HISTORICAL_BOUNDARY,
)
from agent._phase14b_oos_acquisition import CANONICAL_ASSETS


class MockFetcher:
    def __init__(self, raw_data_map=None):
        self.raw_data_map = raw_data_map or {}

    def fetch_candlesticks(self, asset: str, interval: str = "4h", limit: int = 100):
        return self.raw_data_map.get(asset, [])


def create_mock_candle_json(t_sec: int, price: float = 100.0) -> dict:
    return {
        "t": t_sec,
        "o": str(price),
        "h": str(price + 2.0),
        "l": str(price - 1.0),
        "c": str(price + 1.0),
        "v": 1000,
    }


class TestPhase14BOOSCollector(unittest.TestCase):

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmppath = Path(self.tmpdir.name)

        self.protocol_file = self.tmppath / "phase14b1_oos_protocol_manifest.json"
        self.protocol_file.write_text(
            json.dumps({"protocol_sha256": REQUIRED_PROTOCOL_SHA256}), encoding="utf-8"
        )

        self.collector_manifest_file = self.tmppath / "phase14b_oos_collector_manifest.json"
        self.oos_data_dir = self.tmppath / "oos_data"

        self.config = OOSCollectorConfig(
            protocol_manifest_path=self.protocol_file,
            collector_manifest_path=self.collector_manifest_file,
            oos_data_dir=self.oos_data_dir,
            min_total_candles=10, # small threshold for testing readiness
            required_eval_observations=10,
        )
        self.collector = OOSDataCollector(self.config)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_1_is_completed_4h_candle(self):
        # Candle starts at t_sec = 100000. Closes at 114400.
        t_sec = 100000
        self.assertFalse(is_completed_4h_candle(t_sec, now_sec=110000))
        self.assertFalse(is_completed_4h_candle(t_sec, now_sec=114399))
        self.assertTrue(is_completed_4h_candle(t_sec, now_sec=114400))
        self.assertTrue(is_completed_4h_candle(t_sec, now_sec=120000))

    def test_2_incremental_acquisition(self):
        # Existing df has 1 candle at 2026-10-06T04:00:00Z (ts_sec = 1791259200)
        df_exist = pd.DataFrame([{
            "timestamp": "2026-10-06T04:00:00Z", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000
        }])
        # Next candle at 2026-10-06T08:00:00Z (ts_sec = 1791273600)
        c2 = create_mock_candle_json(1791273600, price=102.0)
        mock_fetcher = MockFetcher({"BTC_USDT": [c2]})

        now_sec = 1791273600 + 14400 + 10 # completed
        df_new, cnt, err = self.collector.fetch_and_append_incremental("BTC_USDT", df_exist, mock_fetcher, now_sec)

        self.assertEqual(cnt, 1)
        self.assertEqual(len(df_new), 2)
        self.assertEqual(df_new["timestamp"].iloc[-1], "2026-10-06T08:00:00Z")

    def test_3_restart_resume_behavior(self):
        # Save initial file
        df1 = pd.DataFrame([{
            "timestamp": "2026-10-06T04:00:00Z", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000
        }])
        self.collector.save_oos_data_atomic("BTC_USDT", df1)

        # Reload
        df_loaded = self.collector.load_existing_oos_data("BTC_USDT")
        self.assertEqual(len(df_loaded), 1)
        self.assertEqual(df_loaded["timestamp"].iloc[0], "2026-10-06T04:00:00Z")

    def test_4_duplicate_rejection(self):
        df_exist = pd.DataFrame([{
            "timestamp": "2026-10-06T04:00:00Z", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000
        }])
        # Mock fetcher returns same timestamp
        c1 = create_mock_candle_json(1791259200, price=100.0) # 2026-10-06T04:00:00Z
        mock_fetcher = MockFetcher({"BTC_USDT": [c1]})

        now_sec = 1791259200 + 20000
        df_new, cnt, err = self.collector.fetch_and_append_incremental("BTC_USDT", df_exist, mock_fetcher, now_sec)
        self.assertEqual(cnt, 0)
        self.assertEqual(len(df_new), 1)

    def test_5_overlap_rejection(self):
        df_exist = pd.DataFrame()
        # Candle before historical boundary (2026-10-05T00:00:00Z = ts 1791158400)
        c_old = create_mock_candle_json(1791158400)
        mock_fetcher = MockFetcher({"BTC_USDT": [c_old]})

        now_sec = 1791158400 + 20000
        df_new, cnt, err = self.collector.fetch_and_append_incremental("BTC_USDT", df_exist, mock_fetcher, now_sec)
        self.assertEqual(cnt, 0)
        self.assertTrue(df_new.empty)

    def test_6_incomplete_candle_rejection(self):
        df_exist = pd.DataFrame()
        # Candle starts at now_sec - 1000 (not closed yet)
        now_sec = 1791259200
        c_inc = create_mock_candle_json(now_sec - 1000)
        mock_fetcher = MockFetcher({"BTC_USDT": [c_inc]})

        df_new, cnt, err = self.collector.fetch_and_append_incremental("BTC_USDT", df_exist, mock_fetcher, now_sec)
        self.assertEqual(cnt, 0)

    def test_7_protocol_fingerprint_mismatch(self):
        # Write invalid protocol manifest SHA
        self.protocol_file.write_text(json.dumps({"protocol_sha256": "BAD_SHA"}), encoding="utf-8")
        ok, msg = self.collector.verify_protocol()
        self.assertFalse(ok)
        self.assertIn("PROTOCOL_FINGERPRINT_MISMATCH", msg)

    def test_8_atomic_persistence(self):
        df = pd.DataFrame([{
            "timestamp": "2026-10-06T04:00:00Z", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000
        }])
        self.collector.save_oos_data_atomic("BTC_USDT", df)
        target = self.oos_data_dir / "BTC_USDT_4H_oos.csv"
        self.assertTrue(target.exists())

    def test_9_network_failure_handling(self):
        # Fetcher returns empty list on network failure
        mock_fetcher = MockFetcher({"BTC_USDT": []})
        df_exist = pd.DataFrame([{
            "timestamp": "2026-10-06T04:00:00Z", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000
        }])
        df_new, cnt, err = self.collector.fetch_and_append_incremental("BTC_USDT", df_exist, mock_fetcher, 1791259200 + 20000)
        self.assertEqual(len(df_new), 1) # existing data preserved cleanly


if __name__ == "__main__":
    unittest.main()
