"""
agent/regime_signal_research.py — Isolated Phase 12.8 Regime-Conditioned Research Module (REGIME_SWITCH_V1 & CONFLICT Analysis)

Implements frozen, research-backed regime switching and conflict resolution rules:
1. REGIME_SWITCH_V1:
   - BULLISH_TREND -> Multi-Horizon Momentum direction
   - BEARISH_TREND -> Mean-Reversion direction
   - CONSOLIDATION -> Mean-Reversion direction
   - HIGH_VOLATILITY -> NEUTRAL
2. CONFLICT Resolution Interpretations:
   - FOLLOW_MR
   - FOLLOW_MOMENTUM
   - INVERSE_MR
   - INVERSE_MOMENTUM
   - ALWAYS_LONG
   - ALWAYS_SHORT
   - NEUTRAL
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

from agent.candidate_signal import CandidateSignalV1, CandidateSignalResult


@dataclass(frozen=True)
class RegimeSwitchResult:
    regime: str
    mr_direction: str
    mom_direction: str
    is_conflict: bool
    conflict_type: str             # "MR_LONG_MOM_SHORT", "MR_SHORT_MOM_LONG", "NONE"
    is_high_volatility: bool
    regime_switch_direction: str   # REGIME_SWITCH_V1 output
    conflict_follow_mr: str
    conflict_follow_mom: str
    conflict_inverse_mr: str
    conflict_inverse_mom: str
    conflict_always_long: str
    conflict_always_short: str


class RegimeSignalResearchEngine:
    """
    Regime-Conditioned Signal Research Orchestrator.
    Read-only, non-production, isolated research evaluation path.
    """

    def __init__(self, high_vol_threshold_atr_pct: float = 0.035):
        self.candidate_v1 = CandidateSignalV1()
        self.high_vol_threshold = high_vol_threshold_atr_pct

    def evaluate_bar(self, row: pd.Series, regime: str) -> RegimeSwitchResult:
        cand_res: CandidateSignalResult = self.candidate_v1.evaluate_bar(row)
        atr_pct = float(row.get("atr_pct", 0.0) or 0.0)

        is_high_vol = (atr_pct >= self.high_vol_threshold)

        # Conflict identification & categorization
        mr_dir = cand_res.mr_direction
        mom_dir = cand_res.mom_direction

        is_conflict = (mr_dir != "NEUTRAL" and mom_dir != "NEUTRAL" and mr_dir != mom_dir)

        if mr_dir == "LONG" and mom_dir == "SHORT":
            conflict_type = "MR_LONG_MOM_SHORT"
        elif mr_dir == "SHORT" and mom_dir == "LONG":
            conflict_type = "MR_SHORT_MOM_LONG"
        else:
            conflict_type = "NONE"

        # REGIME_SWITCH_V1 rule
        if is_high_vol or regime == "HIGH_VOLATILITY":
            regime_switch_direction = "NEUTRAL"
        elif regime == "BULLISH_TREND":
            regime_switch_direction = mom_dir
        elif regime in ("BEARISH_TREND", "CONSOLIDATION"):
            regime_switch_direction = mr_dir
        else:
            regime_switch_direction = "NEUTRAL"

        # Conflict interpretation directions
        if is_conflict:
            c_follow_mr = mr_dir
            c_follow_mom = mom_dir
            c_inv_mr = "SHORT" if mr_dir == "LONG" else "LONG"
            c_inv_mom = "SHORT" if mom_dir == "LONG" else "LONG"
            c_always_long = "LONG"
            c_always_short = "SHORT"
        else:
            c_follow_mr = "NEUTRAL"
            c_follow_mom = "NEUTRAL"
            c_inv_mr = "NEUTRAL"
            c_inv_mom = "NEUTRAL"
            c_always_long = "NEUTRAL"
            c_always_short = "NEUTRAL"

        return RegimeSwitchResult(
            regime=regime,
            mr_direction=mr_dir,
            mom_direction=mom_dir,
            is_conflict=is_conflict,
            conflict_type=conflict_type,
            is_high_volatility=is_high_vol,
            regime_switch_direction=regime_switch_direction,
            conflict_follow_mr=c_follow_mr,
            conflict_follow_mom=c_follow_mom,
            conflict_inverse_mr=c_inv_mr,
            conflict_inverse_mom=c_inv_mom,
            conflict_always_long=c_always_long,
            conflict_always_short=c_always_short,
        )
