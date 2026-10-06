"""
agent/_phase124_multi_regime_validation.py — Phase 12.4 Multi-Regime Historical Validation & Audit Script

Runs historical replay on the expanded 1,000 candle dataset across 12 assets (10,920 asset-bar evaluations).
Measures regime distributions, directional pipeline propagation, Top-N selection dynamics,
baseline comparisons, confidence calibration, asset concentration, and shadow isolation.
"""

import sys
from typing import Dict, List, Any
import numpy as np
import pandas as pd

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.calibration import DecisionCalibrationEngine
from agent.schema import DecisionOutcome


def run_multi_regime_validation():
    print("=" * 80)
    print("PHASE 12.4 — MULTI-REGIME HISTORICAL VALIDATION & AUDIT RUN")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    # 1. Dataset Check & Regime Distribution
    total_candles = {asset: len(df) for asset, df in engine._raw_data.items()}
    print(f"Loaded datasets across {len(engine._raw_data)} assets.")
    for ast, cnt in total_candles.items():
        print(f"  {ast}: {cnt} candles")

    # Tracking per-stage counts and scores
    ml_directions = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
    ml_scores = []
    ml_probs = []

    tech_sp_dirs = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
    macro_sp_dirs = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}

    fused_dirs = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
    fused_scores_long = []
    fused_scores_short = []

    top_n_selected = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
    short_rank_distribution = {"Rank_1": 0, "Rank_2": 0, "Rank_3": 0, "Rank_4_plus": 0}

    long_rank_keys = []
    short_rank_keys = []

    proposals_count = {"LONG": 0, "SHORT": 0, "NEUTRAL": 0}
    decisions_count = {"TRADE_CANDIDATE": 0, "WATCH": 0, "NO_TRADE": 0}
    asset_proposal_counts = {}

    regimes_count = {"BULLISH_TREND": 0, "BEARISH_TREND": 0, "CONSOLIDATION": 0, "HIGH_VOLATILITY": 0}
    asset_regimes = {}

    # Run Replay
    min_candles = min(len(df) for df in engine._raw_data.values())
    outcomes: List[DecisionOutcome] = []

    for step in range(engine.config.warmup_period, min_candles):
        step_analyses = []
        asset_bars = {}

        for asset, df in engine._raw_data.items():
            slice_df = df.iloc[: step + 1].copy()
            try:
                feats_df = engine.feature_builder.build(slice_df, is_training=False)
                if not feats_df.empty:
                    asset_bars[asset] = feats_df.iloc[-1]
            except Exception:
                pass

        if not asset_bars:
            continue

        btc_bar = asset_bars.get("BTC_USDT")
        btc_bar_info = dict(btc_bar) if btc_bar is not None else None

        for asset, bar in asset_bars.items():
            analysis = engine._build_asset_analysis_at_step(asset, bar)

            # Track Regime
            reg = analysis.market_regime
            regimes_count[reg] = regimes_count.get(reg, 0) + 1
            if asset not in asset_regimes:
                asset_regimes[asset] = {"BULLISH_TREND": 0, "BEARISH_TREND": 0, "CONSOLIDATION": 0, "HIGH_VOLATILITY": 0, "total": 0}
            asset_regimes[asset][reg] = asset_regimes[asset].get(reg, 0) + 1
            asset_regimes[asset]["total"] += 1

            # ML Stage
            ml_directions[analysis.direction] += 1
            ml_scores.append(analysis.prediction)
            ml_probs.append(analysis.probability)

            # Market Intelligence
            evidences, summary = engine.intelligence.analyze_asset_intelligence(
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

            # Specialists
            sp_tech = engine.decision_agent.tech_specialist.analyze(analysis)
            sp_flow = engine.decision_agent.flow_specialist.analyze(evidences)
            sp_deriv = engine.decision_agent.deriv_specialist.analyze(evidences)
            sp_macro = engine.decision_agent.macro_specialist.analyze(evidences)
            sp_news = engine.decision_agent.news_specialist.analyze(evidences)

            tech_sp_dirs[sp_tech.direction] += 1
            macro_sp_dirs[sp_macro.direction] += 1

            # Fusion
            fusion_res = engine.decision_agent.fusion_engine.fuse(
                asset=asset,
                specialist_outputs=[sp_tech, sp_flow, sp_deriv, sp_macro, sp_news],
                market_evidences=evidences,
                evidence_summary=summary,
            )
            fused_dirs[fusion_res.composite_direction] += 1

            if fusion_res.composite_direction == "LONG":
                fused_scores_long.append(fusion_res.directional_score)
            elif fusion_res.composite_direction == "SHORT":
                fused_scores_short.append(fusion_res.directional_score)

            step_analyses.append(analysis)

        # Sort for Top-N
        step_analyses.sort(
            key=lambda a: abs(a.evidence_summary.weighted_score if a.evidence_summary else a.prediction) * a.confidence * a.probability,
            reverse=True,
        )
        for r, a in enumerate(step_analyses, start=1):
            a.rank = r

            # Collect Rank keys for LONG vs SHORT
            score = a.evidence_summary.weighted_score if a.evidence_summary else a.prediction
            r_key = abs(score) * a.confidence * a.probability
            if a.direction == "LONG":
                long_rank_keys.append(r_key)
            elif a.direction == "SHORT":
                short_rank_keys.append(r_key)
                if r == 1:
                    short_rank_distribution["Rank_1"] += 1
                elif r == 2:
                    short_rank_distribution["Rank_2"] += 1
                elif r == 3:
                    short_rank_distribution["Rank_3"] += 1
                else:
                    short_rank_distribution["Rank_4_plus"] += 1

        top_n = step_analyses[: engine.config.top_n]
        for a in top_n:
            top_n_selected[a.direction] += 1

        proposals = engine.decision_agent.evaluate_scanned_assets(step_analyses)

        # Outcome creation for proposals
        for prop in proposals:
            proposals_count[prop.direction] += 1
            decisions_count[prop.decision] += 1

            ast = prop.asset
            if ast not in asset_proposal_counts:
                asset_proposal_counts[ast] = {"LONG": 0, "SHORT": 0, "TOTAL": 0}
            asset_proposal_counts[ast][prop.direction] += 1
            asset_proposal_counts[ast]["TOTAL"] += 1

            df = engine._raw_data.get(ast)
            if df is not None and step < len(df):
                entry_price = float(df.iloc[step]["close"])
                ts_str = str(df.iloc[step]["timestamp"])

                ret_1 = engine._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
                ret_3 = engine._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
                ret_6 = engine._calc_forward_return(df, step, horizon=6, entry_price=entry_price)

                eval_ret = ret_3 if ret_3 is not None else ret_1
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
                    direction_correct=direction_correct,
                    outcome_class=outcome_class,
                )
                outcomes.append(outcome)

    # Calibration Evaluation
    cal_engine = DecisionCalibrationEngine()
    cal_report = cal_engine.analyze(outcomes)

    total_evals = len(outcomes)
    eval_set = [o for o in outcomes if o.decision == "TRADE_CANDIDATE"] if any(o.decision == "TRADE_CANDIDATE" for o in outcomes) else outcomes
    accuracy = (sum(1 for o in eval_set if o.direction_correct) / len(eval_set) * 100) if eval_set else 0.0
    t3_rets = [o.forward_return_3 for o in eval_set if o.forward_return_3 is not None]
    avg_t3 = float(np.mean(t3_rets) * 100) if t3_rets else 0.0

    print("\n" + "=" * 80)
    print("PHASE 12.4 SUMMARY REPORT METRICS")
    print("=" * 80)
    print(f"Total Step Evaluations: {total_evals}")
    print(f"Regime Distribution: {regimes_count}")
    print(f"ML Directions: {ml_directions}")
    print(f"ML Score Stats: Mean={np.mean(ml_scores):+.4f}, Median={np.median(ml_scores):+.4f}, Min={np.min(ml_scores):+.4f}, Max={np.max(ml_scores):+.4f}")
    print(f"Specialist Tech Dirs: {tech_sp_dirs}")
    print(f"Specialist Macro Dirs: {macro_sp_dirs}")
    print(f"Fused Dirs: {fused_dirs}")
    print(f"Top-N Selected Dirs: {top_n_selected}")
    print(f"SHORT Rank Distribution: {short_rank_distribution}")
    print(f"Proposals Count: {proposals_count}")
    print(f"Decisions Count: {decisions_count}")
    print(f"Accuracy: {accuracy:.2f}%")
    print(f"Avg T+3 Return: {avg_t3:+.4f}%")
    print(f"ECE: {cal_report.expected_calibration_error:.4f} | Brier: {cal_report.brier_score:.4f}")

    print("\nRANK KEY STATS (LONG vs SHORT):")
    if long_rank_keys:
        print(f"  LONG  (n={len(long_rank_keys)}): Mean={np.mean(long_rank_keys):.4f}, Median={np.median(long_rank_keys):.4f}, P25={np.percentile(long_rank_keys, 25):.4f}, P75={np.percentile(long_rank_keys, 75):.4f}, Min={np.min(long_rank_keys):.4f}, Max={np.max(long_rank_keys):.4f}")
    if short_rank_keys:
        print(f"  SHORT (n={len(short_rank_keys)}): Mean={np.mean(short_rank_keys):.4f}, Median={np.median(short_rank_keys):.4f}, P25={np.percentile(short_rank_keys, 25):.4f}, P75={np.percentile(short_rank_keys, 75):.4f}, Min={np.min(short_rank_keys):.4f}, Max={np.max(short_rank_keys):.4f}")

    print("\nASSET PROPOSAL BREAKDOWN:")
    for ast, p_cnt in asset_proposal_counts.items():
        print(f"  {ast:<12} | LONG={p_cnt['LONG']:4d} | SHORT={p_cnt['SHORT']:4d} | TOTAL={p_cnt['TOTAL']:4d}")

    # Baseline Comparisons
    print("\nBASELINE PERFORMANCE COMPARISONS:")
    # Always LONG baseline
    long_correct = sum(1 for o in outcomes if o.forward_return_3 > 0)
    long_acc = (long_correct / total_evals * 100) if total_evals else 0.0
    long_avg_t3 = np.mean([o.forward_return_3 for o in outcomes]) * 100

    # Always SHORT baseline
    short_correct = sum(1 for o in outcomes if o.forward_return_3 < 0)
    short_acc = (short_correct / total_evals * 100) if total_evals else 0.0
    short_avg_t3 = np.mean([-o.forward_return_3 for o in outcomes]) * 100

    print(f"  Multi-Agent System: Accuracy = {accuracy:.2f}%, Avg T+3 Return = {avg_t3:+.4f}%")
    print(f"  Always LONG:        Accuracy = {long_acc:.2f}%, Avg T+3 Return = {long_avg_t3:+.4f}%")
    print(f"  Always SHORT:       Accuracy = {short_acc:.2f}%, Avg T+3 Return = {short_avg_t3:+.4f}%")

if __name__ == "__main__":
    run_multi_regime_validation()
