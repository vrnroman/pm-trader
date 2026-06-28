"""Tests for the runtime promote/blacklist/offers stores."""

from __future__ import annotations

import pytest

from src.copy_trading import promotion_state as ps


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "promoted.json"))
    monkeypatch.setenv("COPY_BLACKLIST_STORE", str(tmp_path / "blacklist.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "offers.json"))
    ps.clear_cache()
    yield
    ps.clear_cache()


def test_promote_roundtrip_case_insensitive(stores):
    assert ps.promoted_wallets() == []
    ps.add_promoted("0xABC", tier="1b")
    assert ps.promoted_set() == {"0xabc"}
    assert ps.promoted_tier_of("0xABC") == "1b"
    assert ps.promoted_tier_of("0xabc") == "1b"
    assert "0xABC" in ps.promoted_wallets()      # original case preserved


def test_promote_invalid_tier_rejected(stores):
    with pytest.raises(ValueError):
        ps.add_promoted("0xABC", tier="1z")


def test_promote_into_1a_allowed(stores):
    ps.add_promoted("0xABC", tier="1a")
    assert ps.promoted_tier_of("0xABC") == "1a"


def test_remove_promoted(stores):
    ps.add_promoted("0xABC")
    assert ps.remove_promoted("0xABC") is True
    assert ps.promoted_wallets() == []
    assert ps.remove_promoted("0xABC") is False


def test_blacklist_active_then_expires(stores):
    now = 1000.0
    ps.add_blacklist("0xBAD", until=now + 100, reason="auto-demote", now=now)
    assert ps.is_blacklisted("0xBAD", now=now + 50) is True
    assert ps.active_blacklist(now=now + 50) == {"0xbad"}
    assert ps.is_blacklisted("0xBAD", now=now + 200) is False
    assert ps.active_blacklist(now=now + 200) == set()


def test_blacklist_permanent_until_zero(stores):
    ps.add_blacklist("0xBAD", until=0, now=1000.0)
    assert ps.is_blacklisted("0xBAD", now=10 ** 9) is True


def test_offers_roundtrip(stores):
    ps.record_offer("0xW", status="offered", n_closed=15, roi=0.2)
    assert ps.offer_status("0xW") == "offered"
    assert "0xw" in ps.offers_map()
    ps.record_offer("0xW", status="dismissed")
    assert ps.offer_status("0xW") == "dismissed"


def test_cache_fresh_after_write(stores):
    assert ps.promoted_wallets() == []      # primes the cache with the empty file
    ps.add_promoted("0xABC")                 # write must invalidate/refresh it
    assert ps.promoted_set() == {"0xabc"}
