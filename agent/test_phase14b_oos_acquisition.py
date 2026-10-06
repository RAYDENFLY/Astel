"""
agent/test_phase14b_oos_acquisition.py — Unit Tests for Phase 14B OOS Dataset Acquisition & Freeze Engine
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
import numpy as np

from agent._phase14b_oos_acquisition import (
    OOSAcquisitionConfig,
    OOSDatasetValidator,
    compute_file_sha256,
    compute_manifest_fingerprint,
    verify_frozen_dataset_integrity,
    CANONICAL_ASSETS,
)


def create_synthetic_df(start_ts: str, n_candles: int = 200, freq_hours: int = 4) -> pd.DataFrame:
    timestamps = pd.date_range(start=start_ts, periods=n_candles, freq=f"{freq_hours}h")
    data = []
    price = 100.0
    for ts in timestamps:
        o = price
        h = price + 2.0
        l = price - 1.0
        c = price + 1.0
        v = 1000.0
        data.append({
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": o, "high": h, "low": l, "close": c, "volume": v
        })
        price = c
    return pd.DataFrame(data)


class TestPhase14BOOSAcquisition(unittest.TestCase):

    def setUp(self):
        self.config = OOSAcquisitionConfig(min_required_oos_candles=10)
        self.validator = OOSDatasetValidator(self.config)

    def test_1_valid_dataset_passes(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        new_dfs = {a: create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["classification"], "READY_FOR_PHASE_14C")
        self.assertFalse(res["overlap_detected"])

    def test_2_overlapping_timestamps_fail(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        # Starts at 2026-10-05 (before 2026-10-06 boundary)
        new_dfs = {a: create_synthetic_df("2026-10-05T00:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "OOS_DATA_NOT_INDEPENDENT")
        self.assertTrue(res["overlap_detected"])

    def test_3_duplicate_timestamps_fail(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df = create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150)
        # Duplicate line 0
        df = pd.concat([df.iloc[[0]], df], ignore_index=True)
        new_dfs = {a: df if a == "BTC_USDT" else create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "DATA_INTEGRITY_FAILURE")

    def test_4_non_monotonic_timestamps_fail(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df = create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150)
        # Swap rows
        df.iloc[5], df.iloc[6] = df.iloc[6].copy(), df.iloc[5].copy()
        new_dfs = {a: df if a == "BTC_USDT" else create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "DATA_INTEGRITY_FAILURE")

    def test_5_ohlc_invalidity_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df = create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150)
        # Invalid high < low
        df.at[5, "high"] = 10.0
        df.at[5, "low"] = 100.0
        new_dfs = {a: df if a == "BTC_USDT" else create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "DATA_INTEGRITY_FAILURE")

    def test_6_nan_inf_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df = create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150)
        df.at[3, "close"] = np.nan
        new_dfs = {a: df if a == "BTC_USDT" else create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "DATA_INTEGRITY_FAILURE")

    def test_7_negative_volume_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df = create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150)
        df.at[2, "volume"] = -100.0
        new_dfs = {a: df if a == "BTC_USDT" else create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "DATA_INTEGRITY_FAILURE")

    def test_8_unexpected_4h_gap_is_detected(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df1 = create_synthetic_df("2026-10-06T04:00:00Z", n_candles=50)
        df2 = create_synthetic_df("2026-10-20T04:00:00Z", n_candles=50) # 14 day gap
        df_gap = pd.concat([df1, df2], ignore_index=True)
        new_dfs = {a: df_gap if a == "BTC_USDT" else create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertGreater(res["asset_reports"]["BTC_USDT"]["gap_count"], 0)

    def test_9_insufficient_warmup_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        # Only 50 candles (less than 90 warmup + 6 horizon + min required)
        new_dfs = {a: create_synthetic_df("2026-10-06T04:00:00Z", n_candles=50) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "INSUFFICIENT_OOS_DATA")

    def test_10_insufficient_future_horizon_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        # Exactly 96 candles (90 warmup + 6 horizon = 0 usable evaluation observations)
        new_dfs = {a: create_synthetic_df("2026-10-06T04:00:00Z", n_candles=96) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["usable_oos_observations"], 0)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "INSUFFICIENT_OOS_DATA")

    def test_11_missing_canonical_asset_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        # Missing SUI_USDT
        new_dfs = {a: create_synthetic_df("2026-10-06T04:00:00Z", n_candles=150) for a in CANONICAL_ASSETS if a != "SUI_USDT"}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["classification"], "DATA_COMPLETENESS_FAILURE")

    def test_12_changed_dataset_hash_fails(self):
        with TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.csv"
            p.write_text("timestamp,close\n2026-10-06T04:00:00Z,100.0\n", encoding="utf-8")
            h1 = compute_file_sha256(p)
            p.write_text("timestamp,close\n2026-10-06T04:00:00Z,105.0\n", encoding="utf-8")
            h2 = compute_file_sha256(p)
            self.assertNotEqual(h1, h2)

    def test_13_changed_manifest_fails(self):
        h_dict = {"BTC_USDT": "abc"}
        f1 = compute_manifest_fingerprint(h_dict, "meta1")
        f2 = compute_manifest_fingerprint(h_dict, "meta2")
        self.assertNotEqual(f1, f2)

    def test_14_modified_timestamp_boundary_fails(self):
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        df_old_ts = create_synthetic_df("2026-10-06T00:00:00Z", n_candles=150) # exact boundary match fails
        new_dfs = {a: df_old_ts for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(new_dfs, old_boundaries)
        self.assertTrue(res["overlap_detected"])

    def test_15_frozen_dataset_verification_succeeds(self):
        with TemporaryDirectory() as tmpdir:
            manifest_file = Path(tmpdir) / "manifest.json"
            manifest_file.write_text(json.dumps({"asset_hashes": {}}), encoding="utf-8")
            self.assertTrue(verify_frozen_dataset_integrity(manifest_file))

    def test_16_old_phase14_dataset_cannot_be_reused(self):
        # Verification that providing old dataset boundaries triggers independence failure
        old_boundaries = {a: "2026-10-06T00:00:00Z" for a in CANONICAL_ASSETS}
        old_dfs = {a: create_synthetic_df("2026-04-22T12:00:00Z", n_candles=1000) for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(old_dfs, old_boundaries)
        self.assertEqual(res["classification"], "OOS_DATA_NOT_INDEPENDENT")


if __name__ == "__main__":
    unittest.main()
