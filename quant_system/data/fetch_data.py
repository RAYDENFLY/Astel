"""Data loading module.

Loads historical OHLCV from per-asset CSV placeholders and aligns to the configured timeframe.
Output is a unified long-format DataFrame with columns:
  timestamp, asset, open, high, low, close, volume

No exchange API calls are made.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd


@dataclass
class DataFetcher:
    cfg: Dict

    def __post_init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)

    def load_ohlcv(self) -> pd.DataFrame:
        """Load and align OHLCV for all configured assets."""
        assets: List[str] = list(self.cfg["assets"])
        timeframe: str = str(self.cfg["system"]["timeframe"]).upper()
        csv_dir = Path(self.cfg["data"]["csv_dir"])

        frames: List[pd.DataFrame] = []
        for asset in assets:
            fp = csv_dir / f"{asset}.csv"
            if not fp.exists():
                raise FileNotFoundError(
                    f"Missing CSV for asset '{asset}' at {fp}. "
                    "Create a placeholder CSV with columns timestamp, open, high, low, close, volume."
                )
            df = pd.read_csv(fp)
            if df.empty:
                self._log.warning("CSV for asset '%s' is empty (%s). Skipping this asset.", asset, fp)
                continue
            df = self._standardize_columns(df)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("timestamp")

            aligned = self._align_to_timeframe(df, timeframe=timeframe)
            aligned["asset"] = asset
            frames.append(aligned)

        if not frames:
            raise ValueError(
                f"No OHLCV data loaded from {csv_dir}. Provide non-empty CSVs before training."
            )

        out = pd.concat(frames, ignore_index=True)
        out = out[["timestamp", "asset", "open", "high", "low", "close", "volume"]]
        out = out.sort_values(["timestamp", "asset"]).reset_index(drop=True)
        return out

    @staticmethod
    def _standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
        col_map = {c: c.strip().lower() for c in df.columns}
        df = df.rename(columns=col_map)
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
        return df

    def _align_to_timeframe(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """Align to timeframe using OHLCV resampling.

        If data is already exactly on the timeframe with no duplicates, this should be a no-op.
        """
        rule = self._timeframe_to_pandas_rule(timeframe)
        df = df.set_index("timestamp")

        ohlcv = df.resample(rule, label="left", closed="left").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        ohlcv = ohlcv.dropna(subset=["open", "high", "low", "close"])
        ohlcv = ohlcv.reset_index()

        # Ensure strict alignment.
        ohlcv["timestamp"] = pd.to_datetime(ohlcv["timestamp"], utc=True)
        return ohlcv

    @staticmethod
    def _timeframe_to_pandas_rule(timeframe: str) -> str:
        if timeframe in {"4H", "4h"}:
            # Use lowercase to avoid pandas FutureWarning for uppercase offset aliases.
            return "4h"
        raise ValueError(f"Unsupported timeframe: {timeframe}")
