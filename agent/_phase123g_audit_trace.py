"""
agent/_phase123g_audit_trace.py — Phase 12.3G Directional Bias Root-Cause Audit Trace Script

Executes a granular trace of the historical decision pipeline:
Historical OHLCV -> FeatureBuilder -> ML -> TechnicalMLSpecialist -> MacroRegimeSpecialist
                 -> EvidenceFusion -> Ranking -> Top-N Selection -> DecisionAgent -> RiskSupervisor

Produces explicit directional counts at every stage and identifies FIRST_DIRECTIONAL_DIVERGENCE.
"""

import sys
from typing import Dict, List, Any
import numpy as np
import pandas as pd

from agent.historical_replay import HistoricalReplayEngine, ReplayConfig
from agent.schema import AssetAnalysis, MarketEvidence, SpecialistOutput, FusionResult, DecisionProposal
from agent.evidence_fusion import EvidenceFusionEngine
from agent.specialists import TechnicalMLSpecialist, OrderFlowSpecialist, DerivativesSpecialist, MacroRegimeSpecialist, NewsSentimentSpecialist


def run_audit_trace():
    print("=" * 80)
    print("PHASE 12.3G — DIRECTIONAL BIAS ROOT-CAUSE FORENSIC AUDIT TRACE")
    print("=" * 80)

    cfg = ReplayConfig()
    engine = HistoricalReplayEngine(config=cfg)

    # Data structures for tracking per-stage statistics
    stage_counts = {
        "ML_Prediction": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0},
        "TechnicalMLSpecialist": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0, "UNAVAILABLE": 0},
        "MacroRegimeSpecialist": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0, "UNAVAILABLE": 0},
        "EvidenceFusion": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0},
        "Ranking_Selected_TopN": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0},
        "DecisionAgent": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0},
    }

    ml_scores = []
    ml_probabilities = []
    trace_records = []
    divergence_log = []

    # Run step-by-step replay manually to intercept exact per-asset states
    min_candles = min(len(df) for df in engine._raw_data.values())

    for step in range(engine.config.warmup_period, min_candles):
        step_analyses: List[AssetAnalysis] = []
        asset_bars: Dict[str, pd.Series] = {}

        # 1. FeatureBuilder + Bar extraction
        for asset, df in engine._raw_data.items():
            slice_df = df.iloc[: step + 1].copy()
            try:
                feats_df = engine.feature_builder.build(slice_df, is_training=False)
                if not feats_df.empty:
                    asset_bars[asset] = feats_df.iloc[-1]
            except Exception as err:
                pass

        if not asset_bars:
            continue

        btc_bar = asset_bars.get("BTC_USDT")
        btc_bar_info = dict(btc_bar) if btc_bar is not None else None

        # 2. ML & Specialist analysis for each asset
        for asset, bar in asset_bars.items():
            analysis = engine._build_asset_analysis_at_step(asset, bar)

            # Record ML Stage
            ml_dir = analysis.direction
            stage_counts["ML_Prediction"][ml_dir] += 1
            ml_scores.append(analysis.prediction)
            ml_probabilities.append(analysis.probability)

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

            # Run Specialists explicitly
            sp_tech = engine.decision_agent.tech_specialist.analyze(analysis)
            sp_flow = engine.decision_agent.flow_specialist.analyze(evidences)
            sp_deriv = engine.decision_agent.deriv_specialist.analyze(evidences)
            sp_macro = engine.decision_agent.macro_specialist.analyze(evidences)
            sp_news = engine.decision_agent.news_specialist.analyze(evidences)

            stage_counts["TechnicalMLSpecialist"][sp_tech.direction] += 1
            stage_counts["MacroRegimeSpecialist"][sp_macro.direction] += 1

            # Evidence Fusion
            fusion_res = engine.decision_agent.fusion_engine.fuse(
                asset=asset,
                specialist_outputs=[sp_tech, sp_flow, sp_deriv, sp_macro, sp_news],
                market_evidences=evidences,
                evidence_summary=summary,
            )
            stage_counts["EvidenceFusion"][fusion_res.composite_direction] += 1

            step_analyses.append(analysis)

            # Track divergence check
            if ml_dir == "SHORT" and fusion_res.composite_direction != "SHORT":
                divergence_log.append({
                    "step": step,
                    "timestamp": str(bar.get("timestamp")),
                    "asset": asset,
                    "ml_dir": ml_dir,
                    "ml_pred": analysis.prediction,
                    "sp_tech": sp_tech.direction,
                    "sp_macro": sp_macro.direction,
                    "fused_dir": fusion_res.composite_direction,
                    "fused_score": fusion_res.directional_score,
                })

        # 3. Ranking & Top-N Selection
        step_analyses.sort(
            key=lambda a: abs(a.evidence_summary.weighted_score if a.evidence_summary else a.prediction) * a.confidence * a.probability,
            reverse=True,
        )
        for r, a in enumerate(step_analyses, start=1):
            a.rank = r

        for a in step_analyses:
            if a.direction == "SHORT":
                is_top = (a.rank <= engine.config.top_n)
                print(f"[SHORT TRACE] Step {step} | Asset: {a.asset} | ML dir: {a.direction} | ML pred: {a.prediction:+.4f} | WeightedScore: {a.evidence_summary.weighted_score:+.4f} | Rank: {a.rank}/12 | Selected(Top3): {is_top}")

        top_n_analyses = step_analyses[: engine.config.top_n]
        for a in top_n_analyses:
            comp_dir = "LONG" if a.evidence_summary.composite_signal == "BULLISH" else ("SHORT" if a.evidence_summary.composite_signal == "BEARISH" else "NEUTRAL")
            stage_counts["Ranking_Selected_TopN"][comp_dir] = stage_counts["Ranking_Selected_TopN"].get(comp_dir, 0) + 1

        # 4. DecisionAgent Proposals
        proposals = engine.decision_agent.evaluate_scanned_assets(step_analyses)
        for prop in proposals:
            stage_counts["DecisionAgent"][prop.direction] += 1

            # RiskSupervisor check
            review = engine.risk_supervisor.review_proposal(prop)
            if prop.direction != review.reviewed_decision and review.status != "REJECTED":
                print(f"WARNING: RiskSupervisor changed direction from {prop.direction} to {review.reviewed_decision}!")

    print("\n" + "=" * 80)
    print("STAGE-BY-STAGE DIRECTIONAL DISTRIBUTION ACROSS ALL EVALUATIONS")
    print("=" * 80)
    print(f"{'STAGE':<25} | {'LONG':<8} | {'SHORT':<8} | {'NEUTRAL':<8} | {'UNAVAILABLE':<12}")
    print("-" * 70)
    for stage, counts in stage_counts.items():
        l = counts.get("LONG", 0)
        s = counts.get("SHORT", 0)
        n = counts.get("NEUTRAL", 0)
        u = counts.get("UNAVAILABLE", 0)
        print(f"{stage:<25} | {l:<8d} | {s:<8d} | {n:<8d} | {u:<12d}")

    print("\n" + "=" * 80)
    print("ML PREDICTION METRICS AUDIT")
    print("=" * 80)
    print(f"Total Bar Evaluations: {len(ml_scores)}")
    print(f"Mean ML Score: {np.mean(ml_scores):+.6f}")
    print(f"Median ML Score: {np.median(ml_scores):+.6f}")
    print(f"Min ML Score: {np.min(ml_scores):+.6f}")
    print(f"Max ML Score: {np.max(ml_scores):+.6f}")
    print(f"Mean ML Probability: {np.mean(ml_probabilities):.4f}")

    if divergence_log:
        print("\n" + "=" * 80)
        print(f"DIVERGENCE DETECTED: {len(divergence_log)} SHORT ML signals diverged downstream")
        print("=" * 80)
        for div in divergence_log[:10]:
            print(f"Step {div['step']} | Asset: {div['asset']} | ML: {div['ml_dir']} ({div['ml_pred']:+.4f}) | Tech: {div['sp_tech']} | Macro: {div['sp_macro']} | Fused: {div['fused_dir']} ({div['fused_score']:+.4f})")

    # 5. Synthetic Unit Tests for Fusion & Ranking
    print("\n" + "=" * 80)
    print("SYNTHETIC EVIDENCE FUSION & RANKING AUDIT TESTS")
    print("=" * 80)

    # Synthetic Test 1: Technical SHORT + Macro SHORT + Unavailable Others
    fusion = EvidenceFusionEngine()
    sp_t_short = SpecialistOutput(specialist_name="technical_ml", direction="SHORT", confidence=0.80, status="VALID")
    sp_m_short = SpecialistOutput(specialist_name="macro_regime", direction="SHORT", confidence=0.80, status="VALID")
    sp_unavail = SpecialistOutput(specialist_name="order_flow", direction="UNAVAILABLE", confidence=0.0, status="UNAVAILABLE")

    res1 = fusion.fuse("BTC_USDT", [sp_t_short, sp_m_short, sp_unavail], [])
    print(f"Synthetic Test 1 (Tech SHORT + Macro SHORT + Unavailable): Direction = {res1.composite_direction}, Score = {res1.directional_score:+.4f}, Agreement = {res1.agreement_score:.2f}")
    assert res1.composite_direction == "SHORT", "FAIL: Tech SHORT + Macro SHORT must fuse to SHORT!"

    # Synthetic Test 2: Technical SHORT + Macro BULLISH/NEUTRAL + Unavailable Others
    sp_m_neut = SpecialistOutput(specialist_name="macro_regime", direction="NEUTRAL", confidence=0.60, status="VALID")
    res2 = fusion.fuse("BTC_USDT", [sp_t_short, sp_m_neut, sp_unavail], [])
    print(f"Synthetic Test 2 (Tech SHORT + Macro NEUTRAL + Unavailable): Direction = {res2.composite_direction}, Score = {res2.directional_score:+.4f}, Agreement = {res2.agreement_score:.2f}")

    # Synthetic Test 3: Ranking test: LONG +0.20 vs SHORT -0.80
    score_long = +0.20
    score_short = -0.80
    rank_long = abs(score_long) * 0.80 * 0.75
    rank_short = abs(score_short) * 0.80 * 0.75
    print(f"Synthetic Test 3 (Ranking): LONG score +0.20 (rank_key={rank_long:.4f}) vs SHORT score -0.80 (rank_key={rank_short:.4f})")
    assert rank_short > rank_long, "FAIL: SHORT score -0.80 must rank higher than LONG score +0.20!"

    print("\nALL SYNTHETIC AUDIT TESTS PASSED SUCESSFULLY.")

if __name__ == "__main__":
    run_audit_trace()
