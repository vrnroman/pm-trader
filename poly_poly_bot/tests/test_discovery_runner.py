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
    assert "Flagged by <b>1f, 1g</b>" in msg and "early-exit swing" in msg


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
    assert "Claude: <b>follow</b>" in sink[0] and "steady curve" in sink[0]


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


# --------------------------------------------------------------------------- #
# Consensus-of-sharps signal wiring
# --------------------------------------------------------------------------- #

from src.copy_trading.outcome_names import OutcomeNameResolver  # noqa: E402

CONSENSUS_CFG = DiscoveryConfig(
    min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0, watchlist_cap=5,
    category_select=False,            # isolate consensus from the category gate
    min_copy_replay_n=12, min_copy_replay_roi=0.0,
    consensus_enabled=True, consensus_min_wallets=3,
    consensus_window_s=86400.0, consensus_min_usd=500.0, consensus_cooldown_s=43200.0,
)


def _sharp(w):
    # qualifies (capture+tstat) AND is copy-validated (proven_positive)
    return Eval(wallet=w, capture_cents=2.0, tstat=12.0, copy_n=15, copy_roi=0.2)


def _consensus_runner(tmp_path, sink, evaluated, fetch_buys, funder_map=None):
    return DiscoveryRunner(
        config=CONSENSUS_CFG,
        watchlist_path=str(tmp_path / "copy_watchlist.json"),
        state_path=str(tmp_path / "discovery_state.json"),
        notify=sink.append,
        evaluate=lambda *a, **k: evaluated,
        now=lambda: 1000.0,
        consensus_fetch_buys=fetch_buys,
        consensus_funder_map=funder_map or (lambda ws: {}),
        consensus_resolver=OutcomeNameResolver(fetcher=lambda cid: ["Yes", "No"]),
    )


def _buy(w):
    return [{"wallet": w, "condition_id": "C", "outcome_index": 1, "usd": 1000.0,
             "price": 0.40, "ts": 1000.0, "title": "Will X win?", "slug": "x",
             "category": "sports"}]


def test_consensus_signal_emitted_and_state_persisted(tmp_path):
    sink: list[str] = []
    evaluated = {w: _sharp(w) for w in ("0xA", "0xB", "0xC")}
    r = _consensus_runner(tmp_path, sink, evaluated, fetch_buys=_buy)
    r.run_once()
    # the consensus signal names the bought outcome
    assert any("sharps → BUY" in m and "“No”" in m for m in sink)
    fired = json.load(open(str(tmp_path / "discovery_state.json") + ".consensus.json"))
    assert "C:1" in fired


def test_consensus_skips_below_k_sharps(tmp_path):
    sink: list[str] = []
    evaluated = {w: _sharp(w) for w in ("0xA", "0xB")}  # only 2 sharps
    r = _consensus_runner(tmp_path, sink, evaluated, fetch_buys=_buy)
    r.run_once()
    assert not any("sharps → BUY" in m for m in sink)


def test_consensus_ignores_unvalidated_wallets(tmp_path):
    sink: list[str] = []
    # 2 validated sharps + 1 NOT copy-validated (copy_n below min) -> below k=3
    evaluated = {"0xA": _sharp("0xA"), "0xB": _sharp("0xB"),
                 "0xC": Eval(wallet="0xC", capture_cents=2.0, tstat=12.0, copy_n=3, copy_roi=0.5)}
    r = _consensus_runner(tmp_path, sink, evaluated, fetch_buys=_buy)
    r.run_once()
    assert not any("sharps → BUY" in m for m in sink)


def test_consensus_skips_with_no_validation_data(tmp_path):
    # gate-off (or any config without resolutions) leaves copy_n=0 so no wallet is
    # copy-validated -> consensus skips before any fetch. The fix does NOT hard-skip
    # on the gate flag alone (copy_n can be populated via a resolution theory / S4),
    # so we model the real cause: unvalidated wallets (copy_n=0).
    sink: list[str] = []
    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0, watchlist_cap=5,
        category_select=False, copy_replay_gate=False,
        consensus_enabled=True, consensus_min_wallets=3, consensus_window_s=86400.0,
        consensus_min_usd=500.0, consensus_cooldown_s=43200.0)
    # capture+tstat qualify them onto the watchlist, but copy_n=0 -> not validated
    evaluated = {w: Eval(wallet=w, capture_cents=2.0, tstat=12.0)
                 for w in ("0xA", "0xB", "0xC")}
    called = {"buys": 0}

    def fetch_buys(w):
        called["buys"] += 1
        return _buy(w)

    r = DiscoveryRunner(
        config=cfg, watchlist_path=str(tmp_path / "wl.json"),
        state_path=str(tmp_path / "st.json"), notify=sink.append,
        evaluate=lambda *a, **k: evaluated, now=lambda: 1000.0,
        consensus_fetch_buys=fetch_buys, consensus_funder_map=lambda ws: {})
    r.run_once()
    assert not any("sharps → BUY" in m for m in sink)
    assert called["buys"] == 0          # short-circuited before any fetch


def test_consensus_fires_with_validated_sharps_even_if_gate_off(tmp_path):
    # the regression the review caught: copy_n can be populated without
    # copy_replay_gate (via a resolution theory / S4), so validated sharps must
    # still produce a consensus signal — the old hard gate-off skip suppressed it.
    sink: list[str] = []
    cfg = DiscoveryConfig(
        min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0, watchlist_cap=5,
        category_select=False, copy_replay_gate=False,
        consensus_enabled=True, consensus_min_wallets=3, consensus_window_s=86400.0,
        consensus_min_usd=500.0, consensus_cooldown_s=43200.0)
    evaluated = {w: _sharp(w) for w in ("0xA", "0xB", "0xC")}  # copy_n=15 -> validated
    r = _consensus_runner(tmp_path, sink, evaluated, fetch_buys=_buy)
    r.cfg = cfg
    r.run_once()
    assert any("sharps → BUY" in m for m in sink)


def test_consensus_unverified_independence_noted(tmp_path):
    # funder map empty -> independence can't be verified -> signal says so
    sink: list[str] = []
    evaluated = {w: _sharp(w) for w in ("0xA", "0xB", "0xC")}
    r = _consensus_runner(tmp_path, sink, evaluated, fetch_buys=_buy,
                          funder_map=lambda ws: {})  # no funder data
    r.run_once()
    assert any("independence not confirmed" in m for m in sink)
