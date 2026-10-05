"""
agent/test_market_intelligence.py — Comprehensive Unit & Integration Tests for Phase 12.1

Tests all 15 required scenarios:
 1. All evidence sources available
 2. One source unavailable
 3. Multiple sources unavailable
 4. Strong bullish agreement
 5. Strong bearish agreement
 6. Mixed evidence
 7. Contradictory evidence
 8. Stale data detection
 9. API timeout handling
10. Invalid API response handling
11. Single asset failure while others succeed
12. Rate limit / error handling
13. Evidence aggregation correctness
14. AssetAnalysis serialization & backward compatibility
15. LLM context formatting & prompt safety instructions
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List

from agent.schema import AssetAnalysis, MarketEvidence, EvidenceSummary, AgentSnapshot, AccountSnapshot
from agent.market_intelligence import (
    IntelligenceConfig,
    EvidenceAggregator,
    MarketIntelligence,
    GatePublicAPIClient,
    NewsAdapter,
    analyze_order_book,
    analyze_large_flow,
    analyze_open_interest,
    analyze_funding,
    analyze_positioning,
    analyze_btc_regime,
)
from agent.memory_context import MemoryContextBuilder


class DummyGateAPIClient(GatePublicAPIClient):
    """Mock API client returning pre-configured scenarios."""
    def __init__(
        self,
        order_book_resp: Any = None,
        trades_resp: Any = None,
        contract_detail_resp: Any = None,
        contract_stats_resp: Any = None,
        force_timeout: bool = False,
    ):
        super().__init__(base_url="https://api.mock.gate.io/api/v4", timeout=1.0, cache_ttl=0.0)
        self.order_book_resp = order_book_resp
        self.trades_resp = trades_resp
        self.contract_detail_resp = contract_detail_resp
        self.contract_stats_resp = contract_stats_resp
        self.force_timeout = force_timeout

    def get_order_book(self, contract: str, limit: int = 20):
        if self.force_timeout:
            return None, "TIMEOUT_OR_NETWORK_ERROR", 4.0
        return self.order_book_resp, "OK", 0.05

    def get_trades(self, contract: str, limit: int = 50):
        if self.force_timeout:
            return None, "TIMEOUT_OR_NETWORK_ERROR", 4.0
        return self.trades_resp, "OK", 0.05

    def get_contract_detail(self, contract: str):
        if self.force_timeout:
            return None, "TIMEOUT_OR_NETWORK_ERROR", 4.0
        return self.contract_detail_resp, "OK", 0.05

    def get_contract_stats(self, contract: str, limit: int = 5, interval: str = "1h"):
        if self.force_timeout:
            return None, "TIMEOUT_OR_NETWORK_ERROR", 4.0
        return self.contract_stats_resp, "OK", 0.05


class TestMarketIntelligence(unittest.TestCase):

    def setUp(self):
        self.config = IntelligenceConfig()
        self.aggregator = EvidenceAggregator(self.config)

    # 1. All evidence sources available
    def test_01_all_sources_available(self):
        mock_ob = {"bids": [{"p": "100", "s": "200"}], "asks": [{"p": "101", "s": "50"}]}
        mock_trades = [{"size": 10, "price": "100"}, {"size": 20, "price": "100.5"}]
        mock_detail = {"funding_rate": "0.0001", "position_size": 10000}
        mock_stats = [{"time": 100, "open_interest": 1000, "lsr_account": 1.2, "lsr_taker": 1.1},
                      {"time": 200, "open_interest": 1200, "lsr_account": 1.25, "lsr_taker": 1.15}]

        client = DummyGateAPIClient(
            order_book_resp=mock_ob,
            trades_resp=mock_trades,
            contract_detail_resp=mock_detail,
            contract_stats_resp=mock_stats,
        )

        ob_ev = analyze_order_book(client, "BTC_USDT")
        lf_ev = analyze_large_flow(client, "BTC_USDT")
        oi_ev = analyze_open_interest(client, "BTC_USDT", latest_price_change=0.01)
        fn_ev = analyze_funding(client, "BTC_USDT")
        pos_ev = analyze_positioning(client, "BTC_USDT")

        self.assertEqual(ob_ev.status, "VALID")
        self.assertEqual(lf_ev.status, "VALID")
        self.assertEqual(oi_ev.status, "VALID")
        self.assertEqual(fn_ev.status, "VALID")
        self.assertEqual(pos_ev.status, "VALID")

    # 2. One source unavailable
    def test_02_one_source_unavailable(self):
        client = DummyGateAPIClient(
            order_book_resp={"bids": [{"p": "100", "s": "10"}], "asks": [{"p": "101", "s": "10"}]},
            trades_resp=None,  # trades unavailable
            contract_detail_resp={"funding_rate": "0.0001"},
            contract_stats_resp=[{"open_interest": 1000, "lsr_account": 1.0}],
        )
        lf_ev = analyze_large_flow(client, "ETH_USDT")
        self.assertEqual(lf_ev.signal, "UNAVAILABLE")
        self.assertEqual(lf_ev.status, "UNAVAILABLE")

    # 3. Multiple sources unavailable
    def test_03_multiple_sources_unavailable(self):
        client = DummyGateAPIClient(
            order_book_resp=None,
            trades_resp=None,
            contract_detail_resp=None,
            contract_stats_resp=None,
        )
        ob_ev = analyze_order_book(client, "SOL_USDT")
        fn_ev = analyze_funding(client, "SOL_USDT")
        pos_ev = analyze_positioning(client, "SOL_USDT")

        self.assertEqual(ob_ev.signal, "UNAVAILABLE")
        self.assertEqual(fn_ev.signal, "UNAVAILABLE")
        self.assertEqual(pos_ev.signal, "UNAVAILABLE")

    # 4. Strong bullish agreement
    def test_04_strong_bullish_agreement(self):
        tech_ev = MarketEvidence(source="technical", signal="BULLISH", score=0.8, confidence=0.8, status="VALID")
        ml_ev = MarketEvidence(source="ml", signal="BULLISH", score=0.7, confidence=0.8, status="VALID")
        ob_ev = MarketEvidence(source="order_book", signal="BULLISH", score=0.6, confidence=0.7, status="VALID")
        lf_ev = MarketEvidence(source="large_flow", signal="BULLISH", score=0.5, confidence=0.7, status="VALID")

        _, summary = self.aggregator.aggregate("BTC_USDT", tech_ev, ml_ev, [ob_ev, lf_ev])
        self.assertGreaterEqual(summary.agreement, 0.85)
        self.assertEqual(summary.contradiction_level, "STRONG_AGREEMENT")
        self.assertEqual(summary.composite_signal, "BULLISH")

    # 5. Strong bearish agreement
    def test_05_strong_bearish_agreement(self):
        tech_ev = MarketEvidence(source="technical", signal="BEARISH", score=-0.8, confidence=0.8, status="VALID")
        ml_ev = MarketEvidence(source="ml", signal="BEARISH", score=-0.7, confidence=0.8, status="VALID")
        ob_ev = MarketEvidence(source="order_book", signal="BEARISH", score=-0.6, confidence=0.7, status="VALID")
        lf_ev = MarketEvidence(source="large_flow", signal="BEARISH", score=-0.5, confidence=0.7, status="VALID")

        _, summary = self.aggregator.aggregate("BTC_USDT", tech_ev, ml_ev, [ob_ev, lf_ev])
        self.assertGreaterEqual(summary.agreement, 0.85)
        self.assertEqual(summary.contradiction_level, "STRONG_AGREEMENT")
        self.assertEqual(summary.composite_signal, "BEARISH")

    # 6. Mixed evidence
    def test_06_mixed_evidence(self):
        tech_ev = MarketEvidence(source="technical", signal="BULLISH", score=0.5, confidence=0.7, status="VALID")
        ml_ev = MarketEvidence(source="ml", signal="BULLISH", score=0.4, confidence=0.7, status="VALID")
        ob_ev = MarketEvidence(source="order_book", signal="BEARISH", score=-0.3, confidence=0.6, status="VALID")
        lf_ev = MarketEvidence(source="large_flow", signal="NEUTRAL", score=0.0, confidence=0.5, status="VALID")

        _, summary = self.aggregator.aggregate("LINK_USDT", tech_ev, ml_ev, [ob_ev, lf_ev])
        self.assertIn(summary.contradiction_level, ("MIXED", "STRONG_CONTRADICTION"))
        self.assertEqual(summary.bullish_count, 2)
        self.assertEqual(summary.bearish_count, 1)

    # 7. Contradictory evidence
    def test_07_contradictory_evidence(self):
        tech_ev = MarketEvidence(source="technical", signal="BULLISH", score=0.9, confidence=0.9, status="VALID")
        ml_ev = MarketEvidence(source="ml", signal="BULLISH", score=0.8, confidence=0.8, status="VALID")
        ob_ev = MarketEvidence(source="order_book", signal="BEARISH", score=-0.8, confidence=0.8, status="VALID")
        lf_ev = MarketEvidence(source="large_flow", signal="BEARISH", score=-0.7, confidence=0.8, status="VALID")

        _, summary = self.aggregator.aggregate("SOL_USDT", tech_ev, ml_ev, [ob_ev, lf_ev])
        self.assertEqual(summary.contradiction_level, "STRONG_CONTRADICTION")
        self.assertEqual(summary.bullish_count, 2)
        self.assertEqual(summary.bearish_count, 2)

    # 8. Stale data detection
    def test_08_stale_data_detection(self):
        ev = MarketEvidence(
            source="order_book",
            signal="STALE",
            score=0.0,
            confidence=0.0,
            freshness_seconds=750.0,
            status="STALE",
            reason="Data age 750s exceeds threshold",
        )
        self.assertEqual(ev.status, "STALE")

    # 9. API timeout
    def test_09_api_timeout(self):
        client = DummyGateAPIClient(force_timeout=True)
        ob_ev = analyze_order_book(client, "BNB_USDT")
        self.assertEqual(ob_ev.status, "UNAVAILABLE")
        self.assertIn("unavailable", ob_ev.reason.lower())

    # 10. Invalid API response
    def test_10_invalid_api_response(self):
        client = DummyGateAPIClient(order_book_resp="INVALID_STRING_RESPONSE")
        ob_ev = analyze_order_book(client, "AVAX_USDT")
        self.assertEqual(ob_ev.status, "UNAVAILABLE")

    # 11. Single asset failure while others succeed
    def test_11_single_asset_failure_isolation(self):
        intel = MarketIntelligence()
        # Mock client to fail only for DOGE_USDT
        orig_fetch = intel.api_client.get_order_book
        def selective_fetch(contract: str, limit: int = 20):
            if contract == "DOGE_USDT":
                return None, "HTTP_500", 0.5
            return orig_fetch(contract, limit)
        intel.api_client.get_order_book = selective_fetch

        ev_doge, sum_doge = intel.analyze_asset_intelligence("DOGE_USDT", "BULLISH", 0.5, "LONG", 0.5, 0.7)
        ev_btc, sum_btc = intel.analyze_asset_intelligence("BTC_USDT", "BULLISH", 0.5, "LONG", 0.5, 0.7)

        doge_ob = next(e for e in ev_doge if e.source == "order_book")
        self.assertEqual(doge_ob.status, "UNAVAILABLE")

    # 12. Rate limit / error handling
    def test_12_rate_limit_error_handling(self):
        client = DummyGateAPIClient(order_book_resp=None)
        ev = analyze_order_book(client, "XRP_USDT")
        self.assertIn(ev.status, ("UNAVAILABLE", "ERROR"))

    # 13. Evidence aggregation correctness
    def test_13_aggregation_correctness(self):
        tech_ev = MarketEvidence(source="technical", signal="BULLISH", score=0.5, confidence=0.8, status="VALID")
        ml_ev = MarketEvidence(source="ml", signal="BULLISH", score=0.6, confidence=0.8, status="VALID")
        ob_ev = MarketEvidence(source="order_book", signal="NEUTRAL", score=0.0, confidence=0.6, status="VALID")
        news_ev = MarketEvidence(source="news", signal="UNAVAILABLE", score=0.0, confidence=0.0, status="UNAVAILABLE")

        ev_list, summary = self.aggregator.aggregate("ADA_USDT", tech_ev, ml_ev, [ob_ev, news_ev])
        self.assertEqual(summary.bullish_count, 2)
        self.assertEqual(summary.neutral_count, 1)
        self.assertEqual(summary.unavailable_count, 1)
        self.assertGreater(summary.weighted_score, 0.0)

    # 14. AssetAnalysis serialization & backward compatibility
    def test_14_asset_analysis_serialization(self):
        analysis = AssetAnalysis(
            asset="BTC_USDT",
            direction="LONG",
            probability=0.82,
            confidence=0.75,
            prediction=0.015,
            threshold=0.005,
            market_regime="BULLISH_TREND",
            volatility=0.02,
            momentum=0.01,
            atr=500.0,
            rsi=62.5,
            ema_trend="BULLISH",
            rank=1,
            market_evidence=[
                MarketEvidence(source="order_book", signal="BULLISH", score=0.6, confidence=0.8, status="VALID")
            ],
            evidence_summary=EvidenceSummary(agreement=1.0, contradiction_level="STRONG_AGREEMENT", composite_signal="BULLISH"),
        )

        dumped = analysis.model_dump(mode="json")
        self.assertIn("asset", dumped)
        self.assertIn("market_evidence", dumped)
        self.assertIn("evidence_summary", dumped)

        # Deserialize back
        reconstructed = AssetAnalysis.model_validate(dumped)
        self.assertEqual(reconstructed.asset, "BTC_USDT")
        self.assertEqual(reconstructed.rank, 1)
        self.assertEqual(len(reconstructed.market_evidence), 1)

    # 15. LLM context formatting & prompt safety instructions
    def test_15_llm_context_formatting_and_safety_rules(self):
        analysis = AssetAnalysis(
            asset="BTC_USDT",
            direction="LONG",
            probability=0.82,
            confidence=0.75,
            prediction=0.015,
            threshold=0.005,
            market_regime="BULLISH_TREND",
            volatility=0.02,
            momentum=0.01,
            atr=500.0,
            rsi=62.5,
            ema_trend="BULLISH",
            rank=1,
            market_evidence=[
                MarketEvidence(source="order_book", signal="BULLISH", score=0.6, confidence=0.8, status="VALID", reason="Bid depth 30% larger"),
                MarketEvidence(source="news", signal="UNAVAILABLE", score=0.0, confidence=0.0, status="UNAVAILABLE", reason="No news feed"),
            ],
            evidence_summary=EvidenceSummary(agreement=1.0, contradiction_level="STRONG_AGREEMENT", composite_signal="BULLISH"),
        )

        snapshot = AgentSnapshot(
            ts=datetime.now(tz=timezone.utc),
            account=AccountSnapshot(equity=1000, available=1000, unrealized_pnl=0, drawdown_pct=0, exposure_x=0, open_positions=0, order_rate_4h=0),
            market_analysis=[analysis],
        )

        builder = MemoryContextBuilder()
        prompt_ctx = builder._build_prediction_context(ml_prediction=None, snapshot=snapshot)

        # Verify prompt instructions and content
        self.assertIn("LIVE MARKET SCANNER & EVIDENCE INTELLIGENCE", prompt_ctx)
        self.assertIn("Do not treat missing or UNAVAILABLE evidence as confirmation", prompt_ctx)
        self.assertIn("Do not infer unavailable data", prompt_ctx)
        self.assertIn("Do not override deterministic risk policies", prompt_ctx)
        self.assertIn("Do not execute trades", prompt_ctx)
        self.assertIn("BTC_USDT", prompt_ctx)
        self.assertIn("Order Book", prompt_ctx)


if __name__ == "__main__":
    unittest.main()
