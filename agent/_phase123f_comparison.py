"""
agent/_phase123f_comparison.py — Phase 12.3F Replay Comparison Script

Runs HistoricalReplayEngine BEFORE (offline_mode=False) vs AFTER (offline_mode=True)
and computes detailed comparative metrics across decisions, outcomes, assets, and calibration.
"""

from typing import Dict, List, Any
import numpy as np

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.calibration import DecisionCalibrationEngine


def run_comparison():
    print("=" * 70)
    print("PHASE 12.3F — HISTORICAL REPLAY BEFORE vs AFTER COMPARISON")
    print("=" * 70)

    # 1. Run BEFORE (offline_mode = False)
    cfg_before = ReplayConfig()
    engine_before = HistoricalReplayEngine(config=cfg_before)
    engine_before.intelligence.offline_mode = False
    outcomes_before, logs_before = engine_before.run_replay()

    # 2. Run AFTER (offline_mode = True)
    cfg_after = ReplayConfig()
    engine_after = HistoricalReplayEngine(config=cfg_after)
    engine_after.intelligence.offline_mode = True
    outcomes_after, logs_after = engine_after.run_replay()

    def analyze_replay_set(outcomes, name):
        total_evals = len(outcomes)
        long_proposals = sum(1 for o in outcomes if o.direction == "LONG")
        short_proposals = sum(1 for o in outcomes if o.direction == "SHORT")
        neutral_proposals = sum(1 for o in outcomes if o.direction == "NEUTRAL")

        trade_candidates = [o for o in outcomes if o.decision == "TRADE_CANDIDATE"]
        watch_decisions = [o for o in outcomes if o.decision == "WATCH"]
        no_trade_decisions = [o for o in outcomes if o.decision == "NO_TRADE"]

        long_candidates = sum(1 for o in trade_candidates if o.direction == "LONG")
        short_candidates = sum(1 for o in trade_candidates if o.direction == "SHORT")

        # Returns and Accuracy on approved TRADE_CANDIDATEs (or all if none)
        eval_set = trade_candidates if trade_candidates else outcomes
        correct = sum(1 for o in eval_set if o.direction_correct)
        accuracy = (correct / len(eval_set) * 100) if eval_set else 0.0

        t1_rets = [o.forward_return_1 for o in eval_set if o.forward_return_1 is not None]
        t3_rets = [o.forward_return_3 for o in eval_set if o.forward_return_3 is not None]
        t6_rets = [o.forward_return_6 for o in eval_set if o.forward_return_6 is not None]

        avg_t1 = np.mean(t1_rets) * 100 if t1_rets else 0.0
        avg_t3 = np.mean(t3_rets) * 100 if t3_rets else 0.0
        avg_t6 = np.mean(t6_rets) * 100 if t6_rets else 0.0

        confidences = [o.confidence for o in outcomes]
        agreements = [o.agreement_score for o in outcomes]

        # Calibration
        analyzer = DecisionCalibrationEngine()
        cal_report = analyzer.analyze(outcomes)

        # Asset breakdown
        asset_counts = {}
        for o in outcomes:
            ast = o.asset
            if ast not in asset_counts:
                asset_counts[ast] = {"total": 0, "LONG": 0, "SHORT": 0, "TRADE_CANDIDATE": 0}
            asset_counts[ast]["total"] += 1
            asset_counts[ast][o.direction] = asset_counts[ast].get(o.direction, 0) + 1
            if o.decision == "TRADE_CANDIDATE":
                asset_counts[ast]["TRADE_CANDIDATE"] += 1

        # Contradiction breakdown
        contradictions = {}
        for o in outcomes:
            c_lvl = o.contradiction_level
            contradictions[c_lvl] = contradictions.get(c_lvl, 0) + 1

        print(f"\n--- {name} RESULTS ---")
        print(f"Total Decision Evaluations: {total_evals}")
        print(f"Proposals: LONG={long_proposals}, SHORT={short_proposals}, NEUTRAL={neutral_proposals}")
        print(f"Decisions: TRADE_CANDIDATE={len(trade_candidates)}, WATCH={len(watch_decisions)}, NO_TRADE={len(no_trade_decisions)}")
        print(f"Candidates by Direction: LONG={long_candidates}, SHORT={short_candidates}")
        print(f"Accuracy: {accuracy:.2f}% ({correct}/{len(eval_set)})")
        print(f"Avg Forward Returns: T+1={avg_t1:+.4f}%, T+3={avg_t3:+.4f}%, T+6={avg_t6:+.4f}%")
        print(f"Confidence: Mean={np.mean(confidences):.4f}, Min={np.min(confidences):.4f}, Max={np.max(confidences):.4f}")
        print(f"Agreement: Mean={np.mean(agreements):.4f}")
        print(f"Contradiction Distribution: {contradictions}")
        print(f"ECE: {cal_report.expected_calibration_error:.4f} | Brier Score: {cal_report.brier_score:.4f}")
        print(f"Calibration Status: {cal_report.calibration_status}")

        return {
            "total_evals": total_evals,
            "long_proposals": long_proposals,
            "short_proposals": short_proposals,
            "neutral_proposals": neutral_proposals,
            "trade_candidates": len(trade_candidates),
            "watch_decisions": len(watch_decisions),
            "no_trade_decisions": len(no_trade_decisions),
            "long_candidates": long_candidates,
            "short_candidates": short_candidates,
            "accuracy": accuracy,
            "avg_t1": avg_t1,
            "avg_t3": avg_t3,
            "avg_t6": avg_t6,
            "mean_conf": float(np.mean(confidences)),
            "mean_agreement": float(np.mean(agreements)),
            "contradictions": contradictions,
            "ece": cal_report.expected_calibration_error,
            "brier": cal_report.brier_score,
            "asset_counts": asset_counts,
        }

    res_before = analyze_replay_set(outcomes_before, "BEFORE 12.3F (Synthetic Bullish OrderFlow)")
    res_after = analyze_replay_set(outcomes_after, "AFTER 12.3F (Offline Evidence Integrity Fix)")

    print("\n" + "=" * 70)
    print("CRITICAL COMPARISON SUMMARY")
    print("=" * 70)
    print(f"SHORT Proposals:   BEFORE = {res_before['short_proposals']:3d}  -->  AFTER = {res_after['short_proposals']:3d}")
    print(f"SHORT Candidates:  BEFORE = {res_before['short_candidates']:3d}  -->  AFTER = {res_after['short_candidates']:3d}")
    print(f"LONG Proposals:    BEFORE = {res_before['long_proposals']:3d}  -->  AFTER = {res_after['long_proposals']:3d}")
    print(f"LONG Candidates:   BEFORE = {res_before['long_candidates']:3d}  -->  AFTER = {res_after['long_candidates']:3d}")
    print(f"WATCH Decisions:   BEFORE = {res_before['watch_decisions']:3d}  -->  AFTER = {res_after['watch_decisions']:3d}")
    print(f"NO_TRADE Decs:     BEFORE = {res_before['no_trade_decisions']:3d}  -->  AFTER = {res_after['no_trade_decisions']:3d}")
    print(f"Accuracy:          BEFORE = {res_before['accuracy']:.2f}%  -->  AFTER = {res_after['accuracy']:.2f}%")
    print(f"Avg T+3 Return:    BEFORE = {res_before['avg_t3']:+.4f}%  -->  AFTER = {res_after['avg_t3']:+.4f}%")
    print(f"ECE:               BEFORE = {res_before['ece']:.4f}  -->  AFTER = {res_after['ece']:.4f}")

if __name__ == "__main__":
    run_comparison()
