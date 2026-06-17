"""Tests for the pure discovery state machine."""

from __future__ import annotations

from src.copy_trading.discovery import (
    DiscoveryConfig,
    DiscoveryState,
    Eval,
    run_discovery_cycle,
    watchlist_to_targets,
)

CFG = DiscoveryConfig(
    min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
    watchlist_cap=3, auto_remove=True,
)


def _ev(w, cap, tstat=12.0):
    return Eval(wallet=w, capture_cents=cap, tstat=tstat, roi=0.5, hit_rate=0.6, n=20)


def test_entry_requires_capture_and_tstat():
    evaluated = {
        "0xA": _ev("0xA", 2.0),            # qualifies
        "0xB": _ev("0xB", 2.0, tstat=5),   # tstat too low
        "0xC": _ev("0xC", 0.4),            # capture too low
    }
    r = run_discovery_cycle(evaluated, DiscoveryState(), CFG)
    assert [e.wallet for e in r.watchlist] == ["0xA"]
    assert [e.wallet for e in r.newly_qualified] == ["0xA"]
    assert r.first_init is True
    assert r.new_state.initialized is True


def test_tail_dominated_wallet_is_rejected():
    # both skilled + capture-qualified; 0xT's buy flow is tail-dominated (un-copyable)
    good = Eval(wallet="0xG", capture_cents=2.0, tstat=12.0, tail_ratio=0.1)
    tail = Eval(wallet="0xT", capture_cents=2.0, tstat=12.0, tail_ratio=0.9)
    r = run_discovery_cycle({"0xG": good, "0xT": tail}, DiscoveryState(), CFG)
    assert [e.wallet for e in r.watchlist] == ["0xG"]   # tail buyer filtered out


def test_tail_gate_threshold_configurable():
    tail = Eval(wallet="0xT", capture_cents=2.0, tstat=12.0, tail_ratio=0.4)
    lenient = run_discovery_cycle({"0xT": tail}, DiscoveryState(),
                                  DiscoveryConfig(max_tail_ratio=0.5))
    strict = run_discovery_cycle({"0xT": tail}, DiscoveryState(),
                                 DiscoveryConfig(max_tail_ratio=0.3))
    assert [e.wallet for e in lenient.watchlist] == ["0xT"]
    assert strict.watchlist == []


def test_theory_flag_qualifies_via_or_path():
    # below the legacy capture/t-stat gate, but an independent theory flagged it
    e = Eval(wallet="0xF", capture_cents=0.0, tstat=2.0,
             flagged_by=("1g",), reason="sports specialist: ROI +40% over 12 markets")
    r = run_discovery_cycle({"0xF": e}, DiscoveryState(), CFG)
    assert [x.wallet for x in r.watchlist] == ["0xF"]
    assert r.new_state.on_watchlist["0xF"]["flagged_by"] == ["1g"]
    assert "specialist" in r.new_state.on_watchlist["0xF"]["reason"]


def test_unflagged_below_gate_not_qualified():
    e = Eval(wallet="0xN", capture_cents=0.0, tstat=2.0)   # fails legacy, no flag
    assert run_discovery_cycle({"0xN": e}, DiscoveryState(), CFG).watchlist == []


def test_tail_gate_blocks_even_a_flagged_wallet():
    # copyability filter is universal — a tail-dominated wallet is skipped even
    # when a theory likes it (we still couldn't follow it at a fillable price)
    e = Eval(wallet="0xT", flagged_by=("1g",), tail_ratio=0.9, tstat=2.0)
    assert run_discovery_cycle({"0xT": e}, DiscoveryState(), CFG).watchlist == []


def test_notify_once_then_silent():
    evaluated = {"0xA": _ev("0xA", 2.0)}
    r1 = run_discovery_cycle(evaluated, DiscoveryState(), CFG)
    # second sweep, same wallet still strong -> on list, NOT newly notified
    r2 = run_discovery_cycle(evaluated, r1.new_state, CFG)
    assert [e.wallet for e in r2.watchlist] == ["0xA"]
    assert r2.newly_qualified == []
    assert r2.first_init is False


def test_hysteresis_keeps_wallet_between_bands():
    on = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), CFG).new_state
    # capture drops to 1.2 — below entry (1.5) but above drop band (1.0): stays
    r = run_discovery_cycle({"0xA": _ev("0xA", 1.2)}, on, CFG)
    assert [e.wallet for e in r.watchlist] == ["0xA"]
    assert r.removed == []
    assert r.newly_qualified == []


def test_auto_remove_below_drop_band():
    on = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), CFG).new_state
    r = run_discovery_cycle({"0xA": _ev("0xA", 0.5)}, on, CFG)  # below drop band
    assert r.watchlist == []
    assert r.removed == ["0xA"]


def test_keep_mode_never_removes_for_decay():
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3, auto_remove=False)
    on = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), cfg).new_state
    r = run_discovery_cycle({"0xA": _ev("0xA", 0.1)}, on, cfg)  # decayed hard
    assert [e.wallet for e in r.watchlist] == ["0xA"]   # still kept
    assert r.removed == []


def test_tstat_decay_removes_even_in_keep_mode():
    # tstat gate is absolute (no hysteresis): losing skill removes regardless
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3, auto_remove=False)
    on = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), cfg).new_state
    r = run_discovery_cycle({"0xA": _ev("0xA", 2.0, tstat=4.0)}, on, cfg)
    assert r.watchlist == []
    assert r.removed == ["0xA"]


def test_cap_keeps_top_by_capture():
    evaluated = {f"0x{i}": _ev(f"0x{i}", float(i)) for i in range(1, 6)}  # cap=1..5
    r = run_discovery_cycle(evaluated, DiscoveryState(), CFG)  # cap=3
    assert [e.wallet for e in r.watchlist] == ["0x5", "0x4", "0x3"]
    assert len(r.newly_qualified) == 3


def test_flagged_wallet_not_starved_by_capture_heavy_wallets():
    # cap=3; three high-capture legacy wallets vs one theory-only wallet at
    # capture 0. A capture-only sort would bury the flagged wallet last and cap
    # it out — flag-count-first must keep it on paper so the theory is measured.
    evaluated = {
        "0xH1": Eval(wallet="0xH1", capture_cents=5.0, tstat=12.0),
        "0xH2": Eval(wallet="0xH2", capture_cents=4.0, tstat=12.0),
        "0xH3": Eval(wallet="0xH3", capture_cents=3.0, tstat=12.0),
        "0xF": Eval(wallet="0xF", capture_cents=0.0, tstat=2.0,
                    flagged_by=("1e",), reason="longshot calibration edge"),
    }
    r = run_discovery_cycle(evaluated, DiscoveryState(), CFG)  # cap=3
    papered = {e.wallet for e in r.watchlist}
    assert "0xF" in papered                      # flagged wallet keeps a slot
    assert r.watchlist[0].wallet == "0xF"         # ranked first (1 flag > 0 flags)
    assert len(r.watchlist) == 3                  # cap honoured (0xH3 dropped)


def test_capped_out_wallet_is_not_notified_or_papered():
    # 4 qualifiers, cap 3 -> the weakest is neither on watchlist nor "newly qualified"
    evaluated = {f"0x{i}": _ev(f"0x{i}", float(i + 1)) for i in range(4)}
    r = run_discovery_cycle(evaluated, DiscoveryState(), CFG)
    papered = {e.wallet for e in r.watchlist}
    assert "0x0" not in papered  # capture 1.0 weakest, capped out
    assert all(e.wallet in papered for e in r.newly_qualified)


def test_state_roundtrips_json():
    r = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), CFG)
    restored = DiscoveryState.from_json(r.new_state.to_json())
    assert set(restored.on_watchlist) == {"0xA"}
    assert restored.initialized is True


def test_targets_serialization_matches_watchlist_shape():
    r = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), CFG)
    out = watchlist_to_targets(r.watchlist, CFG)
    assert out["source"] == "discovery"
    assert out["targets"][0]["wallet"] == "0xA"
    assert out["targets"][0]["rank"] == 1
    assert "capture_cents" in out["targets"][0]
