"""Tests for `_capture_late_bet_lead` gating (Strategy 1c → discovery bridge)."""

from __future__ import annotations

import time
import types

import pytest

from src.copy_trading import geo_market_scanner, late_bet_queue, pattern_detector
from src.models import DetectedTrade


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LATE_BET_QUEUE_STORE", str(tmp_path / "late_bet_queue.json"))
    late_bet_queue.clear_cache()
    # geo market resolving 5h from now (inside the 24h close-proximity window)
    monkeypatch.setattr(pattern_detector, "is_geopolitical_market",
                        lambda *a, **k: True)
    monkeypatch.setattr(geo_market_scanner, "get_geo_market",
                        lambda cid: types.SimpleNamespace(end_ts=time.time() + 5 * 3600))
    yield
    late_bet_queue.clear_cache()


def _trade(side="BUY", price=0.40, size=15000.0, token_id="tok1", cid="cid1"):
    return DetectedTrade(
        id=f"tx-{token_id}-{side}",
        trader_address="0xLEAD",
        timestamp="2026-06-29T00:00:00Z",
        market="Will X withdraw by June 30?",
        condition_id=cid,
        token_id=token_id,
        side=side,
        size=size,
        price=price,
        outcome="Yes",
    )


def test_copyable_late_buy_is_queued(store):
    assert pattern_detector._capture_late_bet_lead(_trade()) is True
    pend = late_bet_queue.pending()
    assert len(pend) == 1
    assert pend[0]["wallet"] == "0xLEAD"


def test_sell_is_not_queued(store):
    assert pattern_detector._capture_late_bet_lead(_trade(side="SELL")) is False
    assert late_bet_queue.pending() == []


def test_price_at_or_above_near_cert_not_queued(store):
    # 0.998 (the original SELL-No insider example, as a BUY) is above 0.95
    assert pattern_detector._capture_late_bet_lead(_trade(price=0.998)) is False
    assert pattern_detector._capture_late_bet_lead(_trade(price=0.95)) is False
    assert late_bet_queue.pending() == []


def test_small_bet_not_queued(store):
    assert pattern_detector._capture_late_bet_lead(_trade(size=500.0)) is False
    assert late_bet_queue.pending() == []


def test_missing_token_id_not_queued(store):
    assert pattern_detector._capture_late_bet_lead(_trade(token_id="")) is False
    assert late_bet_queue.pending() == []


def test_non_geo_market_not_queued(store, monkeypatch):
    monkeypatch.setattr(pattern_detector, "is_geopolitical_market",
                        lambda *a, **k: False)
    assert pattern_detector._capture_late_bet_lead(_trade()) is False
    assert late_bet_queue.pending() == []


def test_outside_proximity_window_not_queued(store, monkeypatch):
    # resolution 100h out — beyond the 24h close-proximity window
    monkeypatch.setattr(geo_market_scanner, "get_geo_market",
                        lambda cid: types.SimpleNamespace(end_ts=time.time() + 100 * 3600))
    assert pattern_detector._capture_late_bet_lead(_trade()) is False
    assert late_bet_queue.pending() == []


def test_already_resolved_market_not_queued(store, monkeypatch):
    # end_ts in the past → hours_to_close <= 0
    monkeypatch.setattr(geo_market_scanner, "get_geo_market",
                        lambda cid: types.SimpleNamespace(end_ts=time.time() - 3600))
    assert pattern_detector._capture_late_bet_lead(_trade()) is False
    assert late_bet_queue.pending() == []


def test_disabled_flag_skips_capture(store, monkeypatch):
    monkeypatch.setattr(pattern_detector.TIER_1C, "late_lead_enabled", False)
    assert pattern_detector._capture_late_bet_lead(_trade()) is False
    assert late_bet_queue.pending() == []
