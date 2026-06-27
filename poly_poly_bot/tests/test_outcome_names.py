"""Tests for the outcome-name resolver (never fabricate the traded side)."""
from __future__ import annotations

from src.copy_trading.outcome_names import OutcomeNameResolver, parse_outcomes


def test_parse_outcomes_json_string_and_list():
    assert parse_outcomes({"outcomes": '["Yes", "No"]'}) == ["Yes", "No"]
    assert parse_outcomes({"outcomes": ["Lakers", "Celtics"]}) == ["Lakers", "Celtics"]
    assert parse_outcomes({"outcomes": "not json"}) == []
    assert parse_outcomes({}) == []


def test_name_maps_index_through_real_array():
    r = OutcomeNameResolver(fetcher=lambda cid: ["Yes", "No"])
    assert r.name("C", 0) == "Yes"
    assert r.name("C", 1) == "No"


def test_name_none_when_out_of_range_or_unknown():
    r = OutcomeNameResolver(fetcher=lambda cid: ["Yes", "No"])
    assert r.name("C", 5) is None            # out of range -> no guess
    r2 = OutcomeNameResolver(fetcher=lambda cid: [])
    assert r2.name("C", 0) is None           # unknown market


def test_label_honest_fallback_never_fabricates():
    r = OutcomeNameResolver(fetcher=lambda cid: [])
    assert r.label("C", 0) == "Outcome #0"   # NOT "Yes"
    assert r.label("C", 1) == "Outcome #1"
    assert r.label("C", None) == "Outcome #?"


def test_label_uses_real_name_when_available():
    r = OutcomeNameResolver(fetcher=lambda cid: ["Lakers", "Celtics"])
    assert r.label("C", 0) == "Lakers"


def test_cache_fetches_once_per_condition():
    calls = []

    def fetch(cid):
        calls.append(cid)
        return ["Yes", "No"]

    r = OutcomeNameResolver(fetcher=fetch)
    r.name("C", 0)
    r.name("C", 1)
    r.label("C", 0)
    assert calls == ["C"]                     # one fetch, then cached


def test_transient_miss_not_cached():
    results = [None, ["Yes", "No"]]

    def fetch(cid):
        return results.pop(0)

    r = OutcomeNameResolver(fetcher=fetch)
    assert r.name("C", 0) is None             # transient failure
    assert r.name("C", 0) == "Yes"            # retried, now resolves


def test_cache_is_bounded():
    # the process-singleton resolver must not grow without limit
    calls = {"n": 0}

    def fetch(cid):
        calls["n"] += 1
        return ["Yes", "No"]

    r = OutcomeNameResolver(fetcher=fetch, max_cache=3)
    for i in range(5):
        r.name(f"C{i}", 0)
    assert len(r._cache) <= 3            # FIFO-evicted, bounded
    # the oldest (C0) was evicted -> a re-query refetches
    before = calls["n"]
    r.name("C0", 0)
    assert calls["n"] == before + 1


def test_empty_result_not_cached_recovers(monkeypatch):
    # #4: a not-yet-indexed market returns [] then later resolves -> must recover
    results = [[], ["Yes", "No"]]
    r = OutcomeNameResolver(fetcher=lambda cid: results.pop(0))
    assert r.label("C", 0) == "Outcome #0"   # empty -> honest fallback, NOT cached
    assert r.label("C", 0) == "Yes"          # refetched, now resolves
