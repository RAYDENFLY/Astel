"""
agent/historical_replay.py — Phase 12.3 Historical Decision Replay Engine

Simulates historical decision-making step-by-step using historical OHLCV datasets.
STRICT NO-LOOKAHEAD BIAS GUARANTEE:
At timestamp T_i, decision generation receives market data strictly <= T_i.
Future market data (T_i+1 ... T_i+24) is ONLY inspected after decision creation
to compute forward returns and evaluate outcome accuracy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from quant_system.features.build_features import FeatureBuilder
from agent.market_intelligence import MarketIntelligence
from agent.decision_agent import DecisionAgent
from agent.risk_supervisor import RiskSupervisor
from agent.schema import (
    AssetAnalysis,
    DecisionProposal,
    RiskSupervisorReview,
    DecisionOutcome,
)

log = logging.getLogger("agent.historical_replay")


@dataclass
class ReplayConfig:
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    timeframe: str = "4h"
    assets: List[str] = field(default_factory=lambda: [
        "BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT", "AVAX_USDT",
        "LINK_USDT", "DOGE_USDT", "ADA_USDT", "LTC_USDT", "AAVE_USDT", "SUI_USDT"
    ])
    warmup_period: int = 75
    top_n: int = 3
    decision_horizon: int = 3       # Default 3 candles forward evaluation (12h for 4h candles)
    llm_replay_enabled: bool = False # Default deterministic mode to avoid API costs
    csv_dir: Path = Path("quant_system/data/csv")


class HistoricalReplayEngine:
    """
    Historical Replay Engine for simulating historical decisions without lookahead bias.
    """

    def __init__(
        self,
        config: Optional[ReplayConfig] = None,
        cfg_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        if config is None:
            config = ReplayConfig()
        self.config = config

        if cfg_dict is None:
            cfg_path = Path("quant_system/config.yaml")
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as f:
                    cfg_dict = yaml.safe_load(f) or {}
            else:
                cfg_dict = {}
        self.cfg = cfg_dict

        self.feature_builder = FeatureBuilder(self.cfg)
        self.intelligence = MarketIntelligence(cfg_dict=self.cfg)
        self.decision_agent = DecisionAgent(
            cfg_dict={"decision_agent": {"top_n": self.config.top_n, "disabled_llm_mode": not self.config.llm_replay_enabled}}
        )
        self.risk_supervisor = RiskSupervisor()

        # Load CSV data cache
        self._raw_data: Dict[str, pd.DataFrame] = {}
        self._load_datasets()

    def _load_datasets(self) -> None:
        """Load and validate historical CSV datasets for configured assets."""
        csv_dir = self.config.csv_dir
        if not csv_dir.exists():
            log.warning("HistoricalReplayEngine: CSV directory %s does not exist", csv_dir)
            return

        for asset in self.config.assets:
            csv_path = csv_dir / f"{asset}.csv"
            if not csv_path.exists():
                alt_path = csv_dir / f"{asset.replace('_', '')}.csv"
                if alt_path.exists():
                    csv_path = alt_path

            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    if "timestamp" in df.columns:
                        df["timestamp"] = pd.to_datetime(df["timestamp"])
                        df = df.sort_values("timestamp").reset_index(drop=True)
                        # Add asset column if missing
                        df["asset"] = asset
                        self._raw_data[asset] = df
                        log.info("Loaded %d candles for asset %s from %s", len(df), asset, csv_path)
                    else:
                        log.warning("CSV file %s missing timestamp column", csv_path)
                except Exception as e:
                    log.warning("Failed loading CSV %s: %s", csv_path, e)
            else:
                log.warning("CSV dataset not found for asset %s", asset)

    def run_replay(self) -> Tuple[List[DecisionOutcome], List[Dict[str, Any]]]:
        """
        Run historical decision replay step-by-step.
        Returns list of DecisionOutcome objects and raw decision logs.
        """
        if not self._raw_data:
            log.error("HistoricalReplayEngine: No historical datasets loaded")
            return [], []

        # Find common index range across loaded datasets
        min_candles = min(len(df) for df in self._raw_data.values())
        if min_candles <= self.config.warmup_period:
            log.error("Insufficient candles (%d) for warmup period (%d)", min_candles, self.config.warmup_period)
            return [], []

        outcomes: List[DecisionOutcome] = []
        raw_logs: List[Dict[str, Any]] = []

        log.info(
            "HistoricalReplayEngine: Starting replay from step %d to %d across %d assets...",
            self.config.warmup_period, min_candles, len(self._raw_data)
        )

        for step in range(self.config.warmup_period, min_candles):
            # 1. Prepare PAST-ONLY feature slices (STRICT NO-LOOKAHEAD BIAS)
            step_analyses: List[AssetAnalysis] = []
            asset_bars: Dict[str, pd.Series] = {}

            # First pass: compute indicators for each asset up to step (index <= step)
            for asset, df in self._raw_data.items():
                slice_df = df.iloc[: step + 1].copy()
                try:
                    feats_df = self.feature_builder.build(slice_df, is_training=False)
                    if not feats_df.empty:
                        latest_bar = feats_df.iloc[-1]
                        asset_bars[asset] = latest_bar
                except Exception as err:
                    log.warning("Replay feature build error for %s at step %d: %s", asset, step, err)

            if not asset_bars:
                continue

            # Extract BTC bar info as macro reference for alts
            btc_bar = asset_bars.get("BTC_USDT")
            btc_bar_info = dict(btc_bar) if btc_bar is not None else None

            # Build AssetAnalysis per asset at step timestamp
            for asset, bar in asset_bars.items():
                analysis = self._build_asset_analysis_at_step(asset, bar)

                # Enrich with Market Intelligence
                try:
                    evidences, summary = self.intelligence.analyze_asset_intelligence(
                        asset=asset,
                        tech_signal=analysis.ema_trend,
                        tech_score=analysis.momentum,
                        ml_signal=analysis.direction,
                        ml_score=analysis.prediction,
                        ml_confidence=analysis.confidence,
                        price_change_1h=analysis.momentum,
                        btc_bar_info=btc_bar_info,
                    )
                    analysis.market_evidence = evidences
                    analysis.evidence_summary = summary
                    analysis.agreement_score = summary.agreement
                    analysis.contradiction_level = summary.contradiction_level
                    analysis.evidence_quality = summary.evidence_quality
                    analysis.data_freshness_sec = summary.evidence_quality
                except Exception as intel_err:
                    log.warning("Replay intelligence error for %s: %s", asset, intel_err)

                step_analyses.append(analysis)

            # Rank assets by composite score
            step_analyses.sort(
                key=lambda a: (a.evidence_summary.weighted_score if a.evidence_summary else a.prediction) * a.confidence * a.probability,
                reverse=True,
            )
            for r, a in enumerate(step_analyses, start=1):
                a.rank = r

            # 2. Generate Decision Proposals & Risk Supervisor Reviews for Top N
            proposals = self.decision_agent.evaluate_scanned_assets(step_analyses)

            # 3. Compute OUTCOMES using FUTURE candles ONLY (index > step)
            for prop in proposals:
                asset = prop.asset
                df = self._raw_data.get(asset)
                if df is None:
                    continue

                entry_price = float(df.iloc[step]["close"])
                ts_str = str(df.iloc[step]["timestamp"])

                # Calculate forward returns for T+1, T+3, T+6, T+12, T+24
                ret_1 = self._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
                ret_3 = self._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
                ret_6 = self._calc_forward_return(df, step, horizon=6, entry_price=entry_price)
                ret_12 = self._calc_forward_return(df, step, horizon=12, entry_price=entry_price)
                ret_24 = self._calc_forward_return(df, step, horizon=24, entry_price=entry_price)

                # Select primary horizon return (e.g., ret_3)
                eval_ret = ret_3 if ret_3 is not None else ret_1

                # Determine direction correctness
                direction_correct = False
                if eval_ret is not None:
                    if prop.direction == "LONG" and eval_ret > 0:
                        direction_correct = True
                        outcome_class = "CORRECT"
                    elif prop.direction == "SHORT" and eval_ret < 0:
                        direction_correct = True
                        outcome_class = "CORRECT"
                    elif prop.direction in ("LONG", "SHORT"):
                        direction_correct = False
                        outcome_class = "INCORRECT"
                    else:
                        outcome_class = "NEUTRAL"
                else:
                    outcome_class = "INSUFFICIENT_DATA"

                fusion = prop.fusion_result
                outcome = DecisionOutcome(
                    decision_id=prop.decision_id,
                    asset=prop.asset,
                    timestamp=ts_str,
                    decision=prop.decision,
                    direction=prop.direction,
                    confidence=prop.confidence,
                    confidence_band=fusion.confidence_band if fusion else "NO_TRADE",
                    agreement_score=fusion.agreement_score if fusion else 0.0,
                    contradiction_level=fusion.contradiction_level if fusion else "INSUFFICIENT_DATA",
                    evidence_quality=fusion.evidence_quality if fusion else 0.0,
                    data_quality=prop.data_quality,
                    data_freshness=prop.freshness,
                    scanner_rank=prop.scanner_rank,
                    forward_return_1=ret_1 if ret_1 is not None else 0.0,
                    forward_return_3=ret_3 if ret_3 is not None else 0.0,
                    forward_return_6=ret_6 if ret_6 is not None else 0.0,
                    forward_return_12=ret_12 if ret_12 is not None else 0.0,
                    forward_return_24=ret_24 if ret_24 is not None else 0.0,
                    direction_correct=direction_correct,
                    outcome_class=outcome_class,
                    market_regime=step_analyses[0].market_regime if step_analyses else "NEUTRAL",
                    fusion_score=fusion.directional_score if fusion else 0.0,
                )
                outcomes.append(outcome)

                raw_logs.append({
                    "step": step,
                    "timestamp": ts_str,
                    "proposal": prop.model_dump(),
                    "outcome": outcome.model_dump(),
                })

        log.info("HistoricalReplayEngine: Replay complete. Evaluated %d decisions.", len(outcomes))
        return outcomes, raw_logs

    def _build_asset_analysis_at_step(self, asset: str, bar: pd.Series) -> AssetAnalysis:
        """Construct AssetAnalysis for a single asset bar at historical step T."""
        ret_1 = float(bar.get("return_1", 0.0) or 0.0)
        atr_val = float(bar.get("atr", 0.0) or 0.0)
        std_20 = float(bar.get("rolling_std_20", 0.0) or 0.0)
        ema_f = float(bar.get("ema_fast", 0.0) or 0.0)
        ema_s = float(bar.get("ema_slow", 0.0) or 0.0)
        ema_slope = float(bar.get("ema_slope", 0.0) or 0.0)
        ema_dist = float(bar.get("ema_distance", 0.0) or 0.0)
        rsi_val = float(bar.get("rsi", 50.0) or 50.0)

        prediction = ema_dist * 2.0 + ret_1 * 0.5
        thr = 0.005

        if prediction > thr:
            direction = "LONG"
        elif prediction < -thr:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        prob_raw = 0.50 + 0.38 * (abs(prediction) / (abs(prediction) + 0.01))
        probability = max(0.10, min(0.90, prob_raw))
        confidence = max(0.15, min(0.95, abs(prediction) / (abs(prediction) + 0.008)))

        ema_trend = "BULLISH" if ema_f >= ema_s else "BEARISH"
        regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

        return AssetAnalysis(
            asset=asset,
            direction=direction,
            probability=probability,
            confidence=confidence,
            prediction=prediction,
            threshold=thr,
            market_regime=regime,
            top_features={"return_1": ret_1, "ema_distance": ema_dist, "atr": atr_val},
            volatility=std_20,
            momentum=ret_1,
            atr=atr_val,
            rsi=rsi_val,
            ema_trend=ema_trend,
        )

    def _calc_forward_return(self, df: pd.DataFrame, step: int, horizon: int, entry_price: float) -> Optional[float]:
        """Calculate price return after horizon steps (forward looking ONLY)."""
        future_idx = step + horizon
        if future_idx < len(df):
            exit_price = float(df.iloc[future_idx]["close"])
            if entry_price > 0:
                return (exit_price - entry_price) / entry_price
        return None
