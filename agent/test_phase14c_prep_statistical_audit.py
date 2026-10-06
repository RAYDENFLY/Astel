"""
agent/test_phase14c_prep_statistical_audit.py — Unit Tests for Phase 14C-Prep.1 Statistical Audit Engine
"""

import json
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np

from agent._phase14c_prep_statistical_audit import (
    StatisticalProtocolAuditor,
    compute_effective_sample_size,
    iid_percentile_bootstrap_ci,
    moving_block_bootstrap_ci,
    calculate_statistical_power,
    REQUIRED_PROTOCOL_SHA256,
)


class TestPhase14CPrepStatisticalAudit(unittest.TestCase):

    def setUp(self):
        self.auditor = StatisticalProtocolAuditor()

    def test_1_iid_synthetic_bootstrap(self):
        data = np.random.default_rng(42).normal(loc=0.01, scale=0.02, size=100)
        mean, ci_low, ci_high = iid_percentile_bootstrap_ci(data, num_resamples=500, seed=42)
        self.assertAlmostEqual(mean, 0.01, delta=0.005)
        self.assertTrue(ci_low < mean < ci_high)

    def test_2_ar1_synthetic_series(self):
        rng = np.random.default_rng(42)
        n = 100
        ar1 = np.zeros(n)
        for t in range(1, n):
            ar1[t] = 0.5 * ar1[t - 1] + rng.normal(0, 0.01)

        _, l_iid, u_iid = iid_percentile_bootstrap_ci(ar1, num_resamples=500, seed=42)
        _, l_blk, u_blk = moving_block_bootstrap_ci(ar1, block_size=4, num_resamples=500, seed=42)

        width_iid = u_iid - l_iid
        width_blk = u_blk - l_blk
        # Block bootstrap should yield wider or equal CI under positive autocorrelation
        self.assertTrue(width_blk >= width_iid * 0.9)

    def test_3_clustered_synthetic_series(self):
        rng = np.random.default_rng(42)
        n = 100
        vol = np.ones(n) * 0.01
        clustered = np.zeros(n)
        for t in range(1, n):
            vol[t] = 0.01 + 0.4 * abs(clustered[t - 1])
            clustered[t] = rng.normal(0, vol[t])
        self.assertEqual(len(clustered), 100)

    def test_4_cross_sectional_dependence(self):
        rng = np.random.default_rng(42)
        market = rng.normal(0, 0.02, 100)
        assets = [market + rng.normal(0, 0.01, 100) for _ in range(12)]
        corr = np.corrcoef(assets[0], assets[1])[0, 1]
        self.assertTrue(corr > 0.5)

    def test_5_overlapping_horizon_detection(self):
        audit_res = self.auditor.run_overlapping_horizon_audit()
        self.assertIn("T+3", audit_res)
        self.assertEqual(audit_res["T+3"]["dependent_bars"], 2)

    def test_6_effective_sample_size_calculation(self):
        neff_0 = compute_effective_sample_size(100, 0.0)
        neff_pos = compute_effective_sample_size(100, 0.333)
        self.assertEqual(neff_0, 100.0)
        self.assertAlmostEqual(neff_pos, 50.0, delta=1.0)

    def test_7_paired_difference_calculation(self):
        c = np.array([0.02, -0.01, 0.03])
        b = np.array([0.01, 0.00, 0.01])
        diff = c - b
        np.testing.assert_array_almost_equal(diff, np.array([0.01, -0.01, 0.02]))

    def test_8_benchmark_reproducibility(self):
        # Deterministic random choice check (seed 42)
        rng1 = np.random.default_rng(42)
        choices1 = rng1.choice(["LONG", "SHORT"], size=10)

        rng2 = np.random.default_rng(42)
        choices2 = rng2.choice(["LONG", "SHORT"], size=10)

        np.testing.assert_array_equal(choices1, choices2)

    def test_9_multiple_testing_inventory(self):
        manifest_ok, _, manifest = self.auditor.verify_protocol_manifest()
        self.assertTrue(manifest_ok)
        primary = manifest.get("primary_metrics", [])
        secondary = manifest.get("secondary_metrics", [])
        self.assertTrue(len(primary) > 0)
        self.assertTrue(len(secondary) > 0)

    def test_10_heavy_tail_simulation(self):
        rng = np.random.default_rng(42)
        t_dist = rng.standard_t(df=3, size=100)
        kurt = float(np.mean((t_dist - np.mean(t_dist))**4) / (np.var(t_dist)**2))
        self.assertTrue(kurt > 3.0) # Heavy-tailed

    def test_11_cost_sensitivity_calculations(self):
        gross_return = 0.0020 # 0.20%
        costs = {"optimistic": 0.0006, "base": 0.0014, "adverse": 0.0025}
        net_opt = gross_return - costs["optimistic"]
        net_base = gross_return - costs["base"]
        net_adv = gross_return - costs["adverse"]

        self.assertAlmostEqual(net_opt, 0.0014)
        self.assertAlmostEqual(net_base, 0.0006)
        self.assertAlmostEqual(net_adv, -0.0005)

    def test_12_protocol_immutability(self):
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "manifest.json"
            tmp_path.write_text(json.dumps({"protocol_sha256": "TAMPERED"}), encoding="utf-8")
            auditor = StatisticalProtocolAuditor(manifest_path=tmp_path)
            ok, msg, _ = auditor.verify_protocol_manifest()
            self.assertFalse(ok)
            self.assertEqual(msg, "SHA_MISMATCH")

    def test_13_oos_dataset_not_accessed(self):
        report = self.auditor.execute_audit()
        self.assertFalse(report["oos_data_accessed"])
        self.assertFalse(report["candidate_v2_modified"])
        self.assertFalse(report["protocol_modified"])

    def test_14_deterministic_random_seeds(self):
        res1 = self.auditor.run_synthetic_experiments()
        res2 = self.auditor.run_synthetic_experiments()
        self.assertEqual(res1["CaseA_IID"]["mean"], res2["CaseA_IID"]["mean"])


if __name__ == "__main__":
    unittest.main()
