"""
agent/_phase124a_edge_audit.py — Phase 12.4A Edge Attribution & Regime-Specific Performance Audit Script

Performs a granular, read-only quantitative evaluation of all 10 candidate systems/baselines:
A. Always LONG
B. Always SHORT
C. Random (seed=42)
D. ML-only
E. Technical-only
F. Macro-only
G. Market Intelligence-only
H. Technical + ML
I. Technical + Macro
J. Full Multi-Agent System

Computes:
1. Baseline comparisons (Accuracy, T+1, T+3, T+6 returns, distribution stats)
2. Regime-specific breakdown (BULLISH, BEARISH, CONSOLIDATION)
3. LONG vs SHORT performance breakdown
4. Component incremental attribution (Delta Accuracy, Delta T+3)
5. Evidence Fusion agreement attribution
6. Confidence bin calibration & accuracy
7. Top-N Rank performance (Rank 1 vs 2 vs 3)
8. Asset-level performance breakdown
9. Regime x Direction matrix for Full Multi-Agent
10. Forward return distribution & bootstrap 95% CIs
11. Chronological Out-of-Sample Split (60% In-Sample / 40% Out-of-Sample)
"""

import sys
import math
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.schema import AssetAnalysis, SpecialistOutput, DecisionOutcome
from agent.evidence_fusion import EvidenceFusionEngine


def bootstrap_ci(arr: List[float], num_samples: int = 1000, ci: float = 95.0) -> Tuple[float, float]:
    if not arr:
        return 0.0, 0.0
    arr_np = np.array(arr)
    n = len(arr_np)
    means = []
    rng = np.random.RandomState(42)
    for _ in range(num_samples):
        sample = rng.choice(arr_np, size=n, replace=True)
        means.append(np.mean(sample))
    lower = np.percentile(means, (100.0 - ci) / 2.0)
    upper = np.percentile(means, 100.0 - (100.0 - ci) / 2.0)
    return float(lower), float(upper)


def run_edge_audit():
    print("=" * 80)
    print("PHASE 12.4A — EDGE ATTRIBUTION & REGIME-SPECIFIC PERFORMANCE AUDIT")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    min_candles = min(len(df) for df in engine._raw_data.values())
    total_steps = min_candles - engine.config.warmup_period
    print(f"Dataset: 12 assets, {min_candles} candles per asset, {total_steps} evaluation steps.")

    # Storage for all evaluation records
    # Each record will store ground truth returns (t1, t3, t6), regime, asset, step, and predictions of all 10 systems
    records = []

    rng_random = np.random.RandomState(42)

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

            # Fusion
            fusion_res = engine.decision_agent.fusion_engine.fuse(
                asset=asset,
                specialist_outputs=[sp_tech, sp_flow, sp_deriv, sp_macro, sp_news],
                market_evidences=evidences,
                evidence_summary=summary,
            )

            df = engine._raw_data[asset]
            entry_price = float(df.iloc[step]["close"])
            ret_1 = engine._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
            ret_3 = engine._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
            ret_6 = engine._calc_forward_return(df, step, horizon=6, entry_price=entry_price)

            # Systems predictions:
            # A. Always LONG
            pred_always_long = "LONG"
            # B. Always SHORT
            pred_always_short = "SHORT"
            # C. Random
            pred_random = "LONG" if rng_random.rand() >= 0.5 else "SHORT"
            # D. ML-only
            pred_ml = analysis.direction
            # E. Technical-only
            pred_tech = "LONG" if analysis.ema_trend == "BULLISH" else ("SHORT" if analysis.ema_trend == "BEARISH" else "NEUTRAL")
            # F. Macro-only
            pred_macro = "LONG" if analysis.market_regime == "BULLISH_TREND" else ("SHORT" if analysis.market_regime == "BEARISH_TREND" else "NEUTRAL")
            # G. Market Intelligence-only
            pred_intel = "LONG" if summary.composite_signal == "BULLISH" else ("SHORT" if summary.composite_signal == "BEARISH" else "NEUTRAL")
            # H. Technical + ML
            pred_tech_ml = sp_tech.direction
            # I. Technical + Macro
            if pred_tech == pred_macro and pred_tech in ("LONG", "SHORT"):
                pred_tech_macro = pred_tech
            elif pred_tech in ("LONG", "SHORT") and pred_macro == "NEUTRAL":
                pred_tech_macro = pred_tech
            else:
                pred_tech_macro = "NEUTRAL"

            # J. Full Multi-Agent composite (prior to ranking)
            pred_multi_agent = fusion_res.composite_direction

            step_analyses.append({
                "step": step,
                "asset": asset,
                "timestamp": str(df.iloc[step]["timestamp"]),
                "regime": analysis.market_regime,
                "ret_1": ret_1 if ret_1 is not None else 0.0,
                "ret_3": ret_3 if ret_3 is not None else 0.0,
                "ret_6": ret_6 if ret_6 is not None else 0.0,
                "ml_prediction": analysis.prediction,
                "ml_confidence": analysis.confidence,
                "ml_probability": analysis.probability,
                "weighted_score": summary.weighted_score,
                "agreement_score": fusion_res.agreement_score,
                "contradiction_level": fusion_res.contradiction_level,
                "confidence_band": fusion_res.confidence_band,
                "directional_score": fusion_res.directional_score,
                "fused_confidence": fusion_res.confidence,
                "pred_always_long": pred_always_long,
                "pred_always_short": pred_always_short,
                "pred_random": pred_random,
                "pred_ml": pred_ml,
                "pred_tech": pred_tech,
                "pred_macro": pred_macro,
                "pred_intel": pred_intel,
                "pred_tech_ml": pred_tech_ml,
                "pred_tech_macro": pred_tech_macro,
                "pred_multi_agent": pred_multi_agent,
                "analysis": analysis,
            })

        # Rank step analyses by magnitude
        step_analyses.sort(
            key=lambda item: abs(item["weighted_score"]) * item["ml_confidence"] * item["ml_probability"],
            reverse=True,
        )
        for r, item in enumerate(step_analyses, start=1):
            item["rank"] = r
            item["selected_top_n"] = (r <= engine.config.top_n)
            records.append(item)

    print(f"Total bar records collected: {len(records)}")

    df_rec = pd.DataFrame(records)

    # System Keys mapping
    SYSTEMS = {
        "Always LONG": "pred_always_long",
        "Always SHORT": "pred_always_short",
        "Random": "pred_random",
        "ML-only": "pred_ml",
        "Technical-only": "pred_tech",
        "Macro-only": "pred_macro",
        "Market Intelligence-only": "pred_intel",
        "Technical + ML": "pred_tech_ml",
        "Technical + Macro": "pred_tech_macro",
        "Full Multi-Agent": "pred_multi_agent",
    }

    # Helper function to evaluate accuracy and returns for a given dataset subset and system prediction
    def eval_system(sub_df: pd.DataFrame, sys_col: str):
        if sub_df.empty:
            return {"n": 0, "acc": 0.0, "long_acc": 0.0, "short_acc": 0.0, "t1": 0.0, "t3": 0.0, "t6": 0.0, "long_cnt": 0, "short_cnt": 0}

        preds = sub_df[sys_col].values
        r1 = sub_df["ret_1"].values
        r3 = sub_df["ret_3"].values
        r6 = sub_df["ret_6"].values

        # Valid active predictions (LONG or SHORT)
        mask_long = (preds == "LONG")
        mask_short = (preds == "SHORT")
        mask_active = mask_long | mask_short

        n_total = len(sub_df)
        n_active = np.sum(mask_active)

        if n_active == 0:
            return {"n": n_total, "active_n": 0, "acc": 0.0, "long_acc": 0.0, "short_acc": 0.0, "t1": 0.0, "t3": 0.0, "t6": 0.0, "long_cnt": 0, "short_cnt": 0}

        # Realized directional accuracy
        correct_long = (r3[mask_long] > 0)
        correct_short = (r3[mask_short] < 0)

        n_long = np.sum(mask_long)
        n_short = np.sum(mask_short)

        long_acc = (np.mean(correct_long) * 100.0) if n_long > 0 else 0.0
        short_acc = (np.mean(correct_short) * 100.0) if n_short > 0 else 0.0

        total_correct = np.sum(correct_long) + np.sum(correct_short)
        acc = (total_correct / n_active * 100.0)

        # Realized returns (LONG return = r, SHORT return = -r)
        rets_t1 = np.concatenate([r1[mask_long], -r1[mask_short]]) if n_active > 0 else np.array([])
        rets_t3 = np.concatenate([r3[mask_long], -r3[mask_short]]) if n_active > 0 else np.array([])
        rets_t6 = np.concatenate([r6[mask_long], -r6[mask_short]]) if n_active > 0 else np.array([])

        mean_t1 = float(np.mean(rets_t1) * 100.0) if len(rets_t1) > 0 else 0.0
        mean_t3 = float(np.mean(rets_t3) * 100.0) if len(rets_t3) > 0 else 0.0
        mean_t6 = float(np.mean(rets_t6) * 100.0) if len(rets_t6) > 0 else 0.0

        return {
            "n": n_total,
            "active_n": int(n_active),
            "acc": float(acc),
            "long_acc": float(long_acc),
            "short_acc": float(short_acc),
            "t1": mean_t1,
            "t3": mean_t3,
            "t6": mean_t6,
            "long_cnt": int(n_long),
            "short_cnt": int(n_short),
            "rets_t3_raw": rets_t3,
        }

    # 1. BASELINE COMPARISON TABLE
    print("\n" + "=" * 80)
    print("1. OVERALL BASELINE PERFORMANCE COMPARISON (All 10,920 Evaluations)")
    print("=" * 80)
    print(f"{'System':<25} | {'Active N':<8} | {'LONG N':<7} | {'SHORT N':<7} | {'Accuracy':<9} | {'Avg T+1':<8} | {'Avg T+3':<8} | {'Avg T+6':<8}")
    print("-" * 95)

    base_results = {}
    for sys_name, sys_col in SYSTEMS.items():
        res = eval_system(df_rec, sys_col)
        base_results[sys_name] = res
        print(f"{sys_name:<25} | {res['active_n']:<8d} | {res['long_cnt']:<7d} | {res['short_cnt']:<7d} | {res['acc']:>7.2f}%  | {res['t1']:>+7.4f}% | {res['t3']:>+7.4f}% | {res['t6']:>+7.4f}%")

    # 2. REGIME-SPECIFIC BREAKDOWN TABLE
    print("\n" + "=" * 80)
    print("2. REGIME-SPECIFIC PERFORMANCE COMPARISON")
    print("=" * 80)

    regimes = ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]
    regime_sys_matrix = {}

    print(f"{'System':<22} | {'Regime':<15} | {'N':<6} | {'Accuracy':<9} | {'LONG Acc':<9} | {'SHORT Acc':<9} | {'Avg T+3':<8}")
    print("-" * 90)
    for sys_name, sys_col in SYSTEMS.items():
        regime_sys_matrix[sys_name] = {}
        for reg in regimes:
            df_sub = df_rec[df_rec["regime"] == reg]
            res = eval_system(df_sub, sys_col)
            regime_sys_matrix[sys_name][reg] = res
            print(f"{sys_name:<22} | {reg:<15} | {res['active_n']:<6d} | {res['acc']:>7.2f}%  | {res['long_acc']:>7.2f}%  | {res['short_acc']:>7.2f}%  | {res['t3']:>+7.4f}%")

    # 3. LONG VS SHORT PERFORMANCE BREAKDOWN
    print("\n" + "=" * 80)
    print("3. LONG VS SHORT PERFORMANCE SEPARATION")
    print("=" * 80)
    print(f"{'System':<22} | {'Dir':<6} | {'N':<6} | {'Accuracy':<9} | {'Avg T+1':<8} | {'Avg T+3':<8} | {'Avg T+6':<8}")
    print("-" * 80)
    for sys_name, sys_col in SYSTEMS.items():
        res = base_results[sys_name]
        print(f"{sys_name:<22} | LONG   | {res['long_cnt']:<6d} | {res['long_acc']:>7.2f}%  | {res['t1']:>+7.4f}% | {res['t3']:>+7.4f}% | {res['t6']:>+7.4f}%")
        print(f"{sys_name:<22} | SHORT  | {res['short_cnt']:<6d} | {res['short_acc']:>7.2f}%  | {res['t1']:>+7.4f}% | {res['t3']:>+7.4f}% | {res['t6']:>+7.4f}%")

    # 4. COMPONENT INCREMENTAL ATTRIBUTION
    print("\n" + "=" * 80)
    print("4. COMPONENT INCREMENTAL ATTRIBUTION (DELTA ANALYSIS)")
    print("=" * 80)

    ml_acc = base_results["ML-only"]["acc"]
    ml_t3 = base_results["ML-only"]["t3"]

    tech_ml_acc = base_results["Technical + ML"]["acc"]
    tech_ml_t3 = base_results["Technical + ML"]["t3"]

    full_acc = base_results["Full Multi-Agent"]["acc"]
    full_t3 = base_results["Full Multi-Agent"]["t3"]

    d_tech_ml_acc = tech_ml_acc - ml_acc
    d_tech_ml_t3 = tech_ml_t3 - ml_t3

    d_full_acc = full_acc - tech_ml_acc
    d_full_t3 = full_t3 - tech_ml_t3

    print(f"ML-only -> Technical + ML:      Delta Acc = {d_tech_ml_acc:>+6.2f}%, Delta T+3 = {d_tech_ml_t3:>+7.4f}%")
    print(f"Technical + ML -> Full Multi:   Delta Acc = {d_full_acc:>+6.2f}%, Delta T+3 = {d_full_t3:>+7.4f}%")

    # 5. EVIDENCE FUSION AGREEMENT ATTRIBUTION
    print("\n" + "=" * 80)
    print("5. EVIDENCE FUSION CONTRADICTION / AGREEMENT ATTRIBUTION")
    print("=" * 80)
    print(f"{'Contradiction Level':<25} | {'N':<6} | {'Accuracy':<9} | {'Avg T+3':<8} | {'Avg Confidence':<14}")
    print("-" * 75)

    for c_level in df_rec["contradiction_level"].unique():
        df_c = df_rec[df_rec["contradiction_level"] == c_level]
        res = eval_system(df_c, "pred_multi_agent")
        avg_conf = float(df_c["fused_confidence"].mean()) if not df_c.empty else 0.0
        print(f"{c_level:<25} | {res['active_n']:<6d} | {res['acc']:>7.2f}%  | {res['t3']:>+7.4f}% | {avg_conf:>14.4f}")

    # 6. CONFIDENCE BIN ATTRIBUTION
    print("\n" + "=" * 80)
    print("6. CONFIDENCE BINS CALIBRATION ATTRIBUTION")
    print("=" * 80)

    bins = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.01)]
    print(f"{'Bin':<12} | {'N':<6} | {'Avg Confidence':<14} | {'Accuracy':<9} | {'Calib Gap':<10} | {'Avg T+3':<8}")
    print("-" * 75)

    for b_low, b_high in bins:
        df_b = df_rec[(df_rec["ml_confidence"] >= b_low) & (df_rec["ml_confidence"] < b_high)]
        res = eval_system(df_b, "pred_multi_agent")
        avg_c = float(df_b["ml_confidence"].mean()) if not df_b.empty else 0.0
        gap = (res["acc"] / 100.0) - avg_c if res["active_n"] > 0 else 0.0
        bin_str = f"[{b_low:.2f}, {b_high:.2f})"
        print(f"{bin_str:<12} | {res['active_n']:<6d} | {avg_c:>14.4f} | {res['acc']:>7.2f}%  | {gap:>+10.4f} | {res['t3']:>+7.4f}%")

    # 7. TOP-N RANK ATTRIBUTION (Rank 1 vs 2 vs 3)
    print("\n" + "=" * 80)
    print("7. TOP-N RANK ATTRIBUTION (Rank 1 vs Rank 2 vs Rank 3)")
    print("=" * 80)

    print(f"{'Rank':<8} | {'LONG N':<7} | {'SHORT N':<7} | {'Accuracy':<9} | {'Avg T+1':<8} | {'Avg T+3':<8} | {'Avg T+6':<8}")
    print("-" * 75)

    df_top_n = df_rec[df_rec["selected_top_n"]]

    for r_val in [1, 2, 3]:
        df_r = df_top_n[df_top_n["rank"] == r_val]
        res = eval_system(df_r, "pred_multi_agent")
        print(f"Rank {r_val:<3d} | {res['long_cnt']:<7d} | {res['short_cnt']:<7d} | {res['acc']:>7.2f}%  | {res['t1']:>+7.4f}% | {res['t3']:>+7.4f}% | {res['t6']:>+7.4f}%")

    # Overall Top-N performance
    res_top_n_all = eval_system(df_top_n, "pred_multi_agent")
    print(f"Top-N All | {res_top_n_all['long_cnt']:<7d} | {res_top_n_all['short_cnt']:<7d} | {res_top_n_all['acc']:>7.2f}%  | {res_top_n_all['t1']:>+7.4f}% | {res_top_n_all['t3']:>+7.4f}% | {res_top_n_all['t6']:>+7.4f}%")

    # 8. ASSET-LEVEL PERFORMANCE BREAKDOWN
    print("\n" + "=" * 80)
    print("8. ASSET-LEVEL PERFORMANCE BREAKDOWN (Full Multi-Agent Top-N Proposals)")
    print("=" * 80)
    print(f"{'Asset':<12} | {'LONG N':<7} | {'SHORT N':<7} | {'Accuracy':<9} | {'LONG Acc':<9} | {'SHORT Acc':<9} | {'Avg T+3':<8}")
    print("-" * 80)

    for ast in cfg.assets:
        df_ast = df_top_n[df_top_n["asset"] == ast]
        res = eval_system(df_ast, "pred_multi_agent")
        print(f"{ast:<12} | {res['long_cnt']:<7d} | {res['short_cnt']:<7d} | {res['acc']:>7.2f}%  | {res['long_acc']:>7.2f}%  | {res['short_acc']:>7.2f}%  | {res['t3']:>+7.4f}%")

    # 9. REGIME X DIRECTION MATRIX FOR FULL MULTI-AGENT
    print("\n" + "=" * 80)
    print("9. REGIME X DIRECTION MATRIX (Full Multi-Agent System)")
    print("=" * 80)
    print(f"{'Regime':<18} | {'LONG N':<7} | {'LONG Acc':<9} | {'LONG T+3':<9} | {'SHORT N':<8} | {'SHORT Acc':<9} | {'SHORT T+3':<9}")
    print("-" * 85)

    for reg in regimes:
        df_reg = df_rec[df_rec["regime"] == reg]
        res = eval_system(df_reg, "pred_multi_agent")

        # LONG return sub
        long_sub = df_reg[df_reg["pred_multi_agent"] == "LONG"]
        l_ret3 = float(long_sub["ret_3"].mean() * 100.0) if not long_sub.empty else 0.0

        # SHORT return sub
        short_sub = df_reg[df_reg["pred_multi_agent"] == "SHORT"]
        s_ret3 = float((-short_sub["ret_3"]).mean() * 100.0) if not short_sub.empty else 0.0

        print(f"{reg:<18} | {res['long_cnt']:<7d} | {res['long_acc']:>7.2f}%  | {l_ret3:>+8.4f}%  | {res['short_cnt']:<8d} | {res['short_acc']:>7.2f}%  | {s_ret3:>+8.4f}%")

    # 10. FORWARD RETURN DISTRIBUTION & BOOTSTRAP 95% CIs
    print("\n" + "=" * 80)
    print("10. FORWARD RETURN DISTRIBUTION & BOOTSTRAP 95% CONFIDENCE INTERVALS")
    print("=" * 80)

    for sys_name in ["Always LONG", "Always SHORT", "ML-only", "Technical + ML", "Full Multi-Agent"]:
        rets = base_results[sys_name]["rets_t3_raw"] * 100.0
        acc = base_results[sys_name]["acc"]

        mean_val = float(np.mean(rets))
        median_val = float(np.median(rets))
        std_val = float(np.std(rets))
        p10 = float(np.percentile(rets, 10))
        p25 = float(np.percentile(rets, 25))
        p75 = float(np.percentile(rets, 75))
        p90 = float(np.percentile(rets, 90))
        pos_pct = float(np.mean(rets > 0) * 100.0)

        # Bootstrap CIs for accuracy and mean return
        # Create boolean correctness array for bootstrap accuracy CI
        correct_arr = (rets > 0).astype(float) * 100.0
        acc_low, acc_high = bootstrap_ci(correct_arr.tolist())
        t3_low, t3_high = bootstrap_ci(rets.tolist())

        print(f"--- {sys_name} ---")
        print(f"  Accuracy: {acc:.2f}% (95% CI: [{acc_low:.2f}%, {acc_high:.2f}%])")
        print(f"  Mean T+3 Return: {mean_val:+.4f}% (95% CI: [{t3_low:+.4f}%, {t3_high:+.4f}%])")
        print(f"  Median T+3: {median_val:+.4f}%, Std: {std_val:.4f}%, WinRate(PosReturn): {pos_pct:.2f}%")
        print(f"  Percentiles: P10={p10:+.4f}%, P25={p25:+.4f}%, P75={p75:+.4f}%, P90={p90:+.4f}%")

    # 11. CHRONOLOGICAL OUT-OF-SAMPLE SPLIT (60% In-Sample / 40% Out-of-Sample)
    print("\n" + "=" * 80)
    print("11. CHRONOLOGICAL OUT-OF-SAMPLE VALIDATION (60% Discovery / 40% Out-of-Sample)")
    print("=" * 80)

    steps = df_rec["step"].unique()
    steps.sort()
    split_idx = int(len(steps) * 0.60)
    in_sample_steps = set(steps[:split_idx])
    out_sample_steps = set(steps[split_idx:])

    df_is = df_rec[df_rec["step"].isin(in_sample_steps)]
    df_oos = df_rec[df_rec["step"].isin(out_sample_steps)]

    print(f"In-Sample (60%): {len(in_sample_steps)} steps, {len(df_is)} bar evaluations.")
    print(f"Out-of-Sample (40%): {len(out_sample_steps)} steps, {len(df_oos)} bar evaluations.")
    print("\nOUT-OF-SAMPLE SYSTEM COMPARISON:")
    print(f"{'System':<25} | {'OOS Accuracy':<12} | {'OOS Avg T+3':<12} | {'OOS LONG Acc':<12} | {'OOS SHORT Acc':<12}")
    print("-" * 80)

    for sys_name, sys_col in SYSTEMS.items():
        res_oos = eval_system(df_oos, sys_col)
        print(f"{sys_name:<25} | {res_oos['acc']:>10.2f}%  | {res_oos['t3']:>+10.4f}% | {res_oos['long_acc']:>10.2f}%  | {res_oos['short_acc']:>10.2f}%")

    # 12. EDGE ATTRIBUTION SCORECARD
    print("\n" + "=" * 80)
    print("12. EDGE ATTRIBUTION SCORECARD")
    print("=" * 80)

    print(f"{'Component':<22} | {'Overall':<10} | {'Bullish':<10} | {'Bearish':<10} | {'Consolidation':<13} | {'Classification':<22}")
    print("-" * 95)

    scorecard_data = [
        ("ML-only", base_results["ML-only"], regime_sys_matrix["ML-only"]),
        ("Technical-only", base_results["Technical-only"], regime_sys_matrix["Technical-only"]),
        ("Macro-only", base_results["Macro-only"], regime_sys_matrix["Macro-only"]),
        ("Market Intelligence", base_results["Market Intelligence-only"], regime_sys_matrix["Market Intelligence-only"]),
        ("Technical + ML", base_results["Technical + ML"], regime_sys_matrix["Technical + ML"]),
        ("Full Multi-Agent", base_results["Full Multi-Agent"], regime_sys_matrix["Full Multi-Agent"]),
    ]

    for name, b_res, r_dict in scorecard_data:
        ov = f"{b_res['acc']:.2f}%"
        bull = f"{r_dict['BULLISH_TREND']['acc']:.2f}%"
        bear = f"{r_dict['BEARISH_TREND']['acc']:.2f}%"
        cons = f"{r_dict['CONSOLIDATION']['acc']:.2f}%"

        # Classification criteria based on whether it beats random (50.0%) and always long/short
        if b_res['acc'] >= 52.0 and b_res['t3'] > 0.20:
            cls = "POSITIVE CONTRIBUTION"
        elif b_res['acc'] >= 49.0:
            cls = "NEUTRAL"
        else:
            cls = "WEAK / NEGATIVE"

        print(f"{name:<22} | {ov:<10} | {bull:<10} | {bear:<10} | {cons:<13} | {cls:<22}")

if __name__ == "__main__":
    run_edge_audit()
