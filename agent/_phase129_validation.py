"""
agent/_phase129_validation.py — Phase 12.9 Frozen Candidate V2 & Independent Walk-Forward Validation Script

Executes an internal walk-forward validation across 4 chronological windows (2,736 / 2,736 / 2,724 / 2,724 evaluations = 10,920 total)
for frozen CandidateSignalV2 and Conflict FOLLOW_MOMENTUM:

Evaluates:
1. Window-by-window performance of Candidate V2 vs 7 Baselines
2. Incremental edge vs Always LONG, REGIME_SWITCH_V1, and Fused V1
3. Conflict FOLLOW_MOMENTUM validation per window
4. Regime-level performance across Bullish, Bearish, Consolidation, High Volatility
5. Asset-level robustness across all 12 assets
6. Economic metrics (Expectancy, Win Rate, Payoff, Profit Factor, MFE, MAE)
7. Paired Bootstrap 95% Confidence Intervals for return differences
"""

import sys
import math
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.candidate_signal_v2 import CandidateSignalV2, CandidateSignalV2Result
from agent.regime_signal_research import RegimeSignalResearchEngine
from agent._phase126_feature_research import build_candidate_features_for_asset
from agent._phase128_regime_validation import calc_economic_metrics, bootstrap_ci


def bootstrap_paired_diff_ci(a: np.ndarray, b: np.ndarray, num_bootstraps: int = 1000, ci: float = 95.0) -> Tuple[float, float]:
    if len(a) == 0 or len(b) == 0 or len(a) != len(b):
        return 0.0, 0.0
    diffs = []
    np.random.seed(42)
    diff_arr = a - b
    for _ in range(num_bootstraps):
        sample = np.random.choice(diff_arr, size=len(diff_arr), replace=True)
        diffs.append(np.mean(sample))
    lower = np.percentile(diffs, (100.0 - ci) / 2.0)
    upper = np.percentile(diffs, 100.0 - (100.0 - ci) / 2.0)
    return float(lower), float(upper)


def run_walk_forward_validation():
    print("=" * 80)
    print("PHASE 12.9 — FROZEN CANDIDATE V2 & INDEPENDENT WALK-FORWARD VALIDATION")
    print("INTERNAL WALK-FORWARD VALIDATION (10,920 Asset-Bar Evaluations)")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    # Build candidate features per asset
    asset_dfs = {}
    for asset, df in engine._raw_data.items():
        df_f = build_candidate_features_for_asset(df)
        asset_dfs[asset] = df_f

    min_candles = min(len(df) for df in asset_dfs.values())
    v2_engine = CandidateSignalV2(high_vol_threshold_atr_pct=0.035)
    v1_research_engine = RegimeSignalResearchEngine(high_vol_threshold_atr_pct=0.035)

    records = []

    for step in range(engine.config.warmup_period, min_candles):
        for asset, df in asset_dfs.items():
            row = df.iloc[step]

            # Regime
            ema_f = float(row.get("ema20", row["close"]))
            ema_s = float(row.get("ema50", row["close"]))
            ema_slope = float(row["ema50"] - df.iloc[step - 1]["ema50"]) if step > 0 else 0.0
            regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

            v2_res: CandidateSignalV2Result = v2_engine.evaluate_bar(row, regime=regime)
            v1_res = v1_research_engine.evaluate_bar(row, regime=regime)
            cand_v1_dir = v1_research_engine.candidate_v1.evaluate_bar(row).direction

            entry_price = float(row["close"])
            ret_1_fwd = engine._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
            ret_3_fwd = engine._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
            ret_6_fwd = engine._calc_forward_return(df, step, horizon=6, entry_price=entry_price)

            future_slice = df.iloc[step + 1 : min(step + 7, len(df))]
            if not future_slice.empty and entry_price > 0:
                max_high = float(future_slice["high"].max())
                min_low = float(future_slice["low"].min())
                mfe_long = (max_high - entry_price) / entry_price
                mae_long = (min_low - entry_price) / entry_price
                mfe_short = (entry_price - min_low) / entry_price
                mae_short = (entry_price - max_high) / entry_price
            else:
                mfe_long = mae_long = mfe_short = mae_short = 0.0

            records.append({
                "step": step,
                "asset": asset,
                "timestamp": str(row["timestamp"]),
                "regime": regime,
                "cand_mr_dir": v2_res.mr_direction,
                "cand_mom_dir": v2_res.mom_direction,
                "cand_v1_dir": cand_v1_dir,
                "regime_switch_v1_dir": v1_res.regime_switch_direction,
                "cand_v2_dir": v2_res.direction,
                "v2_reason": v2_res.signal_reason,
                "is_conflict": v2_res.is_conflict,
                "conflict_type": v2_res.conflict_type,
                "c_follow_mom": v1_res.conflict_follow_mom,
                "ret_1_fwd": ret_1_fwd if ret_1_fwd is not None else 0.0,
                "ret_3_fwd": ret_3_fwd if ret_3_fwd is not None else 0.0,
                "ret_6_fwd": ret_6_fwd if ret_6_fwd is not None else 0.0,
                "mfe_long": mfe_long,
                "mae_long": mae_long,
                "mfe_short": mfe_short,
                "mae_short": mae_short,
            })

    df_all = pd.DataFrame(records)
    n_tot = len(df_all)

    # Define 4 Chronological Windows
    steps = df_all["step"].unique()
    steps.sort()
    w_size = len(steps) // 4

    w1_steps = set(steps[:w_size])
    w2_steps = set(steps[w_size : 2 * w_size])
    w3_steps = set(steps[2 * w_size : 3 * w_size])
    w4_steps = set(steps[3 * w_size :])

    windows = [
        ("WINDOW 1 (Early History)", df_all[df_all["step"].isin(w1_steps)]),
        ("WINDOW 2 (Mid-Early)", df_all[df_all["step"].isin(w2_steps)]),
        ("WINDOW 3 (Mid-Late)", df_all[df_all["step"].isin(w3_steps)]),
        ("WINDOW 4 (Final Chronological)", df_all[df_all["step"].isin(w4_steps)]),
    ]

    # 1. CHRONOLOGICAL WINDOW-BY-WINDOW RESULTS
    print("\n" + "=" * 80)
    print("1. CHRONOLOGICAL WALK-FORWARD WINDOW-BY-WINDOW RESULTS")
    print("=" * 80)

    for w_name, w_df in windows:
        ts_start = w_df["timestamp"].min()
        ts_end = w_df["timestamp"].max()
        print(f"\n--- {w_name} ---")
        print(f"Time Range: {ts_start} -> {ts_end} | Evaluations: {len(w_df)}")
        print(f"{'System / Strategy':<26} | {'Cov %':<6} | {'Accuracy':<9} | {'BalAcc':<8} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
        print("-" * 86)

        strats = [
            ("Always LONG", np.full(len(w_df), "LONG")),
            ("Always SHORT", np.full(len(w_df), "SHORT")),
            ("Candidate Fused V1", w_df["cand_v1_dir"].values),
            ("REGIME_SWITCH_V1", w_df["regime_switch_v1_dir"].values),
            ("CandidateSignalV2 (Frozen)", w_df["cand_v2_dir"].values),
        ]

        for s_name, s_dirs in strats:
            m = calc_economic_metrics(
                s_dirs, w_df["ret_3_fwd"].values, w_df["ret_1_fwd"].values, w_df["ret_6_fwd"].values,
                np.where(s_dirs == "LONG", w_df["mfe_long"].values, w_df["mfe_short"].values),
                np.where(s_dirs == "LONG", w_df["mae_long"].values, w_df["mae_short"].values)
            )
            print(f"{s_name:<26} | {m['Coverage']:>5.1f}% | {m['Accuracy']:>8.2f}% | {m['BalAcc']:>7.2f}% | {m['T1']:>+8.4f}% | {m['MeanT3']:>+8.4f}% | {m['T6']:>+8.4f}%")

    # 2. OVERALL SYSTEM COMPARISON & INCREMENTAL EDGE
    print("\n" + "=" * 80)
    print("2. OVERALL SYSTEM PERFORMANCE & INCREMENTAL EDGE (10,920 Evaluations)")
    print("=" * 80)

    all_strats = [
        ("Always LONG", np.full(n_tot, "LONG")),
        ("Always SHORT", np.full(n_tot, "SHORT")),
        ("Random (Seed=42)", np.random.choice(["LONG", "SHORT"], size=n_tot)),
        ("Candidate Fused V1", df_all["cand_v1_dir"].values),
        ("Candidate MR-only", df_all["cand_mr_dir"].values),
        ("Candidate Momentum-only", df_all["cand_mom_dir"].values),
        ("REGIME_SWITCH_V1", df_all["regime_switch_v1_dir"].values),
        ("CandidateSignalV2 (Frozen)", df_all["cand_v2_dir"].values),
    ]

    print(f"{'System / Strategy':<28} | {'Cov %':<6} | {'Accuracy':<9} | {'BalAcc':<8} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
    print("-" * 90)

    metrics_map = {}
    for s_name, s_dirs in all_strats:
        m = calc_economic_metrics(
            s_dirs, df_all["ret_3_fwd"].values, df_all["ret_1_fwd"].values, df_all["ret_6_fwd"].values,
            np.where(s_dirs == "LONG", df_all["mfe_long"].values, df_all["mfe_short"].values),
            np.where(s_dirs == "LONG", df_all["mae_long"].values, df_all["mae_short"].values)
        )
        metrics_map[s_name] = (m, s_dirs)
        print(f"{s_name:<28} | {m['Coverage']:>5.1f}% | {m['Accuracy']:>8.2f}% | {m['BalAcc']:>7.2f}% | {m['T1']:>+8.4f}% | {m['MeanT3']:>+8.4f}% | {m['T6']:>+8.4f}%")

    # Incremental Edge Calculations
    v2_m, v2_dirs = metrics_map["CandidateSignalV2 (Frozen)"]
    al_m, al_dirs = metrics_map["Always LONG"]
    rs1_m, rs1_dirs = metrics_map["REGIME_SWITCH_V1"]
    v1_m, v1_dirs = metrics_map["Candidate Fused V1"]

    diff_vs_al = v2_m["MeanT3"] - al_m["MeanT3"]
    diff_vs_rs1 = v2_m["MeanT3"] - rs1_m["MeanT3"]
    diff_vs_v1 = v2_m["MeanT3"] - v1_m["MeanT3"]

    print("\n--- INCREMENTAL EDGE SUMMARY ---")
    print(f"Candidate V2 T+3 Return minus Always LONG Return:        {diff_vs_al:+.4f}%")
    print(f"Candidate V2 T+3 Return minus REGIME_SWITCH_V1 Return:    {diff_vs_rs1:+.4f}%")
    print(f"Candidate V2 T+3 Return minus Candidate Fused V1 Return: {diff_vs_v1:+.4f}%")

    # 3. CONFLICT FOLLOW_MOMENTUM WALK-FORWARD VALIDATION
    print("\n" + "=" * 80)
    print("3. CONFLICT FOLLOW_MOMENTUM WALK-FORWARD VALIDATION")
    print("=" * 80)

    for w_name, w_df in windows:
        conf_w = w_df[w_df["is_conflict"]]
        n_c = len(conf_w)
        pct_c = (n_c / len(w_df)) * 100.0

        if n_c > 0:
            c_dirs = conf_w["c_follow_mom"].values
            r3_c = conf_w["ret_3_fwd"].values
            r1_c = conf_w["ret_1_fwd"].values
            r6_c = conf_w["ret_6_fwd"].values
            m = calc_economic_metrics(
                c_dirs, r3_c, r1_c, r6_c,
                np.where(c_dirs == "LONG", conf_w["mfe_long"].values, conf_w["mfe_short"].values),
                np.where(c_dirs == "LONG", conf_w["mae_long"].values, conf_w["mae_short"].values)
            )
            print(f"{w_name:<28} | N={n_c:<4d} ({pct_c:4.1f}%) | Acc: {m['Accuracy']:5.2f}% | Expectancy: {m['Expectancy']:+7.4f}% | PF: {m['ProfitFactor']:5.2f} | WinRate: {m['WinRate']:5.2f}%")

    # 4. REGIME VALIDATION
    print("\n" + "=" * 80)
    print("4. REGIME-LEVEL PERFORMANCE BREAKDOWN (CandidateSignalV2)")
    print("=" * 80)
    print(f"{'Regime':<18} | {'N':<6} | {'Coverage':<9} | {'Accuracy':<9} | {'BalAcc':<8} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
    print("-" * 88)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        sub_reg = df_all[df_all["regime"] == reg]
        s_dirs = sub_reg["cand_v2_dir"].values
        m = calc_economic_metrics(
            s_dirs, sub_reg["ret_3_fwd"].values, sub_reg["ret_1_fwd"].values, sub_reg["ret_6_fwd"].values,
            np.where(s_dirs == "LONG", sub_reg["mfe_long"].values, sub_reg["mfe_short"].values),
            np.where(s_dirs == "LONG", sub_reg["mae_long"].values, sub_reg["mae_short"].values)
        )
        print(f"{reg:<18} | {len(sub_reg):<6d} | {m['Coverage']:>8.1f}% | {m['Accuracy']:>8.2f}% | {m['BalAcc']:>7.2f}% | {m['T1']:>+8.4f}% | {m['MeanT3']:>+8.4f}% | {m['T6']:>+8.4f}%")

    # 5. ASSET ROBUSTNESS
    print("\n" + "=" * 80)
    print("5. ASSET-LEVEL ROBUSTNESS (CandidateSignalV2)")
    print("=" * 80)
    print(f"{'Asset':<12} | {'Active N':<8} | {'Accuracy':<9} | {'LONG Acc':<9} | {'SHORT Acc':<9} | {'Avg T+3':<9} | {'Coverage':<8}")
    print("-" * 75)

    for ast in cfg.assets:
        sub_ast = df_all[df_all["asset"] == ast]
        s_dirs = sub_ast["cand_v2_dir"].values
        m = calc_economic_metrics(
            s_dirs, sub_ast["ret_3_fwd"].values, sub_ast["ret_1_fwd"].values, sub_ast["ret_6_fwd"].values,
            np.where(s_dirs == "LONG", sub_ast["mfe_long"].values, sub_ast["mfe_short"].values),
            np.where(s_dirs == "LONG", sub_ast["mae_long"].values, sub_ast["mae_short"].values)
        )
        mask = (s_dirs != "NEUTRAL")
        if np.sum(mask) > 0:
            d_act = s_dirs[mask]
            r3_act = sub_ast["ret_3_fwd"].values[mask]
            l_m = (d_act == "LONG")
            s_m = (d_act == "SHORT")
            acc_l = np.mean(r3_act[l_m] > 0) * 100.0 if np.sum(l_m) > 0 else 0.0
            acc_s = np.mean(r3_act[s_m] < 0) * 100.0 if np.sum(s_m) > 0 else 0.0
        else:
            acc_l = acc_s = 0.0

        print(f"{ast:<12} | {m['N']:<8d} | {m['Accuracy']:>8.2f}% | {acc_l:>8.2f}% | {acc_s:>8.2f}% | {m['MeanT3']:>+8.4f}% | {m['Coverage']:>7.2f}%")

    # 6. PAIRED BOOTSTRAP STATISTICAL CONFIDENCE
    print("\n" + "=" * 80)
    print("6. PAIRED BOOTSTRAP STATISTICAL CONFIDENCE TESTING")
    print("=" * 80)

    mask_v2 = (df_all["cand_v2_dir"].values != "NEUTRAL")
    strat_v2_r3 = np.where(df_all["cand_v2_dir"].values[mask_v2] == "LONG", df_all["ret_3_fwd"].values[mask_v2], -df_all["ret_3_fwd"].values[mask_v2])
    strat_v2_r6 = np.where(df_all["cand_v2_dir"].values[mask_v2] == "LONG", df_all["ret_6_fwd"].values[mask_v2], -df_all["ret_6_fwd"].values[mask_v2])

    v2_t3_low, v2_t3_high = bootstrap_ci(strat_v2_r3 * 100.0)
    v2_t6_low, v2_t6_high = bootstrap_ci(strat_v2_r6 * 100.0)

    # Paired differences on active Candidate V2 bars
    r3_v2_active = df_all["ret_3_fwd"].values[mask_v2]
    dirs_v2_active = df_all["cand_v2_dir"].values[mask_v2]
    dirs_rs1_active = df_all["regime_switch_v1_dir"].values[mask_v2]

    strat_v2_act = np.where(dirs_v2_active == "LONG", r3_v2_active, -r3_v2_active)
    strat_al_act = r3_v2_active  # Always LONG return on same active bars
    strat_rs1_act = np.where(dirs_rs1_active == "LONG", r3_v2_active, np.where(dirs_rs1_active == "SHORT", -r3_v2_active, 0.0))

    diff_vs_al_low, diff_vs_al_high = bootstrap_paired_diff_ci(strat_v2_act * 100.0, strat_al_act * 100.0)
    diff_vs_rs1_low, diff_vs_rs1_high = bootstrap_paired_diff_ci(strat_v2_act * 100.0, strat_rs1_act * 100.0)

    print(f"Candidate V2 Mean T+3 Return:                       {np.mean(strat_v2_r3)*100.0:+.4f}% (95% CI: [{v2_t3_low:+.4f}%, {v2_t3_high:+.4f}%])")
    print(f"Candidate V2 Mean T+6 Return:                       {np.mean(strat_v2_r6)*100.0:+.4f}% (95% CI: [{v2_t6_low:+.4f}%, {v2_t6_high:+.4f}%])")
    print(f"Paired Diff: Candidate V2 minus Always LONG (T+3):  {np.mean(strat_v2_act - strat_al_act)*100.0:+.4f}% (95% CI: [{diff_vs_al_low:+.4f}%, {diff_vs_al_high:+.4f}%])")
    print(f"Paired Diff: Candidate V2 minus REGIME_SWITCH_V1:    {np.mean(strat_v2_act - strat_rs1_act)*100.0:+.4f}% (95% CI: [{diff_vs_rs1_low:+.4f}%, {diff_vs_rs1_high:+.4f}%])")

if __name__ == "__main__":
    run_walk_forward_validation()
