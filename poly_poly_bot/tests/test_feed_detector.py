"""Tests for the shared global /trades feed detector (System B)."""

from __future__ import annotations

from src.copy_trading.copy_paper_live import (
    TradeFeed,
    make_feed_detector,
    make_feed_exit_detector,
)


def trade(wallet="0xW", side="BUY", price=0.5, size=2000, ts=1000.0,
          tx="0xtx", asset="TOK", cid="0xC"):
    return {
        "proxyWallet": wallet, "side": side, "price": price, "size": size,
        "timestamp": ts, "transactionHash": tx, "asset": asset,
        "conditionId": cid, "outcomeIndex": 0, "title": "Market?",
        "eventSlug": "slug",
    }


class _StubFeed:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, min_usd, max_age_s):
        return self.rows


def test_feed_stops_at_age_cutoff():
    # newest-first: the second row is older than the cutoff -> stop, drop it.
    def fetch(min_usd, offset):
        return [trade(ts=190, tx="a"), trade(ts=40, tx="b")]

    feed = TradeFeed(fetch=fetch, now=lambda: 200.0, ttl_s=0.0)
    out = feed.recent(min_usd=100, max_age_s=150.0)   # cutoff = 50
    assert [t["transactionHash"] for t in out] == ["a"]


def test_feed_ttl_collapses_to_one_fetch():
    calls = {"n": 0}

    def fetch(min_usd, offset):
        calls["n"] += 1
        return [trade(ts=190)]                          # short page -> one fetch

    feed = TradeFeed(fetch=fetch, now=lambda: 200.0, ttl_s=100.0)
    feed.recent(100, 150)
    feed.recent(100, 150)                               # served from cache
    assert calls["n"] == 1


def test_feed_detector_filters_to_watched_copyable_buys():
    rows = [
        trade(wallet="0xW", side="BUY", price=0.5, size=2000, tx="t1"),   # keep
        trade(wallet="0xW", side="SELL", price=0.5, tx="t2"),             # not a BUY
        trade(wallet="0xOTHER", side="BUY", tx="t3"),                      # not watched
        trade(wallet="0xW", side="BUY", price=0.99, tx="t4"),             # out of band
        trade(wallet="0xW", side="BUY", price=0.5, size=10, tx="t5"),     # below min_usd
    ]
    det = make_feed_detector(["0xW"], max_age_s=1e12, min_usd=500,
                             feed=_StubFeed(rows))
    out = det()
    assert len(out) == 1
    assert out[0]["copy_id"] == "t1-TOK"
    assert out[0]["target"] == "0xW" and out[0]["their_price"] == 0.5
    assert out[0]["slug"] == "slug"


def test_feed_detector_stamps_flagged_by_and_horizon():
    det = make_feed_detector(
        ["0xW"], max_age_s=1e12, min_usd=100,
        flagged_by_map={"0xw": ["1b", "1f"]},
        horizon_resolver=lambda cid: 12.0,
        feed=_StubFeed([trade(wallet="0xW", tx="t1")]))
    out = det()
    assert out[0]["flagged_by"] == ("1b", "1f")
    assert out[0]["horizon_days"] == 12.0


def test_feed_exit_detector_filters_watched_sells():
    rows = [
        trade(wallet="0xW", side="SELL", price=0.6, asset="TOK", tx="s1"),  # keep
        trade(wallet="0xW", side="BUY", tx="b1"),                            # not a SELL
        trade(wallet="0xX", side="SELL", tx="s2"),                          # not watched
    ]
    det = make_feed_exit_detector(["0xW"], max_age_s=1e12, feed=_StubFeed(rows))
    out = det()
    assert len(out) == 1
    assert out[0] == {"target": "0xW", "token_id": "TOK", "their_price": 0.6}
