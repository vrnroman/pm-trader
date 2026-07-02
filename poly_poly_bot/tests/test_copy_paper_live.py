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


# --------------------------------------------------------------------------- #
# Watchlist loaders for the winning-markets gate + conviction sizing
# --------------------------------------------------------------------------- #

import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402


def _write_watchlist(d, targets):
    p = os.path.join(d, "wl.json")
    json.dump({"targets": targets}, open(p, "w"))
    return p


def test_load_watchlist_categories_parses_approved():
    with tempfile.TemporaryDirectory() as d:
        p = _write_watchlist(d, [
            {"wallet": "0xAbC", "approved_categories": ["crypto", "research"]},
            {"wallet": "0xDef", "approved_categories": []},   # no proven winner -> omitted
            {"wallet": "0xNoField"},  # missing field -> omitted (unrestricted)
        ])
        out = live.load_watchlist_categories(p)
        # only wallets with a proven winning market are restricted; empty/absent
        # are omitted so the engine leaves them unrestricted (no silent block).
        assert out == {"0xabc": {"crypto", "research"}}
        assert "0xdef" not in out
        assert "0xnofield" not in out


def test_load_watchlist_median_usd_parses_floats():
    with tempfile.TemporaryDirectory() as d:
        p = _write_watchlist(d, [
            {"wallet": "0xAbC", "median_usd": 1500.0},
            {"wallet": "0xDef", "median_usd": 0},   # falsy -> skipped
            {"wallet": "0xGhi"},                    # missing -> skipped
        ])
        out = live.load_watchlist_median_usd(p)
        assert out == {"0xabc": 1500.0}


def test_load_watchlist_loaders_missing_file():
    assert live.load_watchlist_categories("/no/such/file") == {}
    assert live.load_watchlist_median_usd("") == {}


# --------------------------------------------------------------------------- #
# Exit detector pages through the window so fast SELLs aren't missed (item D)
# --------------------------------------------------------------------------- #

def test_exit_detector_pages_until_cutoff(monkeypatch):
    now = 10_000.0
    monkeypatch.setattr(live.time, "time", lambda: now)
    # page 0: 100 BUY events (no sells, all fresh) -> must page again;
    # page 1: the SELL we want (fresh) + an old event that stops paging.
    page0 = [{"type": "TRADE", "side": "BUY", "asset": "X", "price": 0.5,
              "timestamp": now - 60} for _ in range(100)]
    page1 = [{"type": "TRADE", "side": "SELL", "asset": "TOK", "price": 0.6,
              "timestamp": now - 120},
             {"type": "TRADE", "side": "SELL", "asset": "OLD", "price": 0.4,
              "timestamp": now - 9999}]  # older than max_age -> triggers stop

    def fake_get(base, path, **kw):
        return page0 if kw.get("offset", 0) == 0 else page1

    monkeypatch.setattr(live, "_get", fake_get)
    det = live.make_exit_detector(["0xW"], max_age_s=3600)
    out = det()
    assert {"target": "0xW", "token_id": "TOK", "their_price": 0.6} in out
    # the stale "OLD" sell is excluded by the cutoff
    assert all(e["token_id"] != "OLD" for e in out)


def test_exit_detector_single_page_when_short(monkeypatch):
    now = 10_000.0
    monkeypatch.setattr(live.time, "time", lambda: now)
    page = [{"type": "TRADE", "side": "SELL", "asset": "TOK", "price": 0.6,
             "timestamp": now - 60}]

    calls = []

    def fake_get(base, path, **kw):
        calls.append(kw.get("offset", 0))
        return page if kw.get("offset", 0) == 0 else []

    monkeypatch.setattr(live, "_get", fake_get)
    det = live.make_exit_detector(["0xW"], max_age_s=3600)
    out = det()
    assert len(out) == 1
    assert calls == [0]  # short page (<100) -> no second request
