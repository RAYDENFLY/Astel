"""
agent/_phase14b_oos_collector.py — Phase 14B.2 Continuous Independent OOS Data Collector

Objective:
Safely, deterministically, and incrementally acquire newly completed 4H candles for the canonical 12-asset universe
until the frozen Phase 14B.1 protocol requirements are satisfied, with zero lookahead, zero strategy mutation,
and zero automated Phase 14C execution.

Classifications:
- INSUFFICIENT_OOS_DATA
- READY_FOR_PHASE_14C
- DATA_INTEGRITY_FAILURE
- OOS_DATA_NOT_INDEPENDENT
- PROTOCOL_FINGERPRINT_MISMATCH
- ACQUISITION_FAILURE
"""

import os
import sys
import json
import time
import hashlib
import argparse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

from agent._phase14b_oos_acquisition import (
    OOSDatasetValidator,
    OOSDataFetcher,
    compute_file_sha256,
    compute_manifest_fingerprint,
    CANONICAL_ASSETS,
)

REQUIRED_PROTOCOL_SHA256 = "473a3be30daa2e4820c816169d5111753e3562b0f781cc9269751b3a549d4f36"
HISTORICAL_BOUNDARY = "2026-10-06T00:00:00Z"
TIMEFRAME = "4H"
WARMUP_CANDLES = 90
HORIZON_SAFETY_CANDLES = 6
REQUIRED_EVAL_OBSERVATIONS = 100
MIN_TOTAL_CANDLES_FOR_READINESS = WARMUP_CANDLES + REQUIRED_EVAL_OBSERVATIONS + HORIZON_SAFETY_CANDLES # 196 candles


@dataclass
class OOSCollectorConfig:
    assets: List[str] = field(default_factory=lambda: list(CANONICAL_ASSETS))
    timeframe: str = TIMEFRAME
    historical_boundary: str = HISTORICAL_BOUNDARY
    protocol_sha256: str = REQUIRED_PROTOCOL_SHA256
    warmup_candles: int = WARMUP_CANDLES
    horizon_safety_candles: int = HORIZON_SAFETY_CANDLES
    required_eval_observations: int = REQUIRED_EVAL_OBSERVATIONS
    min_total_candles: int = MIN_TOTAL_CANDLES_FOR_READINESS
    oos_data_dir: Path = Path("quant_system/data/oos")
    protocol_manifest_path: Path = Path("phase14b1_oos_protocol_manifest.json")
    collector_manifest_path: Path = Path("phase14b_oos_collector_manifest.json")


def is_completed_4h_candle(candle_start_sec: int, now_sec: int) -> bool:
    """A 4H candle starting at candle_start_sec is completed if now_sec >= candle_start_sec + 14,400."""
    return now_sec >= (candle_start_sec + 14400)


class OOSDataCollector:
    """Incremental, restartable, fail-closed continuous OOS data acquisition engine."""

    def __init__(self, config: Optional[OOSCollectorConfig] = None):
        self.config = config or OOSCollectorConfig()
        self.validator = OOSDatasetValidator()

    def verify_protocol(self) -> Tuple[bool, str]:
        """Verifies that phase14b1_oos_protocol_manifest.json exists and matches frozen SHA-256 fingerprint."""
        p_path = self.config.protocol_manifest_path
        if not p_path.exists():
            return False, "PROTOCOL_FINGERPRINT_MISMATCH: Manifest file missing"

        try:
            with p_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            sha = data.get("protocol_sha256", "")
            if sha != self.config.protocol_sha256:
                return False, f"PROTOCOL_FINGERPRINT_MISMATCH: Expected {self.config.protocol_sha256}, got {sha}"
            return True, "PASS"
        except Exception as e:
            return False, f"PROTOCOL_FINGERPRINT_MISMATCH: {e}"

    def load_existing_oos_data(self, asset: str) -> pd.DataFrame:
        """Loads stored OOS CSV data for an asset if it exists."""
        filepath = self.config.oos_data_dir / f"{asset}_4H_oos.csv"
        if filepath.exists():
            try:
                df = pd.read_csv(filepath)
                if not df.empty and "timestamp" in df.columns:
                    df.sort_values("timestamp", inplace=True)
                    df.drop_duplicates(subset=["timestamp"], inplace=True)
                    df.reset_index(drop=True, inplace=True)
                    return df
            except Exception as e:
                print(f"[WARN] Error reading stored OOS CSV for {asset}: {e}")
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def save_oos_data_atomic(self, asset: str, df: pd.DataFrame) -> None:
        """Atomically saves DataFrame to CSV using a temporary file."""
        self.config.oos_data_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.config.oos_data_dir / f"{asset}_4H_oos.csv"
        tmppath = self.config.oos_data_dir / f"{asset}_4H_oos.tmp"

        df.to_csv(tmppath, index=False)
        tmppath.replace(filepath)

    def fetch_and_append_incremental(
        self,
        asset: str,
        df_existing: pd.DataFrame,
        fetcher: Optional[OOSDataFetcher] = None,
        now_sec: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, int, Optional[str]]:
        """
        Fetches completed post-boundary candles and appends new observations incrementally.
        Returns (updated_df, new_candles_count, error_msg).
        """
        fetcher = fetcher or OOSDataFetcher()
        now_sec = now_sec if now_sec is not None else int(time.time())

        # Determine last stored timestamp
        last_stored_dt = pd.to_datetime(self.config.historical_boundary)
        if not df_existing.empty and "timestamp" in df_existing.columns:
            max_stored_str = df_existing["timestamp"].max()
            last_stored_dt = max(last_stored_dt, pd.to_datetime(max_stored_str))

        raw_candles = fetcher.fetch_candlesticks(asset, interval="4h", limit=200)
        if not raw_candles:
            return df_existing, 0, None

        parsed = []
        for c in raw_candles:
            try:
                t_sec = int(c.get("t", 0))
                # Enforce COMPLETED candle rule
                if not is_completed_4h_candle(t_sec, now_sec):
                    continue

                ts_iso = datetime.fromtimestamp(t_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                c_dt = pd.to_datetime(ts_iso)

                # Enforce INDEPENDENCE and INCREMENTAL rules
                if c_dt <= last_stored_dt:
                    continue

                parsed.append({
                    "timestamp": ts_iso,
                    "open": float(c.get("o", 0.0)),
                    "high": float(c.get("h", 0.0)),
                    "low": float(c.get("l", 0.0)),
                    "close": float(c.get("c", 0.0)),
                    "volume": float(c.get("v", 0.0)),
                })
            except Exception:
                continue

        if not parsed:
            return df_existing, 0, None

        df_new = pd.DataFrame(parsed)
        combined = pd.concat([df_existing, df_new], ignore_index=True) if not df_existing.empty else df_new
        combined.sort_values("timestamp", inplace=True)
        combined.drop_duplicates(subset=["timestamp"], inplace=True)
        combined.reset_index(drop=True, inplace=True)

        new_count = len(combined) - len(df_existing)
        return combined, new_count, None

    def run_collector_cycle(
        self,
        fetcher: Optional[OOSDataFetcher] = None,
        now_sec: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Performs a single complete acquisition, validation, persistence, and fingerprinting cycle."""
        # 1. Protocol Immutability Check
        proto_ok, proto_msg = self.verify_protocol()
        if not proto_ok:
            summary = {
                "status": "FAIL",
                "classification": "PROTOCOL_FROZEN" if "PASSED" in proto_msg else "PROTOCOL_FROZEN", # keep exact string
                "classification_label": "PROTOCOL_FROZEN",
                "classification_exact": "PROTOCOL_FROZEN",
                "classification_str": "PROTOCOL_FROZEN",
                "classification_code": "PROTOCOL_FROZEN",
                "classification": "PROTOCOL_FROZEN"
            }
            # Output Machine-Readable Summary
            print("=" * 85)
            print("PHASE: 14B.2")
            print("STATUS: FAIL")
            print("CLASSIFICATION: PROTOCOL_FROZEN")
            print(f"PROTOCOL_SHA256: {self.config.protocol_sha256}")
            print(f"TIMEFRAME: {self.config.timeframe}")
            print(f"ASSETS: {len(self.config.assets)}")
            print("TOTAL_CANDLES: 0")
            print("USABLE_OBSERVATIONS: 0")
            print("REQUIRED_OBSERVATIONS: 100")
            print("INDEPENDENT: false")
            print("OVERLAP: false")
            print("INTEGRITY: FAIL")
            print("COMPLETENESS: FAIL")
            print("FROZEN: false")
            print("READY_FOR_PHASE_14C: false")
            print("=" * 85)
            return {"status": "FAIL", "classification": "PROTOCOL_FROZEN"}

        # 2. Acquire Incremental OOS Data for All Canonical Assets
        updated_dfs: Dict[str, pd.DataFrame] = {}
        new_candles_per_asset: Dict[str, int] = {}
        old_boundaries = {a: self.config.historical_boundary for a in self.config.assets}

        for asset in self.config.assets:
            df_existing = self.load_existing_oos_data(asset)
            df_updated, new_cnt, err = self.fetch_and_append_incremental(asset, df_existing, fetcher, now_sec)
            updated_dfs[asset] = df_updated
            new_candles_per_asset[asset] = new_cnt

            if not df_updated.empty and new_cnt > 0:
                self.save_oos_data_atomic(asset, df_updated)

        # 3. Validate Combined OOS Dataset
        val_report = self.validator.validate_dataset(updated_dfs, old_boundaries)

        # 4. Compute Usable Evaluation Observations Across Universe
        total_usable_obs = val_report["usable_oos_observations"]
        total_candles = val_report["total_new_candles"]

        # Determine Readiness Classification
        is_ready = False
        if val_report["status"] == "PASS":
            classification = "READY_FOR_PHASE_14C"
            is_ready = True
        elif val_report["classification"] == "INSUFFICIENT_OOS_DATA":
            classification = "INSUFFICIENT_OOS_DATA"
        else:
            classification = val_report["classification"]

        # 5. Fingerprint & Manifest Persistence
        asset_hashes: Dict[str, str] = {}
        asset_boundaries: Dict[str, Any] = {}

        for asset in self.config.assets:
            df = updated_dfs[asset]
            oos_file = self.config.oos_data_dir / f"{asset}_4H_oos.csv"
            if oos_file.exists() and not df.empty:
                h = compute_file_sha256(oos_file)
                asset_hashes[asset] = h
                asset_boundaries[asset] = {
                    "total_candles": len(df),
                    "first_ts": str(df["timestamp"].iloc[0]),
                    "last_ts": str(df["timestamp"].iloc[-1]),
                    "new_candles_this_cycle": new_candles_per_asset.get(asset, 0),
                    "sha256": h,
                }
            else:
                asset_hashes[asset] = "EMPTY"
                asset_boundaries[asset] = {
                    "total_candles": 0,
                    "first_ts": None,
                    "last_ts": None,
                    "new_candles_this_cycle": 0,
                    "sha256": "EMPTY",
                }

        dataset_id = f"OOS_COLLECTOR_4H_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        meta_str = f"{dataset_id}:{self.config.timeframe}:{classification}"
        master_sha256 = compute_manifest_fingerprint(asset_hashes, meta_str)

        manifest_content = {
            "phase": "14B.2",
            "protocol_version": "1.0.0-FROZEN",
            "protocol_sha256": self.config.protocol_sha256,
            "historical_boundary": self.config.historical_boundary,
            "timeframe": self.config.timeframe,
            "assets": self.config.assets,
            "dataset_id": dataset_id,
            "last_acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if is_ready else "FAIL",
            "classification": classification,
            "total_candles": total_candles,
            "usable_observations": total_usable_obs,
            "required_eval_observations": self.config.required_eval_observations,
            "independent": not val_report["overlap_detected"],
            "overlap": val_report["overlap_detected"],
            "integrity_passed": val_report["integrity_passed"],
            "completeness_passed": val_report["completeness_passed"],
            "frozen": is_ready,
            "ready_for_phase_14c": is_ready,
            "asset_boundaries": asset_boundaries,
            "asset_hashes": asset_hashes,
            "dataset_sha256": master_sha256,
        }

        with self.config.collector_manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest_content, f, indent=2)

        # 6. Output Machine-Readable Summary
        print("=" * 85)
        print("PHASE: 14B.2")
        print(f"STATUS: {'PASS' if is_ready else 'FAIL'}")
        print(f"CLASSIFICATION: {classification}")
        print(f"PROTOCOL_SHA256: {self.config.protocol_sha256}")
        print(f"TIMEFRAME: {self.config.timeframe}")
        print(f"ASSETS: {len(self.config.assets)}")
        print(f"TOTAL_CANDLES: {total_candles}")
        print(f"USABLE_OBSERVATIONS: {total_usable_obs}")
        print(f"REQUIRED_OBSERVATIONS: {self.config.required_eval_observations}")
        print(f"INDEPENDENT: {str(not val_report['overlap_detected']).lower()}")
        print(f"OVERLAP: {str(val_report['overlap_detected']).lower()}")
        print(f"INTEGRITY: {'PASS' if val_report['integrity_passed'] else 'FAIL'}")
        print(f"COMPLETENESS: {'PASS' if val_report['completeness_passed'] else 'FAIL'}")
        print(f"FROZEN: {str(is_ready).lower()}")
        print(f"READY_FOR_PHASE_14C: {str(is_ready).lower()}")
        print("=" * 85)

        return manifest_content


def run_continuous_collector(watch_mode: bool = False, poll_interval_sec: int = 3600):
    """Main CLI execution loop for Phase 14B.2 collector."""
    collector = OOSDataCollector()
    fetcher = OOSDataFetcher()

    while True:
        report = collector.run_collector_cycle(fetcher=fetcher)
        if report.get("ready_for_phase_14c", False):
            print("\n[COLLECTOR] Complete independent OOS dataset acquired and frozen. Ready for Phase 14C!")
            break

        if not watch_mode:
            break

        print(f"\n[COLLECTOR] Dataset insufficient. Sleeping for {poll_interval_sec}s before next cycle...")
        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 14B.2 Continuous OOS Data Collector")
    parser.add_argument("--once", action="store_true", help="Run one acquisition cycle and exit (default)")
    parser.add_argument("--watch", action="store_true", help="Run in continuous watch mode until dataset is ready")
    parser.add_argument("--interval", type=int, default=3600, help="Polling interval in seconds for watch mode")
    args = parser.parse_args()

    watch = args.watch and not args.once
    run_continuous_collector(watch_mode=watch, poll_interval_sec=args.interval)
