"""Tests for the live I/O helpers added for bet-horizon routing (Strategy 4).

End-date / mid lookups and horizon stamping are the only network-touching pieces;
here their HTTP layer (`_get`, `fetch_end_ts`) is monkeypatched so the routing
logic is exercised without the network.
"""

from __future__ import annotations

from src.copy_trading import copy_paper_live as live


def test_parse_end_ts_handles_z_suffix_and_naive():
    ts = live._parse_end_ts("2026-12-31T00:00:00Z")
    assert ts is not None
    assert live._parse_end_ts("2026-12-31T00:00:00") == ts   # naive ISO treated as UTC
    assert live._parse_end_ts("") is None
    assert live._parse_end_ts("not-a-date") is None


def test_horizon_resolver_computes_days_and_caches(monkeypatch):
    calls = []

    def fake_end_ts(cid):
        calls.append(cid)
        return 1000.0 * 86400          # market resolves at "day 1000"

    monkeypatch.setattr(live, "fetch_end_ts", fake_end_ts)
    horizon = live.make_horizon_resolver(now=lambda: 900.0 * 86400)  # "day 900"
    assert horizon("0xC") == 100.0     # 1000 - 900 days out
    assert horizon("0xC") == 100.0     # second call served from cache
    assert calls == ["0xC"]            # ...so only one end-date lookup happened
    assert horizon("") is None


def test_horizon_resolver_failed_lookup_is_not_cached(monkeypatch):
    results = [None, 1000.0 * 86400]
    monkeypatch.setattr(live, "fetch_end_ts", lambda cid: results.pop(0))
    horizon = live.make_horizon_resolver(now=lambda: 0.0)
    assert horizon("0xC") is None      # transient miss -> None, not cached
    assert horizon("0xC") == 1000.0    # retried next time, now succeeds


def test_fetch_mid_is_mean_of_best_ask_and_bid(monkeypatch):
    monkeypatch.setattr(live, "_get", lambda base, path, **kw: {
        "asks": [{"price": "0.62", "size": "10"}, {"price": "0.65", "size": "10"}],
        "bids": [{"price": "0.58", "size": "10"}, {"price": "0.55", "size": "10"}],
    })
    assert live.fetch_mid("TOK") == (0.62 + 0.58) / 2   # best ask + best bid


def test_fetch_mid_none_on_one_sided_book(monkeypatch):
    monkeypatch.setattr(live, "_get",
                        lambda base, path, **kw: {"asks": [{"price": "0.6", "size": "5"}], "bids": []})
    assert live.fetch_mid("TOK") is None


_ACT = [{
    "type": "TRADE", "side": "BUY", "timestamp": 1_000_000,
    "price": 0.5, "usdcSize": 1000, "transactionHash": "0xtx",
    "asset": "TOK", "conditionId": "0xC", "outcomeIndex": 0, "title": "Q",
}]


def test_detector_stamps_horizon_days(monkeypatch):
    monkeypatch.setattr(live, "_get", lambda base, path, **kw: _ACT)
    det = live.make_detector(["0xW"], max_age_s=10 ** 12, min_usd=100,
                             horizon_resolver=lambda cid: 300.0)
    trades = det()
    assert len(trades) == 1
    assert trades[0]["horizon_days"] == 300.0
    assert trades[0]["condition_id"] == "0xC"


def test_detector_horizon_none_without_resolver(monkeypatch):
    monkeypatch.setattr(live, "_get", lambda base, path, **kw: _ACT)
    det = live.make_detector(["0xW"], max_age_s=10 ** 12, min_usd=100)
    assert det()[0]["horizon_days"] is None
