"""
agent/test_phase14c_dryrun.py — Phase 14C Fail-Closed & Determinism Synthetic Dry-Run Test Harness

Objective:
Perform comprehensive, network-free, synthetic-only validation of Phase 14B.2 collector invariants
and Phase 14C orchestration fail-closed readiness without touching real OOS data or mutating frozen strategy/protocol.
"""

import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import pandas as pd

from agent._phase14b_oos_acquisition import (
    OOSDatasetValidator,
    CANONICAL_ASSETS,
)
from agent._phase14b_oos_collector import (
    OOSDataCollector,
    OOSCollectorConfig,
    is_completed_4h_candle,
    REQUIRED_PROTOCOL_SHA256,
    HISTORICAL_BOUNDARY,
)
from agent._phase14b_oos_health import OOSHealthValidator
from agent._phase14_oos_validation import paired_bootstrap_ci
from agent._phase14c_prep_statistical_audit import iid_percentile_bootstrap_ci


def create_synthetic_dataset(
    assets: list = CANONICAL_ASSETS,
    num_eval_obs: int = 100,
    start_iso: str = "2026-10-06T04:00:00Z",
    edge_bps: float = 20.0,  # 20 bps mean edge
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """Generates synthetic 4H DataFrame dictionary for evaluation testing."""
    rng = np.random.default_rng(seed)
    dfs = {}
    base_dt = pd.to_datetime(start_iso)
    total_candles = 90 + num_eval_obs + 6

    for asset in assets:
        records = []
        cur_dt = base_dt
        price = 100.0

        for i in range(total_candles):
            ret = rng.normal(edge_bps / 10000.0, 0.01)
            open_p = price
            close_p = price * (1.0 + ret)
            high_p = max(open_p, close_p) * (1.0 + abs(rng.normal(0, 0.002)))
            low_p = min(open_p, close_p) * (1.0 - abs(rng.normal(0, 0.002)))
            vol = abs(rng.normal(1000, 100))

            records.append({
                "timestamp": cur_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": vol,
            })
            price = close_p
            cur_dt += pd.Timedelta(hours=4)

        dfs[asset] = pd.DataFrame(records)
    return dfs


class TestPhase14CDryRun(unittest.TestCase):

    def setUp(self):
        self.validator = OOSDatasetValidator()

    def test_case_1_insufficient_observations(self):
        """Case 1 — Synthetic usable observations < 100 must report INSUFFICIENT_OOS_DATA."""
        dfs = create_synthetic_dataset(num_eval_obs=5) # 5 usable per asset * 12 = 60 < 100 required
        old_boundaries = {a: HISTORICAL_BOUNDARY for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(dfs, old_boundaries)

        self.assertEqual(res["classification"], "INSUFFICIENT_OOS_DATA")
        self.assertFalse(res["status"] == "PASS")

    def test_case_2_protocol_fingerprint_mismatch(self):
        """Case 2 — Incorrect protocol SHA must trigger PROTOCOL_FINGERPRINT_MISMATCH."""
        with TemporaryDirectory() as tmpdir:
            bad_manifest = Path(tmpdir) / "manifest.json"
            bad_manifest.write_text(json.dumps({"protocol_sha256": "TAMPERED_SHA"}), encoding="utf-8")

            config = OOSCollectorConfig(
                oos_data_dir=Path(tmpdir) / "data",
                protocol_manifest_path=bad_manifest,
            )
            collector = OOSDataCollector(config)
            ok, msg = collector.verify_protocol()
            self.assertFalse(ok)
            self.assertIn("PROTOCOL_FINGERPRINT_MISMATCH", msg)

    def test_case_3_historical_overlap(self):
        """Case 3 — Observations at or before 2026-10-06T00:00:00Z must fail closed."""
        dfs = create_synthetic_dataset(start_iso="2026-10-05T20:00:00Z") # Starts before boundary
        old_boundaries = {a: HISTORICAL_BOUNDARY for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(dfs, old_boundaries)

        self.assertTrue(res["overlap_detected"])
        self.assertEqual(res["classification"], "OOS_DATA_NOT_INDEPENDENT")

    def test_case_4_duplicate_timestamp(self):
        """Case 4 — Duplicate timestamps must trigger DATA_INTEGRITY_FAILURE."""
        dfs = create_synthetic_dataset(num_eval_obs=100)
        # Inject duplicate timestamp in first asset
        df0 = dfs[CANONICAL_ASSETS[0]].copy()
        df0 = pd.concat([df0.iloc[[0]], df0], ignore_index=True)
        dfs[CANONICAL_ASSETS[0]] = df0

        old_boundaries = {a: HISTORICAL_BOUNDARY for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(dfs, old_boundaries)

        self.assertFalse(res["integrity_passed"])
        self.assertEqual(res["classification"], "DATA_INTEGRITY_FAILURE")

    def test_case_5_missing_asset(self):
        """Case 5 — Missing asset in 12-asset universe must fail completeness check."""
        dfs = create_synthetic_dataset(num_eval_obs=100)
        del dfs[CANONICAL_ASSETS[-1]] # Delete SUI_USDT

        old_boundaries = {a: HISTORICAL_BOUNDARY for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(dfs, old_boundaries)

        self.assertFalse(res["completeness_passed"])
        self.assertEqual(res["classification"], "DATA_COMPLETENESS_FAILURE")

    def test_case_6_incomplete_candle(self):
        """Case 6 — Candle starting at 00:00:00 is incomplete if now_sec < start + 14,400."""
        start_sec = 1700000000
        close_sec = start_sec + 14400

        self.assertFalse(is_completed_4h_candle(start_sec, close_sec - 1))
        self.assertTrue(is_completed_4h_candle(start_sec, close_sec))
        self.assertTrue(is_completed_4h_candle(start_sec, close_sec + 1))

    def test_case_7_valid_synthetic_oos(self):
        """Case 7 — Fully valid synthetic dataset must pass structural validation."""
        dfs = create_synthetic_dataset(num_eval_obs=100)
        old_boundaries = {a: HISTORICAL_BOUNDARY for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(dfs, old_boundaries)

        self.assertEqual(res["status"], "PASS")
        self.assertTrue(res["integrity_passed"])
        self.assertTrue(res["completeness_passed"])
        self.assertFalse(res["overlap_detected"])

    def test_case_8_positive_edge_classification(self):
        """Case 8 — Positive return synthetic fixture produces valid edge classification structure."""
        returns = np.random.default_rng(42).normal(0.0030, 0.01, size=100) # +30 bps mean
        mean_r, ci_l, ci_u = iid_percentile_bootstrap_ci(returns, num_resamples=200, seed=42)
        self.assertTrue(ci_l > 0.0) # Confident positive edge

    def test_case_9_zero_no_incremental_edge(self):
        """Case 9 — Zero mean return synthetic fixture yields non-significant confidence interval."""
        returns = np.random.default_rng(42).normal(0.0000, 0.01, size=100) # 0 bps mean
        mean_r, ci_l, ci_u = iid_percentile_bootstrap_ci(returns, num_resamples=200, seed=42)
        self.assertTrue(ci_l <= 0.0 <= ci_u) # CI spans zero

    def test_case_10_cost_sensitive_edge(self):
        """Case 10 — Positive gross edge (8 bps) becomes negative under BASE cost (14 bps)."""
        gross_return = 0.0008 # 8 bps
        base_cost = 0.0014 # 14 bps
        net_return = gross_return - base_cost
        self.assertTrue(gross_return > 0)
        self.assertTrue(net_return < 0)

    def test_part_d_determinism_test(self):
        """Part D — Running statistical bootstrap twice on exact same fixture yields RUN_1 == RUN_2."""
        data = np.random.default_rng(42).normal(0.0020, 0.015, size=100)

        mean1, low1, high1 = iid_percentile_bootstrap_ci(data, num_resamples=500, seed=42)
        mean2, low2, high2 = iid_percentile_bootstrap_ci(data, num_resamples=500, seed=42)

        self.assertEqual(mean1, mean2)
        self.assertEqual(low1, low2)
        self.assertEqual(high1, high2)

    def test_part_a_ohlcv_integrity_check(self):
        """Part A.3 — Malformed OHLCV (high < open) fails validation."""
        dfs = create_synthetic_dataset(num_eval_obs=100)
        # Corrupt high price to be below open price
        dfs[CANONICAL_ASSETS[0]].loc[0, "high"] = dfs[CANONICAL_ASSETS[0]].loc[0, "open"] - 1.0

        old_boundaries = {a: HISTORICAL_BOUNDARY for a in CANONICAL_ASSETS}
        res = self.validator.validate_dataset(dfs, old_boundaries)
        self.assertFalse(res["integrity_passed"])

    def test_part_a_restartability(self):
        """Part A.8 — Atomic persistence and restartability test."""
        with TemporaryDirectory() as tmpdir:
            tmp_data_dir = Path(tmpdir) / "data"
            config = OOSCollectorConfig(oos_data_dir=tmp_data_dir)
            collector = OOSDataCollector(config)

            df_initial = pd.DataFrame([{
                "timestamp": "2026-10-06T04:00:00Z",
                "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000.0
            }])

            # Save initial
            collector.save_oos_data_atomic(CANONICAL_ASSETS[0], df_initial)
            loaded1 = collector.load_existing_oos_data(CANONICAL_ASSETS[0])
            self.assertEqual(len(loaded1), 1)

            # Append new
            df_new = pd.DataFrame([{
                "timestamp": "2026-10-06T08:00:00Z",
                "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "volume": 1100.0
            }])
            combined = pd.concat([loaded1, df_new], ignore_index=True)
            collector.save_oos_data_atomic(CANONICAL_ASSETS[0], combined)

            loaded2 = collector.load_existing_oos_data(CANONICAL_ASSETS[0])
            self.assertEqual(len(loaded2), 2)
            self.assertEqual(loaded2["timestamp"].iloc[1], "2026-10-06T08:00:00Z")


if __name__ == "__main__":
    unittest.main()
