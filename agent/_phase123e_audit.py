"""
/tmp/run_phase123e_audit.py — Comprehensive Diagnostic Audit for Phase 12.3E
"""

import glob
import math
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter

from quant_system.features.build_features import FeatureBuilder
from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.market_scanner import MarketScanner
from agent.specialists import (
    TechnicalMLSpecialist,
    OrderFlowSpecialist,
    DerivativesSpecialist,
    MacroRegimeSpecialist,
    NewsSentimentSpecialist,
)
from agent.evidence_fusion import EvidenceFusionEngine, FusionConfig
from agent.decision_agent import DecisionAgent
from agent.risk_supervisor import RiskSupervisor
from agent.schema import AssetAnalysis, DecisionProposal

print("==================================================")
print("PHASE 12.3E — DIRECTIONAL DECISION PATH AUDIT")
print("==================================================")

# Load CSV datasets
csv_dir = Path("quant_system/data/csv")
csv_files = sorted(glob.glob("quant_system/data/csv/*.csv"))
datasets = {}
import yaml

cfg_path = Path("quant_system/config.yaml")
if cfg_path.exists():
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
else:
    cfg = {}

feature_builder = FeatureBuilder(cfg)

for f in csv_files:
    asset = Path(f).stem
    df = pd.read_csv(f)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["asset"] = asset
    df = df.sort_values("timestamp").reset_index(drop=True)
    datasets[asset] = df

# Run replay engine to get step-by-step analyses & outcomes
config = ReplayConfig(warmup_period=30, top_n=3)
engine = HistoricalReplayEngine(config=config)
outcomes, raw_logs = engine.run_replay()

# --------------------------------------------------
# SECTION 1: FEATURE DIRECTION AUDIT
# --------------------------------------------------
print("\n--- SECTION 1: FEATURE DIRECTION AUDIT ---")
target_assets = ["BTC_USDT", "ETH_USDT", "BNB_USDT", "XRP_USDT"]

bearish_bars = []
for asset in target_assets:
    df = datasets[asset]
    for step in range(30, len(df)):
        slice_df = df.iloc[: step + 1].copy()
        feats_df = feature_builder.build(slice_df, is_training=False)
        if feats_df.empty:
            continue
        bar = feats_df.iloc[-1]
        ema_f = float(bar.get("ema_fast", 0.0) or 0.0)
        ema_s = float(bar.get("ema_slow", 0.0) or 0.0)
        ema_slope = float(bar.get("ema_slope", 0.0) or 0.0)
        
        if ema_f < ema_s and ema_slope < 0:
            bearish_bars.append({
                "step": step,
                "timestamp": str(bar["timestamp"]),
                "asset": asset,
                "ema_fast": ema_f,
                "ema_slow": ema_s,
                "ema_slope": ema_slope,
                "ema_distance": float(bar.get("ema_distance", 0.0) or 0.0),
                "rsi": float(bar.get("rsi", 50.0) or 50.0),
                "return_1": float(bar.get("return_1", 0.0) or 0.0),
                "return_3": float(bar.get("return_3", 0.0) or 0.0),
            })

print(f"Identified {len(bearish_bars)} bearish trend bars across {target_assets}")
if bearish_bars:
    sample_df = pd.DataFrame(bearish_bars[:10])
    print(sample_df[["timestamp", "asset", "ema_fast", "ema_slow", "ema_slope", "ema_distance", "rsi", "return_1"]].to_string(index=False))

# --------------------------------------------------
# SECTION 2: ML DIRECTION AUDIT
# --------------------------------------------------
print("\n--- SECTION 2: ML DIRECTION AUDIT ---")
# Check prediction formula in _analyze_asset_bar: prediction = ema_dist * 2.0 + ret_1 * 0.5 (or model prediction)
# Let's inspect predictions across ALL 840 asset steps (70 steps * 12 assets)
ml_directions = []
ml_predictions = []
ml_probs = []

scanner = MarketScanner()

for step in range(30, 100):
    for asset, df in datasets.items():
        slice_df = df.iloc[: step + 1].copy()
        feats_df = feature_builder.build(slice_df, is_training=False)
        if feats_df.empty:
            continue
        bar = feats_df.iloc[-1]
        analysis = scanner._analyze_asset_bar(asset, bar)
        ml_directions.append(analysis.direction)
        ml_predictions.append(analysis.prediction)
        ml_probs.append(analysis.probability)

dir_counts = Counter(ml_directions)
print(f"ML Direction Distribution across 840 total asset bars:")
for k, v in dir_counts.items():
    print(f"  {k:10s}: {v:3d} ({v/len(ml_directions):.1%})")

print(f"ML Prediction Stats -> Min: {min(ml_predictions):+.4f}, Max: {max(ml_predictions):+.4f}, Mean: {np.mean(ml_predictions):+.4f}")
print(f"ML Probability Stats -> Min: {min(ml_probs):.4f}, Max: {max(ml_probs):.4f}, Mean: {np.mean(ml_probs):.4f}")

# --------------------------------------------------
# SECTION 3: MARKET SCANNER DIRECTION AUDIT
# --------------------------------------------------
print("\n--- SECTION 3: MARKET SCANNER DIRECTION AUDIT ---")
# Compare raw signal vs final scanner direction
# In _analyze_asset_bar: thr = 0.005. If prediction < -0.005 -> SHORT.
# How many times is prediction < -0.005?
short_pred_count = sum(1 for p in ml_predictions if p < -0.005)
long_pred_count = sum(1 for p in ml_predictions if p > 0.005)
neutral_pred_count = sum(1 for p in ml_predictions if -0.005 <= p <= 0.005)
print(f"Raw Prediction Threshold Counts (thr = 0.005):")
print(f"  prediction > +0.005 (LONG) : {long_pred_count:3d} ({long_pred_count/len(ml_predictions):.1%})")
print(f"  prediction < -0.005 (SHORT): {short_pred_count:3d} ({short_pred_count/len(ml_predictions):.1%})")
print(f"  -0.005 <= pred <= +0.005  : {neutral_pred_count:3d} ({neutral_pred_count/len(ml_predictions):.1%})")

# --------------------------------------------------
# SECTION 4: SPECIALIST DIRECTION AUDIT
# --------------------------------------------------
print("\n--- SECTION 4: SPECIALIST DIRECTION AUDIT ---")
spec_tech_dirs = []
spec_flow_dirs = []
spec_deriv_dirs = []
spec_macro_dirs = []
spec_news_dirs = []

for entry in raw_logs:
    prop = entry.get("proposal", {})
    specs = prop.get("specialist_outputs", [])
    for sp in specs:
        name = sp.get("specialist_name")
        d = sp.get("direction")
        if name == "technical_ml":
            spec_tech_dirs.append(d)
        elif name == "order_flow":
            spec_flow_dirs.append(d)
        elif name == "derivatives":
            spec_deriv_dirs.append(d)
        elif name == "macro_regime":
            spec_macro_dirs.append(d)
        elif name == "news_sentiment":
            spec_news_dirs.append(d)

print("Specialist Direction Distributions across 210 Replay Proposals:")
for name, d_list in [
    ("technical_ml", spec_tech_dirs),
    ("order_flow", spec_flow_dirs),
    ("derivatives", spec_deriv_dirs),
    ("macro_regime", spec_macro_dirs),
    ("news_sentiment", spec_news_dirs),
]:
    c = Counter(d_list)
    print(f"  {name:15s} -> LONG: {c['LONG']:3d}, SHORT: {c['SHORT']:3d}, NEUTRAL: {c['NEUTRAL']:3d}, UNAVAILABLE: {c['UNAVAILABLE']:3d}")

# --------------------------------------------------
# SECTION 5: EVIDENCE FUSION AUDIT
# --------------------------------------------------
print("\n--- SECTION 5: EVIDENCE FUSION AUDIT ---")
fused_scores = []
fused_dirs = []
fused_bands = []

for entry in raw_logs:
    prop = entry.get("proposal", {})
    fusion = prop.get("fusion_result", {})
    fused_scores.append(fusion.get("directional_score", 0.0))
    fused_dirs.append(fusion.get("composite_direction", "NEUTRAL"))
    fused_bands.append(fusion.get("confidence_band", "NO_TRADE"))

pos_scores = sum(1 for s in fused_scores if s >= 0.18)
neg_scores = sum(1 for s in fused_scores if s <= -0.18)
near_zero = sum(1 for s in fused_scores if -0.18 < s < 0.18)

print(f"Evidence Fusion Directional Score Distribution (threshold = +/-0.18):")
print(f"  Score >= +0.18 (LONG) : {pos_scores:3d} ({pos_scores/len(fused_scores):.1%})")
print(f"  Score <= -0.18 (SHORT): {neg_scores:3d} ({neg_scores/len(fused_scores):.1%})")
print(f"  -0.18 < Score < +0.18 : {near_zero:3d} ({near_zero/len(fused_scores):.1%})")

c_dirs = Counter(fused_dirs)
print(f"Fused Composite Directions: {dict(c_dirs)}")
c_bands = Counter(fused_bands)
print(f"Fused Confidence Bands: {dict(c_bands)}")

# --------------------------------------------------
# SECTION 6: DECISION AGENT AUDIT
# --------------------------------------------------
print("\n--- SECTION 6: DECISION AGENT AUDIT ---")
dec_types = []
for entry in raw_logs:
    prop = entry.get("proposal", {})
    dec_types.append((prop.get("decision"), prop.get("direction")))

c_dec = Counter(dec_types)
print("Decision Agent Output (Decision, Direction):")
for k, v in c_dec.items():
    print(f"  {k} -> {v:3d}")

# --------------------------------------------------
# SECTION 7: RISK SUPERVISOR AUDIT
# --------------------------------------------------
print("\n--- SECTION 7: RISK SUPERVISOR AUDIT ---")
short_entering_risk = [e for e in raw_logs if e["proposal"]["direction"] == "SHORT"]
print(f"SHORT proposals entering RiskSupervisor: {len(short_entering_risk)}")

# --------------------------------------------------
# SECTION 8: TOP-N SELECTION AUDIT
# --------------------------------------------------
print("\n--- SECTION 8: TOP-N SELECTION AUDIT ---")
# Compare all eligible assets before Top-N vs Top-N assets after filtering
all_step_analyses = []
top_step_analyses = []

for step in range(30, 100):
    step_analyses = []
    asset_bars = {}
    for asset, df in datasets.items():
        slice_df = df.iloc[: step + 1].copy()
        feats_df = feature_builder.build(slice_df, is_training=False)
        if feats_df.empty:
            continue
        bar = feats_df.iloc[-1]
        asset_bars[asset] = bar
    
    btc_bar = asset_bars.get("BTC_USDT")
    btc_bar_info = dict(btc_bar) if btc_bar is not None else None

    for asset, bar in asset_bars.items():
        analysis = scanner._analyze_asset_bar(asset, bar)
        step_analyses.append(analysis)
    
    step_analyses.sort(
        key=lambda a: (a.evidence_summary.weighted_score if a.evidence_summary else a.prediction) * a.confidence * a.probability,
        reverse=True,
    )
    for r, a in enumerate(step_analyses, start=1):
        a.rank = r
        all_step_analyses.append(a)
        if r <= 3:
            top_step_analyses.append(a)

all_long = sum(1 for a in all_step_analyses if a.direction == "LONG")
all_short = sum(1 for a in all_step_analyses if a.direction == "SHORT")
all_neutral = sum(1 for a in all_step_analyses if a.direction == "NEUTRAL")

top_long = sum(1 for a in top_step_analyses if a.direction == "LONG")
top_short = sum(1 for a in top_step_analyses if a.direction == "SHORT")
top_neutral = sum(1 for a in top_step_analyses if a.direction == "NEUTRAL")

print(f"BEFORE Top-N Filtering (840 total asset bars):")
print(f"  LONG: {all_long:3d} ({all_long/len(all_step_analyses):.1%}) | SHORT: {all_short:3d} ({all_short/len(all_step_analyses):.1%}) | NEUTRAL: {all_neutral:3d} ({all_neutral/len(all_step_analyses):.1%})")
print(f"AFTER Top-N Filtering (210 selected top-3 asset bars):")
print(f"  LONG: {top_long:3d} ({top_long/len(top_step_analyses):.1%}) | SHORT: {top_short:3d} ({top_short/len(top_step_analyses):.1%}) | NEUTRAL: {top_neutral:3d} ({top_neutral/len(top_step_analyses):.1%})")

# --------------------------------------------------
# SECTION 9: END-TO-END TRACE (20 BEARISH TIMESTAMPS)
# --------------------------------------------------
print("\n--- SECTION 9: END-TO-END TRACE (20 BEARISH TIMESTAMPS) ---")
trace_records = []
for entry in raw_logs:
    step = entry["step"]
    prop = entry["proposal"]
    asset = prop["asset"]
    df = datasets[asset]
    bar = df.iloc[step]

    # Check if market regime at this step was BEARISH_TREND
    regime = prop.get("market_evidence", [])
    # Let's inspect spec outputs
    specs = {s["specialist_name"]: s["direction"] for s in prop.get("specialist_outputs", [])}
    
    trace_records.append({
        "step": step,
        "timestamp": str(bar["timestamp"]),
        "asset": asset,
        "ml_direction": prop["model_signal"],
        "scanner_rank": prop["scanner_rank"],
        "tech_sp": specs.get("technical_ml"),
        "flow_sp": specs.get("order_flow"),
        "deriv_sp": specs.get("derivatives"),
        "macro_sp": specs.get("macro_regime"),
        "news_sp": specs.get("news_sentiment"),
        "fusion_score": prop.get("fusion_result", {}).get("directional_score"),
        "fused_dir": prop.get("fusion_result", {}).get("composite_direction"),
        "decision": prop["decision"],
        "final_direction": prop["direction"],
    })

trace_df = pd.DataFrame(trace_records)
print(f"Total Trace Records Collected: {len(trace_df)}")
print("Sample of 15 trace records:")
print(trace_df[["timestamp", "asset", "ml_direction", "scanner_rank", "tech_sp", "macro_sp", "fusion_score", "fused_dir", "decision", "final_direction"]].head(15).to_string(index=False))

# --------------------------------------------------
# SECTION 10: COUNTERFACTUAL DIAGNOSTICS
# --------------------------------------------------
print("\n--- SECTION 10: COUNTERFACTUAL DIAGNOSTICS ---")
# A. If ML direction is SHORT: how often does final decision remain LONG?
short_ml_props = [p for p in raw_logs if p["proposal"]["model_signal"] == "SHORT"]
final_long_when_short_ml = sum(1 for p in short_ml_props if p["proposal"]["direction"] == "LONG")

# B. If Evidence Fusion score < 0: how often does final decision remain LONG?
neg_fusion_props = [p for p in raw_logs if p["proposal"].get("fusion_result", {}).get("directional_score", 0.0) < 0]
final_long_when_neg_fusion = sum(1 for p in neg_fusion_props if p["proposal"]["direction"] == "LONG")

# C. If MacroRegime = SHORT/BEARISH: how often does final decision remain LONG?
bear_macro_props = []
for p in raw_logs:
    specs = p["proposal"].get("specialist_outputs", [])
    macro_sp = next((s for s in specs if s["specialist_name"] == "macro_regime"), None)
    if macro_sp and macro_sp.get("direction") in ("SHORT", "BEARISH"):
        bear_macro_props.append(p)

final_long_when_bear_macro = sum(1 for p in bear_macro_props if p["proposal"]["direction"] == "LONG")

print(f"Diagnostic A (If ML direction is SHORT, N={len(short_ml_props)}): Final LONG count = {final_long_when_short_ml}")
print(f"Diagnostic B (If Fusion score < 0, N={len(neg_fusion_props)}): Final LONG count = {final_long_when_neg_fusion}")
print(f"Diagnostic C (If MacroRegime is BEARISH, N={len(bear_macro_props)}): Final LONG count = {final_long_when_bear_macro}")

# --------------------------------------------------
# SECTION 11: FALLBACK PATH AUDIT
# --------------------------------------------------
print("\n--- SECTION 11: FALLBACK PATH AUDIT ---")
fallback_count = sum(1 for p in raw_logs if p["proposal"].get("fallback_used", False))
print(f"Fallback path used: {fallback_count} / {len(raw_logs)}")

# --------------------------------------------------
# SECTION 12: CONFIDENCE PATH AUDIT
# --------------------------------------------------
print("\n--- SECTION 12: CONFIDENCE PATH AUDIT ---")
long_confs = [p["proposal"]["confidence"] for p in raw_logs if p["proposal"]["direction"] == "LONG"]
short_confs = [p["proposal"]["confidence"] for p in raw_logs if p["proposal"]["direction"] == "SHORT"]

print(f"LONG Candidates Confidence -> Count: {len(long_confs)}, Mean: {np.mean(long_confs):.4f}, Min: {min(long_confs):.4f}, Max: {max(long_confs):.4f}")
print(f"SHORT Candidates Confidence -> Count: {len(short_confs)}, Mean: {np.mean(short_confs) if short_confs else 0:.4f}")

print("\nAudit script execution complete!")
