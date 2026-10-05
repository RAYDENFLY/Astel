"""
agent/market_scanner.py — Live Market Scanner Module

Scans all configured assets (12 assets from config.yaml) every tick:
- Downloads live OHLCV candles from Gate.io via GateDataFetcher
- Builds indicators using FeatureBuilder (momentum, volatility, trend, volume, RSI)
- Performs ML prediction using LightGBM model
- Ranks and outputs structured AssetAnalysis per asset
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

from quant_system.data.gate_data import GateDataFetcher
from quant_system.execution.gate_executor import GateExecutor
from quant_system.features.build_features import FeatureBuilder
from quant_system.model.model_utils import FEATURE_COLUMNS, load_pickle, load_threshold
from agent.schema import AssetAnalysis, AgentSnapshot, AccountSnapshot, SurvivalMode, AgentMode

log = logging.getLogger("agent.market_scanner")


class MarketScanner:
    """
    MarketScanner integrates the offline quant pipeline with the live agent runtime.
    """

    def __init__(
        self,
        cfg: Optional[Dict[str, Any]] = None,
        config_path: Optional[Path] = None,
        models_dir: Optional[Path] = None,
    ) -> None:
        if cfg is None:
            if config_path is None:
                config_path = Path("quant_system/config.yaml")
            with config_path.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

        self.cfg = cfg
        self.assets: List[str] = list(self.cfg.get("assets", [
            "BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT", "AVAX_USDT",
            "LINK_USDT", "DOGE_USDT", "ADA_USDT", "LTC_USDT", "AAVE_USDT", "SUI_USDT"
        ]))

        if models_dir is None:
            models_dir_path = (self.cfg.get("paths") or {}).get("models_dir", "quant_system/models")
            models_dir = Path(models_dir_path)

        self.models_dir = models_dir
        self._feature_builder = FeatureBuilder(self.cfg)

        # Gate executor setup (public REST endpoints require no secrets)
        gate_cfg = self.cfg.get("gate") or {}
        base_url = gate_cfg.get("base_url", "https://api-testnet.gateapi.io/api/v4")
        api_key = os.environ.get("GATE_API_KEY", "")
        api_secret = os.environ.get("GATE_API_SECRET", "")

        self._executor = GateExecutor(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url if isinstance(base_url, str) else "https://api-testnet.gateapi.io/api/v4",
            fee_rate=0.0004,
            slippage=0.0002,
        )

        self._fetcher = GateDataFetcher(cfg=self.cfg, executor=self._executor)

        # Load ML model & threshold
        self._model = None
        self._threshold = 0.0
        self._load_model()

    def _load_model(self) -> None:
        model_path = self.models_dir / "model.pkl"
        threshold_path = self.models_dir / "threshold.txt"

        if model_path.exists() and threshold_path.exists():
            try:
                self._model = load_pickle(model_path)
                self._threshold = load_threshold(threshold_path)
                log.info("MarketScanner: loaded model from %s (threshold=%.6f)", model_path, self._threshold)
            except Exception as e:
                log.warning("MarketScanner: failed loading model from %s: %s", model_path, e)
        else:
            log.warning(
                "MarketScanner: model or threshold missing at %s. Will fallback to rule-based signal.",
                self.models_dir,
            )

    def scan_all_assets(self, limit_candles: int = 150) -> List[AssetAnalysis]:
        """
        Scan every configured asset using live OHLCV from Gate.io.
        Returns list of AssetAnalysis ordered by rank.
        """
        log.info("MarketScanner: starting scan for %d assets...", len(self.assets))
        results: List[AssetAnalysis] = []

        try:
            ohlcv_df = self._fetcher.load_ohlcv(
                limit=limit_candles,
                exclude_last_open_candle=False,
                persist_to_csv=True,
            )
        except Exception as fetch_err:
            log.warning("MarketScanner: load_ohlcv failed: %s", fetch_err)
            return results

        if ohlcv_df.empty:
            log.warning("MarketScanner: no OHLCV data returned")
            return results

        # Build indicators using FeatureBuilder with is_training=False so latest candle is preserved
        try:
            feats_df = self._feature_builder.build(ohlcv_df, is_training=False)
        except Exception as feat_err:
            log.warning("MarketScanner: build_features failed: %s", feat_err)
            return results

        if feats_df.empty:
            log.warning("MarketScanner: feature dataframe is empty")
            return results

        # Process latest feature bar for each asset
        for asset in self.assets:
            asset_rows = feats_df[feats_df["asset"] == asset]
            if asset_rows.empty:
                # Retry search by alt name (e.g. BTCUSDT)
                alt = asset.replace("_", "")
                asset_rows = feats_df[feats_df["asset"] == alt]

            if asset_rows.empty:
                log.warning("MarketScanner: no feature rows found for asset %s", asset)
                continue

            # Pick the latest bar
            latest_bar = asset_rows.sort_values("timestamp").iloc[-1]
            analysis = self._analyze_asset_bar(asset, latest_bar)
            results.append(analysis)

        # Rank assets by signal strength (composite of abs(prediction), probability, confidence)
        results.sort(key=lambda a: (abs(a.prediction) * a.confidence * a.probability), reverse=True)

        for i, res in enumerate(results, start=1):
            res.rank = i

        log.info(
            "MarketScanner: scan complete. Analyzed %d/%d assets. Top 3: %s",
            len(results), len(self.assets),
            [f"{a.asset}({a.direction}, prob={a.probability:.0%})" for a in results[:3]]
        )

        return results

    def _analyze_asset_bar(self, asset: str, bar: pd.Series) -> AssetAnalysis:
        """Process a single asset's latest feature bar."""
        # 1. Feature values
        ret_1 = float(bar.get("return_1", 0.0) or 0.0)
        ret_3 = float(bar.get("return_3", 0.0) or 0.0)
        atr_val = float(bar.get("atr", 0.0) or 0.0)
        std_20 = float(bar.get("rolling_std_20", 0.0) or 0.0)
        ema_f = float(bar.get("ema_fast", 0.0) or 0.0)
        ema_s = float(bar.get("ema_slow", 0.0) or 0.0)
        ema_slope = float(bar.get("ema_slope", 0.0) or 0.0)
        ema_dist = float(bar.get("ema_distance", 0.0) or 0.0)
        vol_z = float(bar.get("volume_zscore", 0.0) or 0.0)
        rsi_val = float(bar.get("rsi", 50.0) or 50.0)

        # 2. Prediction
        prediction = 0.0
        thr = self._threshold if self._threshold > 0 else 0.005

        if self._model is not None:
            try:
                # Prepare single-row DataFrame for model prediction
                X_dict = {"asset": [asset]}
                for col in FEATURE_COLUMNS:
                    X_dict[col] = [float(bar.get(col, 0.0) or 0.0)]
                X_df = pd.DataFrame(X_dict)
                X_df["asset"] = X_df["asset"].astype("category")
                pred_arr = self._model.predict(X_df)
                prediction = float(pred_arr[0])
            except Exception as pred_err:
                log.warning("Prediction error for %s: %s", asset, pred_err)
                prediction = ema_dist * 2.0  # Heuristic fallback based on EMA distance
        else:
            # Fallback heuristic prediction
            prediction = ema_dist * 2.0 + ret_1 * 0.5

        # 3. Direction
        if prediction > thr:
            direction = "LONG"
        elif prediction < -thr:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # 4. Probability (sigmoid mapping centered around threshold)
        # Scaled so that prediction at thr gives ~65% probability, 2*thr gives ~85%
        scale = 3.0 / max(0.001, thr)
        prob_raw = 1.0 / (1.0 + math.exp(-prediction * scale))
        if direction == "SHORT":
            # Probability of winning the short trade
            prob_raw = 1.0 / (1.0 + math.exp(prediction * scale))
        elif direction == "NEUTRAL":
            prob_raw = 0.50

        probability = max(0.05, min(0.95, prob_raw))

        # 5. Confidence (ratio of magnitude to threshold)
        conf_raw = abs(prediction) / max(0.0001, thr)
        confidence = max(0.10, min(0.99, conf_raw / (conf_raw + 1.0)))

        # 6. EMA Trend & Market Regime
        ema_trend = "BULLISH" if ema_f >= ema_s else "BEARISH"

        if ema_f > ema_s and ema_slope > 0:
            regime = "BULLISH_TREND"
        elif ema_f < ema_s and ema_slope < 0:
            regime = "BEARISH_TREND"
        elif std_20 > 0.035:
            regime = "HIGH_VOLATILITY"
        else:
            regime = "NEUTRAL_CONSOLIDATION"

        # 7. Top features dict
        top_features = {
            "return_1": ret_1,
            "return_3": ret_3,
            "ema_distance": ema_dist,
            "volume_zscore": vol_z,
            "atr": atr_val,
            "rolling_std_20": std_20,
        }

        return AssetAnalysis(
            asset=asset,
            direction=direction,
            probability=probability,
            confidence=confidence,
            prediction=prediction,
            threshold=thr,
            market_regime=regime,
            top_features=top_features,
            volatility=std_20,
            momentum=ret_1,
            atr=atr_val,
            rsi=rsi_val,
            ema_trend=ema_trend,
        )
