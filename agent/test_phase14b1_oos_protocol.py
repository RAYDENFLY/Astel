"""
agent/test_phase14b1_oos_protocol.py — Unit Tests for Phase 14B.1 OOS Protocol Immutability & SHA-256 Fingerprint Engine
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent._phase14b1_oos_protocol import (
    FROZEN_PROTOCOL_SPEC,
    HISTORICAL_BOUNDARY,
    CANONICAL_ASSETS,
    canonicalize_protocol_dict,
    compute_protocol_sha256,
    generate_and_save_protocol_manifest,
    verify_protocol_manifest,
)


class TestPhase14B1OOSProtocol(unittest.TestCase):

    def test_1_unchanged_protocol_passes(self):
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertTrue(is_valid)
            self.assertEqual(classification, "PROTOCOL_FROZEN")
            self.assertIn("protocol_sha256", details)

    def test_2_changed_historical_boundary_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["historical_boundary"] = "2026-11-01T00:00:00Z"
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)
            self.assertEqual(classification, "PROTOCOL_INTEGRITY_FAILURE")

    def test_3_changed_asset_list_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["assets"] = CANONICAL_ASSETS + ["DOGE2_USDT"]
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)
            self.assertEqual(classification, "PROTOCOL_INTEGRITY_FAILURE")

    def test_4_changed_timeframe_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["timeframe"] = "1H"
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)
            self.assertEqual(classification, "PROTOCOL_INTEGRITY_FAILURE")

    def test_5_changed_warmup_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["warmup_candles"] = 50
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)
            self.assertEqual(classification, "PROTOCOL_INTEGRITY_FAILURE")

    def test_6_changed_horizon_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["evaluation_horizons"] = ["T+1", "T+5"]
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_7_changed_benchmark_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["benchmark_definitions"] = {"always_long": "MODIFIED BENCHMARK"}
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_8_changed_outcome_definition_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["outcome_definitions"] = {"formula": "MODIFIED_FORMULA"}
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_9_changed_bootstrap_configuration_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["bootstrap_configuration"] = {"num_resamples": 500}
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_10_changed_confidence_interval_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["bootstrap_configuration"] = {"confidence_level": 99.0}
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_11_changed_cost_model_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["cost_model"] = {"base_roundtrip_pct": 0.0}
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_12_changed_decision_criteria_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["decision_criteria"] = {"STATISTICALLY_SUPPORTED_EDGE": "MODIFIED CRITERIA"}
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_13_changed_missing_data_policy_fails(self):
        spec = dict(FROZEN_PROTOCOL_SPEC)
        spec["missing_data_policy"] = "SILENTLY_INTERPOLATE"
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path, spec)
            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)

    def test_14_changed_protocol_fingerprint_fails(self):
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            generate_and_save_protocol_manifest(manifest_path)
            # Tamper with file SHA256 string directly
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            data["protocol_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
            manifest_path.write_text(json.dumps(data), encoding="utf-8")

            is_valid, classification, details = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)
            self.assertEqual(classification, "PROTOCOL_INTEGRITY_FAILURE")

    def test_15_deterministic_canonicalization_produces_identical_hash(self):
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        h1 = compute_protocol_sha256(d1)
        h2 = compute_protocol_sha256(d2)
        self.assertEqual(h1, h2)

    def test_16_reordered_json_keys_do_not_change_semantic_fingerprint(self):
        spec1 = {"z_key": 10, "a_key": 20, "sub": {"b": 2, "a": 1}}
        spec2 = {"a_key": 20, "z_key": 10, "sub": {"a": 1, "b": 2}}
        str1 = canonicalize_protocol_dict(spec1)
        str2 = canonicalize_protocol_dict(spec2)
        self.assertEqual(str1, str2)

    def test_17_changed_semantic_value_changes_fingerprint(self):
        spec1 = {"key": 100}
        spec2 = {"key": 101}
        h1 = compute_protocol_sha256(spec1)
        h2 = compute_protocol_sha256(spec2)
        self.assertNotEqual(h1, h2)

    def test_18_phase14c_cannot_execute_with_protocol_mismatch(self):
        # Verification that an invalid protocol manifest blocks Phase 14C execution
        with TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "phase14b1_oos_protocol_manifest.json"
            manifest_path.write_text(json.dumps({"invalid": True}), encoding="utf-8")
            is_valid, classification, _ = verify_protocol_manifest(manifest_path)
            self.assertFalse(is_valid)
            self.assertEqual(classification, "PROTOCOL_INTEGRITY_FAILURE")


if __name__ == "__main__":
    unittest.main()
