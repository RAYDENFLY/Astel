"""Model training.

- Global LightGBMRegressor across all assets
- Asset treated as a categorical feature
- Rolling training window in months (config)
- Time-based validation split: last 20% of the window
- Threshold computed as quantile of abs(pred) on validation

Artifacts saved to /models:
- model.pkl
- threshold.txt
- model_version.txt

Logs RMSE and IC (corr(pred, target)) on validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error

from quant_system.model.model_utils import (
    FEATURE_COLUMNS,
    ModelArtifacts,
    make_model_version,
    save_pickle,
    save_threshold,
)


@dataclass(frozen=True)
class TrainedModel:
    model: LGBMRegressor
    threshold: float
    model_version: str


class ModelTrainer:
    def __init__(self, cfg: Dict, models_dir: Path) -> None:
        self.cfg = cfg
        self.models_dir = models_dir
        self.log = logging.getLogger(self.__class__.__name__)

    def train(self, data: pd.DataFrame) -> ModelArtifacts:
        """Train on a rolling window ending at the latest timestamp in `data`."""
        window_months = int(self.cfg["system"]["rolling_window_months"])
        cutoff = pd.Timestamp(data["timestamp"].max()).tz_convert("UTC")
        start = cutoff - pd.DateOffset(months=window_months)
        window = data[(data["timestamp"] >= start) & (data["timestamp"] <= cutoff)].copy()
        window = window.sort_values(["timestamp", "asset"]).reset_index(drop=True)

        min_rows = int(self.cfg.get("model", {}).get("min_train_rows", 200))
        if len(window) < min_rows:
            self.log.warning(
                "Not enough rows to train (%d < %d). Skipping training.",
                len(window),
                min_rows,
            )
            raise ValueError("Insufficient training data")

        X = window[["asset"] + FEATURE_COLUMNS].copy()
        y = window["target"].astype(float)

        # Time-based split: last 20% for validation
        split_idx = int(len(window) * 0.8)
        X_train, X_val = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_val = y.iloc[:split_idx], y.iloc[split_idx:]

        params = dict(self.cfg["model"]["params"])
        model = LGBMRegressor(**params)

        # LightGBM handles pandas categorical dtype.
        model.fit(X_train, y_train)

        pred_val = model.predict(X_val)
        rmse = float(np.sqrt(mean_squared_error(y_val, pred_val)))
        ic = float(np.corrcoef(pred_val, y_val)[0, 1]) if len(y_val) > 1 else float("nan")

        q = float(self.cfg["strategy"]["threshold_quantile"])
        threshold = float(np.quantile(np.abs(pred_val), q))

        self.log.info("Validation RMSE: %.6f", rmse)
        self.log.info("Validation IC: %.6f", ic)
        self.log.info("Threshold (q=%.2f of |pred|): %.6f", q, threshold)

        model_version = make_model_version(prefix="GLM")
        model_path = self.models_dir / "model.pkl"
        threshold_path = self.models_dir / "threshold.txt"
        version_path = self.models_dir / "model_version.txt"

        save_pickle(model, model_path)
        save_threshold(threshold, threshold_path)
        version_path.write_text(model_version, encoding="utf-8")

        return ModelArtifacts(
            model_path=model_path,
            threshold_path=threshold_path,
            model_version=model_version,
            threshold=threshold,
        )
