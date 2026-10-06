"""
agent/_phase127_candidate_validation.py — Phase 12.7 Candidate Signal Implementation & Shadow Replay Validation Script

Runs a comprehensive, read-only historical decision replay across 10,920 evaluations (12 assets, 166.7 days of 4H candles):
Compares:
1. Always LONG
2. Always SHORT
3. Random
4. Previous Baseline Signal (baseline_signal: ema_dist * 2.0 + ret_1 * 0.5)
5. Candidate Mean-Reversion Only
6. Candidate Momentum Only
7. Candidate Fused Signal (candidate_signal_v1)

Evaluates:
- Overall baseline comparison table
- Candidate signal performance & coverage metrics
- Granular signal state breakdown (HIGH_CONSISTENCY_LONG/SHORT, SINGLE_FACTOR_LONG/SHORT, CONFLICT, NEUTRAL)
- Momentum conflict diagnostic frequency & outcomes
- Regime-conditional performance (Bullish, Bearish, Consolidation)
- Asset-level performance across all 12 assets
- Chronological In-Sample (60%) vs Out-of-Sample (40%) stability
- Shadow trade eligibility & MFE/MAE tracking for HIGH_CONSISTENCY signals
- Bootstrap 95% Confidence Intervals for accuracy and returns
"""

import sys
import math
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.candidate_signal import CandidateSignalV1, CandidateSignalResult
from agent._phase126_feature_research import build_candidate_features_for_asset


def bootstrap_ci(vals: np.ndarray, num_bootstraps: int = 1000, ci: float = 95.0) -> Tuple[float, float]:
    if len(vals) == 0:
        return 0.0, 0.0
    means = []
    np.random.seed(42)
    for _ in range(num_bootstraps):
        sample = np.random.choice(vals, size=len(vals), replace=True)
        means.append(np.mean(sample))
    lower = np.percentile(means, (100.0 - ci) / 2.0)
    upper = np.percentile(means, 100.0 - (100.0 - ci) / 2.0)
    return float(lower), float(upper)


def run_candidate_validation():
    print("=" * 80)
    print("PHASE 12.7 — CANDIDATE SIGNAL IMPLEMENTATION & SHADOW REPLAY VALIDATION")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    # Build features for each asset
    asset_dfs = {}
    for asset, df in engine._raw_data.items():
        df_f = build_candidate_features_for_asset(df)
        asset_dfs[asset] = df_f

    min_candles = min(len(df) for df in asset_dfs.values())
    total_steps = min_candles - engine.config.warmup_period

    candidate_engine = CandidateSignalV1()
    records = []

    for step in range(engine.config.warmup_period, min_candles):
        for asset, df in asset_dfs.items():
            row = df.iloc[step]

            # Baseline signal
            ema_dist = float(row.get("ema_distance", 0.0) or 0.0)
            ret_1 = float(row.get("return_1", 0.0) or 0.0)
            base_score = ema_dist * 2.0 + ret_1 * 0.5
            base_dir = "LONG" if base_score > 0.005 else ("SHORT" if base_score < -0.005 else "NEUTRAL")

            # Candidate signal V1
            cand_res: CandidateSignalResult = candidate_engine.evaluate_bar(row)

            # Regime
            ema_f = float(row.get("ema20", row["close"]))
            ema_s = float(row.get("ema50", row["close"]))
            ema_slope = float(row["ema50"] - df.iloc[step - 1]["ema50"]) if step > 0 else 0.0
            regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

            entry_price = float(row["close"])
            ret_1_fwd = engine._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
            ret_3_fwd = engine._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
            ret_6_fwd = engine._calc_forward_return(df, step, horizon=6, entry_price=entry_price)

            # MFE and MAE over 6 candles horizon
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
                "entry_price": entry_price,
                "base_dir": base_dir,
                "cand_mr_dir": cand_res.mr_direction,
                "cand_mom_dir": cand_res.mom_direction,
                "cand_mom_conflict": cand_res.mom_conflict,
                "cand_fused_state": cand_res.fused_state,
                "cand_dir": cand_res.direction,
                "cand_shadow_eligible": cand_res.is_shadow_eligible,
                "ema20_dist_atr": cand_res.ema20_dist_atr,
                "ret_1_fwd": ret_1_fwd if ret_1_fwd is not None else 0.0,
                "ret_3_fwd": ret_3_fwd if ret_3_fwd is not None else 0.0,
                "ret_6_fwd": ret_6_fwd if ret_6_fwd is not None else 0.0,
                "mfe_long": mfe_long,
                "mae_long": mae_long,
                "mfe_short": mfe_short,
                "mae_short": mae_short,
            })

    df_all = pd.DataFrame(records)
    print(f"Total bar records collected: {len(df_all)}")

    # 1. BASELINE & CANDIDATE SYSTEM COMPARISON
    print("\n" + "=" * 80)
    print("1. OVERALL SYSTEM PERFORMANCE COMPARISON (10,920 Evaluations)")
    print("=" * 80)
    print(f"{'System':<28} | {'N':<6} | {'LONG':<5} | {'SHORT':<5} | {'NEUT':<5} | {'Accuracy':<9} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
    print("-" * 98)

    np.random.seed(42)
    rand_dirs = np.random.choice(["LONG", "SHORT"], size=len(df_all))

    systems = [
        ("Always LONG", np.full(len(df_all), "LONG")),
        ("Always SHORT", np.full(len(df_all), "SHORT")),
        ("Random (Seed=42)", rand_dirs),
        ("Previous Baseline Signal", df_all["base_dir"].values),
        ("Candidate MR-only", df_all["cand_mr_dir"].values),
        ("Candidate Momentum-only", df_all["cand_mom_dir"].values),
        ("Candidate Fused Signal (v1)", df_all["cand_dir"].values),
    ]

    for sys_name, dirs in systems:
        mask_active = (dirs != "NEUTRAL")
        n_active = int(np.sum(mask_active))
        n_long = int(np.sum(dirs == "LONG"))
        n_short = int(np.sum(dirs == "SHORT"))
        n_neut = int(np.sum(dirs == "NEUTRAL"))

        if n_active > 0:
            dirs_act = dirs[mask_active]
            r3_act = df_all["ret_3_fwd"].values[mask_active]
            r1_act = df_all["ret_1_fwd"].values[mask_active]
            r6_act = df_all["ret_6_fwd"].values[mask_active]

            correct = ((dirs_act == "LONG") & (r3_act > 0)) | ((dirs_act == "SHORT") & (r3_act < 0))
            acc = float(np.mean(correct) * 100.0)

            # Strategy returns
            strat_r1 = np.where(dirs_act == "LONG", r1_act, -r1_act)
            strat_r3 = np.where(dirs_act == "LONG", r3_act, -r3_act)
            strat_r6 = np.where(dirs_act == "LONG", r6_act, -r6_act)

            t1_avg = float(np.mean(strat_r1) * 100.0)
            t3_avg = float(np.mean(strat_r3) * 100.0)
            t6_avg = float(np.mean(strat_r6) * 100.0)
        else:
            acc = t1_avg = t3_avg = t6_avg = 0.0

        print(f"{sys_name:<28} | {len(dirs):<6d} | {n_long:<5d} | {n_short:<5d} | {n_neut:<5d} | {acc:>8.2f}% | {t1_avg:>+8.4f}% | {t3_avg:>+8.4f}% | {t6_avg:>+8.4f}%")

    # 2. GRANULAR CANDIDATE SIGNAL PERFORMANCE METRICS
    print("\n" + "=" * 80)
    print("2. CANDIDATE FUSED SIGNAL (v1) DETAILED METRICS")
    print("=" * 80)

    cand_dirs = df_all["cand_dir"].values
    r3_all = df_all["ret_3_fwd"].values
    mask_act = (cand_dirs != "NEUTRAL")

    n_tot = len(df_all)
    n_act = np.sum(mask_act)
    coverage = (n_act / n_tot) * 100.0
    neut_pct = ((n_tot - n_act) / n_tot) * 100.0

    if n_act > 0:
        c_dirs = cand_dirs[mask_act]
        c_r3 = r3_all[mask_act]
        c_correct = ((c_dirs == "LONG") & (c_r3 > 0)) | ((c_dirs == "SHORT") & (c_r3 < 0))
        acc_dir = np.mean(c_correct) * 100.0

        c_long = (c_dirs == "LONG")
        c_short = (c_dirs == "SHORT")

        acc_long = np.mean(c_r3[c_long] > 0) * 100.0 if np.sum(c_long) > 0 else 0.0
        acc_short = np.mean(c_r3[c_short] < 0) * 100.0 if np.sum(c_short) > 0 else 0.0
        bal_acc = (acc_long + acc_short) / 2.0

        strat_ret3 = np.where(c_dirs == "LONG", c_r3, -c_r3)
        mean_t3 = np.mean(strat_ret3) * 100.0
        med_t3 = np.median(strat_ret3) * 100.0
        pos_freq = np.mean(strat_ret3 > 0) * 100.0

        acc_lower, acc_upper = bootstrap_ci(c_correct.astype(float) * 100.0)
        ret_lower, ret_upper = bootstrap_ci(strat_ret3 * 100.0)
    else:
        acc_dir = acc_long = acc_short = bal_acc = mean_t3 = med_t3 = pos_freq = 0.0
        acc_lower = acc_upper = ret_lower = ret_upper = 0.0

    print(f"Signal Coverage:                   {coverage:.2f}% ({n_act} active / {n_tot} total)")
    print(f"Neutral Frequency:                 {neut_pct:.2f}%")
    print(f"Directional Accuracy:              {acc_dir:.2f}% (95% CI: [{acc_lower:.2f}%, {acc_upper:.2f}%])")
    print(f"Balanced Accuracy:                 {bal_acc:.2f}% (LONG: {acc_long:.2f}%, SHORT: {acc_short:.2f}%)")
    print(f"Mean T+3 Return:                   {mean_t3:+.4f}% (95% CI: [{ret_lower:+.4f}%, {ret_upper:+.4f}%])")
    print(f"Median T+3 Return:                 {med_t3:+.4f}%")
    print(f"Positive Forward Return Frequency: {pos_freq:.2f}%")

    # 3. SIGNAL STATE BREAKDOWN
    print("\n" + "=" * 80)
    print("3. SIGNAL STATE PERFORMANCE BREAKDOWN")
    print("=" * 80)
    print(f"{'State':<24} | {'N':<6} | {'Freq %':<8} | {'Accuracy':<9} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
    print("-" * 85)

    states = [
        "HIGH_CONSISTENCY_LONG",
        "HIGH_CONSISTENCY_SHORT",
        "SINGLE_FACTOR_LONG",
        "SINGLE_FACTOR_SHORT",
        "CONFLICT",
        "NEUTRAL",
    ]

    for st in states:
        sub = df_all[df_all["cand_fused_state"] == st]
        n_st = len(sub)
        freq_st = (n_st / n_tot) * 100.0

        if n_st > 0 and st not in ("CONFLICT", "NEUTRAL"):
            st_dir = "LONG" if "LONG" in st else "SHORT"
            r3_st = sub["ret_3_fwd"].values
            r1_st = sub["ret_1_fwd"].values
            r6_st = sub["ret_6_fwd"].values

            correct = (r3_st > 0) if st_dir == "LONG" else (r3_st < 0)
            acc_st = np.mean(correct) * 100.0

            strat_r1 = r1_st if st_dir == "LONG" else -r1_st
            strat_r3 = r3_st if st_dir == "LONG" else -r3_st
            strat_r6 = r6_st if st_dir == "LONG" else -r6_st

            t1_val = np.mean(strat_r1) * 100.0
            t3_val = np.mean(strat_r3) * 100.0
            t6_val = np.mean(strat_r6) * 100.0
            acc_str = f"{acc_st:>8.2f}%"
        else:
            t1_val = sub["ret_1_fwd"].mean() * 100.0
            t3_val = sub["ret_3_fwd"].mean() * 100.0
            t6_val = sub["ret_6_fwd"].mean() * 100.0
            acc_str = "    N/A  "

        print(f"{st:<24} | {n_st:<6d} | {freq_st:>7.2f}% | {acc_str} | {t1_val:>+8.4f}% | {t3_val:>+8.4f}% | {t6_val:>+8.4f}%")

    # 4. MOMENTUM CONFLICT DIAGNOSTIC
    print("\n" + "=" * 80)
    print("4. MOMENTUM CONFLICT DIAGNOSTIC (ret_3 * ret_12 < 0)")
    print("=" * 80)
    conf_df = df_all[df_all["cand_mom_conflict"]]
    n_conf = len(conf_df)
    pct_conf = (n_conf / n_tot) * 100.0
    t3_conf = conf_df["ret_3_fwd"].mean() * 100.0
    print(f"Momentum Conflict Frequency: {pct_conf:.2f}% ({n_conf} / {n_tot} bars)")
    print(f"Average T+3 Return during Momentum Conflict: {t3_conf:+.4f}%")

    # 5. REGIME PERFORMANCE
    print("\n" + "=" * 80)
    print("5. REGIME-SPECIFIC PERFORMANCE COMPARISON")
    print("=" * 80)
    print(f"{'Regime':<18} | {'System':<26} | {'N':<6} | {'Accuracy':<9} | {'Avg T+3':<9} | {'Coverage':<8}")
    print("-" * 82)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        sub_reg = df_all[df_all["regime"] == reg]
        n_reg = len(sub_reg)

        # Always LONG
        r3_reg = sub_reg["ret_3_fwd"].values
        acc_long = np.mean(r3_reg > 0) * 100.0
        ret_long = np.mean(r3_reg) * 100.0
        print(f"{reg:<18} | {'Always LONG':<26} | {n_reg:<6d} | {acc_long:>8.2f}% | {ret_long:>+8.4f}% | 100.00%")

        # Previous Baseline Signal
        base_dirs = sub_reg["base_dir"].values
        m_base = (base_dirs != "NEUTRAL")
        if np.sum(m_base) > 0:
            b_dirs = base_dirs[m_base]
            b_r3 = r3_reg[m_base]
            b_corr = ((b_dirs == "LONG") & (b_r3 > 0)) | ((b_dirs == "SHORT") & (b_r3 < 0))
            acc_base = np.mean(b_corr) * 100.0
            ret_base = np.mean(np.where(b_dirs == "LONG", b_r3, -b_r3)) * 100.0
            cov_base = (np.sum(m_base) / n_reg) * 100.0
        else:
            acc_base = ret_base = cov_base = 0.0
        print(f"{'':<18} | {'Previous Baseline Signal':<26} | {n_reg:<6d} | {acc_base:>8.2f}% | {ret_base:>+8.4f}% | {cov_base:>7.2f}%")

        # Candidate Fused Signal
        cand_dirs = sub_reg["cand_dir"].values
        m_cand = (cand_dirs != "NEUTRAL")
        if np.sum(m_cand) > 0:
            c_dirs = cand_dirs[m_cand]
            c_r3 = r3_reg[m_cand]
            c_corr = ((c_dirs == "LONG") & (c_r3 > 0)) | ((c_dirs == "SHORT") & (c_r3 < 0))
            acc_cand = np.mean(c_corr) * 100.0
            ret_cand = np.mean(np.where(c_dirs == "LONG", c_r3, -c_r3)) * 100.0
            cov_cand = (np.sum(m_cand) / n_reg) * 100.0
        else:
            acc_cand = ret_cand = cov_cand = 0.0
        print(f"{'':<18} | {'Candidate Fused Signal (v1)':<26} | {n_reg:<6d} | {acc_cand:>8.2f}% | {ret_cand:>+8.4f}% | {cov_cand:>7.2f}%")

    # 6. ASSET PERFORMANCE
    print("\n" + "=" * 80)
    print("6. ASSET-LEVEL PERFORMANCE BREAKDOWN (Candidate Fused Signal)")
    print("=" * 80)
    print(f"{'Asset':<12} | {'Active N':<8} | {'Accuracy':<9} | {'LONG Acc':<9} | {'SHORT Acc':<9} | {'Avg T+3':<9} | {'Coverage':<8}")
    print("-" * 75)

    for ast in cfg.assets:
        sub_ast = df_all[df_all["asset"] == ast]
        n_ast = len(sub_ast)
        c_dirs = sub_ast["cand_dir"].values
        m_act = (c_dirs != "NEUTRAL")
        n_act = np.sum(m_act)
        cov_ast = (n_act / n_ast) * 100.0

        if n_act > 0:
            dirs_act = c_dirs[m_act]
            r3_act = sub_ast["ret_3_fwd"].values[m_act]

            correct = ((dirs_act == "LONG") & (r3_act > 0)) | ((dirs_act == "SHORT") & (r3_act < 0))
            acc_ast = np.mean(correct) * 100.0

            l_mask = (dirs_act == "LONG")
            s_mask = (dirs_act == "SHORT")
            acc_l = np.mean(r3_act[l_mask] > 0) * 100.0 if np.sum(l_mask) > 0 else 0.0
            acc_s = np.mean(r3_act[s_mask] < 0) * 100.0 if np.sum(s_mask) > 0 else 0.0

            strat_r3 = np.where(dirs_act == "LONG", r3_act, -r3_act)
            ret_ast = np.mean(strat_r3) * 100.0
        else:
            acc_ast = acc_l = acc_s = ret_ast = 0.0

        print(f"{ast:<12} | {n_act:<8d} | {acc_ast:>8.2f}% | {acc_l:>8.2f}% | {acc_s:>8.2f}% | {ret_ast:>+8.4f}% | {cov_ast:>7.2f}%")

    # 7. IN-SAMPLE VS OUT-OF-SAMPLE STABILITY
    print("\n" + "=" * 80)
    print("7. IN-SAMPLE (60%) VS OUT-OF-SAMPLE (40%) VALIDATION")
    print("=" * 80)

    steps = df_all["step"].unique()
    steps.sort()
    split_idx = int(len(steps) * 0.60)
    is_steps = set(steps[:split_idx])
    oos_steps = set(steps[split_idx:])

    df_is = df_all[df_all["step"].isin(is_steps)]
    df_oos = df_all[df_all["step"].isin(oos_steps)]

    print(f"{'System':<28} | {'IS Acc':<9} | {'OOS Acc':<9} | {'IS Avg T+3':<10} | {'OOS Avg T+3':<10}")
    print("-" * 75)

    for sys_name, col_name in [("Previous Baseline Signal", "base_dir"), ("Candidate Fused Signal (v1)", "cand_dir")]:
        for df_sub, label in [(df_is, "IS"), (df_oos, "OOS")]:
            dirs = df_sub[col_name].values
            r3 = df_sub["ret_3_fwd"].values
            mask = (dirs != "NEUTRAL")
            if np.sum(mask) > 0:
                d_act = dirs[mask]
                r3_act = r3[mask]
                corr = ((d_act == "LONG") & (r3_act > 0)) | ((d_act == "SHORT") & (r3_act < 0))
                acc = np.mean(corr) * 100.0
                ret3 = np.mean(np.where(d_act == "LONG", r3_act, -r3_act)) * 100.0
            else:
                acc = ret3 = 0.0
            if label == "IS":
                is_acc, is_ret = acc, ret3
            else:
                oos_acc, oos_ret = acc, ret3

        print(f"{sys_name:<28} | {is_acc:>8.2f}% | {oos_acc:>8.2f}% | {is_ret:>+9.4f}% | {oos_ret:>+9.4f}%")

    # 8. SHADOW OBSERVATIONS & HIGH-CONSISTENCY TRADES
    print("\n" + "=" * 80)
    print("8. SHADOW OBSERVATIONS & HIGH-CONSISTENCY TRADE LIFECYCLE (HIGH_CONSISTENCY)")
    print("=" * 80)

    hc_df = df_all[df_all["cand_shadow_eligible"]]
    n_hc = len(hc_df)
    pct_hc = (n_hc / n_tot) * 100.0

    print(f"Total High-Consistency Shadow Observations: {n_hc} ({pct_hc:.2f}% of all evaluations)")

    if n_hc > 0:
        hc_dirs = hc_df["cand_dir"].values
        r3_hc = hc_df["ret_3_fwd"].values
        r6_hc = hc_df["ret_6_fwd"].values

        corr_hc = ((hc_dirs == "LONG") & (r3_hc > 0)) | ((hc_dirs == "SHORT") & (r3_hc < 0))
        acc_hc = np.mean(corr_hc) * 100.0

        strat_r3_hc = np.where(hc_dirs == "LONG", r3_hc, -r3_hc)
        strat_r6_hc = np.where(hc_dirs == "LONG", r6_hc, -r6_hc)

        mfe_hc = np.where(hc_dirs == "LONG", hc_df["mfe_long"].values, hc_df["mfe_short"].values)
        mae_hc = np.where(hc_dirs == "LONG", hc_df["mae_long"].values, hc_df["mae_short"].values)

        print(f"High-Consistency Directional Accuracy:     {acc_hc:.2f}%")
        print(f"Average High-Consistency T+3 Return:       {np.mean(strat_r3_hc)*100.0:+.4f}%")
        print(f"Average High-Consistency T+6 Return:       {np.mean(strat_r6_hc)*100.0:+.4f}%")
        print(f"Average Maximum Favorable Excursion (MFE): {np.mean(mfe_hc)*100.0:+.4f}%")
        print(f"Average Maximum Adverse Excursion (MAE):   {np.mean(mae_hc)*100.0:+.4f}%")

if __name__ == "__main__":
    run_candidate_validation()
