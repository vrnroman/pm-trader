"""Tests for the resolution-gated late-bet lead queue."""

from __future__ import annotations

import pytest

from src.copy_trading import late_bet_queue as q


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LATE_BET_QUEUE_STORE", str(tmp_path / "late_bet_queue.json"))
    q.clear_cache()
    yield
    q.clear_cache()


def _enqueue(wallet="0xAAA", cid="cid1", token="tok1", end_ts=1000.0, now=0.0,
             price=0.40, size=15000.0):
    return q.enqueue_lead(
        wallet=wallet, condition_id=cid, token_id=token, market="Geo market?",
        outcome="Yes", price=price, size=size, end_ts=end_ts, now=now,
    )


def test_enqueue_and_pending(store):
    assert q.pending() == []
    assert _enqueue() is True
    pend = q.pending()
    assert len(pend) == 1
    assert pend[0]["wallet"] == "0xAAA"
    assert pend[0]["token_id"] == "tok1"


def test_enqueue_dedup_same_wallet_market_outcome(store):
    assert _enqueue() is True
    assert _enqueue() is False           # same (wallet, cid, token) → no dup
    assert len(q.pending()) == 1


def test_enqueue_requires_token_id(store):
    assert q.enqueue_lead(
        wallet="0xAAA", condition_id="cid1", token_id="", market="m",
        outcome="Yes", price=0.4, size=15000.0, end_ts=1000.0, now=0.0,
    ) is False
    assert q.pending() == []


def test_not_matured_is_kept_untouched(store):
    _enqueue(end_ts=1000.0)
    counts = q.process_resolutions(now=500.0,
                                   fetch_market=lambda cid: {"closed": True},
                                   classify=lambda m, t: True)
    assert counts["kept"] == 1
    assert counts["won"] == 0
    assert q.eval_seeds() == []          # never even looked up — not matured
    assert len(q.pending()) == 1


def test_won_becomes_eval_seed(store):
    _enqueue(wallet="0xWIN", end_ts=1000.0)
    counts = q.process_resolutions(now=2000.0,
                                   fetch_market=lambda cid: {"closed": True},
                                   classify=lambda m, t: True)
    assert counts["won"] == 1
    assert counts["seeded"] == 1
    assert q.eval_seeds() == ["0xWIN"]
    assert q.pending() == []             # removed once routed


def test_lost_is_dropped_no_seed(store):
    _enqueue(wallet="0xLOSE", end_ts=1000.0)
    counts = q.process_resolutions(now=2000.0,
                                   fetch_market=lambda cid: {"closed": True},
                                   classify=lambda m, t: False)
    assert counts["lost"] == 1
    assert q.eval_seeds() == []
    assert q.pending() == []


def test_matured_but_unresolved_is_kept_until_expiry(store):
    _enqueue(end_ts=1000.0)
    # classify None = closed-but-unresolved / fetch lag; within wait window → keep
    counts = q.process_resolutions(now=1100.0, max_wait_s=10_000.0,
                                   fetch_market=lambda cid: None,
                                   classify=lambda m, t: None)
    assert counts["kept"] == 1
    assert len(q.pending()) == 1
    # past the wait window → expired and dropped
    counts = q.process_resolutions(now=99_999.0, max_wait_s=10_000.0,
                                   fetch_market=lambda cid: None,
                                   classify=lambda m, t: None)
    assert counts["expired"] == 1
    assert q.pending() == []
    assert q.eval_seeds() == []


def test_seed_dedup_across_two_winning_markets(store):
    _enqueue(wallet="0xWIN", cid="cidA", token="tokA", end_ts=1000.0)
    _enqueue(wallet="0xWIN", cid="cidB", token="tokB", end_ts=1000.0)
    q.process_resolutions(now=2000.0,
                          fetch_market=lambda cid: {"closed": True},
                          classify=lambda m, t: True)
    assert q.eval_seeds() == ["0xWIN"]   # same wallet seeded once, not twice


def test_clear_eval_seeds(store):
    _enqueue(wallet="0xWIN", end_ts=1000.0)
    q.process_resolutions(now=2000.0,
                          fetch_market=lambda cid: {"closed": True},
                          classify=lambda m, t: True)
    assert q.eval_seeds() == ["0xWIN"]
    q.clear_eval_seeds()
    assert q.eval_seeds() == []


def test_classify_exception_keeps_lead(store):
    _enqueue(end_ts=1000.0)

    def boom(cid):
        raise RuntimeError("network down")

    counts = q.process_resolutions(now=1100.0, max_wait_s=10_000.0,
                                   fetch_market=boom,
                                   classify=lambda m, t: True)
    assert counts["kept"] == 1           # failure is treated as unresolved
    assert len(q.pending()) == 1
