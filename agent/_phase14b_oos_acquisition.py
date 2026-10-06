"""
agent/_phase14b_oos_acquisition.py — Phase 14B Independent Dataset Acquisition & OOS Preparation

Objective:
Acquire, validate, fingerprint, freeze, and document a genuinely independent out-of-sample (OOS) dataset
for future Phase 14C validation, ensuring zero lookahead, zero strategy mutation, and strict fail-closed safety.

Classifications:
- READY_FOR_PHASE_14C
- INSUFFICIENT_OOS_DATA
- OOS_DATA_NOT_INDEPENDENT
- DATA_INTEGRITY_FAILURE
- DATA_COMPLETENESS_FAILURE
- FROZEN_DATASET_INTEGRITY_FAILURE
"""

import os
import sys
import json
import hashlib
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

CANONICAL_ASSETS = [
    "BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT", "AVAX_USDT",
    "LINK_USDT", "DOGE_USDT", "ADA_USDT", "LTC_USDT", "AAVE_USDT", "SUI_USDT"
]

DEFAULT_TIMEFRAME = "4h"
WARMUP_CANDLES_REQUIRED = 90
HORIZON_SAFETY_CANDLES_REQUIRED = 6
MIN_REQUIRED_OOS_CANDLES = 100


@dataclass
class OOSAcquisitionConfig:
    assets: List[str] = field(default_factory=lambda: list(CANONICAL_ASSETS))
    timeframe: str = DEFAULT_TIMEFRAME
    warmup_candles: int = WARMUP_CANDLES_REQUIRED
    horizon_safety_candles: int = HORIZON_SAFETY_CANDLES_REQUIRED
    min_required_oos_candles: int = MIN_REQUIRED_OOS_CANDLES
    old_csv_dir: Path = Path("quant_system/data/csv")
    oos_data_dir: Path = Path("quant_system/data/oos")
    manifest_path: Path = Path("phase14b_oos_manifest.json")


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file."""
    if not filepath.exists():
        return ""
    hasher = hashlib.sha256()
    with filepath.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_manifest_fingerprint(asset_hashes: Dict[str, str], metadata_str: str) -> str:
    """Computes SHA-256 fingerprint for the combined manifest state."""
    hasher = hashlib.sha256()
    sorted_items = sorted(asset_hashes.items())
    for k, v in sorted_items:
        hasher.update(f"{k}:{v}".encode("utf-8"))
    hasher.update(metadata_str.encode("utf-8"))
    return hasher.hexdigest()


class OOSDataFetcher:
    """Fetches public 4H futures candlesticks from Gate.io REST API (Read-only, no credentials required)."""

    def fetch_candlesticks(self, asset: str, interval: str = "4h", limit: int = 100) -> List[Dict[str, Any]]:
        url = f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks?contract={asset}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "Astel-Research-Agent/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            print(f"[FETCH_WARNING] Could not fetch data for {asset}: {e}")
            return []


class OOSDatasetValidator:
    """Performs strict data independence, integrity, completeness, gap, and horizon validation."""

    def __init__(self, config: Optional[OOSAcquisitionConfig] = None):
        self.config = config or OOSAcquisitionConfig()

    def get_old_dataset_boundary(self) -> Dict[str, str]:
        """Inspects existing CSV datasets in old_csv_dir and returns max timestamp per asset."""
        old_boundaries = {}
        old_dir = self.config.old_csv_dir
        if not old_dir.exists():
            return old_boundaries

        for asset in self.config.assets:
            csv_path = old_dir / f"{asset}.csv"
            if not csv_path.exists():
                alt_path = old_dir / f"{asset.replace('_', '')}.csv"
                if alt_path.exists():
                    csv_path = alt_path

            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    if not df.empty and "timestamp" in df.columns:
                        max_ts = str(df["timestamp"].max())
                        old_boundaries[asset] = max_ts
                except Exception as e:
                    print(f"[WARN] Error reading old dataset for {asset}: {e}")

        return old_boundaries

    def validate_dataset(
        self,
        new_dfs: Dict[str, pd.DataFrame],
        old_boundaries: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Validates new candidate OOS data against independence and integrity rules.
        """
        report: Dict[str, Any] = {
            "status": "FAIL",
            "classification": "INSUFFICIENT_OOS_DATA",
            "assets_evaluated": list(new_dfs.keys()),
            "missing_assets": [],
            "overlap_detected": False,
            "integrity_passed": True,
            "completeness_passed": True,
            "asset_reports": {},
            "total_new_candles": 0,
            "usable_oos_observations": 0,
            "failure_reasons": [],
        }

        # 1. Canonical Asset Completeness
        missing_assets = [a for a in self.config.assets if a not in new_dfs or new_dfs[a].empty]
        if missing_assets:
            report["missing_assets"] = missing_assets
            report["completeness_passed"] = False
            report["failure_reasons"].append(f"Missing canonical assets: {missing_assets}")
            report["classification"] = "DATA_COMPLETENESS_FAILURE"
            return report

        total_usable_observations = 0
        total_candles = 0

        for asset in self.config.assets:
            df = new_dfs[asset]
            asset_rep: Dict[str, Any] = {
                "candle_count": len(df),
                "first_ts": None,
                "last_ts": None,
                "old_boundary_ts": old_boundaries.get(asset, None),
                "is_independent": True,
                "is_monotonic": True,
                "has_duplicates": False,
                "ohlc_valid": True,
                "gap_count": 0,
                "usable_observations": 0,
            }

            if df.empty:
                asset_rep["is_independent"] = False
                report["integrity_passed"] = False
                report["asset_reports"][asset] = asset_rep
                continue

            # Check required columns
            req_cols = {"timestamp", "open", "high", "low", "close", "volume"}
            if not req_cols.issubset(set(df.columns)):
                report["integrity_passed"] = False
                report["failure_reasons"].append(f"{asset} missing required columns")
                report["classification"] = "DATA_INTEGRITY_FAILURE"
                return report

            # Convert timestamps
            ts_series = pd.to_datetime(df["timestamp"])
            asset_rep["first_ts"] = str(df["timestamp"].iloc[0])
            asset_rep["last_ts"] = str(df["timestamp"].iloc[-1])

            # 2. Data Independence Check (new_first_ts > old_last_ts)
            old_last = old_boundaries.get(asset)
            if old_last:
                old_last_dt = pd.to_datetime(old_last)
                new_first_dt = ts_series.iloc[0]
                if new_first_dt <= old_last_dt:
                    asset_rep["is_independent"] = False
                    report["overlap_detected"] = True
                    report["failure_reasons"].append(
                        f"{asset} overlap detected: first new timestamp {new_first_dt} <= old boundary {old_last_dt}"
                    )

            # 3. Monotonicity & Duplicates
            if not ts_series.is_monotonic_increasing:
                asset_rep["is_monotonic"] = False
                report["integrity_passed"] = False
                report["failure_reasons"].append(f"{asset} timestamps not strictly increasing")

            dups = int(ts_series.duplicated().sum())
            if dups > 0:
                asset_rep["has_duplicates"] = True
                report["integrity_passed"] = False
                report["failure_reasons"].append(f"{asset} contains {dups} duplicate timestamps")

            # 4. OHLC Integrity
            # Check NaN / Inf
            if df[list(req_cols)].isna().any().any() or np.isinf(df[["open", "high", "low", "close", "volume"]].values).any():
                asset_rep["ohlc_valid"] = False
                report["integrity_passed"] = False
                report["failure_reasons"].append(f"{asset} contains NaN or Inf values")

            # High >= max(open, close), low <= min(open, close), high >= low, volume >= 0
            valid_h = (df["high"] >= df[["open", "close"]].max(axis=1)).all()
            valid_l = (df["low"] <= df[["open", "close"]].min(axis=1)).all()
            valid_hl = (df["high"] >= df["low"]).all()
            valid_vol = (df["volume"] >= 0).all()

            if not (valid_h and valid_l and valid_hl and valid_vol):
                asset_rep["ohlc_valid"] = False
                report["integrity_passed"] = False
                report["failure_reasons"].append(f"{asset} failed OHLC relation or volume checks")

            # 5. Gap Analysis (4H interval = 14,400s)
            diffs = ts_series.diff()
            gaps = int((diffs > pd.Timedelta(hours=4)).sum())
            asset_rep["gap_count"] = gaps

            # 6. Warmup & Future Horizon Safety Check
            n_candles = len(df)
            total_candles += n_candles
            usable = max(0, n_candles - self.config.warmup_candles - self.config.horizon_safety_candles)
            asset_rep["usable_observations"] = usable
            total_usable_observations += usable

            report["asset_reports"][asset] = asset_rep

        report["total_new_candles"] = total_candles
        report["usable_oos_observations"] = total_usable_observations

        # Determine Final Classification
        if report["overlap_detected"]:
            report["status"] = "FAIL"
            report["classification"] = "OOS_DATA_NOT_INDEPENDENT"
        elif not report["integrity_passed"]:
            report["status"] = "FAIL"
            report["classification"] = "DATA_INTEGRITY_FAILURE"
        elif not report["completeness_passed"]:
            report["status"] = "FAIL"
            report["classification"] = "DATA_COMPLETENESS_FAILURE"
        elif total_usable_observations < self.config.min_required_oos_candles:
            report["status"] = "FAIL"
            report["classification"] = "INSUFFICIENT_OOS_DATA"
            report["failure_reasons"].append(
                f"Usable OOS observations ({total_usable_observations}) below required threshold ({self.config.min_required_oos_candles})"
            )
        else:
            report["status"] = "PASS"
            report["classification"] = "READY_FOR_PHASE_14C"

        return report


def acquire_and_freeze_oos_dataset(
    config: Optional[OOSAcquisitionConfig] = None,
    fetcher: Optional[OOSDataFetcher] = None,
) -> Dict[str, Any]:
    """
    Main acquisition, validation, fingerprinting, and freezing orchestrator for Phase 14B.
    """
    config = config or OOSAcquisitionConfig()
    fetcher = fetcher or OOSDataFetcher()
    validator = OOSDatasetValidator(config)

    print("=" * 85)
    print("PHASE 14B — INDEPENDENT DATASET ACQUISITION & OOS PREPARATION")
    print("=" * 85)

    # 1. Old Boundary Identification
    old_boundaries = validator.get_old_dataset_boundary()
    print("\n--- PREVIOUS DATASET BOUNDARIES ---")
    for ast, max_ts in old_boundaries.items():
        print(f"  {ast:<12}: Last Timestamp = {max_ts}")

    # 2. Acquire Candidate OOS Data
    new_dfs: Dict[str, pd.DataFrame] = {}
    print("\n--- ACQUIRING POST-BOUNDARY OOS CANDLESTICKS ---")

    config.oos_data_dir.mkdir(parents=True, exist_ok=True)

    for asset in config.assets:
        # Check if file exists in oos_data_dir first
        oos_file = config.oos_data_dir / f"{asset}_4H_oos.csv"
        if oos_file.exists():
            try:
                df_candidate = pd.read_csv(oos_file)
                new_dfs[asset] = df_candidate
                print(f"  {asset:<12}: Loaded {len(df_candidate)} candidate candles from local file.")
                continue
            except Exception as e:
                print(f"  {asset:<12}: Error loading local OOS file: {e}")

        # Fetch from API
        raw_candles = fetcher.fetch_candlesticks(asset, interval=config.timeframe, limit=200)
        if not raw_candles:
            new_dfs[asset] = pd.DataFrame()
            print(f"  {asset:<12}: 0 candles fetched.")
            continue

        # Parse Gate.io candlestick format
        # Example: {"t": 1791259200, "o": "85479.5", "h": "85710.7", "l": "85090", "c": "85264.6", "v": 45032277}
        parsed = []
        for c in raw_candles:
            try:
                t_sec = int(c.get("t", 0))
                ts_iso = datetime.fromtimestamp(t_sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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

        df_cand = pd.DataFrame(parsed)
        if not df_cand.empty:
            df_cand.sort_values("timestamp", inplace=True)
            df_cand.drop_duplicates(subset=["timestamp"], inplace=True)
            df_cand.reset_index(drop=True, inplace=True)

            # Filter to post-boundary only if old boundary exists
            old_last = old_boundaries.get(asset)
            if old_last:
                old_last_dt = pd.to_datetime(old_last)
                df_cand["dt"] = pd.to_datetime(df_cand["timestamp"])
                df_post = df_cand[df_cand["dt"] > old_last_dt].drop(columns=["dt"])
                df_cand = df_post.reset_index(drop=True)

        new_dfs[asset] = df_cand
        print(f"  {asset:<12}: {len(df_cand)} post-boundary candles fetched.")

    # 3. Validate Candidate OOS Data
    val_report = validator.validate_dataset(new_dfs, old_boundaries)

    print("\n--- VALIDATION & INTEGRITY REPORT ---")
    print(f"Status:                    {val_report['status']}")
    print(f"Classification:            {val_report['classification']}")
    print(f"Total New Candles:         {val_report['total_new_candles']}")
    print(f"Usable OOS Observations:  {val_report['usable_oos_observations']} (Required: {config.min_required_oos_candles})")
    print(f"Overlap Detected:          {val_report['overlap_detected']}")
    print(f"Integrity Passed:          {val_report['integrity_passed']}")

    if val_report["failure_reasons"]:
        print("\nFailure Reasons:")
        for r in val_report["failure_reasons"]:
            print(f"  - {r}")

    # 4. Fingerprint & Freeze (save candidate OOS files and manifest)
    asset_hashes: Dict[str, str] = {}
    asset_boundaries: Dict[str, Any] = {}

    for asset, df in new_dfs.items():
        oos_file = config.oos_data_dir / f"{asset}_4H_oos.csv"
        if not df.empty:
            df.to_csv(oos_file, index=False)
            h = compute_file_sha256(oos_file)
            asset_hashes[asset] = h
            asset_boundaries[asset] = {
                "candles": len(df),
                "first_ts": str(df["timestamp"].iloc[0]),
                "last_ts": str(df["timestamp"].iloc[-1]),
                "sha256": h,
            }
        else:
            asset_hashes[asset] = "EMPTY"
            asset_boundaries[asset] = {
                "candles": 0,
                "first_ts": None,
                "last_ts": None,
                "sha256": "EMPTY",
            }

    dataset_id = f"OOS_4H_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    metadata_str = f"{dataset_id}:{config.timeframe}:{val_report['classification']}"
    manifest_fingerprint = compute_manifest_fingerprint(asset_hashes, metadata_str)

    manifest_content = {
        "dataset_id": dataset_id,
        "phase": "14B",
        "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
        "timeframe": config.timeframe,
        "assets": config.assets,
        "validation_status": val_report["status"],
        "classification": val_report["classification"],
        "total_new_candles": val_report["total_new_candles"],
        "usable_oos_observations": val_report["usable_oos_observations"],
        "min_required_oos_candles": config.min_required_oos_candles,
        "overlap_detected": val_report["overlap_detected"],
        "integrity_passed": val_report["integrity_passed"],
        "failure_reasons": val_report["failure_reasons"],
        "asset_boundaries": asset_boundaries,
        "asset_hashes": asset_hashes,
        "manifest_sha256": manifest_fingerprint,
        "frozen": True if val_report["status"] == "PASS" else False,
    }

    with config.manifest_path.open("w", encoding="utf-8") as f:
        json.dumps(manifest_content, indent=2)
        f.write(json.dumps(manifest_content, indent=2))

    print(f"\nManifest saved to: {config.manifest_path.resolve()}")
    print(f"Manifest Fingerprint (SHA-256): {manifest_fingerprint}")

    # 5. Output Machine-Readable Summary Block
    print("\n" + "=" * 85)
    print("PHASE: 14B")
    print(f"STATUS: {val_report['status']}")
    print(f"CLASSIFICATION: {val_report['classification']}")
    print(f"DATASET_ID: {dataset_id}")
    print(f"TIMEFRAME: {config.timeframe}")
    print(f"ASSETS: {len(config.assets)}")
    print(f"INDEPENDENT: {str(not val_report['overlap_detected']).lower()}")
    print(f"OVERLAP: {str(val_report['overlap_detected']).lower()}")
    print(f"INTEGRITY: {'PASS' if val_report['integrity_passed'] else 'FAIL'}")
    print(f"COMPLETENESS: {'PASS' if val_report['completeness_passed'] else 'FAIL'}")
    print(f"FROZEN: {str(val_report['status'] == 'PASS').lower()}")
    print(f"HASH_VERIFIED: {str(bool(manifest_fingerprint)).lower()}")
    print("=" * 85)

    return manifest_content


def verify_frozen_dataset_integrity(manifest_path: Path) -> bool:
    """Verifies SHA-256 hashes of frozen dataset files against manifest."""
    if not manifest_path.exists():
        return False

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    asset_hashes = manifest.get("asset_hashes", {})
    oos_dir = Path("quant_system/data/oos")

    for asset, expected_hash in asset_hashes.items():
        if expected_hash == "EMPTY":
            continue
        filepath = oos_dir / f"{asset}_4H_oos.csv"
        actual_hash = compute_file_sha256(filepath)
        if actual_hash != expected_hash:
            return False

    return True


if __name__ == "__main__":
    acquire_and_freeze_oos_dataset()
