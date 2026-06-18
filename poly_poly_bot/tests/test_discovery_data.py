"""Discovery sweep data layer — chunked fetch/score (memory-bounding).

The sweep fetches + scores the wallet universe in chunks so it never holds
every wallet's raw /activity in memory at once (the unchunked version peaked
~2.5GB and OOM'd a 2GB VM). These tests pin that the chunking is transparent:
the whole universe is still processed, no wallet is dropped or double-fetched,
and the chunk size is honoured.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from src.copy_trading import discovery_data as dd
from src.copy_trading.discovery import DiscoveryConfig


def _stub_scoring(monkeypatch):
    """No skill pool + trivial metrics + no recent buys → sweep exercises the
    fetch/score chunk loop with zero network in the lead-lag stage."""
    monkeypatch.setattr(dd, "compute_wallet_metrics",
                        lambda a, **kw: SimpleNamespace(tstat=5.0, roi=0.1))
    monkeypatch.setattr(dd, "select_targets", lambda scored, **kw: [])
    monkeypatch.setattr(dd, "fetch_recent_buys", lambda *a, **k: [])
    # neutralise the deep-eval signal fetches (no network in tests)
    monkeypatch.setattr(dd, "wallet_entry_profile", lambda *a, **k: dd.EntryProfile())
    monkeypatch.setattr(dd, "wallet_curve_metrics", lambda *a, **k: dd.CurveMetrics())
    monkeypatch.setattr(dd, "build_wallet_context",
                        lambda w, *a, **k: dd.WalletContext(wallet=w, now=0.0))
    monkeypatch.setenv("WALLET_DISCOVERY_BATCH_PAUSE_S", "0")  # no real sleeps in tests


def test_evaluate_sweep_chunks_universe_without_dropping_wallets(monkeypatch):
    universe = [f"0x{i:04d}" for i in range(250)]
    monkeypatch.setattr(dd, "build_universe", lambda target, **kw: list(universe))

    calls: list[list[str]] = []  # wallet list of each fetch_all_activity call

    def fake_fetch_all(wallets, cache_dir, ttl_s, workers=8, stop=None):
        chunk = list(wallets)
        calls.append(chunk)
        return {w: [{"w": w}] for w in chunk}

    monkeypatch.setattr(dd, "fetch_all_activity", fake_fetch_all)
    _stub_scoring(monkeypatch)
    monkeypatch.setenv("WALLET_DISCOVERY_CHUNK", "30")

    out = dd.evaluate_sweep(DiscoveryConfig())

    assert out == {}  # no skill pool / must_include → no lead-lag rows
    assert len(calls) == math.ceil(250 / 30)         # chunked
    assert all(len(c) <= 30 for c in calls)          # chunk size honoured
    flat = [w for c in calls for w in c]
    assert sorted(flat) == sorted(universe)          # nothing dropped
    assert len(flat) == len(set(flat)) == 250        # nothing double-fetched


def test_evaluate_sweep_single_chunk_when_chunk_exceeds_universe(monkeypatch):
    universe = [f"0x{i:04d}" for i in range(10)]
    monkeypatch.setattr(dd, "build_universe", lambda target, **kw: list(universe))

    calls: list[list[str]] = []

    def fake_fetch_all(wallets, *a, **k):
        calls.append(list(wallets))
        return {w: [] for w in wallets}

    monkeypatch.setattr(dd, "fetch_all_activity", fake_fetch_all)
    _stub_scoring(monkeypatch)
    monkeypatch.setenv("WALLET_DISCOVERY_CHUNK", "500")

    dd.evaluate_sweep(DiscoveryConfig())

    assert len(calls) == 1                           # one chunk covers all
    assert sorted(calls[0]) == sorted(universe)


def test_evaluate_sweep_includes_must_include_wallets(monkeypatch):
    universe = [f"0x{i:04d}" for i in range(20)]
    monkeypatch.setattr(dd, "build_universe", lambda target, **kw: list(universe))

    fetched: set[str] = set()

    def fake_fetch_all(wallets, *a, **k):
        fetched.update(wallets)
        return {w: [] for w in wallets}

    monkeypatch.setattr(dd, "fetch_all_activity", fake_fetch_all)
    _stub_scoring(monkeypatch)
    monkeypatch.setenv("WALLET_DISCOVERY_CHUNK", "8")

    dd.evaluate_sweep(DiscoveryConfig(), must_include={"0xWATCHED"})

    # a watchlist wallet not in the universe is still fetched + scored
    assert "0xWATCHED" in fetched
    assert universe[0] in fetched


class _FakeMetrics:
    """Just the surface select_targets / evaluate_sweep read off a metrics obj."""

    def __init__(self, rank: float):
        self.capital = 10_000.0
        self.n_closed = 20
        self.concentration = 0.1
        self.recency_ok = True
        self.tstat = rank
        self.roi = 0.5

    def rank_score(self, method: str) -> float:  # higher rank = stronger
        return self.tstat


def test_evaluate_sweep_streams_global_topk_across_chunks(monkeypatch):
    """The streaming pool must pick the universe-wide best ``skill_pool`` — not
    a per-chunk best. Wallet i gets tstat=i; with chunks far smaller than the
    universe, only a global merge yields the true top-K."""
    universe = [f"0x{i:04d}" for i in range(250)]
    monkeypatch.setattr(dd, "build_universe", lambda target, **kw: list(universe))
    monkeypatch.setattr(dd, "fetch_all_activity",
                        lambda wallets, *a, **k: {w: [{"w": w}] for w in wallets})
    # rank each wallet by its index; keep the REAL select_targets (the thing we
    # are exercising) so the merge logic is what's under test.
    monkeypatch.setattr(dd, "compute_wallet_metrics",
                        lambda a, **kw: _FakeMetrics(int(a[0]["w"][2:])))
    monkeypatch.setattr(dd, "fetch_recent_buys", lambda *a, **k: [])
    monkeypatch.setattr(dd, "wallet_entry_profile", lambda *a, **k: dd.EntryProfile())
    monkeypatch.setattr(dd, "wallet_curve_metrics", lambda *a, **k: dd.CurveMetrics())
    monkeypatch.setattr(dd, "build_wallet_context",
                        lambda w, *a, **k: dd.WalletContext(wallet=w, now=0.0))
    monkeypatch.setenv("WALLET_DISCOVERY_CHUNK", "30")  # 9 chunks, none holds the top 40
    monkeypatch.setenv("WALLET_DISCOVERY_BATCH_PAUSE_S", "0")

    cfg = DiscoveryConfig(skill_pool=40)
    out = dd.evaluate_sweep(cfg)

    expected = {f"0x{i:04d}" for i in range(210, 250)}  # the 40 highest-ranked
    assert set(out) == expected


def test_evaluate_sweep_fetches_and_threads_resolutions_only_when_needed(monkeypatch):
    """A resolution-needing theory (1a/1e) makes the sweep fetch market
    resolutions once and thread them into each wallet's context; with no such
    theory enabled it neither fetches nor passes any."""
    from src.copy_trading.wallet_context import MarketResolution

    universe = ["0x0001"]
    acts = {"0x0001": [{"type": "TRADE", "side": "BUY", "conditionId": "0xCID"}]}
    monkeypatch.setattr(dd, "build_universe", lambda target, **kw: list(universe))
    monkeypatch.setattr(dd, "fetch_all_activity",
                        lambda wallets, *a, **k: {w: acts.get(w, []) for w in wallets})
    monkeypatch.setattr(dd, "compute_wallet_metrics",
                        lambda a, **kw: SimpleNamespace(tstat=5.0, roi=0.1))
    monkeypatch.setattr(dd, "select_targets",
                        lambda scored, **kw: [SimpleNamespace(address=w, metrics=m)
                                              for w, m in scored.items()])
    monkeypatch.setattr(dd, "fetch_recent_buys", lambda *a, **k: [])
    monkeypatch.setattr(dd, "wallet_entry_profile", lambda *a, **k: dd.EntryProfile())
    monkeypatch.setattr(dd, "wallet_curve_metrics", lambda *a, **k: dd.CurveMetrics())

    seen: dict = {}

    def fake_build_ctx(w, *a, resolutions=None, **k):
        seen["resolutions"] = resolutions
        return dd.WalletContext(wallet=w, now=0.0)

    monkeypatch.setattr(dd, "build_wallet_context", fake_build_ctx)

    res_calls = {"n": 0, "cids": None}

    def fake_fetch_res(cids, cache_dir=None, **k):
        res_calls["n"] += 1
        res_calls["cids"] = set(cids)
        return {c: MarketResolution(winning_index=1, end_ts=1.0) for c in cids}

    monkeypatch.setattr(dd, "fetch_resolutions", fake_fetch_res)
    monkeypatch.setenv("WALLET_DISCOVERY_BATCH_PAUSE_S", "0")

    # 1e enabled (needs_resolution) → resolutions fetched for the BUY's market
    # and threaded into the context.
    dd.evaluate_sweep(DiscoveryConfig(enabled_theories=frozenset({"1e"})))
    assert res_calls["n"] == 1
    assert res_calls["cids"] == {"0xCID"}
    assert seen["resolutions"] == {"0xCID": MarketResolution(winning_index=1, end_ts=1.0)}

    # only non-resolution theories AND the copy-replay gate off → no fetch,
    # empty resolutions passed through. (With the gate on — the default —
    # resolutions are always fetched so copies can be replayed to resolution.)
    res_calls["n"] = 0
    seen.clear()
    dd.evaluate_sweep(DiscoveryConfig(enabled_theories=frozenset({"1b"}),
                                      copy_replay_gate=False))
    assert res_calls["n"] == 0
    assert seen["resolutions"] == {}

    # gate on (default) → resolutions fetched even for a non-resolution theory
    res_calls["n"] = 0
    seen.clear()
    dd.evaluate_sweep(DiscoveryConfig(enabled_theories=frozenset({"1b"})))
    assert res_calls["n"] == 1


def test_build_universe_stops_on_short_page_and_paces(monkeypatch):
    """A page shorter than the limit means the tier is exhausted — stop paging
    it (don't burn the whole offset budget) and move to the next stake tier."""
    pages: list[int] = []   # offsets actually requested
    pauses: list[float] = []
    monkeypatch.setattr(dd.time, "sleep", lambda s: pauses.append(s))

    def fake_get(session, base, path, **params):
        pages.append(params["offset"])
        # tier returns one full page then a short page (feed exhausted)
        return [{"proxyWallet": f"0x{params['filterAmount']}_{params['offset']}_{j}"}
                for j in range(500 if params["offset"] == 0 else 3)]

    monkeypatch.setattr(dd, "_get", fake_get)

    wallets = dd.build_universe(target=10_000, min_amounts=(500,),
                                max_offset=100_000, page_pause_s=0.3, window_s=0)

    assert pages == [0, 500]              # stopped after the short second page
    assert pauses == [0.3]               # paused once, between the two pages
    assert len(wallets) == 503


def test_build_universe_window_stops_at_cutoff(monkeypatch):
    """With a time window, paging a combo stops as soon as the newest-first feed
    crosses the cutoff — older trades are skipped, not collected."""
    monkeypatch.setattr(dd.time, "sleep", lambda s: None)
    now = 1_000_000.0
    monkeypatch.setattr(dd.time, "time", lambda: now)
    requested: list[int] = []

    def fake_get(session, base, path, **params):
        requested.append(params["offset"])
        if params["offset"] == 0:                       # all inside the window
            return [{"proxyWallet": f"0xA{j}", "timestamp": now - 100}
                    for j in range(500)]
        # second page straddles the cutoff: half fresh, half too old
        return ([{"proxyWallet": f"0xB{j}", "timestamp": now - 100} for j in range(3)]
                + [{"proxyWallet": f"0xC{j}", "timestamp": now - 9_999} for j in range(2)])

    monkeypatch.setattr(dd, "_get", fake_get)
    wallets = dd.build_universe(target=10_000, min_amounts=(500,),
                                max_offset=100_000, page_pause_s=0, window_s=3600)

    assert requested == [0, 500]                        # stopped once cutoff crossed
    assert "0xC0" not in wallets                         # stale wallet excluded
    assert len([w for w in wallets if w.startswith("0xB")]) == 3
    assert len(wallets) == 503                           # 500 fresh + 3 fresh


def test_build_universe_expand_filters_queries_all_combos(monkeypatch):
    """expand_filters fans out across side (BUY/SELL) × taker (true/false) for
    each stake tier and unions the wallets."""
    monkeypatch.setattr(dd.time, "sleep", lambda s: None)
    seen_params: list[tuple] = []

    def fake_get(session, base, path, **params):
        seen_params.append((params["filterAmount"], params.get("side"), params["takerOnly"]))
        return [{"proxyWallet": f"0x{params.get('side')}_{params['takerOnly']}"}]  # short page

    monkeypatch.setattr(dd, "_get", fake_get)
    wallets = dd.build_universe(target=10_000, min_amounts=(500,),
                                page_pause_s=0, window_s=0, expand_filters=True)

    combos = set(seen_params)
    assert combos == {(500, "BUY", "true"), (500, "BUY", "false"),
                      (500, "SELL", "true"), (500, "SELL", "false")}
    assert len(wallets) == 4                              # one distinct wallet per combo


def test_prune_cache_removes_stale_and_caps_count(monkeypatch, tmp_path):
    import os
    import time as _t
    d = tmp_path / "wcache"
    d.mkdir()
    now = _t.time()
    # 2 stale (older than ttl), 3 fresh
    ages = {"old1": 100_000, "old2": 90_000, "f1": 10, "f2": 20, "f3": 30}
    for name, age in ages.items():
        p = d / f"{name}.json"
        p.write_text("[]")
        os.utime(p, (now - age, now - age))
    (d / "notes.txt").write_text("ignore me")           # non-json untouched

    removed = dd.prune_cache(str(d), ttl_s=86400, max_files=None)
    assert removed == 2                                  # both stale gone
    left = {f for f in os.listdir(d) if f.endswith(".json")}
    assert left == {"f1.json", "f2.json", "f3.json"}
    assert (d / "notes.txt").exists()

    # hard cap: keep only the 1 newest of the 3 fresh (f1 has the smallest age)
    removed2 = dd.prune_cache(str(d), ttl_s=86400, max_files=1)
    assert removed2 == 2
    assert {f for f in os.listdir(d) if f.endswith(".json")} == {"f1.json"}
