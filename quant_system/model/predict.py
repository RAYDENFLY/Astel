"""Signal generation (inference).

For each new 4H candle (per asset):
- generate prediction
- Long if pred > threshold
- Short if pred < -threshold
- else no-trade

Returns structured signal objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from quant_system.model.model_utils import FEATURE_COLUMNS, load_pickle, load_threshold


@dataclass(frozen=True)
class Signal:
    timestamp: pd.Timestamp
    asset: str
    side: str  # "LONG" | "SHORT"
    prediction: float


class SignalGenerator:
    def __init__(self, cfg: Dict, models_dir: Path) -> None:
        self.cfg = cfg
        self.models_dir = models_dir
        self.log = logging.getLogger(self.__class__.__name__)

        self._model = None
        self._threshold: Optional[float] = None

    def is_ready(self) -> bool:
        if self._model is None or self._threshold is None:
            self._try_load()
        return self._model is not None and self._threshold is not None

    def _try_load(self) -> None:
        model_path = self.models_dir / "model.pkl"
        threshold_path = self.models_dir / "threshold.txt"
        if model_path.exists() and threshold_path.exists():
            self._model = load_pickle(model_path)
            self._threshold = load_threshold(threshold_path)

    def generate_signals(self, bar: pd.DataFrame) -> List[Signal]:
        """Generate signals for a cross-section (same timestamp) DataFrame."""
        if not self.is_ready():
            return []

        X = bar[["asset"] + FEATURE_COLUMNS].copy()
        preds = self._model.predict(X)

        out: List[Signal] = []
        thr = float(self._threshold)
        for i, row in bar.reset_index(drop=True).iterrows():
            p = float(preds[i])
            if p > thr:
                side = "LONG"
            elif p < -thr:
                side = "SHORT"
            else:
                continue

            out.append(
                Signal(
                    timestamp=pd.Timestamp(row["timestamp"]),
                    asset=str(row["asset"]),
                    side=side,
                    prediction=p,
                )
            )
        return out
