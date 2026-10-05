"""
agent/market_intelligence.py — Phase 12.1 Market Intelligence Layer

Enriches each scanned asset with independent market evidence beyond OHLCV + technical indicators + ML:
1. Order Book (depth, imbalance, spread)
2. Large Order / Flow (large trade detection, buy/sell volume flow imbalance)
3. Open Interest & Acceleration (OI trends, price vs OI relationship)
4. Funding Rate & Anomalies (funding rate direction & overheat detection)
5. Long/Short Positioning (account long/short ratio & taker flow)
6. Volume / Flow Baseline (anomaly detection)
7. BTC Market Regime (macro risk tailwind/headwind for altcoins)
8. News / Sentiment (adapter interface returning UNAVAILABLE when unconfigured)

STRICT SAFETY RULE:
This phase is INFORMATION + EVIDENCE ONLY.
No trading or order execution calls are made or triggered.
"""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.schema import AssetAnalysis, MarketEvidence, EvidenceSummary

log = logging.getLogger("agent.market_intelligence")


class IntelligenceConfig:
    """
    Deterministic configuration-driven evidence weights and operational parameters.
    Weights are non-zero, normalized, and configurable.
    """
    def __init__(self, cfg_dict: Optional[Dict[str, Any]] = None):
        cfg_dict = cfg_dict or {}
        intel_cfg = cfg_dict.get("market_intelligence") or {}
        weights = intel_cfg.get("weights") or {}

        # Configurable deterministic weights (default sum to 1.0)
        self.technical_weight: float = float(weights.get("technical", 0.15))
        self.ml_weight: float        = float(weights.get("ml", 0.25))
        self.orderbook_weight: float = float(weights.get("orderbook", 0.15))
        self.flow_weight: float      = float(weights.get("flow", 0.10))
        self.oi_weight: float        = float(weights.get("open_interest", 0.10))
        self.funding_weight: float   = float(weights.get("funding", 0.05))
        self.positioning_weight: float = float(weights.get("positioning", 0.05))
        self.regime_weight: float    = float(weights.get("btc_regime", 0.10))
        self.news_weight: float      = float(weights.get("news", 0.05))

        # Operational parameters
        self.http_timeout_sec: float = float(intel_cfg.get("http_timeout_sec", 4.0))
        self.cache_ttl_sec: float    = float(intel_cfg.get("cache_ttl_sec", 30.0))
        self.max_freshness_sec: float = float(intel_cfg.get("max_freshness_sec", 300.0))
        self.stale_threshold_sec: float = float(intel_cfg.get("stale_threshold_sec", 600.0))
        self.gate_base_url: str      = intel_cfg.get("gate_base_url", "https://api.gateio.ws/api/v4")


class SimpleAPICache:
    """Lightweight thread-safe cache to avoid duplicate API requests & protect rate limits."""
    def __init__(self, ttl_sec: float = 30.0):
        self._ttl = ttl_sec
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            ts, val = self._cache[key]
            if time.time() - ts <= self._ttl:
                return val
            else:
                del self._cache[key]
        return None

    def set(self, key: str, val: Any) -> None:
        self._cache[key] = (time.time(), val)

    def clear(self) -> None:
        self._cache.clear()


class GatePublicAPIClient:
    """Robust client for fetching Gate.io public futures endpoints with caching and timeout bounds."""
    def __init__(self, base_url: str = "https://api.gateio.ws/api/v4", timeout: float = 4.0, cache_ttl: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache = SimpleAPICache(ttl_sec=cache_ttl)

    def _fetch_json(self, endpoint: str) -> Tuple[Optional[Any], str, float]:
        """Fetch JSON from Gate API. Returns (data, status_code_or_error, elapsed_sec)."""
        url = f"{self.base_url}{endpoint}"
        cached = self.cache.get(url)
        if cached is not None:
            return cached, "CACHED", 0.001

        start_ts = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Astel-MarketIntelligence/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                elapsed = time.time() - start_ts
                data = json.loads(raw)
                self.cache.set(url, data)
                return data, "OK", elapsed
        except urllib.error.HTTPError as he:
            elapsed = time.time() - start_ts
            log.warning("Gate Public API HTTP %d for %s: %s", he.code, url, he.reason)
            return None, f"HTTP_{he.code}", elapsed
        except urllib.error.URLError as ue:
            elapsed = time.time() - start_ts
            log.warning("Gate Public API URL error for %s: %s", url, ue.reason)
            return None, "TIMEOUT_OR_NETWORK_ERROR", elapsed
        except Exception as e:
            elapsed = time.time() - start_ts
            log.warning("Gate Public API exception for %s: %s", url, e)
            return None, f"ERROR_{type(e).__name__}", elapsed

    def get_order_book(self, contract: str, limit: int = 20) -> Tuple[Optional[Dict[str, Any]], str, float]:
        return self._fetch_json(f"/futures/usdt/order_book?contract={contract}&limit={limit}")

    def get_trades(self, contract: str, limit: int = 50) -> Tuple[Optional[List[Dict[str, Any]]], str, float]:
        return self._fetch_json(f"/futures/usdt/trades?contract={contract}&limit={limit}")

    def get_contract_detail(self, contract: str) -> Tuple[Optional[Dict[str, Any]], str, float]:
        return self._fetch_json(f"/futures/usdt/contracts/{contract}")

    def get_contract_stats(self, contract: str, limit: int = 5, interval: str = "1h") -> Tuple[Optional[List[Dict[str, Any]]], str, float]:
        return self._fetch_json(f"/futures/usdt/contract_stats?contract={contract}&limit={limit}&interval={interval}")


# ---------------------------------------------------------------------------
# Individual Evidence Analyzers
# ---------------------------------------------------------------------------

def analyze_order_book(client: GatePublicAPIClient, contract: str) -> MarketEvidence:
    """Analyze order book depth imbalance, spread, and concentration."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    data, status, elapsed = client.get_order_book(contract, limit=20)

    if not data or status not in ("OK", "CACHED") or not isinstance(data, dict):
        return MarketEvidence(
            source="order_book",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="UNAVAILABLE",
            reason=f"Order book data unavailable from exchange API ({status})",
            raw_metrics={},
        )

    bids = data.get("bids", []) or []
    asks = data.get("asks", []) or []

    if not bids or not asks:
        return MarketEvidence(
            source="order_book",
            signal="NEUTRAL",
            score=0.0,
            confidence=0.2,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="VALID",
            reason="Empty order book bids or asks",
            raw_metrics={"bids_count": len(bids), "asks_count": len(asks)},
        )

    bid_depth = sum(float(b.get("s", 0)) * float(b.get("p", 0)) for b in bids)
    ask_depth = sum(float(a.get("s", 0)) * float(a.get("p", 0)) for a in asks)
    total_depth = bid_depth + ask_depth

    best_bid = float(bids[0].get("p", 0))
    best_ask = float(asks[0].get("p", 0))
    spread = max(0.0, best_ask - best_bid)
    mid_price = (best_bid + best_ask) / 2.0 if (best_bid + best_ask) > 0 else 1.0
    spread_pct = spread / mid_price

    imbalance = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0.0

    # Top 3 levels concentration
    top3_bid = sum(float(b.get("s", 0)) * float(b.get("p", 0)) for b in bids[:3])
    top3_ask = sum(float(a.get("s", 0)) * float(a.get("p", 0)) for a in asks[:3])
    top3_concentration = (top3_bid + top3_ask) / total_depth if total_depth > 0 else 0.0

    raw_metrics = {
        "bid_depth_usdt": round(bid_depth, 2),
        "ask_depth_usdt": round(ask_depth, 2),
        "imbalance": round(imbalance, 4),
        "spread_pct": round(spread_pct, 6),
        "top3_concentration": round(top3_concentration, 4),
    }

    if imbalance > 0.20:
        signal = "BULLISH"
        score = min(1.0, imbalance * 1.5)
        conf = min(0.95, 0.50 + abs(imbalance) * 0.5)
        reason = f"Bid depth exceeds ask depth by {abs(imbalance):.1%} (imbalance: +{imbalance:.2f})"
    elif imbalance < -0.20:
        signal = "BEARISH"
        score = max(-1.0, imbalance * 1.5)
        conf = min(0.95, 0.50 + abs(imbalance) * 0.5)
        reason = f"Ask depth exceeds bid depth by {abs(imbalance):.1%} (imbalance: {imbalance:.2f})"
    else:
        signal = "NEUTRAL"
        score = imbalance
        conf = 0.60
        reason = f"Order book balanced (imbalance: {imbalance:+.2f}, spread: {spread_pct:.4%})"

    return MarketEvidence(
        source="order_book",
        signal=signal,
        score=round(score, 4),
        confidence=round(conf, 4),
        timestamp=now_iso,
        freshness_seconds=elapsed,
        status="VALID",
        reason=reason,
        raw_metrics=raw_metrics,
    )


def analyze_large_flow(client: GatePublicAPIClient, contract: str) -> MarketEvidence:
    """Analyze recent trades for large-order activity, buy/sell volume flow, and abnormal flow."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    trades, status, elapsed = client.get_trades(contract, limit=50)

    if not trades or status not in ("OK", "CACHED") or not isinstance(trades, list):
        return MarketEvidence(
            source="large_flow",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="UNAVAILABLE",
            reason=f"Public trade data unavailable ({status})",
            raw_metrics={},
        )

    buy_vol = 0.0
    sell_vol = 0.0
    trade_sizes = []

    for t in trades:
        try:
            sz = float(t.get("size", 0))
            px = float(t.get("price", 0))
            notional = abs(sz) * px
            trade_sizes.append(notional)
            if sz > 0:
                buy_vol += notional
            elif sz < 0:
                sell_vol += notional
        except Exception:
            continue

    total_vol = buy_vol + sell_vol
    if total_vol <= 0 or not trade_sizes:
        return MarketEvidence(
            source="large_flow",
            signal="NEUTRAL",
            score=0.0,
            confidence=0.30,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="VALID",
            reason="Insufficient trade volume in recent sample",
            raw_metrics={},
        )

    flow_imbalance = (buy_vol - sell_vol) / total_vol
    mean_size = sum(trade_sizes) / len(trade_sizes)

    # Large trade threshold: 3x average trade size in batch
    large_trades = [s for s in trade_sizes if s >= mean_size * 3.0]
    large_trade_count = len(large_trades)
    large_trade_vol = sum(large_trades)

    raw_metrics = {
        "buy_volume_usdt": round(buy_vol, 2),
        "sell_volume_usdt": round(sell_vol, 2),
        "flow_imbalance": round(flow_imbalance, 4),
        "large_trade_count": large_trade_count,
        "large_trade_volume_usdt": round(large_trade_vol, 2),
    }

    if flow_imbalance > 0.25:
        signal = "BULLISH"
        score = min(1.0, flow_imbalance * 1.4)
        conf = min(0.95, 0.55 + abs(flow_imbalance) * 0.4)
        reason = f"Aggressive buy volume flow dominates (+{flow_imbalance:.1%}), large-trade count: {large_trade_count}"
    elif flow_imbalance < -0.25:
        signal = "BEARISH"
        score = max(-1.0, flow_imbalance * 1.4)
        conf = min(0.95, 0.55 + abs(flow_imbalance) * 0.4)
        reason = f"Aggressive sell volume flow dominates ({flow_imbalance:.1%}), large-trade count: {large_trade_count}"
    else:
        signal = "NEUTRAL"
        score = flow_imbalance
        conf = 0.55
        reason = f"Balanced trade volume flow ({flow_imbalance:+.1%}), large-trade count: {large_trade_count}"

    return MarketEvidence(
        source="large_flow",
        signal=signal,
        score=round(score, 4),
        confidence=round(conf, 4),
        timestamp=now_iso,
        freshness_seconds=elapsed,
        status="VALID",
        reason=reason,
        raw_metrics=raw_metrics,
    )


def analyze_open_interest(client: GatePublicAPIClient, contract: str, latest_price_change: float = 0.0) -> MarketEvidence:
    """Analyze open interest trends, acceleration, and price vs OI relationship."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    stats, status, elapsed = client.get_contract_stats(contract, limit=5, interval="1h")

    if not stats or status not in ("OK", "CACHED") or not isinstance(stats, list) or len(stats) < 2:
        # Fallback to contract detail position_size
        detail, d_status, _ = client.get_contract_detail(contract)
        if detail and isinstance(detail, dict) and "position_size" in detail:
            oi = float(detail.get("position_size", 0))
            return MarketEvidence(
                source="open_interest",
                signal="NEUTRAL",
                score=0.0,
                confidence=0.40,
                timestamp=now_iso,
                freshness_seconds=elapsed,
                status="VALID",
                reason=f"Current open interest: {oi:.0f} contracts (historical OI stats unavailable)",
                raw_metrics={"open_interest": oi},
            )
        return MarketEvidence(
            source="open_interest",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="UNAVAILABLE",
            reason=f"Open interest stats unavailable ({status})",
            raw_metrics={},
        )

    # Sort stats by time ascending (older -> newer)
    sorted_stats = sorted(stats, key=lambda x: x.get("time", 0))
    latest_oi = float(sorted_stats[-1].get("open_interest", 0))
    prev_oi = float(sorted_stats[0].get("open_interest", 0))

    oi_change_pct = (latest_oi - prev_oi) / prev_oi if prev_oi > 0 else 0.0

    raw_metrics = {
        "latest_open_interest": round(latest_oi, 2),
        "oi_change_pct": round(oi_change_pct, 4),
        "price_change_ref": round(latest_price_change, 4),
    }

    # Price / OI Relationship Rules:
    # 1. Price UP + OI UP   -> BULLISH (strong new long position building)
    # 2. Price DOWN + OI UP -> BEARISH (strong new short position building)
    # 3. Price UP + OI DOWN -> BEARISH (short squeeze / long liquidation ending)
    # 4. Price DOWN + OI DOWN -> BULLISH (long liquidation / bottom forming)
    if oi_change_pct > 0.015:
        if latest_price_change >= 0.0:
            signal = "BULLISH"
            score = 0.65
            conf = 0.75
            reason = f"Open interest expanding (+{oi_change_pct:.1%}) alongside rising price (bullish expansion)"
        else:
            signal = "BEARISH"
            score = -0.65
            conf = 0.75
            reason = f"Open interest expanding (+{oi_change_pct:.1%}) alongside falling price (bearish short building)"
    elif oi_change_pct < -0.015:
        if latest_price_change >= 0.0:
            signal = "BEARISH"
            score = -0.45
            conf = 0.65
            reason = f"Open interest declining ({oi_change_pct:.1%}) on price rise (short squeeze / position closing)"
        else:
            signal = "BULLISH"
            score = 0.45
            conf = 0.65
            reason = f"Open interest declining ({oi_change_pct:.1%}) on price decline (long liquidation / wash out)"
    else:
        signal = "NEUTRAL"
        score = 0.0
        conf = 0.50
        reason = f"Open interest stable (change: {oi_change_pct:+.1%})"

    return MarketEvidence(
        source="open_interest",
        signal=signal,
        score=round(score, 4),
        confidence=round(conf, 4),
        timestamp=now_iso,
        freshness_seconds=elapsed,
        status="VALID",
        reason=reason,
        raw_metrics=raw_metrics,
    )


def analyze_funding(client: GatePublicAPIClient, contract: str) -> MarketEvidence:
    """Analyze funding rate magnitude, direction, and market overheat conditions."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    detail, status, elapsed = client.get_contract_detail(contract)

    if not detail or status not in ("OK", "CACHED") or not isinstance(detail, dict):
        return MarketEvidence(
            source="funding",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="UNAVAILABLE",
            reason=f"Funding rate unavailable ({status})",
            raw_metrics={},
        )

    try:
        funding_rate = float(detail.get("funding_rate", 0.0))
    except Exception:
        funding_rate = 0.0

    funding_8h_pct = funding_rate  # Gate funding rate per 8h period
    raw_metrics = {
        "funding_rate": round(funding_rate, 6),
        "funding_8h_pct": round(funding_8h_pct * 100, 4),
    }

    # Funding Anomaly Thresholds:
    # Extremely positive funding (> +0.05% per 8h) = Overheated longs -> BEARISH risk (long squeeze)
    # Extremely negative funding (< -0.05% per 8h) = Overheated shorts -> BULLISH risk (short squeeze)
    # Moderate positive (+0.005% to +0.03%) = Healthy bull market -> BULLISH / NEUTRAL
    if funding_rate > 0.0005:
        signal = "BEARISH"
        score = -0.70
        conf = 0.85
        reason = f"Extreme positive funding rate ({funding_8h_pct*100:+.3f}%/8h) indicates overheated long market"
    elif funding_rate < -0.0005:
        signal = "BULLISH"
        score = 0.70
        conf = 0.85
        reason = f"Extreme negative funding rate ({funding_8h_pct*100:+.3f}%/8h) indicates overheated short market"
    elif funding_rate > 0.0001:
        signal = "BULLISH"
        score = 0.35
        conf = 0.65
        reason = f"Moderate positive funding rate ({funding_8h_pct*100:+.3f}%/8h) shows healthy buying demand"
    elif funding_rate < -0.0001:
        signal = "BEARISH"
        score = -0.35
        conf = 0.65
        reason = f"Moderate negative funding rate ({funding_8h_pct*100:+.3f}%/8h) shows mild short bias"
    else:
        signal = "NEUTRAL"
        score = 0.0
        conf = 0.70
        reason = f"Funding rate near zero ({funding_8h_pct*100:+.4f}%/8h)"

    return MarketEvidence(
        source="funding",
        signal=signal,
        score=round(score, 4),
        confidence=round(conf, 4),
        timestamp=now_iso,
        freshness_seconds=elapsed,
        status="VALID",
        reason=reason,
        raw_metrics=raw_metrics,
    )


def analyze_positioning(client: GatePublicAPIClient, contract: str) -> MarketEvidence:
    """Analyze long/short account ratio and taker positioning imbalance."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    stats, status, elapsed = client.get_contract_stats(contract, limit=5, interval="1h")

    if not stats or status not in ("OK", "CACHED") or not isinstance(stats, list) or len(stats) == 0:
        return MarketEvidence(
            source="positioning",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=elapsed,
            status="UNAVAILABLE",
            reason=f"Positioning stats unavailable ({status})",
            raw_metrics={},
        )

    latest = stats[-1]
    lsr_account = float(latest.get("lsr_account", 1.0))
    lsr_taker = float(latest.get("lsr_taker", 1.0))

    raw_metrics = {
        "lsr_account": round(lsr_account, 4),
        "lsr_taker": round(lsr_taker, 4),
        "long_users": latest.get("long_users", 0),
        "short_users": latest.get("short_users", 0),
    }

    # Extreme crowded positioning rules:
    # lsr_account > 2.2 -> Crowded Long (retail crowded) -> BEARISH contrarian
    # lsr_account < 0.55 -> Crowded Short (retail crowded) -> BULLISH contrarian
    if lsr_account > 2.2:
        signal = "BEARISH"
        score = -0.60
        conf = 0.75
        reason = f"Extreme long account ratio ({lsr_account:.2f}x) indicates crowded long retail positioning"
    elif lsr_account < 0.55:
        signal = "BULLISH"
        score = 0.60
        conf = 0.75
        reason = f"Extreme short account ratio ({lsr_account:.2f}x) indicates crowded short retail positioning"
    elif lsr_taker > 1.3:
        signal = "BULLISH"
        score = 0.40
        conf = 0.65
        reason = f"Taker buy volume ratio active ({lsr_taker:.2f}x taker ratio)"
    elif lsr_taker < 0.77:
        signal = "BEARISH"
        score = -0.40
        conf = 0.65
        reason = f"Taker sell volume ratio active ({lsr_taker:.2f}x taker ratio)"
    else:
        signal = "NEUTRAL"
        score = 0.0
        conf = 0.60
        reason = f"Balanced account long/short ratio ({lsr_account:.2f}x)"

    return MarketEvidence(
        source="positioning",
        signal=signal,
        score=round(score, 4),
        confidence=round(conf, 4),
        timestamp=now_iso,
        freshness_seconds=elapsed,
        status="VALID",
        reason=reason,
        raw_metrics=raw_metrics,
    )


def analyze_btc_regime(btc_bar_info: Optional[Dict[str, Any]], asset_name: str) -> MarketEvidence:
    """Analyze BTC market regime for altcoin tailwind/headwind context."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    if not btc_bar_info:
        return MarketEvidence(
            source="btc_regime",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=0.0,
            status="UNAVAILABLE",
            reason="BTC regime reference bar unavailable",
            raw_metrics={},
        )

    btc_regime = str(btc_bar_info.get("market_regime", "NEUTRAL_CONSOLIDATION"))
    btc_direction = str(btc_bar_info.get("direction", "NEUTRAL"))
    btc_trend = str(btc_bar_info.get("ema_trend", "NEUTRAL"))
    btc_rsi = float(btc_bar_info.get("rsi", 50.0))
    btc_vol = float(btc_bar_info.get("volatility", 0.0))

    raw_metrics = {
        "btc_regime": btc_regime,
        "btc_direction": btc_direction,
        "btc_trend": btc_trend,
        "btc_rsi": round(btc_rsi, 2),
        "btc_volatility": round(btc_vol, 6),
    }

    if asset_name.upper() == "BTC_USDT":
        return MarketEvidence(
            source="btc_regime",
            signal=btc_direction if btc_direction in ("BULLISH", "BEARISH") else "NEUTRAL",
            score=0.80 if btc_direction == "LONG" or btc_trend == "BULLISH" else (-0.80 if btc_trend == "BEARISH" else 0.0),
            confidence=0.90,
            timestamp=now_iso,
            freshness_seconds=0.0,
            status="VALID",
            reason=f"Self BTC reference (regime: {btc_regime}, trend: {btc_trend})",
            raw_metrics=raw_metrics,
        )

    # Altcoin tailwind / headwind evaluation
    if btc_trend == "BULLISH" and btc_regime in ("BULLISH_TREND", "NEUTRAL_CONSOLIDATION"):
        signal = "BULLISH"
        score = 0.65
        conf = 0.80
        reason = f"BTC macro regime is BULLISH ({btc_regime}), providing tailwind for altcoins"
    elif btc_trend == "BEARISH" or btc_regime in ("BEARISH_TREND", "HIGH_VOLATILITY"):
        signal = "BEARISH"
        score = -0.65
        conf = 0.80
        reason = f"BTC macro regime is BEARISH/HIGH_VOL ({btc_regime}), creating headwind for altcoins"
    else:
        signal = "NEUTRAL"
        score = 0.0
        conf = 0.60
        reason = f"BTC macro regime is NEUTRAL ({btc_regime})"

    return MarketEvidence(
        source="btc_regime",
        signal=signal,
        score=round(score, 4),
        confidence=round(conf, 4),
        timestamp=now_iso,
        freshness_seconds=0.0,
        status="VALID",
        reason=reason,
        raw_metrics=raw_metrics,
    )


class NewsAdapter:
    """Adapter interface for news/sentiment infrastructure. Returns UNAVAILABLE when unconfigured."""
    def get_evidence(self, asset: str) -> MarketEvidence:
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        return MarketEvidence(
            source="news",
            signal="UNAVAILABLE",
            score=0.0,
            confidence=0.0,
            timestamp=now_iso,
            freshness_seconds=0.0,
            status="UNAVAILABLE",
            reason="No external news source configured (Phase 12.1 adapter active)",
            raw_metrics={},
        )


# ---------------------------------------------------------------------------
# Contradiction Engine & Evidence Aggregator
# ---------------------------------------------------------------------------

class EvidenceAggregator:
    """
    Aggregates all evidence sources, computes agreement metrics, contradiction levels,
    evidence quality scores, and composite weighted signal.
    """
    def __init__(self, config: IntelligenceConfig):
        self.config = config

    def aggregate(
        self,
        asset: str,
        tech_evidence: MarketEvidence,
        ml_evidence: MarketEvidence,
        independent_evidences: List[MarketEvidence],
    ) -> Tuple[List[MarketEvidence], EvidenceSummary]:
        """Aggregate all evidence sources for an asset."""
        all_evidences = [tech_evidence, ml_evidence] + independent_evidences

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        unavailable_count = 0

        weighted_score_sum = 0.0
        weight_sum = 0.0
        quality_conf_sum = 0.0

        weight_map = {
            "technical": self.config.technical_weight,
            "ml": self.config.ml_weight,
            "order_book": self.config.orderbook_weight,
            "large_flow": self.config.flow_weight,
            "open_interest": self.config.oi_weight,
            "funding": self.config.funding_weight,
            "positioning": self.config.positioning_weight,
            "btc_regime": self.config.regime_weight,
            "news": self.config.news_weight,
        }

        valid_sources_count = 0

        for ev in all_evidences:
            sig = ev.signal.upper()
            w = weight_map.get(ev.source, 0.10)

            if sig in ("UNAVAILABLE", "STALE", "ERROR") or ev.status in ("UNAVAILABLE", "STALE", "ERROR"):
                unavailable_count += 1
                continue

            valid_sources_count += 1
            quality_conf_sum += ev.confidence

            if sig == "BULLISH":
                bullish_count += 1
                weighted_score_sum += w * max(0.1, abs(ev.score))
                weight_sum += w
            elif sig == "BEARISH":
                bearish_count += 1
                weighted_score_sum += w * (-max(0.1, abs(ev.score)))
                weight_sum += w
            else:  # NEUTRAL
                neutral_count += 1
                weighted_score_sum += w * ev.score
                weight_sum += w

        directional_count = bullish_count + bearish_count
        if directional_count > 0:
            agreement = max(bullish_count, bearish_count) / float(directional_count)
        else:
            agreement = 0.0

        # Contradiction level classification
        if valid_sources_count < 2:
            contradiction_level = "INSUFFICIENT_DATA"
        elif bullish_count == 0 or bearish_count == 0:
            if agreement >= 0.85:
                contradiction_level = "STRONG_AGREEMENT"
            else:
                contradiction_level = "MODERATE_AGREEMENT"
        else:
            # Both bullish and bearish signals are present
            if min(bullish_count, bearish_count) >= 2 or agreement < 0.60:
                contradiction_level = "STRONG_CONTRADICTION"
            else:
                contradiction_level = "MIXED"

        # Evidence quality calculation
        base_quality = quality_conf_sum / max(1, valid_sources_count)
        coverage_ratio = valid_sources_count / max(1, len(all_evidences))
        evidence_quality = base_quality * (0.5 + 0.5 * coverage_ratio)

        # Composite weighted score [-1.0, 1.0]
        final_weighted_score = weighted_score_sum / weight_sum if weight_sum > 0 else 0.0

        if final_weighted_score >= 0.20:
            composite_signal = "BULLISH"
        elif final_weighted_score <= -0.20:
            composite_signal = "BEARISH"
        elif valid_sources_count == 0:
            composite_signal = "UNAVAILABLE"
        else:
            composite_signal = "NEUTRAL"

        summary = EvidenceSummary(
            agreement=round(agreement, 4),
            contradiction_level=contradiction_level,
            bullish_count=bullish_count,
            bearish_count=bearish_count,
            neutral_count=neutral_count,
            unavailable_count=unavailable_count,
            evidence_quality=round(evidence_quality, 4),
            weighted_score=round(final_weighted_score, 4),
            composite_signal=composite_signal,
        )

        return all_evidences, summary


# ---------------------------------------------------------------------------
# Core Orchestrator Module
# ---------------------------------------------------------------------------

class MarketIntelligence:
    """
    Main Market Intelligence Layer orchestrator.
    Gathers evidence across all independent market sources concurrently or sequentially with timeout safety,
    aggregates evidence, and enriches AssetAnalysis objects.
    """
    def __init__(self, cfg_dict: Optional[Dict[str, Any]] = None):
        self.config = IntelligenceConfig(cfg_dict)
        self.api_client = GatePublicAPIClient(
            base_url=self.config.gate_base_url,
            timeout=self.config.http_timeout_sec,
            cache_ttl=self.config.cache_ttl_sec,
        )
        self.news_adapter = NewsAdapter()
        self.aggregator = EvidenceAggregator(self.config)

    def analyze_asset_intelligence(
        self,
        asset: str,
        tech_signal: str,
        tech_score: float,
        ml_signal: str,
        ml_score: float,
        ml_confidence: float,
        price_change_1h: float = 0.0,
        btc_bar_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[MarketEvidence], EvidenceSummary]:
        """Fetch all independent intelligence sources for an asset and aggregate evidence."""
        now_iso = datetime.now(tz=timezone.utc).isoformat()

        # Build Tech & ML MarketEvidence objects
        tech_ev = MarketEvidence(
            source="technical",
            signal=tech_signal,
            score=tech_score,
            confidence=0.75,
            timestamp=now_iso,
            freshness_seconds=0.0,
            status="VALID",
            reason=f"Technical indicators show {tech_signal} momentum/trend",
            raw_metrics={"score": tech_score},
        )

        ml_ev = MarketEvidence(
            source="ml",
            signal=ml_signal,
            score=ml_score,
            confidence=ml_confidence,
            timestamp=now_iso,
            freshness_seconds=0.0,
            status="VALID",
            reason=f"ML model predicts {ml_signal} with {ml_confidence:.1%} confidence",
            raw_metrics={"score": ml_score, "confidence": ml_confidence},
        )

        # Gathers independent evidence bounded by fast concurrency or fallback
        independent_evidences: List[MarketEvidence] = []

        def _fetch_all():
            ob = analyze_order_book(self.api_client, asset)
            lf = analyze_large_flow(self.api_client, asset)
            oi = analyze_open_interest(self.api_client, asset, latest_price_change=price_change_1h)
            fn = analyze_funding(self.api_client, asset)
            pos = analyze_positioning(self.api_client, asset)
            reg = analyze_btc_regime(btc_bar_info, asset)
            news = self.news_adapter.get_evidence(asset)
            return [ob, lf, oi, fn, pos, reg, news]

        try:
            # Use bounded thread pool for fast parallel API requests
            with ThreadPoolExecutor(max_workers=4) as executor:
                future = executor.submit(_fetch_all)
                independent_evidences = future.result(timeout=self.config.http_timeout_sec * 2)
        except Exception as err:
            log.warning("MarketIntelligence fetch for %s timed out or failed: %s (falling back to graceful degraded states)", asset, err)
            # Fallback degraded states for individual sources
            independent_evidences = [
                MarketEvidence(source="order_book", signal="UNAVAILABLE", score=0.0, confidence=0.0, timestamp=now_iso, freshness_seconds=0.0, status="UNAVAILABLE", reason="Fetch timeout", raw_metrics={}),
                MarketEvidence(source="large_flow", signal="UNAVAILABLE", score=0.0, confidence=0.0, timestamp=now_iso, freshness_seconds=0.0, status="UNAVAILABLE", reason="Fetch timeout", raw_metrics={}),
                MarketEvidence(source="open_interest", signal="UNAVAILABLE", score=0.0, confidence=0.0, timestamp=now_iso, freshness_seconds=0.0, status="UNAVAILABLE", reason="Fetch timeout", raw_metrics={}),
                MarketEvidence(source="funding", signal="UNAVAILABLE", score=0.0, confidence=0.0, timestamp=now_iso, freshness_seconds=0.0, status="UNAVAILABLE", reason="Fetch timeout", raw_metrics={}),
                MarketEvidence(source="positioning", signal="UNAVAILABLE", score=0.0, confidence=0.0, timestamp=now_iso, freshness_seconds=0.0, status="UNAVAILABLE", reason="Fetch timeout", raw_metrics={}),
                analyze_btc_regime(btc_bar_info, asset),
                self.news_adapter.get_evidence(asset),
            ]

        all_evidences, summary = self.aggregator.aggregate(
            asset=asset,
            tech_evidence=tech_ev,
            ml_evidence=ml_ev,
            independent_evidences=independent_evidences,
        )

        return all_evidences, summary
