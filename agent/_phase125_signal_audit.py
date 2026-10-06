"""
agent/_phase125_signal_audit.py — Phase 12.5 Signal Calibration & Feature Predictive Value Audit Script

Performs a granular, read-only diagnostic audit of the underlying feature components:
- ema_distance
- return_1 (momentum)
- score = ema_distance * 2.0 + return_1 * 0.5
- threshold boundaries (±0.02, ±0.01, ±0.005, 0)
- signal stability (flip rates, direction durations)
- quantile performance (Q1-Q5)
- regime & asset robustness
- IS (60%) vs OOS (40%) validation
"""

import sys
import math
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig


def calc_correlations(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return 0.0, 0.0
    p_corr, _ = stats.pearsonr(x, y)
    s_corr, _ = stats.spearmanr(x, y)
    return float(p_corr), float(s_corr)


def run_signal_audit():
    print("=" * 80)
    print("PHASE 12.5 — SIGNAL CALIBRATION & FEATURE PREDICTIVE VALUE AUDIT")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    min_candles = min(len(df) for df in engine._raw_data.values())
    total_steps = min_candles - engine.config.warmup_period

    records = []

    for step in range(engine.config.warmup_period, min_candles):
        for asset, df in engine._raw_data.items():
            slice_df = df.iloc[: step + 1].copy()
            if "asset" not in slice_df.columns:
                slice_df["asset"] = asset
            try:
                feats_df = engine.feature_builder.build(slice_df, is_training=False)
                if feats_df.empty:
                    continue
                bar = feats_df.iloc[-1]
            except Exception as e:
                continue

            analysis = engine._build_asset_analysis_at_step(asset, bar)

            ret_1_feat = float(bar.get("return_1", 0.0) or 0.0)
            ema_dist = float(bar.get("ema_distance", 0.0) or 0.0)
            score = analysis.prediction

            entry_price = float(df.iloc[step]["close"])
            ret_1_fwd = engine._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
            ret_3_fwd = engine._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
            ret_6_fwd = engine._calc_forward_return(df, step, horizon=6, entry_price=entry_price)

            records.append({
                "step": step,
                "asset": asset,
                "timestamp": str(df.iloc[step]["timestamp"]),
                "regime": analysis.market_regime,
                "ema_dist": ema_dist,
                "ret_1": ret_1_feat,
                "score": score,
                "direction": analysis.direction,
                "probability": analysis.probability,
                "confidence": analysis.confidence,
                "ret_1_fwd": ret_1_fwd if ret_1_fwd is not None else 0.0,
                "ret_3_fwd": ret_3_fwd if ret_3_fwd is not None else 0.0,
                "ret_6_fwd": ret_6_fwd if ret_6_fwd is not None else 0.0,
            })

    df_all = pd.DataFrame(records)
    print(f"Total bar records collected: {len(df_all)}")

    if df_all.empty:
        print("ERROR: No evaluation records collected!")
        return

    # 1. CURRENT SIGNAL DECOMPOSITION STATS
    print("\n" + "=" * 80)
    print("1. FEATURE DECOMPOSITION SUMMARY STATISTICS")
    print("=" * 80)
    print(f"{'Feature':<15} | {'N':<6} | {'Mean':<10} | {'Median':<10} | {'Std':<10} | {'Min':<10} | {'Max':<10}")
    print("-" * 80)
    for feat in ["ema_dist", "ret_1", "score"]:
        vals = df_all[feat].values
        print(f"{feat:<15} | {len(vals):<6d} | {np.mean(vals):>+10.6f} | {np.median(vals):>+10.6f} | {np.std(vals):>10.6f} | {np.min(vals):>+10.6f} | {np.max(vals):>+10.6f}")

    # 2. FEATURE-TO-FUTURE-RETURN RELATIONSHIP (CORRELATION & SIGN ACCURACY)
    print("\n" + "=" * 80)
    print("2. FEATURE-TO-FUTURE-RETURN RELATIONSHIP (CORRELATION & SIGN ACCURACY)")
    print("=" * 80)
    print(f"{'Feature':<12} | {'Horizon':<8} | {'Pearson':<9} | {'Spearman':<9} | {'Sign Acc':<9} | {'Mean > 0':<10} | {'Mean < 0':<10}")
    print("-" * 85)

    horizons = [("ret_1_fwd", "T+1"), ("ret_3_fwd", "T+3"), ("ret_6_fwd", "T+6")]
    features = ["ema_dist", "ret_1", "score"]

    for feat in features:
        for fwd_col, h_label in horizons:
            x = df_all[feat].values
            y = df_all[fwd_col].values

            p_corr, s_corr = calc_correlations(x, y)

            mask_active = (x != 0)
            if np.sum(mask_active) > 0:
                sign_match = ((x[mask_active] > 0) & (y[mask_active] > 0)) | ((x[mask_active] < 0) & (y[mask_active] < 0))
                sign_acc = np.mean(sign_match) * 100.0
            else:
                sign_acc = 0.0

            mean_pos = float(np.mean(y[x > 0]) * 100.0) if np.sum(x > 0) > 0 else 0.0
            mean_neg = float(np.mean(y[x < 0]) * 100.0) if np.sum(x < 0) > 0 else 0.0

            print(f"{feat:<12} | {h_label:<8} | {p_corr:>+9.4f} | {s_corr:>+9.4f} | {sign_acc:>8.2f}% | {mean_pos:>+9.4f}% | {mean_neg:>+9.4f}%")

    # 3. FEATURE QUANTILE ANALYSIS (5 BINS)
    print("\n" + "=" * 80)
    print("3. FEATURE QUANTILE ANALYSIS (5 QUANTILES)")
    print("=" * 80)

    for feat in features:
        print(f"\n--- Quantile Breakdown for: {feat} ---")
        print(f"{'Quantile':<10} | {'N':<6} | {'Avg Feature':<12} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9} | {'Pos T+3 %':<10}")
        print("-" * 80)

        df_all["q_bin"] = pd.qcut(df_all[feat], q=5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"], duplicates="drop")
        for q_label in ["Q1", "Q2", "Q3", "Q4", "Q5"]:
            df_q = df_all[df_all["q_bin"] == q_label]
            if df_q.empty:
                continue
            avg_f = df_q[feat].mean()
            t1_val = df_q["ret_1_fwd"].mean() * 100.0
            t3_val = df_q["ret_3_fwd"].mean() * 100.0
            t6_val = df_q["ret_6_fwd"].mean() * 100.0
            pos_pct = (df_q["ret_3_fwd"] > 0).mean() * 100.0
            print(f"{q_label:<10} | {len(df_q):<6d} | {avg_f:>+12.6f} | {t1_val:>+8.4f}% | {t3_val:>+8.4f}% | {t6_val:>+8.4f}% | {pos_pct:>9.2f}%")

    # 4. DIAGNOSTIC LINEAR REGRESSION (Combined Effect)
    print("\n" + "=" * 80)
    print("4. DIAGNOSTIC LINEAR REGRESSION: T+3 Forward Return ~ ema_dist + ret_1")
    print("=" * 80)

    X = np.column_stack([df_all["ema_dist"].values, df_all["ret_1"].values])
    X_design = np.column_stack([np.ones(len(X)), X])
    Y = df_all["ret_3_fwd"].values

    beta, residuals, rank, s = np.linalg.lstsq(X_design, Y, rcond=None)
    y_pred = X_design @ beta
    ss_tot = np.sum((Y - np.mean(Y)) ** 2)
    ss_res = np.sum((Y - y_pred) ** 2)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

    print(f"Regression Intercept (beta_0): {beta[0]:+.6f}")
    print(f"ema_dist Coefficient (beta_1):  {beta[1]:+.6f}")
    print(f"ret_1 Coefficient (beta_2):     {beta[2]:+.6f}")
    print(f"Regression R-squared (R^2):    {r_squared:.6f}")

    # 5. THRESHOLD DIAGNOSTIC AUDIT
    print("\n" + "=" * 80)
    print("5. THRESHOLD DIAGNOSTIC AUDIT AROUND PRODUCTION SCORE THRESHOLDS")
    print("=" * 80)

    thresh_bins = [
        ("Extreme Bear (< -0.02)", lambda s: s < -0.02),
        ("Bearish [-0.02, -0.01)", lambda s: (s >= -0.02) & (s < -0.01)),
        ("Weak Bear [-0.01, -0.005)", lambda s: (s >= -0.01) & (s < -0.005)),
        ("Neutral Noise [-0.005, +0.005]", lambda s: (s >= -0.005) & (s <= +0.005)),
        ("Weak Bull (+0.005, +0.01]", lambda s: (s > +0.005) & (s <= +0.01)),
        ("Bullish (+0.01, +0.02]", lambda s: (s > +0.01) & (s <= +0.02)),
        ("Extreme Bull (> +0.02)", lambda s: s > +0.02),
    ]

    print(f"{'Threshold Region':<32} | {'N':<6} | {'Sign Acc':<9} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
    print("-" * 85)

    for label, mask_fn in thresh_bins:
        sub = df_all[mask_fn(df_all["score"])]
        if sub.empty:
            print(f"{label:<32} | 0      |     0.00% |   +0.0000% |   +0.0000% |   +0.0000%")
            continue
        n_sub = len(sub)
        scores_sub = sub["score"].values
        ret3_sub = sub["ret_3_fwd"].values
        sign_match = ((scores_sub > 0) & (ret3_sub > 0)) | ((scores_sub < 0) & (ret3_sub < 0))
        sign_acc = np.mean(sign_match) * 100.0 if n_sub > 0 else 0.0

        t1_avg = sub["ret_1_fwd"].mean() * 100.0
        t3_avg = sub["ret_3_fwd"].mean() * 100.0
        t6_avg = sub["ret_6_fwd"].mean() * 100.0

        print(f"{label:<32} | {n_sub:<6d} | {sign_acc:>8.2f}% | {t1_avg:>+8.4f}% | {t3_avg:>+8.4f}% | {t6_avg:>+8.4f}%")

    # 6. REGIME-SPECIFIC FEATURE CORRELATIONS
    print("\n" + "=" * 80)
    print("6. REGIME-SPECIFIC FEATURE CORRELATIONS (T+3 Horizon)")
    print("=" * 80)
    print(f"{'Regime':<18} | {'Feature':<12} | {'N':<6} | {'Pearson':<9} | {'Spearman':<9} | {'Sign Acc':<9} | {'Avg T+3':<9}")
    print("-" * 80)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        sub_reg = df_all[df_all["regime"] == reg]
        for feat in ["ema_dist", "ret_1", "score"]:
            x = sub_reg[feat].values
            y = sub_reg["ret_3_fwd"].values
            p_corr, s_corr = calc_correlations(x, y)
            sign_match = ((x > 0) & (y > 0)) | ((x < 0) & (y < 0))
            sign_acc = np.mean(sign_match) * 100.0 if len(x) > 0 else 0.0
            t3_avg = np.mean(y) * 100.0
            print(f"{reg:<18} | {feat:<12} | {len(x):<6d} | {p_corr:>+9.4f} | {s_corr:>+9.4f} | {sign_acc:>8.2f}% | {t3_avg:>+8.4f}%")

    # 7. ASSET-LEVEL SIGNAL ACCURACY
    print("\n" + "=" * 80)
    print("7. ASSET-LEVEL SIGNAL ACCURACY (T+3 Horizon)")
    print("=" * 80)
    print(f"{'Asset':<12} | {'EMA Acc':<9} | {'ret_1 Acc':<9} | {'Score Acc':<9} | {'Avg T+3':<9}")
    print("-" * 60)

    for ast in cfg.assets:
        sub_ast = df_all[df_all["asset"] == ast]
        if sub_ast.empty:
            continue
        y = sub_ast["ret_3_fwd"].values

        x_ema = sub_ast["ema_dist"].values
        acc_ema = np.mean(((x_ema > 0) & (y > 0)) | ((x_ema < 0) & (y < 0))) * 100.0

        x_ret = sub_ast["ret_1"].values
        acc_ret = np.mean(((x_ret > 0) & (y > 0)) | ((x_ret < 0) & (y < 0))) * 100.0

        x_score = sub_ast["score"].values
        acc_score = np.mean(((x_score > 0) & (y > 0)) | ((x_score < 0) & (y < 0))) * 100.0

        t3_avg = np.mean(y) * 100.0

        print(f"{ast:<12} | {acc_ema:>8.2f}% | {acc_ret:>8.2f}% | {acc_score:>8.2f}% | {t3_avg:>+8.4f}%")

    # 8. SIGNAL STABILITY & FLIP RATE AUDIT
    print("\n" + "=" * 80)
    print("8. SIGNAL STABILITY & DIRECTION FLIP RATE AUDIT")
    print("=" * 80)

    flip_counts = 0
    total_transitions = 0
    durations = []

    for ast in cfg.assets:
        sub_ast = df_all[df_all["asset"] == ast].sort_values("step")
        dirs = sub_ast["direction"].values

        curr_dir = dirs[0]
        curr_len = 1
        for d in dirs[1:]:
            total_transitions += 1
            if d != curr_dir:
                flip_counts += 1
                durations.append(curr_len)
                curr_dir = d
                curr_len = 1
            else:
                curr_len += 1
        durations.append(curr_len)

    flip_rate = (flip_counts / total_transitions * 100.0) if total_transitions > 0 else 0.0
    mean_duration = float(np.mean(durations)) if durations else 0.0

    print(f"Total Direction Transitions: {total_transitions}")
    print(f"Total Direction Flips: {flip_counts}")
    print(f"Signal Flip Rate: {flip_rate:.2f}% (frequent noise switches)")
    print(f"Average Duration per Directional Run: {mean_duration:.2f} candles ({mean_duration * 4:.1f} hours)")

    # 9. IN-SAMPLE VS OUT-OF-SAMPLE FEATURE RELATIONSHIP
    print("\n" + "=" * 80)
    print("9. IN-SAMPLE (60%) VS OUT-OF-SAMPLE (40%) FEATURE CORRELATION CHECK")
    print("=" * 80)

    steps = df_all["step"].unique()
    steps.sort()
    split_idx = int(len(steps) * 0.60)
    is_steps = set(steps[:split_idx])
    oos_steps = set(steps[split_idx:])

    df_is = df_all[df_all["step"].isin(is_steps)]
    df_oos = df_all[df_all["step"].isin(oos_steps)]

    print(f"{'Feature':<12} | {'IS Pearson':<11} | {'OOS Pearson':<11} | {'IS Sign Acc':<11} | {'OOS Sign Acc':<11}")
    print("-" * 75)

    for feat in ["ema_dist", "ret_1", "score"]:
        p_is, _ = calc_correlations(df_is[feat].values, df_is["ret_3_fwd"].values)
        p_oos, _ = calc_correlations(df_oos[feat].values, df_oos["ret_3_fwd"].values)

        acc_is = np.mean(((df_is[feat] > 0) & (df_is["ret_3_fwd"] > 0)) | ((df_is[feat] < 0) & (df_is["ret_3_fwd"] < 0))) * 100.0
        acc_oos = np.mean(((df_oos[feat] > 0) & (df_oos["ret_3_fwd"] > 0)) | ((df_oos[feat] < 0) & (df_oos["ret_3_fwd"] < 0))) * 100.0

        print(f"{feat:<12} | {p_is:>+11.4f} | {p_oos:>+11.4f} | {acc_is:>10.2f}% | {acc_oos:>10.2f}%")

if __name__ == "__main__":
    run_signal_audit()
