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
    monkeypatch.setenv("WALLET_DISCOVERY_CHUNK", "30")  # 9 chunks, none holds the top 40
    monkeypatch.setenv("WALLET_DISCOVERY_BATCH_PAUSE_S", "0")

    cfg = DiscoveryConfig(skill_pool=40)
    out = dd.evaluate_sweep(cfg)

    expected = {f"0x{i:04d}" for i in range(210, 250)}  # the 40 highest-ranked
    assert set(out) == expected


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
                                max_offset=100_000, page_pause_s=0.3)

    assert pages == [0, 500]              # stopped after the short second page
    assert pauses == [0.3]               # paused once, between the two pages
    assert len(wallets) == 503
