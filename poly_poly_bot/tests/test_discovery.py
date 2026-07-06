"""Tests for the pure discovery state machine."""

from __future__ import annotations

from src.copy_trading.discovery import (
    DiscoveryConfig,
    DiscoveryState,
    Eval,
    long_horizon_to_targets,
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


# --- money-curve gates (RCA 2026-07 scooper fix) --------------------------- #

# ship-config: the money-curve gates ON at the conservative production thresholds.
SHIP = DiscoveryConfig(
    min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
    watchlist_cap=5, auto_remove=True,
    max_tail_ratio=0.4, max_curve_drawdown=1.5, max_hit_rate=0.95, min_curve_n=20,
)


def _scooper_dd(w="0xDD"):
    # flashy stats (t-stat 25, 98% hit) but a catastrophic dollar curve — the
    # exact near-$1 settlement-lag scooper the LLM kept rejecting.
    return Eval(wallet=w, capture_cents=2.0, tstat=25.0, n=30, n_closed=100,
                curve_drawdown=1.87, curve_sharpe=-0.3, net_pnl=-3000.0,
                closed_hit_rate=0.98)


def _good_highvar(w="0xGV"):
    # the population we WANT: real risk, ~62% hit, positive money curve, modest DD.
    return Eval(wallet=w, capture_cents=2.0, tstat=12.0, n=30, n_closed=100,
                curve_drawdown=0.6, curve_sharpe=0.8, net_pnl=5000.0,
                closed_hit_rate=0.62)


def test_backward_safe_scooper_admitted_at_legacy_values():
    # C1: at legacy knob values (CFG leaves the new gates OFF) the scooper still
    # qualifies exactly as before — the new gates are pure no-ops until turned on.
    r = run_discovery_cycle({"0xDD": _scooper_dd()}, DiscoveryState(), CFG)
    assert [e.wallet for e in r.watchlist] == ["0xDD"]


def test_drawdown_ceiling_rejects_scooper():
    r = run_discovery_cycle({"0xDD": _scooper_dd()}, DiscoveryState(), SHIP)
    assert r.watchlist == []


def test_hit_suspicion_rejects_high_hit_loser_but_not_winner():
    # high hit + losing/spiky curve -> scooper -> rejected; high hit + WINNING
    # curve -> genuine winner -> admitted (the AND guards the false positive).
    loser = Eval(wallet="0xHL", capture_cents=2.0, tstat=25.0, n=30, n_closed=100,
                 curve_drawdown=0.5, curve_sharpe=-0.1, net_pnl=-500.0,
                 closed_hit_rate=0.99)
    winner = Eval(wallet="0xHW", capture_cents=2.0, tstat=25.0, n=30, n_closed=100,
                  curve_drawdown=0.3, curve_sharpe=1.2, net_pnl=5000.0,
                  closed_hit_rate=0.98)
    r = run_discovery_cycle({"0xHL": loser, "0xHW": winner}, DiscoveryState(), SHIP)
    assert [e.wallet for e in r.watchlist] == ["0xHW"]


def test_good_high_variance_wallet_not_rejected():
    # the FP guard the RCA left unmeasured: a genuinely-good higher-variance
    # informed trader must survive every new gate.
    r = run_discovery_cycle({"0xGV": _good_highvar()}, DiscoveryState(), SHIP)
    assert [e.wallet for e in r.watchlist] == ["0xGV"]


def test_curve_gates_skip_thin_book_insufficient_evidence():
    # n_closed below min_curve_n -> the drawdown/hit gates DON'T fire (a thin,
    # noisy book is never rejected on curve shape; it keeps accruing evidence).
    thin = Eval(wallet="0xTH", capture_cents=2.0, tstat=25.0, n=30, n_closed=5,
                curve_drawdown=3.0, curve_sharpe=-0.5, net_pnl=-100.0,
                closed_hit_rate=0.99)
    r = run_discovery_cycle({"0xTH": thin}, DiscoveryState(), SHIP)
    assert [e.wallet for e in r.watchlist] == ["0xTH"]


def test_discovery_replay_roi_independent_of_promote_floor():
    # C3: the discovery copy-replay bar (+0.02, paper) must never be the
    # real-money promote floor (+0.10). Distinct config knobs, distinct code paths.
    from src.config import CONFIG
    assert CONFIG.wallet_discovery_min_copy_replay_roi == 0.02
    assert CONFIG.copy_promote_min_roi == 0.10
    assert (CONFIG.wallet_discovery_min_copy_replay_roi
            != CONFIG.copy_promote_min_roi)


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
    # copy-replay selection signal is serialized for the harness + observability
    assert "copy_roi" in out["targets"][0]
    assert "copy_n" in out["targets"][0]
    assert "fade" in out["targets"][0]


# --------------------------------------------------------------------------- #
# Copy-replay selection gate + rank (the ROI-leak fix)
# --------------------------------------------------------------------------- #

def test_copy_replay_gate_drops_proven_negative_wallet():
    # a theory likes it, but replaying our copy action (hold to resolution) over
    # enough resolved bets proves it loses — drop it regardless of the flag.
    bad = Eval(wallet="0xBAD", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
               copy_n=15, copy_roi=-0.30)
    assert run_discovery_cycle({"0xBAD": bad}, DiscoveryState(), CFG).watchlist == []


def test_copy_replay_thin_sample_is_not_dropped():
    # too few resolved replayed copies to judge -> insufficient evidence, keep it
    thin = Eval(wallet="0xTHIN", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
                copy_n=5, copy_roi=-0.30)
    r = run_discovery_cycle({"0xTHIN": thin}, DiscoveryState(), CFG)
    assert [e.wallet for e in r.watchlist] == ["0xTHIN"]


def test_copy_validated_wallet_ranks_above_higher_flag_count():
    # 0xVAL has a PROVEN positive copy-and-hold edge; 0xMULTI has more theory
    # flags + capture but no replay data. Copy-validated must rank first.
    val = Eval(wallet="0xVAL", flagged_by=("1b",), tstat=12.0, capture_cents=0.0,
               copy_n=20, copy_roi=0.50, approved_categories=("sports",))
    multi = Eval(wallet="0xMULTI", flagged_by=("1b", "1c", "1g"), tstat=12.0,
                 capture_cents=5.0)
    r = run_discovery_cycle({"0xVAL": val, "0xMULTI": multi}, DiscoveryState(), CFG)
    assert r.watchlist[0].wallet == "0xVAL"
    assert {e.wallet for e in r.watchlist} == {"0xVAL", "0xMULTI"}


def test_copy_replay_gate_off_keeps_negative_wallet():
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3,
                          copy_replay_gate=False,
                          # isolate the copy-replay gate from the orthogonal
                          # winning-markets gate (tested separately)
                          require_approved_category=False)
    bad = Eval(wallet="0xBAD", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
               copy_n=15, copy_roi=-0.30)
    r = run_discovery_cycle({"0xBAD": bad}, DiscoveryState(), cfg)
    assert [e.wallet for e in r.watchlist] == ["0xBAD"]  # gate disabled -> legacy path


# --------------------------------------------------------------------------- #
# Strategy 4 — long-horizon wallets tracked alongside the copy funnel (dual
# membership: a wallet can feed the copier AND the long-horizon book at once)
# --------------------------------------------------------------------------- #

S4_CFG = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0, drop_capture_cents=1.0,
                         watchlist_cap=3, s4_enabled=True, long_horizon_cap=3)


def test_strategy4_default_off_keeps_long_horizon_in_copy_funnel():
    # with s4 disabled (default), a long-horizon-flagged wallet still flows through
    # the near-term path unchanged and the long-horizon list stays empty — opt-in.
    lh = Eval(wallet="0xLH", capture_cents=2.0, tstat=12.0, long_horizon=True)
    r = run_discovery_cycle({"0xLH": lh}, DiscoveryState(), CFG)  # CFG has s4 off
    assert [e.wallet for e in r.watchlist] == ["0xLH"]
    assert r.long_horizon == []


def test_strategy4_dual_membership_wallet_on_both_lists():
    # a wallet that is BOTH near-term-copyable AND carries a long book appears on
    # the copy watchlist *and* the long-horizon list — the long-horizon track no
    # longer peels it off the copier (its short bets are still copied).
    near = _ev("0xN", 2.0)                                  # near-term only
    both = Eval(wallet="0xB", capture_cents=2.0, tstat=12.0, long_horizon=True,
                long_horizon_ratio=0.8, horizon_days=300)
    r = run_discovery_cycle({"0xN": near, "0xB": both}, DiscoveryState(), S4_CFG)
    assert "0xB" in [e.wallet for e in r.watchlist]        # still in the copy funnel
    assert [e.wallet for e in r.long_horizon] == ["0xB"]   # AND on the long track


def test_strategy4_list_ranked_by_horizon_and_capped():
    evals = {
        f"0x{i}": Eval(wallet=f"0x{i}", long_horizon=True,
                       long_horizon_ratio=r, horizon_days=100 * i)
        for i, r in enumerate([0.6, 0.9, 0.7, 0.95], start=1)
    }
    res = run_discovery_cycle(evals, DiscoveryState(), S4_CFG)  # long_horizon_cap=3
    # ranked by long_horizon_ratio desc (0.95, 0.9, 0.7), capped at 3
    assert [e.wallet for e in res.long_horizon] == ["0x4", "0x2", "0x3"]


def test_strategy4_long_only_wallet_tracked_without_copy_gates():
    # a purely long-horizon wallet has no closed markets / copy-replay data and
    # won't pass the copy funnel — it's still tracked on the long-horizon list.
    longh = Eval(wallet="0xLH", capture_cents=0.0, tstat=0.0, long_horizon=True,
                 long_horizon_ratio=0.9, horizon_days=400)
    r = run_discovery_cycle({"0xLH": longh}, DiscoveryState(), S4_CFG)
    assert r.watchlist == []
    assert [e.wallet for e in r.long_horizon] == ["0xLH"]


def test_long_horizon_serialization_is_distinct_source():
    longh = Eval(wallet="0xLH", strategy="4", long_horizon=True,
                 long_horizon_ratio=0.8, horizon_days=300)
    out = long_horizon_to_targets([longh], S4_CFG)
    assert out["source"] == "discovery_long_horizon"   # not the copy watchlist
    assert out["targets"][0]["wallet"] == "0xLH"
    assert out["targets"][0]["strategy"] == "4"
    assert out["targets"][0]["long_horizon"] is True
    assert out["targets"][0]["long_horizon_ratio"] == 0.8


def test_watchlist_meta_includes_strategy_tag():
    r = run_discovery_cycle({"0xA": _ev("0xA", 2.0)}, DiscoveryState(), CFG)
    out = watchlist_to_targets(r.watchlist, CFG)
    assert out["targets"][0]["strategy"] == "1"        # near-term by default
    assert "long_horizon_ratio" in out["targets"][0]


# --------------------------------------------------------------------------- #
# Winning-markets-only gate + serialization (item A)
# --------------------------------------------------------------------------- #

def test_drops_wallet_with_replay_data_but_no_winning_market():
    # a category reached min_category_n (a fair chance) yet none cleared the cost
    # floor -> nowhere profitable to copy -> drop.
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3,
                          min_category_n=8)
    e = Eval(wallet="0xNW", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
             copy_n=20, copy_roi=0.10, approved_categories=(),
             category_edges=(("sports", 12, -0.30, False),))
    r = run_discovery_cycle({"0xNW": e}, DiscoveryState(), cfg)
    assert r.watchlist == []


def test_diversified_wallet_not_dropped_before_a_category_matures():
    # 8+ total copies but spread across categories, NONE at min_category_n yet ->
    # must NOT be dropped (it should keep accruing until one category matures).
    # Regression: gating the drop on whole-wallet copy_n permanently excluded
    # diversified wallets.
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3, min_category_n=8)
    e = Eval(wallet="0xDV", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
             copy_n=9, copy_roi=0.10, approved_categories=(),
             category_edges=(("crypto", 4, 0.2, False), ("sports", 3, -0.1, False),
                             ("research", 2, -0.3, False)))
    r = run_discovery_cycle({"0xDV": e}, DiscoveryState(), cfg)
    assert [w.wallet for w in r.watchlist] == ["0xDV"]


def test_keeps_wallet_with_a_winning_market():
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3,
                          min_category_n=8)
    e = Eval(wallet="0xWM", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
             copy_n=20, copy_roi=0.10, approved_categories=("crypto",))
    r = run_discovery_cycle({"0xWM": e}, DiscoveryState(), cfg)
    assert [w.wallet for w in r.watchlist] == ["0xWM"]


def test_thin_replay_wallet_not_dropped_by_category_gate():
    # below min_category_n -> insufficient evidence -> NOT dropped for lack of a
    # winning market (consistent with the copy-replay thin-sample rule).
    cfg = DiscoveryConfig(min_capture_cents=1.5, min_tstat=10.0,
                          drop_capture_cents=1.0, watchlist_cap=3, min_category_n=8)
    e = Eval(wallet="0xTH", flagged_by=("1g",), tstat=2.0, tail_ratio=0.1,
             copy_n=4, copy_roi=0.10, approved_categories=())
    r = run_discovery_cycle({"0xTH": e}, DiscoveryState(), cfg)
    assert [w.wallet for w in r.watchlist] == ["0xTH"]


def test_meta_serializes_winning_markets_fields():
    from src.copy_trading.discovery import _meta
    e = Eval(wallet="0xWM", approved_categories=("crypto", "research"),
             category_edges=(("crypto", 12, 0.40, True),), median_usd=1500.0)
    m = _meta(e)
    assert m["approved_categories"] == ["crypto", "research"]
    assert m["category_edges"] == [["crypto", 12, 0.40, True]]
    assert m["median_usd"] == 1500.0
