"""
agent/_phase14b_oos_health.py — Phase 14B.2 OOS Health & Status Validator (Read-Only)

Calculates complete, non-mutating integrity metrics for stored OOS datasets.
Reports asset coverage, candle counts, timestamp gaps, duplicates, OHLCV anomalies,
historical boundary violations, and frozen protocol compliance without modifying any data.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd

from agent._phase14b_oos_acquisition import CANONICAL_ASSETS, compute_file_sha256

REQUIRED_PROTOCOL_SHA256 = "473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36"
HISTORICAL_BOUNDARY = "2026-10-06T00:00:00Z"
REQUIRED_EVAL_OBSERVATIONS = 100
WARMUP_CANDLES = 90
HORIZON_SAFETY_CANDLES = 6
MIN_TOTAL_CANDLES_FOR_READINESS = WARMUP_CANDLES + REQUIRED_EVAL_OBSERVATIONS + HORIZON_SAFETY_CANDLES  # 196 candles


class OOSHealthValidator:
    """Read-only health and integrity auditor for Phase 14B.2 OOS dataset."""

    def __init__(
        self,
        oos_dir: Path = Path("quant_system/data/oos"),
        protocol_manifest_path: Path = Path("phase14b1_oos_protocol_manifest.json"),
    ):
        self.oos_dir = oos_dir
        self.protocol_manifest_path = protocol_manifest_path

    def verify_protocol_fingerprint(self) -> Tuple[bool, str]:
        """Verifies that the frozen protocol manifest exists and matches REQUIRED_PROTOCOL_SHA256."""
        if not self.protocol_manifest_path.exists():
            return False, "PROTOCOL_MANIFEST_MISSING"
        try:
            with self.protocol_manifest_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            sha = data.get("protocol_sha256", "")
            if sha != REQUIRED_PROTOCOL_SHA256:
                return False, f"PROTOCOL_FINGERPRINT_MISMATCH: Expected {REQUIRED_PROTOCOL_SHA256}, got {sha}"
            return True, "PASS"
        except Exception as e:
            return False, f"PROTOCOL_FINGERPRINT_ERROR: {e}"

    def inspect_dataset_health(self) -> Dict[str, Any]:
        """Performs full read-only health audit across stored CSV files for canonical assets."""
        proto_ok, proto_msg = self.verify_protocol_fingerprint()

        asset_candle_counts: Dict[str, int] = {}
        total_duplicates = 0
        total_gaps = 0
        total_overlaps = 0
        total_invalid = 0
        historical_overlap = False

        found_assets = 0
        bound_dt = pd.to_datetime(HISTORICAL_BOUNDARY)

        for asset in CANONICAL_ASSETS:
            csv_path = self.oos_dir / f"{asset}_4H_oos.csv"
            if not csv_path.exists():
                asset_candle_counts[asset] = 0
                continue

            found_assets += 1
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                asset_candle_counts[asset] = 0
                total_invalid += 1
                continue

            if df.empty or "timestamp" not in df.columns:
                asset_candle_counts[asset] = 0
                continue

            asset_candle_counts[asset] = len(df)

            # Check duplicates
            dups = df.duplicated(subset=["timestamp"]).sum()
            total_duplicates += int(dups)

            # Check timestamps
            ts_series = pd.to_datetime(df["timestamp"], errors="coerce")

            # Historical overlap check
            min_ts = ts_series.min()
            if pd.notnull(min_ts) and min_ts <= bound_dt:
                historical_overlap = True

            # Gaps check (strictly 4H steps)
            ts_sorted = ts_series.sort_values()
            diffs = ts_sorted.diff()
            expected_diff = pd.Timedelta(hours=4)
            gaps = (diffs.dropna() != expected_diff).sum()
            total_gaps += int(gaps)

            # OHLCV Integrity checks
            for _, row in df.iterrows():
                try:
                    o = float(row["open"])
                    h = float(row["high"])
                    l = float(row["low"])
                    c = float(row["close"])
                    v = float(row["volume"])

                    # Fail closed on non-finite
                    if any(math.isnan(x) or math.isinf(x) for x in [o, h, l, c, v]):
                        total_invalid += 1
                        continue

                    if h < max(o, c) or l > min(o, c) or h < l or v < 0:
                        total_invalid += 1
                except Exception:
                    total_invalid += 1

        min_candles = min(asset_candle_counts.values()) if asset_candle_counts else 0
        max_candles = max(asset_candle_counts.values()) if asset_candle_counts else 0
        total_candles = sum(asset_candle_counts.values())

        # Determine readiness
        independent_oos = not historical_overlap and total_overlaps == 0
        ready_for_phase_14c = (
            proto_ok
            and found_assets == len(CANONICAL_ASSETS)
            and min_candles >= MIN_TOTAL_CANDLES_FOR_READINESS
            and total_duplicates == 0
            and total_invalid == 0
            and not historical_overlap
        )

        report = {
            "asset_count": found_assets,
            "canonical_total": len(CANONICAL_ASSETS),
            "min_candles": min_candles,
            "max_candles": max_candles,
            "total_candles": total_candles,
            "duplicate_count": total_duplicates,
            "gap_count": total_gaps,
            "overlap_count": total_overlaps,
            "invalid_candle_count": total_invalid,
            "historical_overlap": historical_overlap,
            "protocol_fingerprint_match": proto_ok,
            "independent_oos": independent_oos,
            "frozen": ready_for_phase_14c,
            "ready_for_phase_14c": ready_for_phase_14c,
            "asset_candle_counts": asset_candle_counts,
        }
        return report

    def print_health_summary(self, report: Optional[Dict[str, Any]] = None) -> None:
        """Prints readable status summary."""
        report = report or self.inspect_dataset_health()
        print("PHASE_14B.2 HEALTH")
        print("==================")
        print(f"asset_count: {report['asset_count']}/{report['canonical_total']}")
        print(f"min_candles: {report['min_candles']}")
        print(f"max_candles: {report['max_candles']}")
        print(f"total_candles: {report['total_candles']}")
        print(f"duplicate_count: {report['duplicate_count']}")
        print(f"gap_count: {report['gap_count']}")
        print(f"overlap_count: {report['overlap_count']}")
        print(f"invalid_candle_count: {report['invalid_candle_count']}")
        print(f"historical_overlap: {str(report['historical_overlap']).lower()}")
        print(f"protocol_fingerprint_match: {str(report['protocol_fingerprint_match']).lower()}")
        print(f"independent_oos: {str(report['independent_oos']).lower()}")
        print(f"frozen: {str(report['frozen']).lower()}")
        print(f"ready_for_phase_14c: {str(report['ready_for_phase_14c']).lower()}")


if __name__ == "__main__":
    validator = OOSHealthValidator()
    validator.print_health_summary()
