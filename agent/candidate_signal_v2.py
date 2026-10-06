"""
agent/candidate_signal_v2.py — Frozen Candidate Signal Architecture V2

Implements strictly frozen CandidateSignalV2 logic:
1. Rule A — Regime Conditioning:
   - BULLISH_TREND -> Multi-Horizon Momentum
   - BEARISH_TREND -> Mean-Reversion
   - CONSOLIDATION -> Multi-Horizon Momentum
   - HIGH_VOLATILITY -> NEUTRAL
2. Rule B — Conflict Resolution:
   - MR LONG + MOM SHORT -> SHORT (FOLLOW_MOMENTUM)
   - MR SHORT + MOM LONG -> LONG (FOLLOW_MOMENTUM)
3. Rule C — Normal Signals:
   - MR LONG: RSI14 < 35 & %B < 0.10
   - MR SHORT: RSI14 > 65 & %B > 0.90
   - MOM LONG: ret_3 > 0 & ret_6 > 0 & ret_12 > 0
   - MOM SHORT: ret_3 < 0 & ret_6 < 0 & ret_12 < 0
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import pandas as pd

from agent.candidate_signal import CandidateSignalV1, CandidateSignalResult


@dataclass(frozen=True)
class CandidateSignalV2Result:
    regime: str
    mr_direction: str
    mom_direction: str
    is_conflict: bool
    conflict_type: str            # "MR_LONG_MOM_SHORT", "MR_SHORT_MOM_LONG", "NONE"
    is_high_volatility: bool
    direction: str                # Frozen Candidate V2 output direction
    signal_reason: str            # "CONFLICT_MOMENTUM", "REGIME_MOMENTUM", "REGIME_MR", "HIGH_VOL_NEUTRAL", "NEUTRAL"


class CandidateSignalV2:
    """
    Frozen Candidate Signal V2 Orchestrator.
    Read-only, non-production, isolated research evaluation path.
    """

    def __init__(self, high_vol_threshold_atr_pct: float = 0.035):
        self.candidate_v1 = CandidateSignalV1()
        self.high_vol_threshold = high_vol_threshold_atr_pct

    def evaluate_bar(self, row: pd.Series, regime: str) -> CandidateSignalV2Result:
        cand_res: CandidateSignalResult = self.candidate_v1.evaluate_bar(row)
        atr_pct = float(row.get("atr_pct", 0.0) or 0.0)

        is_high_vol = (atr_pct >= self.high_vol_threshold) or (regime == "HIGH_VOLATILITY")

        mr_dir = cand_res.mr_direction
        mom_dir = cand_res.mom_direction

        is_conflict = (mr_dir != "NEUTRAL" and mom_dir != "NEUTRAL" and mr_dir != mom_dir)

        if mr_dir == "LONG" and mom_dir == "SHORT":
            conflict_type = "MR_LONG_MOM_SHORT"
        elif mr_dir == "SHORT" and mom_dir == "LONG":
            conflict_type = "MR_SHORT_MOM_LONG"
        else:
            conflict_type = "NONE"

        # Frozen Rule Engine
        if is_high_vol:
            direction = "NEUTRAL"
            reason = "HIGH_VOL_NEUTRAL"
        elif is_conflict:
            # Rule B: CONFLICT RESOLUTION -> FOLLOW_MOMENTUM
            direction = mom_dir
            reason = "CONFLICT_MOMENTUM"
        elif regime in ("BULLISH_TREND", "CONSOLIDATION"):
            # Rule A: BULLISH / CONSOLIDATION -> Momentum
            direction = mom_dir
            reason = "REGIME_MOMENTUM"
        elif regime == "BEARISH_TREND":
            # Rule A: BEARISH -> Mean-Reversion
            direction = mr_dir
            reason = "REGIME_MR"
        else:
            direction = "NEUTRAL"
            reason = "NEUTRAL"

        return CandidateSignalV2Result(
            regime=regime,
            mr_direction=mr_dir,
            mom_direction=mom_dir,
            is_conflict=is_conflict,
            conflict_type=conflict_type,
            is_high_volatility=is_high_vol,
            direction=direction,
            signal_reason=reason,
        )
