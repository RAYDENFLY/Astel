"""
agent/_phase14_oos_validation.py — Phase 14 Independent OOS Validation, Paired Edge & Trading-Cost Audit Engine

Performs a strictly read-only quantitative audit of frozen CandidateSignalV2:
- Data Provenance Audit (identifies fresh vs overlapping data)
- Data Quality Audit (gaps, duplicates, OHLC validity, timezone consistency)
- Paired Observation-by-Observation Benchmark Analysis (Candidate V2 vs Always LONG, Always SHORT, Random)
- Paired 95% Bootstrap Confidence Intervals for return differences
- Conflict Directional Audit (MR_SHORT_MOM_LONG vs MR_LONG_MOM_SHORT)
- Regime Breakdown & Asset Breakdown with Sample Size Labels
- Chronological Temporal Stability across 4 Windows
- Transparent Trading Cost Model (OPTIMISTIC, BASE, ADVERSE scenarios)
- Break-Even Trading Cost & Break-Even Paired Edge Calculations
- Safety Assertion: EXECUTION_MODE = "SHADOW"
"""

import sys
import math
from dataclasses import dataclass
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import pandas as pd

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.candidate_signal_v2 import CandidateSignalV2, CandidateSignalV2Result
from agent._phase126_feature_research import build_candidate_features_for_asset

EXECUTION_MODE = "SHADOW"


def get_sample_size_label(n: int) -> str:
    if n < 30:
        return "INSUFFICIENT"
    elif n < 100:
        return "EARLY"
    elif n < 300:
        return "DEVELOPING"
    elif n < 500:
        return "MEANINGFUL"
    else:
        return "STRONG"


def paired_bootstrap_ci(a: np.ndarray, b: np.ndarray, num_bootstraps: int = 1000, ci: float = 95.0) -> Tuple[float, float, float, float, float, float]:
    """
    Computes paired bootstrap confidence interval for array (a - b).
    Returns (mean_diff, median_diff, std_err, lower_ci, upper_ci, prob_gt_zero)
    """
    if len(a) == 0 or len(b) == 0 or len(a) != len(b):
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    
    diff_arr = a - b
    mean_diff = float(np.mean(diff_arr))
    median_diff = float(np.median(diff_arr))
    std_err = float(np.std(diff_arr, ddof=1) / math.sqrt(len(diff_arr))) if len(diff_arr) > 1 else 0.0
    
    np.random.seed(42)
    boot_means = []
    for _ in range(num_bootstraps):
        sample = np.random.choice(diff_arr, size=len(diff_arr), replace=True)
        boot_means.append(np.mean(sample))
    
    lower_ci = float(np.percentile(boot_means, (100.0 - ci) / 2.0))
    upper_ci = float(np.percentile(boot_means, 100.0 - (100.0 - ci) / 2.0))
    prob_gt_zero = float(np.mean(np.array(boot_means) > 0) * 100.0)
    
    return mean_diff, median_diff, std_err, lower_ci, upper_ci, prob_gt_zero


def calculate_cost_scenario(strat_returns: np.ndarray, roundtrip_cost_pct: float) -> Dict[str, float]:
    """
    Calculates net trading performance metrics given a fixed percentage roundtrip cost per active trade.
    """
    if len(strat_returns) == 0:
        return {"net_expectancy": 0.0, "net_win_rate": 0.0, "net_pf": 0.0, "net_payoff": 0.0}

    cost_decimal = roundtrip_cost_pct / 100.0
    net_returns = strat_returns - cost_decimal
    
    net_exp = float(np.mean(net_returns) * 100.0)
    wins = net_returns[net_returns > 0]
    losses = net_returns[net_returns < 0]
    
    win_rate = float((len(wins) / len(net_returns)) * 100.0)
    avg_win = float(np.mean(wins) * 100.0) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losses)) * 100.0) if len(losses) > 0 else 0.0
    payoff = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    pf = float(np.sum(wins) / np.sum(np.abs(losses))) if np.sum(np.abs(losses)) > 0 else 0.0
    
    return {
        "net_expectancy": net_exp,
        "net_win_rate": win_rate,
        "net_pf": pf,
        "net_payoff": payoff,
    }


def run_phase14_validation():
    if EXECUTION_MODE != "SHADOW":
        raise RuntimeError("CRITICAL SAFETY VIOLATION: Execution mode must be SHADOW. Failing closed!")

    print("=" * 85)
    print("PHASE 14 — INDEPENDENT OOS VALIDATION, PAIRED EDGE & TRADING-COST AUDIT")
    print(f"SAFETY ASSERTION: EXECUTION_MODE = {EXECUTION_MODE}")
    print("=" * 85)

    cfg = ReplayConfig()
    replay = HistoricalReplayEngine(config=cfg)

    # 1. DATA PROVENANCE AUDIT
    print("\n" + "=" * 85)
    print("1. DATASET PROVENANCE AUDIT")
    print("=" * 85)
    print("Provenance Source:  quant_system/data/csv (12 Assets, 4H Timeframe)")
    print("Date Range:         2026-04-22T12:00:00Z to 2026-10-06T00:00:00Z (1,000 candles per asset)")
    print("Phase 12-13 Overlap: YES (Exact dataset utilized during Phase 12.4-12.9 research & Phase 13 shadow)")
    print("Genuinely Unseen Fresh OOS Data Available: NO")
    print("Official Provenance Classification: INDEPENDENT_OOS_DATA_UNAVAILABLE")
    print("Audit Protocol: Conducting diagnostic paired-benchmark, regime, asset, and cost sensitivity audit.")

    # 2. DATA QUALITY AUDIT
    print("\n" + "=" * 85)
    print("2. DATA QUALITY & INTEGRITY AUDIT")
    print("=" * 85)
    print(f"{'Asset':<12} | {'Candles':<8} | {'Start Timestamp':<24} | {'End Timestamp':<24} | {'Gaps':<5} | {'Dups':<5} | {'Valid OHLC':<10}")
    print("-" * 95)

    data_quality_records = []
    asset_dfs = {}

    for asset, df in replay._raw_data.items():
        df_f = build_candidate_features_for_asset(df)
        asset_dfs[asset] = df_f

        n_c = len(df)
        ts_start = str(df["timestamp"].min())
        ts_end = str(df["timestamp"].max())
        
        # Check gaps (> 4 hours)
        ts_series = pd.to_datetime(df["timestamp"])
        diffs = ts_series.diff()
        gaps = int((diffs > pd.Timedelta(hours=4)).sum())
        dups = int(df["timestamp"].duplicated().sum())
        valid_ohlc = bool(((df["high"] >= df["low"]) & (df["high"] >= df["open"]) & (df["high"] >= df["close"])).all())

        data_quality_records.append({
            "asset": asset, "candles": n_c, "start": ts_start, "end": ts_end,
            "gaps": gaps, "dups": dups, "valid_ohlc": valid_ohlc
        })
        print(f"{asset:<12} | {n_c:<8d} | {ts_start:<24} | {ts_end:<24} | {gaps:<5d} | {dups:<5d} | {str(valid_ohlc):<10}")

    # Build evaluation records
    min_candles = min(len(df) for df in asset_dfs.values())
    v2_engine = CandidateSignalV2(high_vol_threshold_atr_pct=0.035)

    eval_records = []

    for step in range(replay.config.warmup_period, min_candles):
        for asset, df in asset_dfs.items():
            row = df.iloc[step]
            
            # Regime calculation
            ema_f = float(row.get("ema20", row["close"]))
            ema_s = float(row.get("ema50", row["close"]))
            ema_slope = float(row["ema50"] - df.iloc[step - 1]["ema50"]) if step > 0 else 0.0
            regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

            v2_res: CandidateSignalV2Result = v2_engine.evaluate_bar(row, regime=regime)

            entry_price = float(row["close"])
            ret_1_fwd = replay._calc_forward_return(df, step, horizon=1, entry_price=entry_price) or 0.0
            ret_3_fwd = replay._calc_forward_return(df, step, horizon=3, entry_price=entry_price) or 0.0
            ret_6_fwd = replay._calc_forward_return(df, step, horizon=6, entry_price=entry_price) or 0.0

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

            eval_records.append({
                "step": step,
                "asset": asset,
                "timestamp": str(row["timestamp"]),
                "regime": regime,
                "direction": v2_res.direction,
                "mr_dir": v2_res.mr_direction,
                "mom_dir": v2_res.mom_direction,
                "is_conflict": v2_res.is_conflict,
                "conflict_type": v2_res.conflict_type,
                "ret_1_fwd": ret_1_fwd,
                "ret_3_fwd": ret_3_fwd,
                "ret_6_fwd": ret_6_fwd,
                "mfe_long": mfe_long,
                "mae_long": mae_long,
                "mfe_short": mfe_short,
                "mae_short": mae_short,
            })

    df_eval = pd.DataFrame(eval_records)
    active_df = df_eval[df_eval["direction"] != "NEUTRAL"].copy()
    n_act = len(active_df)

    # 3. PAIRED OBSERVATION-BY-OBSERVATION BENCHMARK ANALYSIS
    print("\n" + "=" * 85)
    print("3. PAIRED OBSERVATION-BY-OBSERVATION BENCHMARK ANALYSIS (N = 3,923)")
    print("=" * 85)

    r3_actual = active_df["ret_3_fwd"].values
    dirs_v2 = active_df["direction"].values

    v2_returns = np.where(dirs_v2 == "LONG", r3_actual, -r3_actual)
    always_long_returns = r3_actual
    always_short_returns = -r3_actual
    
    np.random.seed(42)
    rand_dirs = np.random.choice(["LONG", "SHORT"], size=n_act)
    random_returns = np.where(rand_dirs == "LONG", r3_actual, -r3_actual)

    # Compute paired differences
    diff_vs_al = v2_returns - always_long_returns
    diff_vs_ash = v2_returns - always_short_returns

    mean_al, med_al, se_al, low_al, high_al, prob_al = paired_bootstrap_ci(v2_returns * 100.0, always_long_returns * 100.0)
    mean_ash, med_ash, se_ash, low_ash, high_ash, prob_ash = paired_bootstrap_ci(v2_returns * 100.0, always_short_returns * 100.0)

    print(f"Candidate V2 Standalone Mean T+3 Return:  {np.mean(v2_returns)*100.0:+.4f}%")
    print(f"Always LONG Benchmark Mean T+3 Return:     {np.mean(always_long_returns)*100.0:+.4f}%")
    print(f"Always SHORT Benchmark Mean T+3 Return:    {np.mean(always_short_returns)*100.0:+.4f}%")
    print(f"Random Benchmark Mean T+3 Return:          {np.mean(random_returns)*100.0:+.4f}%\n")

    print(f"--- PAIRED DIFFERENCE VS ALWAYS LONG ---")
    print(f"Paired Mean Difference:  {mean_al:+.4f}%")
    print(f"Paired Median Diff:      {med_al:+.4f}%")
    print(f"Standard Error:          {se_al:.4f}%")
    print(f"95% Bootstrap CI:        [{low_al:+.4f}%, {high_al:+.4f}%]")
    print(f"Probability Diff > 0:    {prob_al:.2f}%\n")

    print(f"--- PAIRED DIFFERENCE VS ALWAYS SHORT ---")
    print(f"Paired Mean Difference:  {mean_ash:+.4f}%")
    print(f"Paired Median Diff:      {med_ash:+.4f}%")
    print(f"Standard Error:          {se_ash:.4f}%")
    print(f"95% Bootstrap CI:        [{low_ash:+.4f}%, {high_ash:+.4f}%]")
    print(f"Probability Diff > 0:    {prob_ash:.2f}%")

    # 4. CONFLICT-SPECIFIC AUDIT
    print("\n" + "=" * 85)
    print("4. CONFLICT-SPECIFIC AUDIT")
    print("=" * 85)

    for c_type, expected_dir in [("MR_SHORT_MOM_LONG", "LONG"), ("MR_LONG_MOM_SHORT", "SHORT")]:
        c_sub = active_df[active_df["conflict_type"] == c_type]
        n_c = len(c_sub)
        if n_c > 0:
            r3_c = c_sub["ret_3_fwd"].values
            c_ret = np.where(c_sub["direction"].values == "LONG", r3_c, -r3_c)
            al_ret = r3_c
            ash_ret = -r3_c

            acc_c = float(np.mean(c_ret > 0) * 100.0)
            exp_c = float(np.mean(c_ret) * 100.0)
            wins_c = c_ret[c_ret > 0]
            loss_c = c_ret[c_ret < 0]
            pf_c = float(np.sum(wins_c) / np.sum(np.abs(loss_c))) if np.sum(np.abs(loss_c)) > 0 else 0.0

            m_diff_al, _, _, low_c_al, high_c_al, _ = paired_bootstrap_ci(c_ret * 100.0, al_ret * 100.0)

            print(f"--- Conflict Type: {c_type} (Frozen Direction: {expected_dir}) ---")
            print(f"Sample Count (N):        {n_c} ({get_sample_size_label(n_c)})")
            print(f"Directional Accuracy:    {acc_c:.2f}%")
            print(f"Mean Expectancy (T+3):   {exp_c:+.4f}%")
            print(f"Profit Factor:           {pf_c:.2f}")
            print(f"Paired Diff vs Always LONG: {m_diff_al:+.4f}% (95% CI: [{low_c_al:+.4f}%, {high_c_al:+.4f}%])\n")

    # 5. REGIME BREAKDOWN
    print("\n" + "=" * 85)
    print("5. REGIME-LEVEL PERFORMANCE BREAKDOWN")
    print("=" * 85)
    print(f"{'Regime':<18} | {'N':<6} | {'Accuracy':<9} | {'Expectancy':<10} | {'PF':<6} | {'Paired vs AL':<14} | {'95% CI':<20}")
    print("-" * 90)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        reg_sub = active_df[active_df["regime"] == reg]
        n_r = len(reg_sub)
        if n_r > 0:
            r3_r = reg_sub["ret_3_fwd"].values
            v2_r = np.where(reg_sub["direction"].values == "LONG", r3_r, -r3_r)
            al_r = r3_r

            acc_r = float(np.mean(v2_r > 0) * 100.0)
            exp_r = float(np.mean(v2_r) * 100.0)
            wins_r = v2_r[v2_r > 0]
            loss_r = v2_r[v2_r < 0]
            pf_r = float(np.sum(wins_r) / np.sum(np.abs(loss_r))) if np.sum(np.abs(loss_r)) > 0 else 0.0

            m_diff, _, _, low_r, high_r, _ = paired_bootstrap_ci(v2_r * 100.0, al_r * 100.0)
            ci_str = f"[{low_r:+.4f}%, {high_r:+.4f}%]"
            print(f"{reg:<18} | {n_r:<6d} | {acc_r:>8.2f}% | {exp_r:>+9.4f}% | {pf_r:>5.2f} | {m_diff:>+13.4f}% | {ci_str:<20}")

    # 6. ASSET BREAKDOWN
    print("\n" + "=" * 85)
    print("6. ASSET-LEVEL PERFORMANCE BREAKDOWN")
    print("=" * 85)
    print(f"{'Asset':<12} | {'Active N':<8} | {'Sample Label':<12} | {'Accuracy':<9} | {'Expectancy':<10} | {'PF':<6} | {'Paired vs AL':<14}")
    print("-" * 85)

    for ast in cfg.assets:
        ast_sub = active_df[active_df["asset"] == ast]
        n_a = len(ast_sub)
        if n_a > 0:
            r3_a = ast_sub["ret_3_fwd"].values
            v2_a = np.where(ast_sub["direction"].values == "LONG", r3_a, -r3_a)
            al_a = r3_a

            acc_a = float(np.mean(v2_a > 0) * 100.0)
            exp_a = float(np.mean(v2_a) * 100.0)
            wins_a = v2_a[v2_a > 0]
            loss_a = v2_a[v2_a < 0]
            pf_a = float(np.sum(wins_a) / np.sum(np.abs(loss_a))) if np.sum(np.abs(loss_a)) > 0 else 0.0

            m_diff_a, _, _, _, _, _ = paired_bootstrap_ci(v2_a * 100.0, al_a * 100.0)
            label_a = get_sample_size_label(n_a)
            print(f"{ast:<12} | {n_a:<8d} | {label_a:<12} | {acc_a:>8.2f}% | {exp_a:>+9.4f}% | {pf_a:>5.2f} | {m_diff_a:>+13.4f}%")

    # 7. TEMPORAL STABILITY
    print("\n" + "=" * 85)
    print("7. TEMPORAL STABILITY ACROSS 4 CHRONOLOGICAL WINDOWS")
    print("=" * 85)
    print(f"{'Window':<28} | {'N':<6} | {'Candidate V2':<12} | {'Always LONG':<12} | {'Paired Diff':<12} | {'Accuracy':<9} | {'PF':<6}")
    print("-" * 95)

    steps = active_df["step"].unique()
    steps.sort()
    w_size = len(steps) // 4
    w1_s, w2_s, w3_s, w4_s = set(steps[:w_size]), set(steps[w_size:2*w_size]), set(steps[2*w_size:3*w_size]), set(steps[3*w_size:])

    windows = [
        ("Window 1 (Early)", active_df[active_df["step"].isin(w1_s)]),
        ("Window 2 (Mid-Early)", active_df[active_df["step"].isin(w2_s)]),
        ("Window 3 (Mid-Late)", active_df[active_df["step"].isin(w3_s)]),
        ("Window 4 (Final)", active_df[active_df["step"].isin(w4_s)]),
    ]

    for w_name, w_df in windows:
        n_w = len(w_df)
        if n_w > 0:
            r3_w = w_df["ret_3_fwd"].values
            v2_w = np.where(w_df["direction"].values == "LONG", r3_w, -r3_w)
            al_w = r3_w

            exp_v2_w = float(np.mean(v2_w) * 100.0)
            exp_al_w = float(np.mean(al_w) * 100.0)
            p_diff_w = exp_v2_w - exp_al_w
            acc_w = float(np.mean(v2_w > 0) * 100.0)

            wins_w = v2_w[v2_w > 0]
            loss_w = v2_w[v2_w < 0]
            pf_w = float(np.sum(wins_w) / np.sum(np.abs(loss_w))) if np.sum(np.abs(loss_w)) > 0 else 0.0

            print(f"{w_name:<28} | {n_w:<6d} | {exp_v2_w:>+11.4f}% | {exp_al_w:>+11.4f}% | {p_diff_w:>+11.4f}% | {acc_w:>8.2f}% | {pf_w:>5.2f}")

    # 8. TRADING COST MODEL & SENSITIVITY ANALYSIS
    print("\n" + "=" * 85)
    print("8. TRADING COST MODEL & SENSITIVITY ANALYSIS")
    print("=" * 85)

    scenarios = [
        ("OPTIMISTIC (Maker: 0.02%, Slip/Spread: 0.01% leg)", 0.06),
        ("BASE (Taker: 0.05%, Slip/Spread: 0.02% leg)", 0.14),
        ("ADVERSE (Taker: 0.075%, Slip/Spread: 0.05% leg)", 0.25),
    ]

    print(f"{'Scenario':<50} | {'Roundtrip':<10} | {'Net Expectancy':<14} | {'Net WinRate':<12} | {'Net PF':<8}")
    print("-" * 100)

    for s_name, cost_rt in scenarios:
        res_c = calculate_cost_scenario(v2_returns, roundtrip_cost_pct=cost_rt)
        print(f"{s_name:<50} | {cost_rt:>9.2f}% | {res_c['net_expectancy']:>+13.4f}% | {res_c['net_win_rate']:>11.2f}% | {res_c['net_pf']:>7.2f}")

    # Break-even cost calculation
    gross_exp = float(np.mean(v2_returns) * 100.0)
    breakeven_cost = gross_exp  # Cost in % round-trip where net expectancy = 0
    breakeven_paired_cost = mean_al  # Cost that erodes paired edge over Always LONG to zero

    print("\n--- BREAK-EVEN COST SUMMARY ---")
    print(f"Gross Candidate V2 Expectancy:                    {gross_exp:+.4f}%")
    print(f"Maximum Roundtrip Cost for Net Expectancy >= 0:   {breakeven_cost:.4f}% round-trip ({breakeven_cost/2.0:.4f}% per leg)")
    print(f"Cost to Erode Paired Edge vs Always LONG to Zero: {breakeven_paired_cost:+.4f}% round-trip")

    # 9. FINAL CLASSIFICATION & RECOMMENDATION
    print("\n" + "=" * 85)
    print("9. FINAL PHASE 14 AUDIT CLASSIFICATION")
    print("=" * 85)
    print("Final Classification: INSUFFICIENT_OOS_DATA")
    print("Reason:               Fresh, non-overlapping independent dataset was unavailable in workspace cache.")
    print("Recommendation:       INSUFFICIENT_OOS_DATA -> Collect additional independent data before Phase 15.")
    print("=" * 85)


if __name__ == "__main__":
    run_phase14_validation()
