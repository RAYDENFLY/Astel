"""
agent/test_phase14c_prep_statistical_audit_review.py — Unit Tests for Phase 14C-Prep.1 Power Analysis & Mathematical Review Engine
"""

import math
import unittest
import numpy as np

def calculate_analytical_power_z(
    delta: float, sigma: float, n_obs: int, alpha: float = 0.05
) -> float:
    """
    Calculates exact two-sided Z-test statistical power for detecting mean difference delta
    given standard deviation sigma and sample size n_obs at significance level alpha (default 0.05).
    """
    if sigma <= 0 or n_obs <= 0:
        return 0.0
    se = sigma / math.sqrt(n_obs)
    delta_z = delta / se
    z_critical = 1.959963984540054 # norm.ppf(0.975)

    # Power = P(Z > z_crit - delta_z) + P(Z < -z_crit - delta_z)
    power_upper = 1.0 - 0.5 * (1.0 + math.erf((z_critical - delta_z) / math.sqrt(2.0)))
    power_lower = 0.5 * (1.0 + math.erf((-z_critical - delta_z) / math.sqrt(2.0)))
    return float(power_upper + power_lower)


class TestPhase14CPrepStatisticalAuditReview(unittest.TestCase):

    def test_1_recalculate_power_delta_0002_n100(self):
        sigma = 0.02
        delta = 0.0020
        n_obs = 100
        se = sigma / math.sqrt(n_obs)
        self.assertAlmostEqual(se, 0.0020, places=6)

        delta_z = delta / se
        self.assertAlmostEqual(delta_z, 1.00, places=4)

        power = calculate_analytical_power_z(delta, sigma, n_obs)
        # Power for delta_z = 1.00 is ~17.00%, NOT 88.5%!
        self.assertAlmostEqual(power, 0.1700, delta=0.005)
        self.assertNotAlmostEqual(power, 0.885, delta=0.10)

    def test_2_recalculate_power_full_table(self):
        sigma = 0.02
        deltas = [0.0002, 0.0005, 0.0010, 0.0020]

        power_n100 = [calculate_analytical_power_z(d, sigma, 100) for d in deltas]
        power_n196 = [calculate_analytical_power_z(d, sigma, 196) for d in deltas]

        # Verify N=100 power values
        self.assertAlmostEqual(power_n100[0], 0.0511, delta=0.002) # 0.02% -> ~5.1%
        self.assertAlmostEqual(power_n100[1], 0.0571, delta=0.002) # 0.05% -> ~5.7%
        self.assertAlmostEqual(power_n100[2], 0.0790, delta=0.002) # 0.10% -> ~7.9%
        self.assertAlmostEqual(power_n100[3], 0.1700, delta=0.005) # 0.20% -> ~17.0%

        # Verify N=196 power values
        self.assertAlmostEqual(power_n196[0], 0.0522, delta=0.002) # 0.02% -> ~5.2%
        self.assertAlmostEqual(power_n196[1], 0.0642, delta=0.002) # 0.05% -> ~6.4%
        self.assertAlmostEqual(power_n196[2], 0.1097, delta=0.005) # 0.10% -> ~11.0%
        self.assertAlmostEqual(power_n196[3], 0.2871, delta=0.005) # 0.20% -> ~28.7%

    def test_3_required_effect_size_for_80_percent_power(self):
        sigma = 0.02
        # For 80% power at N=100 (SE=0.0020), non-centrality z_delta = 1.96 + 0.8416 = 2.8016
        # delta = 2.8016 * 0.0020 = 0.005603 (56 bps!)
        required_delta_n100 = 2.8016 * (sigma / math.sqrt(100))
        power = calculate_analytical_power_z(required_delta_n100, sigma, 100)
        self.assertAlmostEqual(power, 0.800, delta=0.01)
        self.assertAlmostEqual(required_delta_n100, 0.005603, delta=0.0005)

    def test_4_n_eff_formula_verification(self):
        n_nominal = 100
        rhos = [0.00, 0.15, 0.30, 0.33, 0.35, 0.45]
        neffs = [n_nominal * (1 - r) / (1 + r) for r in rhos]

        self.assertAlmostEqual(neffs[0], 100.0, places=4)
        self.assertAlmostEqual(neffs[1], 73.9130, places=3)
        self.assertAlmostEqual(neffs[2], 53.8461, places=3)
        self.assertAlmostEqual(neffs[3], 50.3759, places=3)
        self.assertAlmostEqual(neffs[4], 48.1481, places=3)
        self.assertAlmostEqual(neffs[5], 37.9310, places=3)

    def test_5_raw_candles_vs_eval_n_distinction(self):
        warmup = 90
        eval_n = 100
        horizon = 6
        total_candles = warmup + eval_n + horizon
        self.assertEqual(total_candles, 196)
        self.assertNotEqual(eval_n, total_candles)


if __name__ == "__main__":
    unittest.main()
