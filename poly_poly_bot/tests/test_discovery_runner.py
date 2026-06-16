"""Tests for the discovery daemon orchestration (IO via temp files, no network)."""

from __future__ import annotations

import json

from src.copy_trading.discovery import DiscoveryConfig, Eval
from src.copy_trading.discovery_runner import DiscoveryRunner, format_find

CFG = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                      drop_capture_cents=1.0, watchlist_cap=3, auto_remove=True)


def _runner(tmp_path, evaluated_seq, sink):
    """Runner whose evaluate() returns successive dicts from evaluated_seq."""
    calls = {"i": 0}

    def fake_eval(cfg, **kw):
        d = evaluated_seq[min(calls["i"], len(evaluated_seq) - 1)]
        calls["i"] += 1
        return d

    return DiscoveryRunner(
        config=CFG,
        watchlist_path=str(tmp_path / "copy_watchlist.json"),
        state_path=str(tmp_path / "discovery_state.json"),
        notify=sink.append,
        evaluate=fake_eval,
        now=lambda: 1000.0,
    )


def _ev(w, cap, tstat=12.0):
    return Eval(wallet=w, capture_cents=cap, tstat=tstat, roi=0.5, hit_rate=0.6, n=20)


def test_first_sweep_writes_watchlist_and_sends_one_summary(tmp_path):
    sink: list[str] = []
    r = _runner(tmp_path, [{"0xA": _ev("0xA", 2.0), "0xB": _ev("0xB", 1.8)}], sink)
    r.run_once()

    wl = json.load(open(tmp_path / "copy_watchlist.json"))
    assert [t["wallet"] for t in wl["targets"]] == ["0xA", "0xB"]
    assert wl["source"] == "discovery"
    # exactly one init summary, not one-per-wallet
    assert len(sink) == 1 and "initialized" in sink[0]

    state = json.load(open(tmp_path / "discovery_state.json"))
    assert state["initialized"] is True
    assert state["last_run"] == 1000.0


def test_second_sweep_pings_only_new_wallets(tmp_path):
    sink: list[str] = []
    r = _runner(tmp_path, [
        {"0xA": _ev("0xA", 2.0)},                      # sweep 1: init
        {"0xA": _ev("0xA", 2.0), "0xB": _ev("0xB", 2.5)},  # sweep 2: 0xB is new
    ], sink)
    r.run_once()
    sink.clear()
    r.run_once()

    # only 0xB pinged, as an individual find (not a summary)
    assert len(sink) == 1
    assert "0xB" in sink[0] and "New copyable wallet" in sink[0]
    wl = json.load(open(tmp_path / "copy_watchlist.json"))
    assert {t["wallet"] for t in wl["targets"]} == {"0xA", "0xB"}


def test_decayed_wallet_removed_from_watchlist_quietly(tmp_path):
    sink: list[str] = []
    r = _runner(tmp_path, [
        {"0xA": _ev("0xA", 2.0)},     # on paper
        {"0xA": _ev("0xA", 0.3)},     # decays below drop band
    ], sink)
    r.run_once()
    sink.clear()
    r.run_once()

    wl = json.load(open(tmp_path / "copy_watchlist.json"))
    assert wl["targets"] == []          # removed
    assert sink == []                   # removal is silent (logged, not pinged)


def test_empty_evaluation_is_noop(tmp_path):
    sink: list[str] = []
    r = _runner(tmp_path, [{}], sink)
    assert r.run_once() is None
    assert sink == []


def test_format_find_has_profile_link_and_stats():
    msg = format_find(_ev("0xABC", 2.34))
    assert "polymarket.com/profile/0xABC" in msg
    assert "+2.34¢" in msg
    assert "paper watchlist" in msg


def test_format_find_shows_theory_reasons():
    e = Eval(wallet="0xABC", capture_cents=2.0, tstat=12.0,
             flagged_by=("1f", "1g"), reason="early-exit swing: 10 round-trips")
    msg = format_find(e)
    assert "flagged by *1f, 1g*" in msg and "early-exit swing" in msg


def test_llm_review_annotates_only_new_qualifiers_when_enabled(tmp_path):
    from src.copy_trading.llm_review import LLMVerdict

    sink: list[str] = []
    reviewed: list[str] = []

    def fake_review(dossier, model=None):
        reviewed.append(dossier["wallet"])
        return LLMVerdict("follow", "high", True, 0.8, "steady curve, copyable")

    seq = [
        {"0xA": _ev("0xA", 2.0)},                          # sweep 1: init (no review)
        {"0xA": _ev("0xA", 2.0), "0xB": _ev("0xB", 2.5)},  # sweep 2: 0xB is new
    ]
    calls = {"i": 0}

    def fake_eval(cfg, **kw):
        d = seq[min(calls["i"], len(seq) - 1)]
        calls["i"] += 1
        return d

    r = DiscoveryRunner(
        config=CFG,
        watchlist_path=str(tmp_path / "copy_watchlist.json"),
        state_path=str(tmp_path / "discovery_state.json"),
        notify=sink.append,
        evaluate=fake_eval,
        llm_review=fake_review,
        llm_review_enabled=True,
        now=lambda: 1000.0,
    )
    r.run_once()        # init — no per-wallet review
    assert reviewed == []
    sink.clear()
    r.run_once()        # 0xB newly qualified → reviewed + annotated

    assert reviewed == ["0xB"]                  # only the new qualifier
    assert len(sink) == 1
    assert "Claude: *follow*" in sink[0] and "steady curve" in sink[0]


def test_llm_review_off_by_default_leaves_ping_clean(tmp_path):
    sink: list[str] = []
    r = _runner(tmp_path, [
        {"0xA": _ev("0xA", 2.0)},
        {"0xA": _ev("0xA", 2.0), "0xB": _ev("0xB", 2.5)},
    ], sink)
    r.run_once()
    sink.clear()
    r.run_once()
    assert "Claude" not in sink[0]              # no LLM line when disabled


def test_release_freed_memory_never_raises():
    """Runs in the daemon loop after every sweep to return the peak heap to
    the OS. Must be safe on any platform — on non-glibc dev boxes malloc_trim
    is absent, so it should gc.collect and best-effort trim, swallowing the
    latter. A raise here would kill the discovery thread."""
    from src.copy_trading.discovery_runner import _release_freed_memory

    _release_freed_memory()  # must not raise
    _release_freed_memory()  # idempotent / repeatable
