"""Train model using Gate exchange candles for all configured pairs.

This script:
- loads `quant_system/config.yaml`
- downloads historical candles for each configured asset from Gate (public endpoint)
- builds features
- trains the global LightGBM model

It will automatically skip assets that don't exist on the current Gate environment
(e.g., testnet has fewer contracts).

Usage (PowerShell):
  python scripts\train_from_gate.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quant_system.utils.env import load_dotenv
from quant_system.execution.gate_executor import GateExecutor
from quant_system.data.gate_data import GateDataFetcher
from quant_system.features.build_features import FeatureBuilder
from quant_system.model.train import ModelTrainer


def main() -> None:
    root = ROOT
    cfg = yaml.safe_load((root / "quant_system" / "config.yaml").read_text(encoding="utf-8"))

    load_dotenv()
    api_key = os.getenv("GATE_API_KEY")
    api_secret = os.getenv("GATE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("Missing GATE_API_KEY/GATE_API_SECRET in environment (or .env)")

    models_dir = root / cfg["paths"]["models_dir"]
    models_dir.mkdir(parents=True, exist_ok=True)

    executor = GateExecutor(
        api_key=api_key,
        api_secret=api_secret,
        base_url=str(cfg["gate"]["base_url"]),
        fee_rate=float(cfg["execution"]["fee_rate"]),
        slippage=float(cfg["execution"]["slippage_bps"]) / 10000.0,
    )

    fetcher = GateDataFetcher(cfg=cfg, executor=executor)
    ohlcv = fetcher.load_ohlcv(persist_to_csv=True)

    fb = FeatureBuilder(cfg)
    feats = fb.build(ohlcv)

    trainer = ModelTrainer(cfg, models_dir=models_dir)
    art = trainer.train(feats)

    print(f"trained model_version={art.model_version} threshold={art.threshold:.6f}")


if __name__ == "__main__":
    main()
