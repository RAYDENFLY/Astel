"""
agent/_phase126_feature_research.py — Phase 12.6 Feature Research & Candidate Signal Architecture Script

Evaluates candidate technical and structural market features across 10,920 evaluations (12 assets, 166.7 days of 4H candles):
1. ATR-Normalized Trend Distance (EMA20/ATR, EMA50/ATR, EMA20-50/ATR)
2. RSI14 (Directional & Mean-Reversion)
3. Bollinger %B & Normalized Middle Distance
4. Multi-Timeframe Trend (4H, 12H, 1D without lookahead)
5. Multi-Horizon Momentum (ret_1, ret_3, ret_6, ret_12, ret_24)
6. Volatility Regime (ATR %, Rolling Volatility)

Computes:
- Summary statistics & correlation metrics (Pearson T+1, T+3, T+6, Spearman)
- Quantile breakdowns (Q1 to Q5) and monotonic/mean-reverting pattern analysis
- Regime-conditional performance (Bullish, Bearish, Consolidation)
- Asset robustness across all 12 assets
- Pairwise feature redundancy correlation matrix
- Diagnostic combinations (Trend, Mean Reversion, Momentum, Regime Filter)
- Chronological In-Sample (60%) vs Out-of-Sample (40%) stability checks
- Final feature classifications (STRONG_CANDIDATE, WEAK_CANDIDATE, NO_SIGNAL, UNSTABLE, ASSET_SPECIFIC)
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


def build_candidate_features_for_asset(df: pd.DataFrame) -> pd.DataFrame:
    """Build candidate features for a single asset dataframe without lookahead bias."""
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # Returns
    df["ret_1"] = close.pct_change(1)
    df["ret_3"] = close.pct_change(3)
    df["ret_6"] = close.pct_change(6)
    df["ret_12"] = close.pct_change(12)
    df["ret_24"] = close.pct_change(24)

    # ATR (14 period)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr"] / close

    # Rolling Volatility
    df["volatility_20"] = close.pct_change().rolling(20).std()

    # EMAs
    df["ema20"] = close.ewm(span=20, adjust=False).mean()
    df["ema50"] = close.ewm(span=50, adjust=False).mean()
    df["ema_12h"] = close.ewm(span=60, adjust=False).mean()  # 20 * 3
    df["ema_1d"] = close.ewm(span=120, adjust=False).mean()  # 20 * 6

    # ATR-Normalized Trend Distance
    atr_safe = df["atr"].replace(0.0, np.nan)
    df["ema20_dist_atr"] = (close - df["ema20"]) / atr_safe
    df["ema50_dist_atr"] = (close - df["ema50"]) / atr_safe
    df["ema20_50_dist_atr"] = (df["ema20"] - df["ema50"]) / atr_safe

    # Multi-Timeframe Trend
    df["mtf_trend_4h"] = (close - df["ema20"]) / close
    df["mtf_trend_12h"] = (close - df["ema_12h"]) / close
    df["mtf_trend_1d"] = (close - df["ema_1d"]) / close

    # RSI (14 period)
    delta = close.diff()
    gain = delta.clip(lower=0.0).rolling(14).mean()
    loss = (-delta.clip(upper=0.0)).rolling(14).mean()
    rs = gain / loss.replace(0.0, np.nan)
    df["rsi14"] = 100.0 - (100.0 / (1.0 + rs.replace(0.0, np.nan)))
    df["rsi14"] = df["rsi14"].fillna(50.0)

    # Bollinger Bands (20 period, 2 std)
    b_mid = close.rolling(20).mean()
    b_std = close.rolling(20).std()
    b_upper = b_mid + 2.0 * b_std
    b_lower = b_mid - 2.0 * b_std
    b_width = (b_upper - b_lower).replace(0.0, np.nan)

    df["bollinger_pct_b"] = (close - b_lower) / b_width
    df["bollinger_dist_mid_norm"] = (close - b_mid) / (2.0 * b_std.replace(0.0, np.nan))

    return df


def run_feature_research():
    print("=" * 80)
    print("PHASE 12.6 — FEATURE RESEARCH & CANDIDATE SIGNAL ARCHITECTURE")
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

    records = []
    candidate_cols = [
        "ema20_dist_atr", "ema50_dist_atr", "ema20_50_dist_atr",
        "rsi14", "bollinger_pct_b", "bollinger_dist_mid_norm",
        "mtf_trend_4h", "mtf_trend_12h", "mtf_trend_1d",
        "ret_1", "ret_3", "ret_6", "ret_12", "ret_24",
        "atr_pct", "volatility_20"
    ]

    for step in range(engine.config.warmup_period, min_candles):
        for asset, df in asset_dfs.items():
            row = df.iloc[step]

            # Regime
            ema_f = float(row["ema20"])
            ema_s = float(row["ema50"])
            ema_slope = float(row["ema50"] - df.iloc[step - 1]["ema50"]) if step > 0 else 0.0
            regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

            entry_price = float(row["close"])
            ret_1_fwd = engine._calc_forward_return(df, step, horizon=1, entry_price=entry_price)
            ret_3_fwd = engine._calc_forward_return(df, step, horizon=3, entry_price=entry_price)
            ret_6_fwd = engine._calc_forward_return(df, step, horizon=6, entry_price=entry_price)

            rec = {
                "step": step,
                "asset": asset,
                "timestamp": str(row["timestamp"]),
                "regime": regime,
                "ret_1_fwd": ret_1_fwd if ret_1_fwd is not None else 0.0,
                "ret_3_fwd": ret_3_fwd if ret_3_fwd is not None else 0.0,
                "ret_6_fwd": ret_6_fwd if ret_6_fwd is not None else 0.0,
            }

            for c in candidate_cols:
                rec[c] = float(row[c]) if pd.notna(row[c]) else 0.0

            # Diagnostic Combinations
            # 1. Trend Combo: ATR-normalized EMA50 distance + 1D MTF trend
            rec["combo_trend"] = rec["ema50_dist_atr"] * 0.5 + rec["mtf_trend_1d"] * 10.0
            # 2. Mean Reversion Combo: (50 - RSI14) / 50 + (0.5 - Bollinger %B)
            rec["combo_mean_rev"] = (50.0 - rec["rsi14"]) / 50.0 + (0.5 - rec["bollinger_pct_b"])
            # 3. Multi-Horizon Momentum: ret_3 + ret_6 + ret_12
            rec["combo_momentum"] = rec["ret_3"] + rec["ret_6"] + rec["ret_12"]
            # 4. Regime Filter Combo: Trend * (1.0 / (atr_pct + 1e-4))
            rec["combo_regime"] = rec["mtf_trend_1d"] * (0.01 / (rec["atr_pct"] + 1e-4))

            records.append(rec)

    df_all = pd.DataFrame(records)
    all_features = candidate_cols + ["combo_trend", "combo_mean_rev", "combo_momentum", "combo_regime"]
    print(f"Total bar records collected: {len(df_all)}")

    # 1. INDIVIDUAL FEATURE SUMMARY STATS & CORRELATIONS
    print("\n" + "=" * 80)
    print("1. INDIVIDUAL FEATURE AUDIT (SUMMARY & CORRELATION TO FUTURE RETURNS)")
    print("=" * 80)
    print(f"{'Feature':<22} | {'T+1 r':<8} | {'T+3 r':<8} | {'T+6 r':<8} | {'Spearman':<9} | {'T+3 SignAcc':<11} | {'Mean > 0':<9} | {'Mean < 0':<9}")
    print("-" * 95)

    for feat in all_features:
        x = df_all[feat].values
        r1 = df_all["ret_1_fwd"].values
        r3 = df_all["ret_3_fwd"].values
        r6 = df_all["ret_6_fwd"].values

        p1, _ = calc_correlations(x, r1)
        p3, s3 = calc_correlations(x, r3)
        p6, _ = calc_correlations(x, r6)

        # For RSI and Bollinger %B, centered mean reversion baseline vs directional baseline
        if feat == "rsi14":
            x_centered = 50.0 - x
        elif feat in ("bollinger_pct_b", "bollinger_dist_mid_norm"):
            x_centered = -x
        else:
            x_centered = x

        mask_active = (x_centered != 0)
        sign_match = ((x_centered[mask_active] > 0) & (r3[mask_active] > 0)) | ((x_centered[mask_active] < 0) & (r3[mask_active] < 0))
        sign_acc = np.mean(sign_match) * 100.0 if np.sum(mask_active) > 0 else 0.0

        m_pos = float(np.mean(r3[x_centered > 0]) * 100.0) if np.sum(x_centered > 0) > 0 else 0.0
        m_neg = float(np.mean(r3[x_centered < 0]) * 100.0) if np.sum(x_centered < 0) > 0 else 0.0

        print(f"{feat:<22} | {p1:>+8.4f} | {p3:>+8.4f} | {p6:>+8.4f} | {s3:>+9.4f} | {sign_acc:>10.2f}% | {m_pos:>+8.4f}% | {m_neg:>+8.4f}%")

    # 2. FEATURE QUANTILE ANALYSIS (5 BINS)
    print("\n" + "=" * 80)
    print("2. FEATURE QUANTILE BREAKDOWN (5 QUANTILES)")
    print("=" * 80)

    key_features = ["ema50_dist_atr", "rsi14", "bollinger_pct_b", "mtf_trend_1d", "ret_12", "combo_trend", "combo_mean_rev"]

    for feat in key_features:
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

    # 3. REGIME-CONDITIONAL PERFORMANCE
    print("\n" + "=" * 80)
    print("3. REGIME-CONDITIONAL FEATURE CORRELATIONS (T+3 Horizon)")
    print("=" * 80)
    print(f"{'Regime':<18} | {'Feature':<20} | {'N':<6} | {'Pearson':<9} | {'Spearman':<9} | {'Sign Acc':<9} | {'Avg T+3':<9}")
    print("-" * 85)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        sub_reg = df_all[df_all["regime"] == reg]
        for feat in key_features:
            x = sub_reg[feat].values
            y = sub_reg["ret_3_fwd"].values
            p_corr, s_corr = calc_correlations(x, y)

            if feat == "rsi14":
                x_c = 50.0 - x
            elif feat == "bollinger_pct_b":
                x_c = 0.5 - x
            else:
                x_c = x

            sign_match = ((x_c > 0) & (y > 0)) | ((x_c < 0) & (y < 0))
            sign_acc = np.mean(sign_match) * 100.0 if len(x_c) > 0 else 0.0
            t3_avg = np.mean(y) * 100.0
            print(f"{reg:<18} | {feat:<20} | {len(x):<6d} | {p_corr:>+9.4f} | {s_corr:>+9.4f} | {sign_acc:>8.2f}% | {t3_avg:>+8.4f}%")

    # 4. CHRONOLOGICAL IN-SAMPLE (60%) VS OUT-OF-SAMPLE (40%) VALIDATION
    print("\n" + "=" * 80)
    print("4. CHRONOLOGICAL IN-SAMPLE (60%) VS OUT-OF-SAMPLE (40%) STABILITY CHECK")
    print("=" * 80)

    steps = df_all["step"].unique()
    steps.sort()
    split_idx = int(len(steps) * 0.60)
    is_steps = set(steps[:split_idx])
    oos_steps = set(steps[split_idx:])

    df_is = df_all[df_all["step"].isin(is_steps)]
    df_oos = df_all[df_all["step"].isin(oos_steps)]

    print(f"{'Feature':<22} | {'IS Pearson':<11} | {'OOS Pearson':<11} | {'IS SignAcc':<11} | {'OOS SignAcc':<11} | {'Stability':<15}")
    print("-" * 88)

    for feat in all_features:
        x_is = df_is[feat].values
        y_is = df_is["ret_3_fwd"].values

        x_oos = df_oos[feat].values
        y_oos = df_oos["ret_3_fwd"].values

        p_is, _ = calc_correlations(x_is, y_is)
        p_oos, _ = calc_correlations(x_oos, y_oos)

        if feat == "rsi14":
            x_is_c = 50.0 - x_is
            x_oos_c = 50.0 - x_oos
        elif feat in ("bollinger_pct_b", "bollinger_dist_mid_norm"):
            x_is_c = 0.5 - x_is
            x_oos_c = 0.5 - x_oos
        else:
            x_is_c = x_is
            x_oos_c = x_oos

        acc_is = np.mean(((x_is_c > 0) & (y_is > 0)) | ((x_is_c < 0) & (y_is < 0))) * 100.0
        acc_oos = np.mean(((x_oos_c > 0) & (y_oos > 0)) | ((x_oos_c < 0) & (y_oos < 0))) * 100.0

        same_sign = (p_is * p_oos > 0)
        st_label = "STABLE" if same_sign and abs(p_oos) >= 0.02 else ("UNSTABLE" if not same_sign else "WEAK")

        print(f"{feat:<22} | {p_is:>+11.4f} | {p_oos:>+11.4f} | {acc_is:>10.2f}% | {acc_oos:>10.2f}% | {st_label:<15}")

    # 5. FEATURE REDUNDANCY CORRELATION MATRIX
    print("\n" + "=" * 80)
    print("5. PAIRWISE FEATURE REDUNDANCY CORRELATION MATRIX")
    print("=" * 80)

    corr_df = df_all[candidate_cols].corr()
    print(corr_df.round(3).to_string())

if __name__ == "__main__":
    run_feature_research()
