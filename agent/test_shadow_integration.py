"""
agent/test_shadow_integration.py — Phase 12.3C Shadow Observation Integration Unit Tests

Verifies:
1. ShadowObservation hook creates ShadowTrade for approved TRADE_CANDIDATE proposals
2. Ineligible decisions (WATCH, NO_TRADE, REJECTED) are safely skipped
3. Idempotency guard prevents duplicate records for same decision_id
4. Price updates and excursion tracking (MFE/MAE) work as expected
5. Strict execution isolation (zero exchange execution / order placement calls)
"""

import pytest
import os
import tempfile
import uuid
from typing import List

from agent.schema import (
    DecisionProposal,
    RiskSupervisorReview,
    FusionResult,
    AssetAnalysis,
    ShadowTrade,
)
from agent.shadow_trading import ShadowTradingEngine
from agent.storage import SQLiteAgentStorage, make_storage
from agent.market_scanner import MarketScanner


@pytest.fixture
def temp_storage():
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    storage = SQLiteAgentStorage(db_path)
    storage.init_schema()
    yield storage
    try:
        os.remove(db_path)
    except Exception:
        pass


def make_sample_proposal_and_review(
    asset: str = "BTC_USDT",
    decision: str = "TRADE_CANDIDATE",
    status: str = "APPROVED_FOR_RISK_REVIEW",
    direction: str = "LONG",
    decision_id: str = None,
):
    if not decision_id:
        decision_id = str(uuid.uuid4())

    fusion = FusionResult(
        composite_direction=direction,
        confidence=0.75,
        agreement_score=0.80,
        contradiction_level="MODERATE_AGREEMENT",
        evidence_quality=0.85,
        confidence_band="HIGH",
    )

    prop = DecisionProposal(
        decision_id=decision_id,
        timestamp="2026-10-05T20:00:00Z",
        asset=asset,
        direction=direction,
        decision=decision,
        confidence=0.75,
        fusion_result=fusion,
    )

    review = RiskSupervisorReview(
        proposal_id=decision_id,
        asset=asset,
        status=status,
        rejection_reasons=[],
        risk_score=0.20,
        timestamp="2026-10-05T20:00:01Z",
        reviewed_decision=decision,
    )

    return prop, review


def test_shadow_record_decision_approved_candidate(temp_storage):
    engine = ShadowTradingEngine(storage=temp_storage)
    prop, review = make_sample_proposal_and_review()

    trade = engine.record_decision(prop, review, reference_price=65000.0)

    assert trade is not None
    assert isinstance(trade, ShadowTrade)
    assert trade.asset == "BTC_USDT"
    assert trade.direction == "LONG"
    assert trade.entry_reference_price == 65000.0
    assert trade.execution_mode == "SHADOW"
    assert trade.outcome == "OPEN"

    # Check persistence in DB
    db_trades = temp_storage.get_recent_shadow_trades(limit=10)
    assert len(db_trades) == 1
    assert db_trades[0]["decision_id"] == prop.decision_id


def test_shadow_record_decision_skips_ineligible(temp_storage):
    engine = ShadowTradingEngine(storage=temp_storage)

    # 1. WATCH status
    prop1, review1 = make_sample_proposal_and_review(decision="WATCH", status="WATCH")
    t1 = engine.record_decision(prop1, review1, reference_price=65000.0)
    assert t1 is None

    # 2. REJECTED status
    prop2, review2 = make_sample_proposal_and_review(decision="TRADE_CANDIDATE", status="REJECTED")
    t2 = engine.record_decision(prop2, review2, reference_price=65000.0)
    assert t2 is None

    # 3. Invalid reference price
    prop3, review3 = make_sample_proposal_and_review()
    t3 = engine.record_decision(prop3, review3, reference_price=0.0)
    assert t3 is None

    # Verify zero trades created in storage
    db_trades = temp_storage.get_recent_shadow_trades(limit=10)
    assert len(db_trades) == 0


def test_shadow_idempotency_duplicate_guard(temp_storage):
    engine = ShadowTradingEngine(storage=temp_storage)
    prop, review = make_sample_proposal_and_review()

    # First record: success
    t1 = engine.record_decision(prop, review, reference_price=65000.0)
    assert t1 is not None

    # Second record with same decision_id: skipped due to duplicate decision_id
    t2 = engine.record_decision(prop, review, reference_price=65000.0)
    assert t2 is None

    # DB should still contain exactly 1 trade
    db_trades = temp_storage.get_recent_shadow_trades(limit=10)
    assert len(db_trades) == 1


def test_shadow_update_prices_excursions(temp_storage):
    engine = ShadowTradingEngine(storage=temp_storage)
    prop, review = make_sample_proposal_and_review(direction="LONG")
    trade = engine.record_decision(prop, review, reference_price=100.0)

    # Price moves up to 101 (+1%)
    updated = engine.update_prices({"BTC_USDT": 101.0})
    assert len(updated) == 1
    assert updated[0].unrealized_return == 0.01
    assert updated[0].max_favorable_excursion == 0.01
    assert updated[0].max_adverse_excursion == 0.0

    # Price drops to 99 (-1%)
    updated2 = engine.update_prices({"BTC_USDT": 99.0})
    assert len(updated2) == 1
    assert updated2[0].unrealized_return == -0.01
    assert updated2[0].max_favorable_excursion == 0.01
    assert updated2[0].max_adverse_excursion == -0.01

    # Price jumps to 104 (+4% - hits +3% TP threshold)
    updated3 = engine.update_prices({"BTC_USDT": 104.0})
    # Trade should auto-close with outcome WIN
    db_trades = temp_storage.get_recent_shadow_trades(limit=10)
    assert db_trades[0]["outcome"] == "WIN"
    assert db_trades[0]["final_return"] == 0.04


def test_market_scanner_evaluate_decisions_integration(temp_storage):
    scanner = MarketScanner(storage=temp_storage)
    scanned_results = [
        AssetAnalysis(
            asset="BTC_USDT",
            direction="LONG",
            probability=0.75,
            confidence=0.80,
            prediction=0.02,
            threshold=0.005,
            market_regime="BULLISH_TREND",
            volatility=0.015,
            momentum=0.01,
            atr=500.0,
            rsi=55.0,
            ema_trend="BULLISH",
            rank=1,
            close_price=65000.0,
        )
    ]

    proposals, reviews = scanner.evaluate_decisions(scanned_results)
    assert len(proposals) > 0
    assert len(reviews) > 0

    # Check shadow engine records stored in DB
    db_trades = temp_storage.get_recent_shadow_trades(limit=10)
    # If the proposal was approved as a TRADE_CANDIDATE, it should be in DB
    if any(p.decision == "TRADE_CANDIDATE" for p in proposals) and any(r.status == "APPROVED_FOR_RISK_REVIEW" for r in reviews):
        assert len(db_trades) >= 1
        assert db_trades[0]["execution_mode"] == "SHADOW"


def test_execution_isolation_audit(temp_storage):
    engine = ShadowTradingEngine(storage=temp_storage)
    assert engine.execution_mode == "SHADOW"
    assert not hasattr(engine, "place_order")
    assert not hasattr(engine, "open_position")
    assert not hasattr(engine, "close_position")
    assert not hasattr(engine, "submit_order")
