"""
agent/specialists.py — Phase 12.2 Specialist Analyzers

Implements 5 deterministic specialist analyzers:
1. Technical/ML Specialist
2. Order Flow Specialist
3. Derivatives Specialist
4. Macro/Regime Specialist
5. News/Sentiment Specialist

Rule:
Each specialist consumes structured AssetAnalysis & MarketEvidence, producing a SpecialistOutput.
No trading or order execution calls are made.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.schema import AssetAnalysis, MarketEvidence, SpecialistOutput

log = logging.getLogger("agent.specialists")


class TechnicalMLSpecialist:
    """
    Evaluates technical indicators, trend, momentum, RSI, volatility, and ML predictions.
    NOTE: Does NOT treat ML probability as guaranteed probability of profit.
    """
    def analyze(self, asset_analysis: AssetAnalysis) -> SpecialistOutput:
        asset = asset_analysis.asset
        direction = asset_analysis.direction  # "LONG" | "SHORT" | "NEUTRAL"
        prob = asset_analysis.probability
        conf = asset_analysis.confidence
        prediction = asset_analysis.prediction
        trend = asset_analysis.ema_trend
        rsi = asset_analysis.rsi
        vol = asset_analysis.volatility

        evidence: List[str] = []
        reasons: List[str] = []

        reasons.append(f"ML model prediction score is {prediction:+.4f} (threshold: {asset_analysis.threshold:.4f})")
        reasons.append(f"Model calibrated probability: {prob:.1%}, model confidence: {conf:.1%}")
        reasons.append(f"Technical EMA trend is {trend}, 14-period RSI is {rsi:.1f}, rolling volatility is {vol:.4f}")

        if direction == "LONG":
            evidence.append(f"Positive ML prediction (+{prediction:.4f}) with {prob:.1%} probability")
            if trend == "BULLISH":
                evidence.append("Technical EMA trend aligns with LONG prediction")
            if rsi < 70.0:
                evidence.append(f"RSI ({rsi:.1f}) is not overbought")
        elif direction == "SHORT":
            evidence.append(f"Negative ML prediction ({prediction:.4f}) with {prob:.1%} probability")
            if trend == "BEARISH":
                evidence.append("Technical EMA trend aligns with SHORT prediction")
            if rsi > 30.0:
                evidence.append(f"RSI ({rsi:.1f}) is not oversold")
        else:
            evidence.append(f"ML model prediction ({prediction:+.4f}) is within neutral threshold range")

        metrics = {
            "prediction": round(prediction, 4),
            "probability": round(prob, 4),
            "confidence": round(conf, 4),
            "ema_trend": trend,
            "rsi": round(rsi, 2),
            "volatility": round(vol, 6),
        }

        return SpecialistOutput(
            specialist_name="technical_ml",
            direction=direction,
            confidence=round(conf, 4),
            evidence=evidence,
            reasons=reasons,
            status="VALID",
            metrics=metrics,
        )


class OrderFlowSpecialist:
    """
    Evaluates order book depth imbalance, spread %, large trade activity, and volume flow.
    NOTE: Uses 'large flow' or 'large trade activity', avoids 'whale' unless supported by data.
    """
    def analyze(self, market_evidences: List[MarketEvidence]) -> SpecialistOutput:
        ob_ev = next((e for e in market_evidences if e.source == "order_book"), None)
        lf_ev = next((e for e in market_evidences if e.source == "large_flow"), None)

        evidence: List[str] = []
        reasons: List[str] = []

        if not ob_ev and not lf_ev:
            return SpecialistOutput(
                specialist_name="order_flow",
                direction="UNAVAILABLE",
                confidence=0.0,
                evidence=["Order book and trade flow data unavailable"],
                reasons=["No order flow evidence sources returned from market scanner"],
                status="UNAVAILABLE",
                metrics={},
            )

        ob_sig = ob_ev.signal if ob_ev else "UNAVAILABLE"
        lf_sig = lf_ev.signal if lf_ev else "UNAVAILABLE"

        ob_metrics = ob_ev.raw_metrics if ob_ev else {}
        lf_metrics = lf_ev.raw_metrics if lf_ev else {}

        imbalance = ob_metrics.get("imbalance", 0.0)
        spread_pct = ob_metrics.get("spread_pct", 0.0)
        flow_imbalance = lf_metrics.get("flow_imbalance", 0.0)
        large_count = lf_metrics.get("large_trade_count", 0)

        if ob_ev and ob_ev.status == "VALID":
            reasons.append(f"Order book bid/ask depth imbalance is {imbalance:+.2f} (spread: {spread_pct:.4%})")
        if lf_ev and lf_ev.status == "VALID":
            reasons.append(f"Aggressive buy/sell flow imbalance is {flow_imbalance:+.2f} across {large_count} large trade events")

        # Direction synthesis
        if ob_sig == "BULLISH" or lf_sig == "BULLISH":
            if ob_sig != "BEARISH" and lf_sig != "BEARISH":
                direction = "LONG"
                confidence = max(ob_ev.confidence if ob_ev else 0.0, lf_ev.confidence if lf_ev else 0.0)
                if imbalance > 0.20:
                    evidence.append(f"Bid depth exceeds ask depth by {abs(imbalance):.1%}")
                if flow_imbalance > 0.25:
                    evidence.append(f"Net buyer volume flow is +{flow_imbalance:.1%} with {large_count} large buy trades")
            else:
                direction = "NEUTRAL"
                confidence = 0.50
                evidence.append("Order book and recent trade volume flow contradict each other")
        elif ob_sig == "BEARISH" or lf_sig == "BEARISH":
            if ob_sig != "BULLISH" and lf_sig != "BULLISH":
                direction = "SHORT"
                confidence = max(ob_ev.confidence if ob_ev else 0.0, lf_ev.confidence if lf_ev else 0.0)
                if imbalance < -0.20:
                    evidence.append(f"Ask depth exceeds bid depth by {abs(imbalance):.1%}")
                if flow_imbalance < -0.25:
                    evidence.append(f"Net seller volume flow is {flow_imbalance:.1%} with {large_count} large sell trades")
            else:
                direction = "NEUTRAL"
                confidence = 0.50
                evidence.append("Order book and recent trade volume flow contradict each other")
        else:
            direction = "NEUTRAL"
            confidence = 0.55
            evidence.append("Order book and trade flow volume are balanced")

        metrics = {
            "imbalance": imbalance,
            "spread_pct": spread_pct,
            "flow_imbalance": flow_imbalance,
            "large_trade_count": large_count,
        }

        return SpecialistOutput(
            specialist_name="order_flow",
            direction=direction,
            confidence=round(confidence, 4),
            evidence=evidence,
            reasons=reasons,
            status="VALID",
            metrics=metrics,
        )


class DerivativesSpecialist:
    """
    Evaluates Open Interest trends, funding rates, long/short positioning ratios, and taker flows.
    Analyzes: long buildup, short buildup, short squeeze, long liquidation, crowded positioning, overheated funding.
    """
    def analyze(self, market_evidences: List[MarketEvidence]) -> SpecialistOutput:
        oi_ev = next((e for e in market_evidences if e.source == "open_interest"), None)
        fn_ev = next((e for e in market_evidences if e.source == "funding"), None)
        pos_ev = next((e for e in market_evidences if e.source == "positioning"), None)

        evidence: List[str] = []
        reasons: List[str] = []

        valid_evs = [e for e in (oi_ev, fn_ev, pos_ev) if e and e.status == "VALID"]
        if not valid_evs:
            return SpecialistOutput(
                specialist_name="derivatives",
                direction="UNAVAILABLE",
                confidence=0.0,
                evidence=["Derivatives statistics unavailable"],
                reasons=["No open interest, funding, or positioning data received"],
                status="UNAVAILABLE",
                metrics={},
            )

        oi_change = oi_ev.raw_metrics.get("oi_change_pct", 0.0) if oi_ev else 0.0
        funding_rate = fn_ev.raw_metrics.get("funding_rate", 0.0) if fn_ev else 0.0
        lsr_account = pos_ev.raw_metrics.get("lsr_account", 1.0) if pos_ev else 1.0
        lsr_taker = pos_ev.raw_metrics.get("lsr_taker", 1.0) if pos_ev else 1.0

        if oi_ev and oi_ev.status == "VALID":
            reasons.append(f"Open interest change is {oi_change:+.1%} ({oi_ev.reason})")
        if fn_ev and fn_ev.status == "VALID":
            reasons.append(f"Funding rate is {funding_rate*100:+.4f}%/8h ({fn_ev.reason})")
        if pos_ev and pos_ev.status == "VALID":
            reasons.append(f"Long/Short account ratio is {lsr_account:.2f}x, taker ratio is {lsr_taker:.2f}x")

        # Classify derivatives dynamics
        bullish_flags = 0
        bearish_flags = 0

        if oi_ev and oi_ev.signal == "BULLISH":
            bullish_flags += 1
            evidence.append(oi_ev.reason)
        elif oi_ev and oi_ev.signal == "BEARISH":
            bearish_flags += 1
            evidence.append(oi_ev.reason)

        if fn_ev and fn_ev.signal == "BULLISH":
            bullish_flags += 1
            evidence.append(fn_ev.reason)
        elif fn_ev and fn_ev.signal == "BEARISH":
            bearish_flags += 1
            evidence.append(fn_ev.reason)

        if pos_ev and pos_ev.signal == "BULLISH":
            bullish_flags += 1
            evidence.append(pos_ev.reason)
        elif pos_ev and pos_ev.signal == "BEARISH":
            bearish_flags += 1
            evidence.append(pos_ev.reason)

        if bullish_flags > bearish_flags:
            direction = "LONG"
            confidence = min(0.90, 0.55 + 0.15 * (bullish_flags - bearish_flags))
        elif bearish_flags > bullish_flags:
            direction = "SHORT"
            confidence = min(0.90, 0.55 + 0.15 * (bearish_flags - bullish_flags))
        else:
            direction = "NEUTRAL"
            confidence = 0.55
            evidence.append("Derivatives metrics (OI, funding, positioning) are neutral or balanced")

        metrics = {
            "oi_change_pct": oi_change,
            "funding_rate": funding_rate,
            "lsr_account": lsr_account,
            "lsr_taker": lsr_taker,
        }

        return SpecialistOutput(
            specialist_name="derivatives",
            direction=direction,
            confidence=round(confidence, 4),
            evidence=evidence,
            reasons=reasons,
            status="VALID",
            metrics=metrics,
        )


class MacroRegimeSpecialist:
    """
    Evaluates BTC market regime, trend, volatility, and momentum context.
    Determines macro tailwind, macro headwind, or neutral regime for altcoin assets.
    NOTE: Does NOT automatically override asset-specific evidence.
    """
    def analyze(self, market_evidences: List[MarketEvidence]) -> SpecialistOutput:
        reg_ev = next((e for e in market_evidences if e.source == "btc_regime"), None)

        evidence: List[str] = []
        reasons: List[str] = []

        if not reg_ev or reg_ev.status != "VALID":
            return SpecialistOutput(
                specialist_name="macro_regime",
                direction="UNAVAILABLE",
                confidence=0.0,
                evidence=["BTC macro regime context unavailable"],
                reasons=["No BTC market regime reference returned"],
                status="UNAVAILABLE",
                metrics={},
            )

        regime = reg_ev.raw_metrics.get("btc_regime", "NEUTRAL_CONSOLIDATION")
        btc_trend = reg_ev.raw_metrics.get("btc_trend", "NEUTRAL")
        reasons.append(f"BTC macro regime is {regime} with {btc_trend} trend ({reg_ev.reason})")

        if reg_ev.signal == "BULLISH":
            direction = "LONG"
            confidence = reg_ev.confidence
            evidence.append(f"Macro tailwind: BTC regime is {regime} (trend: {btc_trend})")
        elif reg_ev.signal == "BEARISH":
            direction = "SHORT"
            confidence = reg_ev.confidence
            evidence.append(f"Macro headwind: BTC regime is {regime} (trend: {btc_trend})")
        else:
            direction = "NEUTRAL"
            confidence = 0.60
            evidence.append(f"Macro neutral: BTC regime is {regime}")

        return SpecialistOutput(
            specialist_name="macro_regime",
            direction=direction,
            confidence=round(confidence, 4),
            evidence=evidence,
            reasons=reasons,
            status="VALID",
            metrics=reg_ev.raw_metrics,
        )


class NewsSentimentSpecialist:
    """
    Wraps NewsAdapter. If news is unconfigured, returns UNAVAILABLE status and NEUTRAL signal.
    Does NOT invent news or infer sentiment.
    """
    def analyze(self, market_evidences: List[MarketEvidence]) -> SpecialistOutput:
        news_ev = next((e for e in market_evidences if e.source == "news"), None)

        if not news_ev or news_ev.status == "UNAVAILABLE" or news_ev.signal == "UNAVAILABLE":
            return SpecialistOutput(
                specialist_name="news_sentiment",
                direction="UNAVAILABLE",
                confidence=0.0,
                evidence=["External news feed unconfigured (Phase 12.1 adapter active)"],
                reasons=["No external news API or RSS feed configured"],
                status="UNAVAILABLE",
                metrics={},
            )

        return SpecialistOutput(
            specialist_name="news_sentiment",
            direction=news_ev.signal if news_ev.signal in ("LONG", "SHORT", "NEUTRAL") else "NEUTRAL",
            confidence=news_ev.confidence,
            evidence=[news_ev.reason],
            reasons=[news_ev.reason],
            status=news_ev.status,
            metrics=news_ev.raw_metrics,
        )
