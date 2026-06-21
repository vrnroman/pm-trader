"""Gamma market-resolution parsing + disk cache (no network)."""

from __future__ import annotations

import json

from src.copy_trading import market_resolution as mr
from src.copy_trading.market_resolution import fetch_resolution, parse_resolution


def test_parse_resolved_yes():
    m = {"closed": True, "outcomes": ["Yes", "No"], "outcomePrices": ["1", "0"],
         "endDate": "2026-05-01T12:00:00Z"}
    r = parse_resolution(m)
    assert r.winning_index == 0 and r.end_ts > 0


def test_parse_resolved_no_is_index_1():
    m = {"closed": True, "outcomePrices": ["0", "1"], "endDate": "2026-05-01T12:00:00Z"}
    assert parse_resolution(m).winning_index == 1


def test_parse_open_market_has_no_winner():
    m = {"closed": False, "outcomePrices": ["0.4", "0.6"], "endDate": "2026-09-01T00:00:00Z"}
    r = parse_resolution(m)
    assert r.winning_index is None and r.end_ts > 0


def test_parse_string_encoded_prices():
    m = {"closed": True, "outcomePrices": "[\"1\", \"0\"]", "endDate": "2026-05-01T00:00:00Z"}
    assert parse_resolution(m).winning_index == 0


def test_fetch_caches_resolved_only(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_get(session, cid):
        calls["n"] += 1
        return {"closed": True, "outcomePrices": ["1", "0"], "endDate": "2026-05-01T00:00:00Z"}

    monkeypatch.setattr(mr, "_get", fake_get)
    r1 = fetch_resolution("0xabc", cache_dir=str(tmp_path))
    assert r1.winning_index == 0
    assert (tmp_path / "res_0xabc.json").exists()
    # second call served from cache — no extra fetch
    r2 = fetch_resolution("0xabc", cache_dir=str(tmp_path))
    assert r2.winning_index == 0 and calls["n"] == 1


def test_fetch_does_not_cache_open_market(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "_get", lambda s, c: {"closed": False, "outcomePrices": ["0.5", "0.5"]})
    r = fetch_resolution("0xopen", cache_dir=str(tmp_path))
    assert r.winning_index is None
    assert not (tmp_path / "res_0xopen.json").exists()   # open markets aren't cached


def test_get_queries_closed_markets(monkeypatch):
    # Regression: Gamma's /markets defaults to OPEN markets, so resolution
    # lookups MUST pass closed=true or they silently return nothing.
    seen = {}

    class _Resp:
        status_code = 200

        def json(self):
            return [{"conditionId": "0xabc", "closed": True, "outcomePrices": ["1", "0"]}]

    class _Sess:
        def get(self, url, params=None, timeout=None):
            seen["params"] = params
            return _Resp()

    mr._get(_Sess(), "0xabc")
    assert seen["params"].get("closed") == "true"


def test_get_batch_queries_closed_markets(monkeypatch):
    seen = {}

    class _Resp:
        status_code = 200

        def json(self):
            return []

    class _Sess:
        def get(self, url, params=None, timeout=None):
            seen["params"] = params
            return _Resp()

    mr._get_batch(_Sess(), ["0xa", "0xb"])
    assert ("closed", "true") in seen["params"]


def test_open_batch_does_not_filter_closed(monkeypatch):
    # Strategy 4 needs OPEN markets, so the open batch must NOT send closed=true
    seen = {}

    class _Resp:
        status_code = 200

        def json(self):
            return []

    class _Sess:
        def get(self, url, params=None, timeout=None):
            seen["params"] = params
            return _Resp()

    mr._get_open_batch(_Sess(), ["0xa", "0xb"])
    assert all(k != "closed" for k, _v in seen["params"])


def test_fetch_open_end_dates_returns_unresolved_rows_with_end_ts(monkeypatch):
    def fake_open_batch(session, cids):
        return [{"conditionId": c, "closed": False, "outcomePrices": ["0.5", "0.5"],
                 "endDate": "2026-12-01T00:00:00Z"} for c in cids]

    monkeypatch.setattr(mr, "_get_open_batch", fake_open_batch)
    res = mr.fetch_open_end_dates(["0xa", "0xb"])
    assert set(res) == {"0xa", "0xb"}
    assert all(r.winning_index is None and r.end_ts > 0 for r in res.values())


def test_fetch_open_end_dates_skips_markets_without_end_date(monkeypatch):
    monkeypatch.setattr(mr, "_get_open_batch",
                        lambda s, cids: [{"conditionId": "0xa", "closed": False}])
    assert mr.fetch_open_end_dates(["0xa"]) == {}


def test_fetch_resolutions_batches_and_caches(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_batch(session, cids):
        calls["n"] += 1
        return [{"conditionId": c, "closed": True, "outcomePrices": ["1", "0"],
                 "endDate": "2026-05-01T00:00:00Z"} for c in cids]

    monkeypatch.setattr(mr, "_get_batch", fake_batch)
    cids = [f"0x{i:02d}" for i in range(120)]
    res = mr.fetch_resolutions(cids, cache_dir=str(tmp_path), batch_size=50)
    assert len(res) == 120 and all(r.winning_index == 0 for r in res.values())
    assert calls["n"] == 3                                   # 120 / 50 -> 3 batched calls
    # second run is fully served from disk cache -> no further batch calls
    res2 = mr.fetch_resolutions(cids, cache_dir=str(tmp_path), batch_size=50)
    assert len(res2) == 120 and calls["n"] == 3
