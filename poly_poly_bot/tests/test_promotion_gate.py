"""Tests for the trustworthy promotion gate — statistical floor + demote rigor.

The load-bearing cases (the manager's both-directions DONE gate):
  * a fake-edge wallet (concentrated / decaying) generates NO offer;
  * a +EV LONGSHOT (low win rate, positive ROI, well-distributed) is NOT blocked;
  * demote fires on a real loser but not on micro-capital noise.
"""

from __future__ import annotations

from src.copy_trading import promotion_gate as pg
from src.copy_trading.copy_paper import PaperPosition

FLOOR = dict(
    min_n=15, min_roi=0.10, min_tstat=0.0,
    min_second_half_roi=-0.10, min_conditions=8, min_categories=3,
)
DEMOTE = dict(min_n=15, max_roi=-0.05, min_abs_loss=5.0, max_wilson=0.50)


def pos(target, i, *, pnl, spent=10.0, entry=0.5, won=None,
        condition=None, category=None, closed_ts=None):
    """A settled paper position with per-bet knobs for the floor's checks."""
    return PaperPosition(
        copy_id=f"{target}-{i}", target=target,
        condition_id=condition if condition is not None else f"c{i}",
        token_id=f"T{i}", outcome_index=0,
        category=category if category is not None else f"cat{i % 4}",
        their_price=entry, entry_price=entry, shares=spent / entry, spent=spent,
        drag_bps=0, opened_ts=float(i), closed=True,
        won=(pnl > 0) if won is None else won, pnl=pnl,
        closed_ts=float(closed_ts if closed_ts is not None else i),
    )


def _clean_positive(target="0x" + "a" * 40, n=15):
    """A steady, diversified, positive edge — should clear the floor."""
    # distinct condition per bet, categories cycle over 4, small positive pnl.
    return [pos(target, i, pnl=1.2, spent=10.0, entry=0.5) for i in range(n)]


# --------------------------------------------------------------------------- #
# compute_stats
# --------------------------------------------------------------------------- #

def test_compute_stats_basic():
    s = pg.compute_stats("0xA", _clean_positive("0xA", 15))
    assert s.n_closed == 15
    assert s.wins == 15 and s.losses == 0
    assert round(s.roi, 3) == 0.12            # +1.2 on 10 spent
    assert s.roi_tstat > 0                     # all-positive returns => strong +edge
    assert s.distinct_conditions == 15
    assert s.distinct_categories == 4


def test_compute_stats_empty_is_safe():
    s = pg.compute_stats("0xA", [])
    assert s.n_closed == 0 and s.roi is None and s.roi_tstat == 0.0


def test_compute_stats_ignores_zero_spent():
    ps = _clean_positive("0xA", 15) + [pos("0xA", 99, pnl=0.0, spent=0.0)]
    s = pg.compute_stats("0xA", ps)
    assert s.n_closed == 15                     # the zero-capital row is dropped


def test_compute_stats_tstat_is_finite_json_safe():
    import json
    import math
    # identical positive returns => zero variance => degenerate t-stat, must be
    # a FINITE value (json-standard, no inf) so the history log stays valid JSON.
    ps = [pos("0xA", i, pnl=1.0, spent=10.0, condition=f"c{i}", category=f"k{i % 4}")
          for i in range(15)]
    s = pg.compute_stats("0xA", ps)
    assert math.isfinite(s.roi_tstat) and s.roi_tstat > 0
    json.dumps({"roi_tstat": s.roi_tstat})        # must not emit Infinity


def test_compute_stats_never_raises_on_malformed():
    from types import SimpleNamespace
    junk = [
        SimpleNamespace(spent="oops", pnl="bad", won=True),       # non-numeric
        SimpleNamespace(spent=None, pnl=None, won=None),          # None fields
        SimpleNamespace(),                                        # missing attrs
    ]
    s = pg.compute_stats("0xA", junk)             # must not raise
    assert s.n_closed == 0                         # nothing had valid capital


# --------------------------------------------------------------------------- #
# evaluate_floor — the block direction
# --------------------------------------------------------------------------- #

def test_floor_passes_clean_positive():
    s = pg.compute_stats("0xA", _clean_positive("0xA", 15))
    r = pg.evaluate_floor(s, **FLOOR)
    assert r.passed is True and r.reasons == []


def test_floor_holds_too_few():
    s = pg.compute_stats("0xA", _clean_positive("0xA", 10))
    r = pg.evaluate_floor(s, **FLOOR)
    assert r.passed is False
    assert any("settled copies" in x for x in r.reasons)


def test_floor_holds_low_roi():
    ps = [pos("0xA", i, pnl=0.2, spent=10.0) for i in range(15)]   # +2% ROI
    r = pg.evaluate_floor(pg.compute_stats("0xA", ps), **FLOOR)
    assert r.passed is False
    assert any("copy ROI" in x for x in r.reasons)


def test_floor_holds_concentrated():
    # 15 winning bets but all on ONE market and ONE category -> correlated.
    ps = [pos("0xA", i, pnl=1.2, spent=10.0, condition="cSAME", category="sports")
          for i in range(15)]
    r = pg.evaluate_floor(pg.compute_stats("0xA", ps), **FLOOR)
    assert r.passed is False
    assert any("concentrated" in x for x in r.reasons)


def test_floor_holds_decaying_edge():
    # strong first half, reversed second half -> nets positive but decaying.
    first = [pos("0xA", i, pnl=3.0, spent=10.0, condition=f"c{i}", category=f"k{i % 4}",
                 closed_ts=i) for i in range(8)]
    second = [pos("0xA", 8 + i, pnl=-2.5, spent=10.0, condition=f"d{i}",
                  category=f"k{i % 4}", closed_ts=8 + i) for i in range(8)]
    s = pg.compute_stats("0xA", first + second)
    assert s.roi > 0                            # still net-positive overall
    r = pg.evaluate_floor(s, **FLOOR)
    assert r.passed is False
    assert any("decaying" in x for x in r.reasons)


def test_floor_tstat_hard_floor_when_configured():
    # noisy positive edge: passes at default tstat=0, held once a positive floor is set.
    ps = []
    for i in range(20):
        win = i % 3 != 0                        # ~2/3 win; ROI ~+11% (clears floor)
        ps.append(pos("0xA", i, pnl=(2.0 if win else -0.5), spent=10.0,
                      condition=f"c{i}", category=f"k{i % 4}"))
    s = pg.compute_stats("0xA", ps)
    assert s.roi >= 0.10                         # not held on ROI — isolate the t-stat
    assert pg.evaluate_floor(s, **FLOOR).passed is True          # default 0.0
    strict = {**FLOOR, "min_tstat": 5.0}
    assert pg.evaluate_floor(s, **strict).passed is False


# --------------------------------------------------------------------------- #
# evaluate_floor — the DON'T-block-longshots direction (the key case)
# --------------------------------------------------------------------------- #

def test_floor_passes_positive_longshot_low_winrate():
    """A +EV longshot: wins ~35% of the time at ~30¢ entries (payout ~3.3x),
    positive ROI, spread across markets. It MUST clear the floor — a win-rate
    gate would wrongly hold exactly this wallet."""
    target = "0x" + "c" * 40
    ps = []
    # 18 bets, 7 wins / 11 losses = 39% hit; win pays +23.3 on 10 spent, loss -10.
    outcomes = [True] * 7 + [False] * 11
    # interleave so both halves carry wins (diversified in time too)
    interleaved = []
    w = [o for o in outcomes if o]
    l = [o for o in outcomes if not o]
    while w or l:
        if l:
            interleaved.append(l.pop())
        if w:
            interleaved.append(w.pop())
        if l:
            interleaved.append(l.pop())
    for i, won in enumerate(interleaved):
        ps.append(pos(target, i, pnl=(23.3 if won else -10.0), spent=10.0,
                      entry=0.30, won=won, condition=f"c{i}", category=f"k{i % 5}"))
    s = pg.compute_stats(target, ps)
    assert s.roi > 0.10                          # genuinely +EV
    assert (s.wins / s.n_closed) < 0.5           # and a LOSING win rate by design
    r = pg.evaluate_floor(s, **FLOOR)
    assert r.passed is True, r.reasons           # not blocked
    # its win-rate CI is below breakeven -> surfaced as a non-blocking warning
    assert any("win-rate" in w for w in r.warnings)


# --------------------------------------------------------------------------- #
# should_demote — symmetric rigor
# --------------------------------------------------------------------------- #

def test_demote_real_loser():
    ps = [pos("0xB", i, pnl=-1.0, spent=10.0) for i in range(15)]   # -10% ROI, -$15
    s = pg.compute_stats("0xB", ps)
    demote, reason = pg.should_demote(s, **DEMOTE)
    assert demote is True and reason


def test_demote_skips_microcapital_noise():
    # 15 bets on tiny capital, net a few cents negative -> noise, not a proven loser.
    ps = [pos("0xB", i, pnl=-0.02, spent=0.30) for i in range(15)]
    s = pg.compute_stats("0xB", ps)
    demote, reason = pg.should_demote(s, **DEMOTE)
    assert demote is False
    assert "noise" in reason


def test_demote_skips_when_winrate_holds_up():
    # negative ROI from a couple big losses but wins most bets -> hold, not demote.
    ps = [pos("0xB", i, pnl=0.5, spent=10.0) for i in range(13)]           # 13 small wins
    ps += [pos("0xB", 13 + i, pnl=-40.0, spent=10.0, won=False) for i in range(2)]  # 2 big losses
    s = pg.compute_stats("0xB", ps)
    assert s.roi < -0.05 and s.net_pnl < -5.0
    demote, reason = pg.should_demote(s, **DEMOTE)
    assert demote is False
    assert "win-rate holds up" in reason


def test_demote_skips_too_few():
    ps = [pos("0xB", i, pnl=-2.0, spent=10.0) for i in range(10)]
    demote, _ = pg.should_demote(pg.compute_stats("0xB", ps), **DEMOTE)
    assert demote is False
