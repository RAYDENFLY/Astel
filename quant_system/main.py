"""Main engine for the quant system.

Runs a simple bar-by-bar backtest-style loop over 4H data:
- loads OHLCV
- builds features/target
- (re)trains model on weekly schedule using a rolling window
- generates signals, applies risk rules
- executes trades via mock executor
- logs to SQLite
- produces a weekly performance report

This is intentionally offline and uses a mock execution layer (no exchange API calls).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yaml

from quant_system.data.fetch_data import DataFetcher
from quant_system.database.db import Database
from quant_system.database.journal import Journal
from quant_system.execution.gate_executor import GateExecutor
from quant_system.execution.mock_executor import MockExecutor
from quant_system.features.build_features import FeatureBuilder
from quant_system.model.predict import SignalGenerator
from quant_system.model.train import ModelTrainer
from quant_system.risk.risk_manager import RiskManager
from quant_system.reporting.weekly_report import WeeklyReporter


@dataclass(frozen=True)
class Config:
    raw: Dict

    @property
    def assets(self) -> List[str]:
        return list(self.raw["assets"])


def load_config(config_path: Path) -> Dict:
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(cfg: Dict) -> None:
    level_name = str(cfg.get("logging", {}).get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _is_monday_00(ts: pd.Timestamp) -> bool:
    ts = pd.Timestamp(ts)
    return ts.dayofweek == 0 and ts.hour == 0


def run_engine(config_path: Path) -> None:
    cfg = load_config(config_path)
    setup_logging(cfg)
    log = logging.getLogger("quant_system")

    execution_mode = str(cfg.get("execution_mode", "mock")).lower()

    paths = cfg["paths"]
    db_path = Path(paths["db_path"])
    schema_path = Path(paths["schema_path"])
    models_dir = Path(paths["models_dir"])
    reports_dir = Path(paths["reports_dir"])
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    db = Database(db_path=db_path, schema_path=schema_path)
    db.initialize()
    journal = Journal(db)

    fetcher = DataFetcher(cfg)
    fb = FeatureBuilder(cfg)
    trainer = ModelTrainer(cfg, models_dir=models_dir)
    signaler = SignalGenerator(cfg, models_dir=models_dir)
    risk = RiskManager(cfg)

    if execution_mode == "gate":
        # This engine is an offline research loop which assumes mock-style position objects
        # and simulated exits. For live trading with Gate, implement a dedicated live runner
        # (polling websocket/REST candles, submitting orders, and reading exchange positions).
        raise RuntimeError(
            "execution_mode='gate' requires a dedicated live runner. "
            "Keep execution_mode='mock' for the offline engine."
        )
    else:
        executor = MockExecutor(cfg)
    reporter = WeeklyReporter(cfg, reports_dir=reports_dir)

    ohlcv = fetcher.load_ohlcv()
    feats = fb.build(ohlcv)

    # We run on rows where features are available (target may be NaN at the end).
    feats = feats.sort_values(["timestamp", "asset"]).reset_index(drop=True)

    equity = float(cfg["risk"]["starting_equity"])
    open_positions: Dict[str, Dict] = {}

    # Drive the loop with unique timestamps.
    timestamps = feats["timestamp"].drop_duplicates().sort_values().to_list()
    last_week_id: Optional[str] = None

    for ts in timestamps:
        ts = pd.Timestamp(ts)

        # Weekly retraining trigger (Monday 00:00 in dataset timezone).
        if cfg["system"]["retrain_frequency"] == "weekly" and _is_monday_00(ts):
            # Train on all data strictly before this timestamp.
            train_df = feats[feats["timestamp"] < ts].copy()
            if len(train_df) > 0:
                model_art = trainer.train(train_df)
                log.info(
                    "Model trained: version=%s threshold=%.6f",
                    model_art.model_version,
                    model_art.threshold,
                )

        # Slice current bar across assets.
        bar = feats[feats["timestamp"] == ts].copy()
        if bar.empty:
            continue

        # 1) Check exits first (stop or time exit next close).
        for asset, pos in list(open_positions.items()):
            asset_row = bar[bar["asset"] == asset]
            if asset_row.empty:
                continue
            row = asset_row.iloc[0]
            exit_result = executor.check_exit(position=pos, bar=row)
            if exit_result is not None:
                pnl = float(exit_result["pnl"])
                equity += pnl
                journal.log_trade_exit(exit_result)
                journal.update_equity(ts=ts, equity=equity)
                del open_positions[asset]

        # 2) Generate new entries.
        # Avoid entry if we don't have a trained model yet.
        if not signaler.is_ready():
            continue

        signals = signaler.generate_signals(bar)
        for sig in signals:
            asset = sig.asset
            if asset in open_positions:
                continue

            rm = risk.size_position(
                signal=sig,
                bar=bar[bar["asset"] == asset].iloc[0],
                equity=equity,
                open_positions=open_positions,
            )
            if rm is None:
                continue

            entry = executor.enter_trade(signal=sig, bar=bar[bar["asset"] == asset].iloc[0], risk_meta=rm)
            if entry is None:
                continue

            journal.log_trade_entry(entry)
            open_positions[asset] = entry

        # 3) Weekly metrics + report on Mondays 00:00 after processing.
        week_id = ts.strftime("%G-W%V")
        if last_week_id is None:
            last_week_id = week_id
        if week_id != last_week_id:
            metrics = reporter.compute_weekly_metrics(db=db, week_id=last_week_id)
            if metrics is not None:
                journal.store_weekly_metrics(metrics)
                reporter.print_report(metrics)
                reporter.save_csv(metrics)
            last_week_id = week_id

    # Final weekly report for the last week in the dataset.
    if last_week_id is not None:
        metrics = reporter.compute_weekly_metrics(db=db, week_id=last_week_id)
        if metrics is not None:
            journal.store_weekly_metrics(metrics)
            reporter.print_report(metrics)
            reporter.save_csv(metrics)

    log.info("Run complete. Final equity: %.2f", equity)


def main() -> None:
    root = Path(__file__).resolve().parent
    config_path = root / "config.yaml"
    run_engine(config_path)


if __name__ == "__main__":
    main()
