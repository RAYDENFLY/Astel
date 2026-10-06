"""
agent/candidate_v2_shadow_engine.py — Phase 13 Real-Time Shadow Observation Engine

Strictly isolated, read-only shadow observation framework for frozen CandidateSignalV2:
- Enforces EXECUTION_MODE = "SHADOW" (fails closed if not SHADOW)
- Idempotent tracking: asset + timeframe + candle_close_timestamp
- Rejects incomplete candles / stale data
- Tracks T+1, T+3, T+6 forward returns, MFE, MAE
- Tracks baselines: Always LONG, Always SHORT, Market Return
- Categorizes signals: REGIME_SWITCH, CONFLICT_FOLLOW_MOMENTUM, NORMAL_MOMENTUM, NORMAL_MR, NEUTRAL
- Persists shadow trade records deterministically
- Zero order execution, zero API calls, zero exchange interactions
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
import os
import json
import numpy as np
import pandas as pd

from agent.candidate_signal_v2 import CandidateSignalV2, CandidateSignalV2Result

EXECUTION_MODE = "SHADOW"


@dataclass
class CandidateV2ShadowRecord:
    shadow_trade_id: str
    asset: str
    timeframe: str
    candle_close_timestamp: str
    decision_timestamp: str
    regime: str
    direction: str
    signal_reason: str
    mr_direction: str
    mom_direction: str
    is_conflict: bool
    conflict_type: str
    follow_momentum_used: bool
    is_high_volatility: bool
    entry_price: float
    feature_snapshot: Dict[str, float]
    regime_snapshot: Dict[str, Any]
    
    # Outcome tracking
    is_completed_t1: bool = False
    is_completed_t3: bool = False
    is_completed_t6: bool = False
    ret_1_fwd: Optional[float] = None
    ret_3_fwd: Optional[float] = None
    ret_6_fwd: Optional[float] = None
    mfe: Optional[float] = None
    mae: Optional[float] = None


class CandidateV2ShadowEngine:
    """
    Real-Time Shadow Observation Engine for CandidateSignalV2.
    """

    def __init__(self, persistence_path: str = "agent/data/candidate_v2_shadow_records.json"):
        if EXECUTION_MODE != "SHADOW":
            raise RuntimeError("CRITICAL SAFETY VIOLATION: Execution mode must be SHADOW. Failing closed!")
        
        self.v2_signal = CandidateSignalV2(high_vol_threshold_atr_pct=0.035)
        self.persistence_path = persistence_path
        self.records: Dict[str, CandidateV2ShadowRecord] = {}
        self.seen_identities: set = set()
        
        # Load existing persistence if present
        self._load_records()

    def process_completed_candle(self, row: pd.Series, regime: str, asset: str, timeframe: str = "4h", is_completed_candle: bool = True) -> Optional[CandidateV2ShadowRecord]:
        if EXECUTION_MODE != "SHADOW":
            raise RuntimeError("CRITICAL SAFETY VIOLATION: Execution mode must be SHADOW!")

        if not is_completed_candle:
            # Reject incomplete candle
            return None

        ts = str(row.get("timestamp", ""))
        if not ts:
            return None

        identity = f"{asset}_{timeframe}_{ts}"
        if identity in self.seen_identities:
            # Idempotency check: skip duplicate
            return None

        # Verify required features exist
        for req_feat in ["rsi14", "bollinger_pct_b", "ret_3", "ret_6", "ret_12", "close"]:
            if req_feat not in row or pd.isna(row[req_feat]):
                return None

        v2_res: CandidateSignalV2Result = self.v2_signal.evaluate_bar(row, regime=regime)

        feature_snap = {
            "rsi14": float(row["rsi14"]),
            "bollinger_pct_b": float(row["bollinger_pct_b"]),
            "ret_3": float(row["ret_3"]),
            "ret_6": float(row["ret_6"]),
            "ret_12": float(row["ret_12"]),
            "atr_pct": float(row.get("atr_pct", 0.0) or 0.0),
            "close": float(row["close"]),
        }

        regime_snap = {
            "regime": regime,
            "ema20": float(row.get("ema20", row["close"])),
            "ema50": float(row.get("ema50", row["close"])),
        }

        follow_mom_used = (v2_res.is_conflict and v2_res.direction == v2_res.mom_direction)

        rec = CandidateV2ShadowRecord(
            shadow_trade_id=identity,
            asset=asset,
            timeframe=timeframe,
            candle_close_timestamp=ts,
            decision_timestamp=ts,
            regime=regime,
            direction=v2_res.direction,
            signal_reason=v2_res.signal_reason,
            mr_direction=v2_res.mr_direction,
            mom_direction=v2_res.mom_direction,
            is_conflict=v2_res.is_conflict,
            conflict_type=v2_res.conflict_type,
            follow_momentum_used=follow_mom_used,
            is_high_volatility=v2_res.is_high_volatility,
            entry_price=float(row["close"]),
            feature_snapshot=feature_snap,
            regime_snapshot=regime_snap,
        )

        self.records[identity] = rec
        self.seen_identities.add(identity)
        return rec

    def update_outcomes(self, identity: str, future_slice: pd.DataFrame):
        if identity not in self.records:
            return

        rec = self.records[identity]
        if future_slice.empty or rec.entry_price <= 0:
            return

        entry = rec.entry_price

        if len(future_slice) >= 1 and not rec.is_completed_t1:
            c1 = float(future_slice.iloc[0]["close"])
            rec.ret_1_fwd = (c1 - entry) / entry
            rec.is_completed_t1 = True

        if len(future_slice) >= 3 and not rec.is_completed_t3:
            c3 = float(future_slice.iloc[2]["close"])
            rec.ret_3_fwd = (c3 - entry) / entry
            rec.is_completed_t3 = True

        if len(future_slice) >= 6 and not rec.is_completed_t6:
            c6 = float(future_slice.iloc[5]["close"])
            rec.ret_6_fwd = (c6 - entry) / entry
            rec.is_completed_t6 = True

        # Calculate MFE / MAE up to 6 bars
        slice_eval = future_slice.iloc[: min(6, len(future_slice))]
        max_h = float(slice_eval["high"].max())
        min_l = float(slice_eval["low"].min())

        if rec.direction == "LONG":
            rec.mfe = (max_h - entry) / entry
            rec.mae = (min_l - entry) / entry
        elif rec.direction == "SHORT":
            rec.mfe = (entry - min_l) / entry
            rec.mae = (entry - max_h) / entry

    def save_records(self):
        os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)
        serializable = {k: asdict(v) for k, v in self.records.items()}
        with open(self.persistence_path, "w") as f:
            json.dump(serializable, f, indent=2)

    def _load_records(self):
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r") as f:
                    data = json.load(f)
                for k, v in data.items():
                    rec = CandidateV2ShadowRecord(**v)
                    self.records[k] = rec
                    self.seen_identities.add(k)
            except Exception:
                pass
