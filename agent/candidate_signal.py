"""
agent/candidate_signal.py — Isolated Phase 12.7 Candidate Signal Architecture (candidate_signal_v1)

Implements frozen, research-backed candidate signal logic without modifying production components:
1. Subsystem A: Mean-Reversion (RSI14 < 35 & %B < 0.10 -> LONG; RSI14 > 65 & %B > 0.90 -> SHORT)
2. Subsystem B: Multi-Horizon Momentum (ret_3 > 0 & ret_6 > 0 & ret_12 > 0 -> LONG; ret_3 < 0 & ret_6 < 0 & ret_12 < 0 -> SHORT)
3. Momentum Conflict Check (ret_3 * ret_12 < 0)
4. Deterministic Categorical Fusion:
   - HIGH_CONSISTENCY_LONG (MR LONG + MOM LONG)
   - HIGH_CONSISTENCY_SHORT (MR SHORT + MOM SHORT)
   - SINGLE_FACTOR_LONG (One LONG, one NEUTRAL)
   - SINGLE_FACTOR_SHORT (One SHORT, one NEUTRAL)
   - CONFLICT (Opposing directions)
   - NEUTRAL (Both NEUTRAL)
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CandidateSignalResult:
    mr_direction: str          # "LONG", "SHORT", "NEUTRAL"
    mom_direction: str         # "LONG", "SHORT", "NEUTRAL"
    mom_conflict: bool         # True if ret_3 * ret_12 < 0
    fused_state: str           # HIGH_CONSISTENCY_LONG, HIGH_CONSISTENCY_SHORT, SINGLE_FACTOR_LONG, SINGLE_FACTOR_SHORT, CONFLICT, NEUTRAL
    direction: str             # "LONG", "SHORT", "NEUTRAL"
    is_shadow_eligible: bool   # True only for HIGH_CONSISTENCY_LONG / SHORT
    ema20_dist_atr: float      # Diagnostic ATR-normalized trend distance


class CandidateSignalV1:
    """
    Candidate Signal V1 Orchestrator (Frozen Hypotheses).
    Read-only, non-production, isolated evaluation path.
    """

    def evaluate_bar(self, row: pd.Series) -> CandidateSignalResult:
        rsi14 = float(row.get("rsi14", 50.0) or 50.0)
        pct_b = float(row.get("bollinger_pct_b", 0.5) or 0.5)

        ret_3 = float(row.get("ret_3", 0.0) or 0.0)
        ret_6 = float(row.get("ret_6", 0.0) or 0.0)
        ret_12 = float(row.get("ret_12", 0.0) or 0.0)

        close = float(row.get("close", 0.0) or 0.0)
        ema20 = float(row.get("ema20", close) or close)
        atr = float(row.get("atr", 1.0) or 1.0)
        atr_safe = atr if atr > 0 else 1.0

        ema20_dist_atr = (close - ema20) / atr_safe

        # 1. Mean-Reversion Subsystem
        if rsi14 < 35.0 and pct_b < 0.10:
            mr_direction = "LONG"
        elif rsi14 > 65.0 and pct_b > 0.90:
            mr_direction = "SHORT"
        else:
            mr_direction = "NEUTRAL"

        # 2. Multi-Horizon Momentum Subsystem
        if ret_3 > 0.0 and ret_6 > 0.0 and ret_12 > 0.0:
            mom_direction = "LONG"
        elif ret_3 < 0.0 and ret_6 < 0.0 and ret_12 < 0.0:
            mom_direction = "SHORT"
        else:
            mom_direction = "NEUTRAL"

        # 3. Momentum Conflict Check
        mom_conflict = (ret_3 * ret_12 < 0.0)

        # 4. Deterministic Fusion Rules
        if mr_direction == "LONG" and mom_direction == "LONG":
            fused_state = "HIGH_CONSISTENCY_LONG"
            direction = "LONG"
            is_shadow_eligible = True
        elif mr_direction == "SHORT" and mom_direction == "SHORT":
            fused_state = "HIGH_CONSISTENCY_SHORT"
            direction = "SHORT"
            is_shadow_eligible = True
        elif (mr_direction == "LONG" and mom_direction == "SHORT") or (mr_direction == "SHORT" and mom_direction == "LONG"):
            fused_state = "CONFLICT"
            direction = "NEUTRAL"
            is_shadow_eligible = False
        elif mr_direction == "LONG" and mom_direction == "NEUTRAL":
            fused_state = "SINGLE_FACTOR_LONG"
            direction = "LONG"
            is_shadow_eligible = False
        elif mom_direction == "LONG" and mr_direction == "NEUTRAL":
            fused_state = "SINGLE_FACTOR_LONG"
            direction = "LONG"
            is_shadow_eligible = False
        elif mr_direction == "SHORT" and mom_direction == "NEUTRAL":
            fused_state = "SINGLE_FACTOR_SHORT"
            direction = "SHORT"
            is_shadow_eligible = False
        elif mom_direction == "SHORT" and mr_direction == "NEUTRAL":
            fused_state = "SINGLE_FACTOR_SHORT"
            direction = "SHORT"
            is_shadow_eligible = False
        else:
            fused_state = "NEUTRAL"
            direction = "NEUTRAL"
            is_shadow_eligible = False

        return CandidateSignalResult(
            mr_direction=mr_direction,
            mom_direction=mom_direction,
            mom_conflict=mom_conflict,
            fused_state=fused_state,
            direction=direction,
            is_shadow_eligible=is_shadow_eligible,
            ema20_dist_atr=ema20_dist_atr,
        )
