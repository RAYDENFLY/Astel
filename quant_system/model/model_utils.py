"""Model utilities: feature list, persistence, versioning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import joblib


FEATURE_COLUMNS: List[str] = [
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
]


@dataclass(frozen=True)
class ModelArtifacts:
    model_path: Path
    threshold_path: Path
    model_version: str
    threshold: float


def make_model_version(prefix: str = "GLM") -> str:
    now = datetime.now(timezone.utc)
    return f"{prefix}_{now.strftime('%Y%m%d')}"


def save_pickle(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, path)


def load_pickle(path: Path) -> object:
    return joblib.load(path)


def save_threshold(threshold: float, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{threshold:.12f}", encoding="utf-8")


def load_threshold(path: Path) -> float:
    return float(path.read_text(encoding="utf-8").strip())
