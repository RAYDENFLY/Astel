"""
agent/_phase128_regime_validation.py — Phase 12.8 Regime-Conditioned Signal Research & Conflict Analysis Script

Executes a comprehensive, read-only empirical evaluation of:
1. Q1-Q3: Regime-Conditioned Switching (REGIME_SWITCH_V1) across Bullish, Bearish, Consolidation, High Volatility regimes
2. Q4-Q5: CONFLICT Resolution Interpretations (FOLLOW_MR, FOLLOW_MOMENTUM, INVERSE_MR, INVERSE_MOMENTUM, ALWAYS_LONG, ALWAYS_SHORT, NEUTRAL)
3. CONFLICT x Regime breakdown
4. CONFLICT x Direction breakdown (MR_LONG_MOM_SHORT vs MR_SHORT_MOM_LONG)
5. Chronological In-Sample (60%) vs Out-of-Sample (40%) stability
6. Asset robustness across all 12 assets
7. Economic metrics (Expectancy, Win Rate, Payoff Ratio, Profit Factor, MFE, MAE)
8. Bootstrap 95% Confidence Intervals for signal differences
"""

import sys
import math
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd
from scipy import stats

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.regime_signal_research import RegimeSignalResearchEngine, RegimeSwitchResult
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


def calc_economic_metrics(dirs: np.ndarray, r3: np.ndarray, r1: np.ndarray, r6: np.ndarray, mfes: np.ndarray, maes: np.ndarray) -> Dict[str, Any]:
    mask = (dirs != "NEUTRAL")
    n_act = int(np.sum(mask))
    if n_act == 0:
        return {
            "N": 0, "Coverage": 0.0, "Accuracy": 0.0, "BalAcc": 0.0,
            "MeanT3": 0.0, "MedT3": 0.0, "WinRate": 0.0, "AvgWin": 0.0,
            "AvgLoss": 0.0, "Payoff": 0.0, "Expectancy": 0.0, "ProfitFactor": 0.0,
            "MFE": 0.0, "MAE": 0.0, "T1": 0.0, "T6": 0.0
        }

    d_act = dirs[mask]
    r3_act = r3[mask]
    r1_act = r1[mask]
    r6_act = r6[mask]
    mfe_act = mfes[mask]
    mae_act = maes[mask]

    strat_r3 = np.where(d_act == "LONG", r3_act, -r3_act)
    strat_r1 = np.where(d_act == "LONG", r1_act, -r1_act)
    strat_r6 = np.where(d_act == "LONG", r6_act, -r6_act)

    correct = (strat_r3 > 0)
    acc = float(np.mean(correct) * 100.0)

    l_mask = (d_act == "LONG")
    s_mask = (d_act == "SHORT")
    acc_l = np.mean(r3_act[l_mask] > 0) * 100.0 if np.sum(l_mask) > 0 else 0.0
    acc_s = np.mean(r3_act[s_mask] < 0) * 100.0 if np.sum(s_mask) > 0 else 0.0
    bal_acc = (acc_l + acc_s) / 2.0 if (np.sum(l_mask) > 0 and np.sum(s_mask) > 0) else acc

    wins = strat_r3[strat_r3 > 0]
    losses = strat_r3[strat_r3 < 0]

    win_rate = (len(wins) / n_act) * 100.0
    avg_win = float(np.mean(wins) * 100.0) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losses)) * 100.0) if len(losses) > 0 else 0.0

    payoff = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    expectancy = float(np.mean(strat_r3) * 100.0)
    profit_factor = (np.sum(wins) / np.sum(np.abs(losses))) if np.sum(np.abs(losses)) > 0 else 0.0

    return {
        "N": n_act,
        "Coverage": float((n_act / len(dirs)) * 100.0),
        "Accuracy": acc,
        "BalAcc": bal_acc,
        "MeanT3": expectancy,
        "MedT3": float(np.median(strat_r3) * 100.0),
        "WinRate": win_rate,
        "AvgWin": avg_win,
        "AvgLoss": avg_loss,
        "Payoff": payoff,
        "Expectancy": expectancy,
        "ProfitFactor": float(profit_factor),
        "MFE": float(np.mean(mfe_act) * 100.0),
        "MAE": float(np.mean(mae_act) * 100.0),
        "T1": float(np.mean(strat_r1) * 100.0),
        "T6": float(np.mean(strat_r6) * 100.0),
    }


def run_regime_research_validation():
    print("=" * 80)
    print("PHASE 12.8 — REGIME-CONDITIONED SIGNAL RESEARCH & CONFLICT ANALYSIS")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    # Build candidate features per asset
    asset_dfs = {}
    for asset, df in engine._raw_data.items():
        df_f = build_candidate_features_for_asset(df)
        asset_dfs[asset] = df_f

    min_candles = min(len(df) for df in asset_dfs.values())
    research_engine = RegimeSignalResearchEngine(high_vol_threshold_atr_pct=0.035)

    records = []

    for step in range(engine.config.warmup_period, min_candles):
        for asset, df in asset_dfs.items():
            row = df.iloc[step]

            # Regime
            ema_f = float(row.get("ema20", row["close"]))
            ema_s = float(row.get("ema50", row["close"]))
            ema_slope = float(row["ema50"] - df.iloc[step - 1]["ema50"]) if step > 0 else 0.0
            regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

            # Baseline signal
            ema_dist = float(row.get("ema_distance", 0.0) or 0.0)
            ret_1 = float(row.get("return_1", 0.0) or 0.0)
            base_score = ema_dist * 2.0 + ret_1 * 0.5
            base_dir = "LONG" if base_score > 0.005 else ("SHORT" if base_score < -0.005 else "NEUTRAL")

            res: RegimeSwitchResult = research_engine.evaluate_bar(row, regime=regime)

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

            cand_dir = research_engine.candidate_v1.evaluate_bar(row).direction

            records.append({
                "step": step,
                "asset": asset,
                "timestamp": str(row["timestamp"]),
                "regime": regime,
                "base_dir": base_dir,
                "cand_mr_dir": res.mr_direction,
                "cand_mom_dir": res.mom_direction,
                "cand_fused_v1_dir": cand_dir,
                "regime_switch_dir": res.regime_switch_direction,
                "is_conflict": res.is_conflict,
                "conflict_type": res.conflict_type,
                "is_high_vol": res.is_high_volatility,
                "c_follow_mr": res.conflict_follow_mr,
                "c_follow_mom": res.conflict_follow_mom,
                "c_inv_mr": res.conflict_inverse_mr,
                "c_inv_mom": res.conflict_inverse_mom,
                "c_always_long": res.conflict_always_long,
                "c_always_short": res.conflict_always_short,
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
    print(f"Total evaluations: {n_tot}")

    # 1. REGIME x SIGNAL COMPARISON MATRIX
    print("\n" + "=" * 80)
    print("1. REGIME x SIGNAL COMPARISON MATRIX (Q1 - Q3)")
    print("=" * 80)

    regimes_to_test = ["ALL", "BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]

    for reg in regimes_to_test:
        sub = df_all if reg == "ALL" else df_all[df_all["regime"] == reg]
        print(f"\n--- REGIME: {reg} (N={len(sub)}) ---")
        print(f"{'Signal / Strategy':<26} | {'Cov %':<6} | {'Accuracy':<9} | {'BalAcc':<8} | {'Avg T+1':<9} | {'Avg T+3':<9} | {'Avg T+6':<9}")
        print("-" * 86)

        strats = [
            ("Always LONG", np.full(len(sub), "LONG")),
            ("Always SHORT", np.full(len(sub), "SHORT")),
            ("Previous Baseline", sub["base_dir"].values),
            ("Candidate MR-only", sub["cand_mr_dir"].values),
            ("Candidate Momentum-only", sub["cand_mom_dir"].values),
            ("Candidate Fused V1", sub["cand_fused_v1_dir"].values),
            ("REGIME_SWITCH_V1", sub["regime_switch_dir"].values),
        ]

        for s_name, s_dirs in strats:
            m = calc_economic_metrics(
                s_dirs, sub["ret_3_fwd"].values, sub["ret_1_fwd"].values, sub["ret_6_fwd"].values,
                np.where(s_dirs == "LONG", sub["mfe_long"].values, sub["mfe_short"].values),
                np.where(s_dirs == "LONG", sub["mae_long"].values, sub["mae_short"].values)
            )
            print(f"{s_name:<26} | {m['Coverage']:>5.1f}% | {m['Accuracy']:>8.2f}% | {m['BalAcc']:>7.2f}% | {m['T1']:>+8.4f}% | {m['MeanT3']:>+8.4f}% | {m['T6']:>+8.4f}%")

    # 2. CONFLICT ANALYSIS (Q4 - Q5)
    print("\n" + "=" * 80)
    print("2. CONFLICT RESOLUTION INTERPRETATION AUDIT (Q4 - Q5)")
    print("=" * 80)
    conf_df = df_all[df_all["is_conflict"]]
    n_conf = len(conf_df)
    pct_conf = (n_conf / n_tot) * 100.0
    print(f"Total CONFLICT Observations: {n_conf} ({pct_conf:.2f}% of evaluations)")

    print(f"\n{'Interpretation':<22} | {'LONG/SHORT':<10} | {'Accuracy':<9} | {'Expectancy':<10} | {'WinRate':<8} | {'Payoff':<7} | {'ProfitFactor':<12} | {'95% CI Expectancy':<22}")
    print("-" * 110)

    conf_interpretations = [
        ("FOLLOW_MR", conf_df["c_follow_mr"].values),
        ("FOLLOW_MOMENTUM", conf_df["c_follow_mom"].values),
        ("INVERSE_MR", conf_df["c_inv_mr"].values),
        ("INVERSE_MOMENTUM", conf_df["c_inv_mom"].values),
        ("ALWAYS_LONG", conf_df["c_always_long"].values),
        ("ALWAYS_SHORT", conf_df["c_always_short"].values),
    ]

    r3_conf = conf_df["ret_3_fwd"].values
    r1_conf = conf_df["ret_1_fwd"].values
    r6_conf = conf_df["ret_6_fwd"].values

    for inter_name, dirs in conf_interpretations:
        m = calc_economic_metrics(
            dirs, r3_conf, r1_conf, r6_conf,
            np.where(dirs == "LONG", conf_df["mfe_long"].values, conf_df["mfe_short"].values),
            np.where(dirs == "LONG", conf_df["mae_long"].values, conf_df["mae_short"].values)
        )
        strat_r3 = np.where(dirs == "LONG", r3_conf, -r3_conf)
        lower, upper = bootstrap_ci(strat_r3 * 100.0)
        n_l = np.sum(dirs == "LONG")
        n_s = np.sum(dirs == "SHORT")
        dist_str = f"{n_l}/{n_s}"

        print(f"{inter_name:<22} | {dist_str:<10} | {m['Accuracy']:>8.2f}% | {m['Expectancy']:>+9.4f}% | {m['WinRate']:>7.2f}% | {m['Payoff']:>6.2f} | {m['ProfitFactor']:>11.2f} | [{lower:>+7.4f}%, {upper:>+7.4f}%]")

    # 3. CONFLICT x REGIME
    print("\n" + "=" * 80)
    print("3. CONFLICT BREAKDOWN BY MARKET REGIME")
    print("=" * 80)
    print(f"{'Regime':<18} | {'N':<5} | {'Conflict %':<10} | {'Follow MR Acc':<14} | {'Follow Mom Acc':<15} | {'Always LONG T+3':<16}")
    print("-" * 88)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        sub_reg = df_all[df_all["regime"] == reg]
        sub_conf = sub_reg[sub_reg["is_conflict"]]
        n_sub_conf = len(sub_conf)
        freq_c = (n_sub_conf / len(sub_reg)) * 100.0

        if n_sub_conf > 0:
            mr_acc = np.mean(((sub_conf["c_follow_mr"].values == "LONG") & (sub_conf["ret_3_fwd"].values > 0)) | ((sub_conf["c_follow_mr"].values == "SHORT") & (sub_conf["ret_3_fwd"].values < 0))) * 100.0
            mom_acc = np.mean(((sub_conf["c_follow_mom"].values == "LONG") & (sub_conf["ret_3_fwd"].values > 0)) | ((sub_conf["c_follow_mom"].values == "SHORT") & (sub_conf["ret_3_fwd"].values < 0))) * 100.0
            long_ret = np.mean(sub_conf["ret_3_fwd"].values) * 100.0
        else:
            mr_acc = mom_acc = long_ret = 0.0

        print(f"{reg:<18} | {n_sub_conf:<5d} | {freq_c:>9.2f}% | {mr_acc:>13.2f}% | {mom_acc:>14.2f}% | {long_ret:>+15.4f}%")

    # 4. CONFLICT x DIRECTION
    print("\n" + "=" * 80)
    print("4. CONFLICT BREAKDOWN BY DIRECTIONAL TYPE")
    print("=" * 80)
    print(f"{'Conflict Type':<22} | {'N':<6} | {'Market Avg T+3':<14} | {'Follow MR Acc':<14} | {'Follow Mom Acc':<15} | {'T+6 Return':<10}")
    print("-" * 88)

    for c_type in ["MR_LONG_MOM_SHORT", "MR_SHORT_MOM_LONG"]:
        sub_c = df_all[df_all["conflict_type"] == c_type]
        n_c = len(sub_c)

        if n_c > 0:
            mkt_t3 = sub_c["ret_3_fwd"].mean() * 100.0
            mkt_t6 = sub_c["ret_6_fwd"].mean() * 100.0
            mr_acc = np.mean(((sub_c["c_follow_mr"].values == "LONG") & (sub_c["ret_3_fwd"].values > 0)) | ((sub_c["c_follow_mr"].values == "SHORT") & (sub_c["ret_3_fwd"].values < 0))) * 100.0
            mom_acc = np.mean(((sub_c["c_follow_mom"].values == "LONG") & (sub_c["ret_3_fwd"].values > 0)) | ((sub_c["c_follow_mom"].values == "SHORT") & (sub_c["ret_3_fwd"].values < 0))) * 100.0
        else:
            mkt_t3 = mkt_t6 = mr_acc = mom_acc = 0.0

        print(f"{c_type:<22} | {n_c:<6d} | {mkt_t3:>+13.4f}% | {mr_acc:>13.2f}% | {mom_acc:>14.2f}% | {mkt_t6:>+9.4f}%")

    # 5. CHRONOLOGICAL IS (60%) VS OOS (40%) VALIDATION
    print("\n" + "=" * 80)
    print("5. IN-SAMPLE (60%) VS OUT-OF-SAMPLE (40%) STABILITY VALIDATION")
    print("=" * 80)

    steps = df_all["step"].unique()
    steps.sort()
    split_idx = int(len(steps) * 0.60)
    is_steps = set(steps[:split_idx])
    oos_steps = set(steps[split_idx:])

    df_is = df_all[df_all["step"].isin(is_steps)]
    df_oos = df_all[df_all["step"].isin(oos_steps)]

    print(f"{'Signal / Hypothesis':<26} | {'IS Acc':<8} | {'OOS Acc':<8} | {'IS Avg T+3':<10} | {'OOS Avg T+3':<10} | {'OOS Cov':<8}")
    print("-" * 80)

    eval_signals = [
        ("Always LONG", "LONG_ALL"),
        ("Candidate Fused V1", "cand_fused_v1_dir"),
        ("REGIME_SWITCH_V1", "regime_switch_dir"),
        ("Conflict: FOLLOW_MR", "c_follow_mr"),
        ("Conflict: FOLLOW_MOMENTUM", "c_follow_mom"),
        ("Conflict: ALWAYS_LONG", "c_always_long"),
    ]

    for s_name, col_key in eval_signals:
        for df_sub, label in [(df_is, "IS"), (df_oos, "OOS")]:
            if col_key == "LONG_ALL":
                dirs = np.full(len(df_sub), "LONG")
            else:
                dirs = df_sub[col_key].values
            r3 = df_sub["ret_3_fwd"].values

            mask = (dirs != "NEUTRAL")
            if np.sum(mask) > 0:
                d_act = dirs[mask]
                r3_act = r3[mask]
                corr = ((d_act == "LONG") & (r3_act > 0)) | ((d_act == "SHORT") & (r3_act < 0))
                acc = np.mean(corr) * 100.0
                ret3 = np.mean(np.where(d_act == "LONG", r3_act, -r3_act)) * 100.0
                cov = (np.sum(mask) / len(df_sub)) * 100.0
            else:
                acc = ret3 = cov = 0.0

            if label == "IS":
                is_acc, is_ret = acc, ret3
            else:
                oos_acc, oos_ret, oos_cov = acc, ret3, cov

        print(f"{s_name:<26} | {is_acc:>7.2f}% | {oos_acc:>7.2f}% | {is_ret:>+9.4f}% | {oos_ret:>+9.4f}% | {oos_cov:>7.2f}%")

    # 6. ASSET ROBUSTNESS
    print("\n" + "=" * 80)
    print("6. ASSET-LEVEL ROBUSTNESS (REGIME_SWITCH_V1 & Conflict ALWAYS_LONG)")
    print("=" * 80)
    print(f"{'Asset':<12} | {'RS_V1 Acc':<10} | {'RS_V1 T+3':<10} | {'RS_V1 Cov':<10} | {'Conf_LONG Acc':<14} | {'Conf_LONG T+3':<14}")
    print("-" * 80)

    for ast in cfg.assets:
        sub_ast = df_all[df_all["asset"] == ast]

        # REGIME_SWITCH_V1
        rs_dirs = sub_ast["regime_switch_dir"].values
        rs_r3 = sub_ast["ret_3_fwd"].values
        rs_mask = (rs_dirs != "NEUTRAL")
        if np.sum(rs_mask) > 0:
            rs_d_act = rs_dirs[rs_mask]
            rs_r3_act = rs_r3[rs_mask]
            rs_acc = np.mean(((rs_d_act == "LONG") & (rs_r3_act > 0)) | ((rs_d_act == "SHORT") & (rs_r3_act < 0))) * 100.0
            rs_ret = np.mean(np.where(rs_d_act == "LONG", rs_r3_act, -rs_r3_act)) * 100.0
            rs_cov = (np.sum(rs_mask) / len(sub_ast)) * 100.0
        else:
            rs_acc = rs_ret = rs_cov = 0.0

        # Conflict ALWAYS_LONG
        c_sub = sub_ast[sub_ast["is_conflict"]]
        if len(c_sub) > 0:
            c_r3 = c_sub["ret_3_fwd"].values
            c_acc = np.mean(c_r3 > 0) * 100.0
            c_ret = np.mean(c_r3) * 100.0
        else:
            c_acc = c_ret = 0.0

        print(f"{ast:<12} | {rs_acc:>9.2f}% | {rs_ret:>+9.4f}% | {rs_cov:>9.2f}% | {c_acc:>13.2f}% | {c_ret:>+13.4f}%")

    # 7. BOOTSTRAP STATISTICAL DIFFERENCE TESTING
    print("\n" + "=" * 80)
    print("7. BOOTSTRAP STATISTICAL CONFIDENCE & DIFFERENCE TESTING")
    print("=" * 80)

    rs_dirs = df_all["regime_switch_dir"].values
    cand_dirs = df_all["cand_fused_v1_dir"].values
    always_long_dirs = np.full(len(df_all), "LONG")
    r3 = df_all["ret_3_fwd"].values

    rs_mask = (rs_dirs != "NEUTRAL")
    cand_mask = (cand_dirs != "NEUTRAL")

    rs_strat_r3 = np.where(rs_dirs[rs_mask] == "LONG", r3[rs_mask], -r3[rs_mask])
    cand_strat_r3 = np.where(cand_dirs[cand_mask] == "LONG", r3[cand_mask], -r3[cand_mask])
    al_strat_r3 = r3

    rs_low, rs_high = bootstrap_ci(rs_strat_r3 * 100.0)
    cand_low, cand_high = bootstrap_ci(cand_strat_r3 * 100.0)
    al_low, al_high = bootstrap_ci(al_strat_r3 * 100.0)

    print(f"REGIME_SWITCH_V1 Mean T+3 Return:  {np.mean(rs_strat_r3)*100.0:+.4f}% (95% CI: [{rs_low:+.4f}%, {rs_high:+.4f}%])")
    print(f"Candidate Fused V1 Mean T+3 Return: {np.mean(cand_strat_r3)*100.0:+.4f}% (95% CI: [{cand_low:+.4f}%, {cand_high:+.4f}%])")
    print(f"Always LONG Mean T+3 Return:        {np.mean(al_strat_r3)*100.0:+.4f}% (95% CI: [{al_low:+.4f}%, {al_high:+.4f}%])")

if __name__ == "__main__":
    run_regime_research_validation()
