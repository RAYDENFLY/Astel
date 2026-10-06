"""
agent/_phase13_shadow_runner.py — Phase 13 Candidate V2 Real-Time Shadow Observation Runner

Executes a real-time shadow observation replay harness across completed 4H candles (10,920 asset-bar evaluations):
- Enforces EXECUTION_MODE = "SHADOW"
- Processes completed 4H candles deterministically
- Tracks outcomes at Checkpoints A (30), B (100), C (300), and D (500 completed T+3 observations)
- Audits Conflict FOLLOW_MOMENTUM, regime performance, asset performance, MFE/MAE, profit factor, expectancy, and incremental edge vs baselines
"""

import sys
import os
import json
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.candidate_v2_shadow_engine import CandidateV2ShadowEngine, CandidateV2ShadowRecord, EXECUTION_MODE
from agent._phase126_feature_research import build_candidate_features_for_asset
from agent._phase128_regime_validation import bootstrap_ci


def format_sample_gate(n: int) -> str:
    if n < 30:
        return "INSUFFICIENT_SAMPLE"
    elif n < 100:
        return "EARLY_OBSERVATION"
    elif n < 300:
        return "DEVELOPING_SAMPLE"
    elif n < 500:
        return "MEANINGFUL_SAMPLE"
    else:
        return "STRONG_OBSERVATION_SAMPLE"


def compute_shadow_metrics(records: List[CandidateV2ShadowRecord]) -> Dict[str, Any]:
    active_recs = [r for r in records if r.direction != "NEUTRAL" and r.is_completed_t3]
    n_act = len(active_recs)
    if n_act == 0:
        return {
            "N": 0, "Accuracy": 0.0, "BalAcc": 0.0, "Expectancy": 0.0,
            "MedT3": 0.0, "WinRate": 0.0, "AvgWin": 0.0, "AvgLoss": 0.0,
            "Payoff": 0.0, "ProfitFactor": 0.0, "MFE": 0.0, "MAE": 0.0,
            "T1": 0.0, "T6": 0.0, "Gate": format_sample_gate(0)
        }

    strat_r3 = np.array([r.ret_3_fwd if r.direction == "LONG" else -r.ret_3_fwd for r in active_recs])
    strat_r1 = np.array([r.ret_1_fwd if r.direction == "LONG" else -r.ret_1_fwd for r in active_recs if r.ret_1_fwd is not None])
    strat_r6 = np.array([r.ret_6_fwd if r.direction == "LONG" else -r.ret_6_fwd for r in active_recs if r.ret_6_fwd is not None])

    correct = (strat_r3 > 0)
    acc = float(np.mean(correct) * 100.0)

    l_recs = [r for r in active_recs if r.direction == "LONG"]
    s_recs = [r for r in active_recs if r.direction == "SHORT"]
    acc_l = np.mean([r.ret_3_fwd > 0 for r in l_recs]) * 100.0 if len(l_recs) > 0 else 0.0
    acc_s = np.mean([r.ret_3_fwd < 0 for r in s_recs]) * 100.0 if len(s_recs) > 0 else 0.0
    bal_acc = (acc_l + acc_s) / 2.0 if (len(l_recs) > 0 and len(s_recs) > 0) else acc

    wins = strat_r3[strat_r3 > 0]
    losses = strat_r3[strat_r3 < 0]

    win_rate = (len(wins) / n_act) * 100.0
    avg_win = float(np.mean(wins) * 100.0) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losses)) * 100.0) if len(losses) > 0 else 0.0

    payoff = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    expectancy = float(np.mean(strat_r3) * 100.0)
    profit_factor = (np.sum(wins) / np.sum(np.abs(losses))) if np.sum(np.abs(losses)) > 0 else 0.0

    mfes = np.array([r.mfe for r in active_recs if r.mfe is not None])
    maes = np.array([r.mae for r in active_recs if r.mae is not None])

    return {
        "N": n_act,
        "Accuracy": acc,
        "BalAcc": bal_acc,
        "Expectancy": expectancy,
        "MedT3": float(np.median(strat_r3) * 100.0),
        "WinRate": win_rate,
        "AvgWin": avg_win,
        "AvgLoss": avg_loss,
        "Payoff": payoff,
        "ProfitFactor": float(profit_factor),
        "MFE": float(np.mean(mfes) * 100.0) if len(mfes) > 0 else 0.0,
        "MAE": float(np.mean(maes) * 100.0) if len(maes) > 0 else 0.0,
        "T1": float(np.mean(strat_r1) * 100.0) if len(strat_r1) > 0 else 0.0,
        "T6": float(np.mean(strat_r6) * 100.0) if len(strat_r6) > 0 else 0.0,
        "Gate": format_sample_gate(n_act),
    }


def run_phase13_shadow_observation():
    print("=" * 80)
    print("PHASE 13 — CANDIDATE V2 REAL-TIME SHADOW OBSERVATION")
    print(f"EXECUTION MODE ASSERTION: {EXECUTION_MODE}")
    print("=" * 80)

    cfg = ReplayConfig()
    replay = HistoricalReplayEngine(config=cfg)

    # Build candidate features per asset
    asset_dfs = {}
    for asset, df in replay._raw_data.items():
        df_f = build_candidate_features_for_asset(df)
        asset_dfs[asset] = df_f

    min_candles = min(len(df) for df in asset_dfs.values())
    shadow_engine = CandidateV2ShadowEngine(persistence_path="agent/data/candidate_v2_shadow_records.json")

    processed_count = 0

    for step in range(replay.config.warmup_period, min_candles):
        for asset, df in asset_dfs.items():
            row = df.iloc[step]

            # Regime calculation
            ema_f = float(row.get("ema20", row["close"]))
            ema_s = float(row.get("ema50", row["close"]))
            ema_slope = float(row["ema50"] - df.iloc[step - 1]["ema50"]) if step > 0 else 0.0
            regime = "BULLISH_TREND" if (ema_f > ema_s and ema_slope > 0) else ("BEARISH_TREND" if (ema_f < ema_s and ema_slope < 0) else "CONSOLIDATION")

            rec = shadow_engine.process_completed_candle(row, regime=regime, asset=asset, is_completed_candle=True)
            if rec is not None:
                processed_count += 1
                future_slice = df.iloc[step + 1 : min(step + 7, len(df))]
                shadow_engine.update_outcomes(rec.shadow_trade_id, future_slice)

    shadow_engine.save_records()
    all_recs = list(shadow_engine.records.values())

    print(f"Total Completed 4H Candles Processed: {processed_count}")
    print(f"Total Shadow Records Stored:          {len(all_recs)}")

    # 1. OVERALL SIGNAL STATISTICS
    print("\n" + "=" * 80)
    print("1. OVERALL SHADOW SIGNAL STATISTICS")
    print("=" * 80)
    
    n_total = len(all_recs)
    n_act = sum(1 for r in all_recs if r.direction != "NEUTRAL")
    n_neut = n_total - n_act
    cov_pct = (n_act / n_total) * 100.0 if n_total > 0 else 0.0
    n_long = sum(1 for r in all_recs if r.direction == "LONG")
    n_short = sum(1 for r in all_recs if r.direction == "SHORT")

    print(f"Total Evaluations:   {n_total}")
    print(f"Active Signals:      {n_act} ({cov_pct:.2f}% coverage)")
    print(f"Neutral Signals:     {n_neut} ({(n_neut/n_total)*100.0:.2f}%)")
    print(f"LONG Signals:        {n_long} ({(n_long/n_total)*100.0:.2f}%)")
    print(f"SHORT Signals:       {n_short} ({(n_short/n_total)*100.0:.2f}%)")

    # 2. CHECKPOINT RESULTS (A: 30, B: 100, C: 300, D: 500, OVERALL)
    print("\n" + "=" * 80)
    print("2. SHADOW OBSERVATION CHECKPOINT RESULTS")
    print("=" * 80)

    completed_recs = [r for r in all_recs if r.direction != "NEUTRAL" and r.is_completed_t3]

    checkpoints = [
        ("Checkpoint A", 30),
        ("Checkpoint B", 100),
        ("Checkpoint C", 300),
        ("Checkpoint D", 500),
        ("Full Observation", len(completed_recs)),
    ]

    print(f"{'Checkpoint':<18} | {'N':<6} | {'Sample Gate':<24} | {'Accuracy':<9} | {'Expectancy':<10} | {'WinRate':<8} | {'PF':<6} | {'Payoff':<6}")
    print("-" * 100)

    for cp_name, target_n in checkpoints:
        sub_recs = completed_recs[: min(target_n, len(completed_recs))]
        m = compute_shadow_metrics(sub_recs)
        print(f"{cp_name:<18} | {m['N']:<6d} | {m['Gate']:<24} | {m['Accuracy']:>8.2f}% | {m['Expectancy']:>+9.4f}% | {m['WinRate']:>7.2f}% | {m['ProfitFactor']:>5.2f} | {m['Payoff']:>5.2f}")

    # 3. CONFLICT FOLLOW_MOMENTUM PERFORMANCE
    print("\n" + "=" * 80)
    print("3. CONFLICT FOLLOW_MOMENTUM SHADOW PERFORMANCE")
    print("=" * 80)

    conf_recs = [r for r in all_recs if r.is_conflict and r.is_completed_t3]
    m_conf = compute_shadow_metrics(conf_recs)
    r3_conf = np.array([r.ret_3_fwd if r.direction == "LONG" else -r.ret_3_fwd for r in conf_recs])
    ci_low, ci_high = bootstrap_ci(r3_conf * 100.0)

    print(f"Sample Gate:           {m_conf['Gate']} (N={m_conf['N']})")
    print(f"Directional Accuracy:  {m_conf['Accuracy']:.2f}%")
    print(f"Balanced Accuracy:     {m_conf['BalAcc']:.2f}%")
    print(f"Mean Expectancy (T+3): {m_conf['Expectancy']:+.4f}% (95% CI: [{ci_low:+.4f}%, {ci_high:+.4f}%])")
    print(f"Median T+3 Return:     {m_conf['MedT3']:+.4f}%")
    print(f"Win Rate:              {m_conf['WinRate']:.2f}%")
    print(f"Payoff Ratio:          {m_conf['Payoff']:.2f}")
    print(f"Profit Factor:         {m_conf['ProfitFactor']:.2f}")
    print(f"Average MFE:           {m_conf['MFE']:+.4f}%")
    print(f"Average MAE:           {m_conf['MAE']:+.4f}%")

    # 4. CONFLICT DIRECTION BREAKDOWN
    print("\n" + "=" * 80)
    print("4. CONFLICT DIRECTION BREAKDOWN")
    print("=" * 80)

    for c_type in ["MR_LONG_MOM_SHORT", "MR_SHORT_MOM_LONG"]:
        sub_c = [r for r in conf_recs if r.conflict_type == c_type]
        m_ct = compute_shadow_metrics(sub_c)
        print(f"{c_type:<22} | N={m_ct['N']:<5d} | Accuracy: {m_ct['Accuracy']:5.2f}% | Expectancy: {m_ct['Expectancy']:+7.4f}% | PF: {m_ct['ProfitFactor']:5.2f} | WinRate: {m_ct['WinRate']:5.2f}%")

    # 5. REGIME PERFORMANCE
    print("\n" + "=" * 80)
    print("5. REGIME-LEVEL SHADOW BREAKDOWN (Candidate V2)")
    print("=" * 80)
    print(f"{'Regime':<18} | {'Active N':<8} | {'Accuracy':<9} | {'Expectancy':<10} | {'WinRate':<8} | {'PF':<6} | {'Avg T+6':<9}")
    print("-" * 80)

    for reg in ["BULLISH_TREND", "BEARISH_TREND", "CONSOLIDATION"]:
        reg_recs = [r for r in completed_recs if r.regime == reg]
        m_reg = compute_shadow_metrics(reg_recs)
        print(f"{reg:<18} | {m_reg['N']:<8d} | {m_reg['Accuracy']:>8.2f}% | {m_reg['Expectancy']:>+9.4f}% | {m_reg['WinRate']:>7.2f}% | {m_reg['ProfitFactor']:>5.2f} | {m_reg['T6']:>+8.4f}%")

    # 6. ASSET PERFORMANCE
    print("\n" + "=" * 80)
    print("6. ASSET-LEVEL SHADOW BREAKDOWN (Candidate V2)")
    print("=" * 80)
    print(f"{'Asset':<12} | {'Active N':<8} | {'Accuracy':<9} | {'Expectancy':<10} | {'WinRate':<8} | {'PF':<6} | {'MFE':<8} | {'MAE':<8}")
    print("-" * 85)

    for ast in cfg.assets:
        ast_recs = [r for r in completed_recs if r.asset == ast]
        m_ast = compute_shadow_metrics(ast_recs)
        print(f"{ast:<12} | {m_ast['N']:<8d} | {m_ast['Accuracy']:>8.2f}% | {m_ast['Expectancy']:>+9.4f}% | {m_ast['WinRate']:>7.2f}% | {m_ast['ProfitFactor']:>5.2f} | {m_ast['MFE']:>+7.2f}% | {m_ast['MAE']:>+7.2f}%")

    # 7. BASELINE COMPARISON & INCREMENTAL EDGE
    print("\n" + "=" * 80)
    print("7. BASELINE COMPARISON & INCREMENTAL EDGE")
    print("=" * 80)

    al_ret3 = np.mean([r.ret_3_fwd for r in completed_recs]) * 100.0
    ash_ret3 = np.mean([-r.ret_3_fwd for r in completed_recs]) * 100.0
    v2_ret3 = np.mean([r.ret_3_fwd if r.direction == "LONG" else -r.ret_3_fwd for r in completed_recs]) * 100.0
    conf_ret3 = np.mean([r.ret_3_fwd if r.direction == "LONG" else -r.ret_3_fwd for r in conf_recs]) * 100.0

    print(f"Candidate V2 Mean T+3 Return:                     {v2_ret3:+.4f}%")
    print(f"Conflict FOLLOW_MOMENTUM Mean T+3 Return:         {conf_ret3:+.4f}%")
    print(f"Always LONG Benchmark Mean T+3 Return:            {al_ret3:+.4f}%")
    print(f"Always SHORT Benchmark Mean T+3 Return:           {ash_ret3:+.4f}%")
    print(f"Incremental Edge (Candidate V2 minus Always LONG): {v2_ret3 - al_ret3:+.4f}%")
    print(f"Incremental Edge (Conflict minus Always LONG):     {conf_ret3 - al_ret3:+.4f}%")


if __name__ == "__main__":
    run_phase13_shadow_observation()
