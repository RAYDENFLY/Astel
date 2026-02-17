"""Feature engineering.

Computes momentum/volatility/trend/volume features per asset and a forward-looking target:
  future_return = close.shift(-1)/close - 1
  target = future_return / ATR

Asset is kept as a categorical column for LightGBM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureBuilder:
    cfg: Dict

    def build(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        ohlcv = ohlcv.copy()
        ohlcv["timestamp"] = pd.to_datetime(ohlcv["timestamp"], utc=True)
        ohlcv = ohlcv.sort_values(["asset", "timestamp"]).reset_index(drop=True)

        g = ohlcv.groupby("asset", group_keys=False)

        # Momentum
        ohlcv["return_1"] = g["close"].pct_change(1)
        ohlcv["return_2"] = g["close"].pct_change(2)
        ohlcv["return_3"] = g["close"].pct_change(3)

        # Volatility
        atr_period = int(self.cfg["features"]["atr_period"])
        prev_close = g["close"].shift(1)
        tr = pd.concat(
            [
                (ohlcv["high"] - ohlcv["low"]).abs(),
                (ohlcv["high"] - prev_close).abs(),
                (ohlcv["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        ohlcv["atr"] = tr.groupby(ohlcv["asset"]).rolling(atr_period).mean().reset_index(level=0, drop=True)

        std_period = int(self.cfg["features"]["rolling_std_period"])
        ohlcv["rolling_std_20"] = (
            g["close"].pct_change().rolling(std_period).std().reset_index(level=0, drop=True)
        )

        # Trend
        ema_fast = int(self.cfg["features"]["ema_fast"])
        ema_slow = int(self.cfg["features"]["ema_slow"])
        ohlcv["ema_fast"] = g["close"].apply(lambda s: s.ewm(span=ema_fast, adjust=False).mean())
        ohlcv["ema_slow"] = g["close"].apply(lambda s: s.ewm(span=ema_slow, adjust=False).mean())
        ohlcv["ema_distance"] = (ohlcv["ema_fast"] - ohlcv["ema_slow"]) / ohlcv["close"].replace(
            0.0, np.nan
        )
        ohlcv["ema_slope"] = g["ema_slow"].apply(lambda s: s.diff())

        # Volume
        vz_period = int(self.cfg["features"]["volume_zscore_period"])
        vol_mean = g["volume"].rolling(vz_period).mean().reset_index(level=0, drop=True)
        vol_std = g["volume"].rolling(vz_period).std(ddof=0).reset_index(level=0, drop=True)
        ohlcv["volume_zscore"] = (ohlcv["volume"] - vol_mean) / vol_std.replace(0.0, np.nan)

        # Target (no leakage: future return is shifted -1)
        ohlcv["future_return"] = g["close"].shift(-1) / ohlcv["close"] - 1.0
        ohlcv["target"] = ohlcv["future_return"] / ohlcv["atr"].replace(0.0, np.nan)

        # Asset categorical
        ohlcv["asset"] = ohlcv["asset"].astype("category")

        # Drop NaNs properly.
        feature_cols = [
            "return_1",
            "return_2",
            "return_3",
            "atr",
            "rolling_std_20",
            "ema_fast",
            "ema_slow",
            "ema_slope",
            "ema_distance",
            "volume_zscore",
            "target",
        ]
        ohlcv = ohlcv.dropna(subset=feature_cols).reset_index(drop=True)

        return ohlcv


