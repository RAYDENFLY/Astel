"""
agent/calibration.py — Phase 12.3 Decision Calibration & Baseline Validation Engine

Evaluates decision outcomes to determine:
1. Is reported decision confidence statistically calibrated?
2. Does evidence agreement correlate with better forward returns?
3. Does the Decision Agent outperform simple baselines (Always LONG/SHORT, Random, Tech-only, ML-only)?
4. Asset-by-Asset and Regime-by-Regime performance breakdown.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import (
    DecisionOutcome,
    CalibrationBin,
    CalibrationReport,
)

log = logging.getLogger("agent.calibration")


class DecisionCalibrationEngine:
    """
    Rigorously evaluates DecisionOutcome records to compute calibration metrics,
    Brier score, ECE, baseline comparisons, and readiness status.
    """

    def __init__(self, bin_ranges: Optional[List[Tuple[float, float]]] = None) -> None:
        if bin_ranges is None:
            bin_ranges = [
                (0.50, 0.60),
                (0.60, 0.70),
                (0.70, 0.80),
                (0.80, 0.90),
                (0.90, 1.00),
            ]
        self.bin_ranges = bin_ranges

    def analyze(self, outcomes: List[DecisionOutcome]) -> CalibrationReport:
        """Analyze historical decision outcomes and return comprehensive CalibrationReport."""
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        if not outcomes:
            return CalibrationReport(
                timestamp=now_iso,
                total_decisions=0,
                evaluated_decisions=0,
                calibration_status="INSUFFICIENT_SAMPLE",
                performance_status="INSUFFICIENT_SAMPLE",
            )

        # Filter directional decisions (TRADE_CANDIDATE / WATCH)
        directional_outcomes = [o for o in outcomes if o.direction in ("LONG", "SHORT")]
        evaluated_count = len(directional_outcomes)

        if evaluated_count == 0:
            return CalibrationReport(
                timestamp=now_iso,
                total_decisions=len(outcomes),
                evaluated_decisions=0,
                calibration_status="INSUFFICIENT_SAMPLE",
                performance_status="INSUFFICIENT_SAMPLE",
            )

        # 1. Overall Accuracy & Positive Return Ratio
        correct_count = sum(1 for o in directional_outcomes if o.direction_correct)
        overall_accuracy = correct_count / evaluated_count

        pos_returns = [o.forward_return_3 for o in directional_outcomes if o.forward_return_3 > 0]
        pos_ratio = len(pos_returns) / evaluated_count if evaluated_count > 0 else 0.0

        # 2. Confidence Bins & Brier Score / ECE
        bins: List[CalibrationBin] = []
        ece_accumulator = 0.0
        brier_accumulator = 0.0

        for b_min, b_max in self.bin_ranges:
            bin_items = [o for o in directional_outcomes if b_min <= o.confidence < b_max]
            n_bin = len(bin_items)

            if n_bin > 0:
                mean_conf = statistics.mean(o.confidence for o in bin_items)
                acc_bin = sum(1 for o in bin_items if o.direction_correct) / n_bin
                cal_err = abs(mean_conf - acc_bin)

                returns = [o.forward_return_3 for o in bin_items]
                avg_ret = statistics.mean(returns)
                med_ret = statistics.median(returns)

                ece_accumulator += (n_bin / evaluated_count) * cal_err
                for o in bin_items:
                    target = 1.0 if o.direction_correct else 0.0
                    brier_accumulator += (o.confidence - target) ** 2
            else:
                mean_conf = (b_min + b_max) / 2.0
                acc_bin = 0.0
                cal_err = 0.0
                avg_ret = 0.0
                med_ret = 0.0

            bins.append(CalibrationBin(
                bin_min=b_min,
                bin_max=b_max,
                sample_count=n_bin,
                predicted_confidence=round(mean_conf, 4),
                actual_accuracy=round(acc_bin, 4),
                calibration_error=round(cal_err, 4),
                avg_forward_return=round(avg_ret, 6),
                median_forward_return=round(med_ret, 6),
            ))

        brier_score = round(brier_accumulator / evaluated_count, 4) if evaluated_count > 0 else 0.0
        ece = round(ece_accumulator, 4)

        # 3. Mandatory Baseline Comparisons
        baselines = self._evaluate_baselines(outcomes)

        # 4. Asset Breakdown
        asset_breakdown = self._evaluate_asset_breakdown(outcomes)

        # 5. Market Regime Breakdown
        regime_breakdown = self._evaluate_regime_breakdown(outcomes)

        # 6. Evidence Agreement Breakdown
        agreement_breakdown = self._evaluate_agreement_breakdown(outcomes)

        # 7. Validation Status Gates
        if evaluated_count < 15:
            cal_status = "INSUFFICIENT_SAMPLE"
            perf_status = "INSUFFICIENT_SAMPLE"
        else:
            if ece < 0.10:
                cal_status = "CALIBRATED"
            elif ece <= 0.20:
                cal_status = "PARTIALLY_CALIBRATED"
            else:
                cal_status = "UNCALIBRATED"

            # Check if agent accuracy exceeds best baseline
            best_base_acc = max(b.get("accuracy", 0.0) for b in baselines.values())
            if overall_accuracy > best_base_acc + 0.03:
                perf_status = "POSITIVE_EDGE"
            elif overall_accuracy >= best_base_acc:
                perf_status = "POSSIBLE_EDGE"
            else:
                perf_status = "NO_EDGE"

        return CalibrationReport(
            timestamp=now_iso,
            total_decisions=len(outcomes),
            evaluated_decisions=evaluated_count,
            brier_score=brier_score,
            expected_calibration_error=ece,
            overall_accuracy=round(overall_accuracy, 4),
            positive_return_ratio=round(pos_ratio, 4),
            bins=bins,
            baseline_comparisons=baselines,
            asset_breakdown=asset_breakdown,
            regime_breakdown=regime_breakdown,
            agreement_breakdown=agreement_breakdown,
            calibration_status=cal_status,
            performance_status=perf_status,
        )

    def _evaluate_baselines(self, outcomes: List[DecisionOutcome]) -> Dict[str, Dict[str, float]]:
        """Evaluate Agent against Mandatory Baselines A through F."""
        eval_items = [o for o in outcomes if o.forward_return_3 != 0.0]
        N = len(eval_items)
        if N == 0:
            return {}

        # Agent
        agent_correct = sum(1 for o in eval_items if o.direction_correct)
        agent_returns = [o.forward_return_3 if o.direction == "LONG" else -o.forward_return_3 for o in eval_items if o.direction in ("LONG", "SHORT")]
        agent_acc = agent_correct / N
        agent_avg_ret = statistics.mean(agent_returns) if agent_returns else 0.0

        # Baseline A: Always LONG
        long_correct = sum(1 for o in eval_items if o.forward_return_3 > 0)
        long_returns = [o.forward_return_3 for o in eval_items]
        long_acc = long_correct / N
        long_avg_ret = statistics.mean(long_returns)

        # Baseline B: Always SHORT
        short_correct = sum(1 for o in eval_items if o.forward_return_3 < 0)
        short_returns = [-o.forward_return_3 for o in eval_items]
        short_acc = short_correct / N
        short_avg_ret = statistics.mean(short_returns)

        # Baseline C: Random Direction (Simulated expected 50% accuracy)
        rand_acc = 0.50
        rand_avg_ret = (long_avg_ret + short_avg_ret) / 2.0

        # Baseline D: Technical-Only Signal (EMA Trend proxy)
        tech_returns = [o.forward_return_3 if o.market_regime == "BULLISH_TREND" else -o.forward_return_3 for o in eval_items]
        tech_correct = sum(1 for r in tech_returns if r > 0)
        tech_acc = tech_correct / N
        tech_avg_ret = statistics.mean(tech_returns)

        # Baseline E: ML-Only Signal
        ml_returns = [o.forward_return_3 if o.direction == "LONG" else -o.forward_return_3 for o in eval_items]
        ml_correct = sum(1 for r in ml_returns if r > 0)
        ml_acc = ml_correct / N
        ml_avg_ret = statistics.mean(ml_returns)

        # Baseline F: Market Intelligence Signal
        intel_returns = [o.forward_return_3 if o.fusion_score > 0 else -o.forward_return_3 for o in eval_items]
        intel_correct = sum(1 for r in intel_returns if r > 0)
        intel_acc = intel_correct / N
        intel_avg_ret = statistics.mean(intel_returns)

        return {
            "Agent_Multi_Agent": {"accuracy": round(agent_acc, 4), "avg_return": round(agent_avg_ret, 6)},
            "Baseline_A_Always_LONG": {"accuracy": round(long_acc, 4), "avg_return": round(long_avg_ret, 6)},
            "Baseline_B_Always_SHORT": {"accuracy": round(short_acc, 4), "avg_return": round(short_avg_ret, 6)},
            "Baseline_C_Random": {"accuracy": round(rand_acc, 4), "avg_return": round(rand_avg_ret, 6)},
            "Baseline_D_Tech_Only": {"accuracy": round(tech_acc, 4), "avg_return": round(tech_avg_ret, 6)},
            "Baseline_E_ML_Only": {"accuracy": round(ml_acc, 4), "avg_return": round(ml_avg_ret, 6)},
            "Baseline_F_Intelligence_Only": {"accuracy": round(intel_acc, 4), "avg_return": round(intel_avg_ret, 6)},
        }

    def _evaluate_asset_breakdown(self, outcomes: List[DecisionOutcome]) -> Dict[str, Dict[str, Any]]:
        """Compute performance breakdown per configured asset."""
        result: Dict[str, Dict[str, Any]] = {}
        assets = sorted(list(set(o.asset for o in outcomes)))

        for asset in assets:
            items = [o for o in outcomes if o.asset == asset]
            n_total = len(items)
            directional = [o for o in items if o.direction in ("LONG", "SHORT")]
            n_dir = len(directional)

            if n_dir > 0:
                acc = sum(1 for o in directional if o.direction_correct) / n_dir
                returns = [o.forward_return_3 for o in directional]
                avg_ret = statistics.mean(returns)
                mean_conf = statistics.mean(o.confidence for o in directional)
                cal_err = abs(mean_conf - acc)
            else:
                acc = 0.0
                avg_ret = 0.0
                cal_err = 0.0

            result[asset] = {
                "total_decisions": n_total,
                "directional_decisions": n_dir,
                "accuracy": round(acc, 4),
                "avg_return": round(avg_ret, 6),
                "calibration_error": round(cal_err, 4),
            }

        return result

    def _evaluate_regime_breakdown(self, outcomes: List[DecisionOutcome]) -> Dict[str, Dict[str, Any]]:
        """Compute performance breakdown per market regime."""
        result: Dict[str, Dict[str, Any]] = {}
        regimes = sorted(list(set(o.market_regime for o in outcomes)))

        for reg in regimes:
            items = [o for o in outcomes if o.market_regime == reg and o.direction in ("LONG", "SHORT")]
            n = len(items)
            if n > 0:
                acc = sum(1 for o in items if o.direction_correct) / n
                avg_ret = statistics.mean(o.forward_return_3 for o in items)
            else:
                acc = 0.0
                avg_ret = 0.0

            result[reg] = {
                "count": n,
                "accuracy": round(acc, 4),
                "avg_return": round(avg_ret, 6),
            }

        return result

    def _evaluate_agreement_breakdown(self, outcomes: List[DecisionOutcome]) -> Dict[str, Dict[str, Any]]:
        """Compute performance breakdown by specialist evidence agreement & contradiction level."""
        result: Dict[str, Dict[str, Any]] = {}
        levels = sorted(list(set(o.contradiction_level for o in outcomes)))

        for lvl in levels:
            items = [o for o in outcomes if o.contradiction_level == lvl and o.direction in ("LONG", "SHORT")]
            n = len(items)
            if n > 0:
                acc = sum(1 for o in items if o.direction_correct) / n
                avg_ret = statistics.mean(o.forward_return_3 for o in items)
            else:
                acc = 0.0
                avg_ret = 0.0

            result[lvl] = {
                "count": n,
                "accuracy": round(acc, 4),
                "avg_return": round(avg_ret, 6),
            }

        return result
