"""Tests for the two-stage watchlist combine/filter/rank logic (pure)."""

from __future__ import annotations

from backtest.two_stage_watchlist import combine_and_rank
from src.copy_trading.lead_lag import WalletLeadLag
from src.copy_trading.trader_scoring import RankedMetrics, WalletMetrics


def _cand(addr, tstat_pnls):
    # pnls drive tstat; give enough capital/closed so roi etc. are well-defined
    m = WalletMetrics(capital=10000.0, pnl=sum(tstat_pnls),
                      n_closed=len(tstat_pnls), wins=sum(p > 0 for p in tstat_pnls),
                      pnls=list(tstat_pnls))
    return RankedMetrics(address=addr, metrics=m)


def _ll(capture_cents, lead_cents=None, n=10):
    # build a WalletLeadLag whose avg_capture == capture_cents/100
    w = WalletLeadLag()
    w.n = n
    w.capture_sum = (capture_cents / 100.0) * n
    w.lead_sum = ((lead_cents if lead_cents is not None else capture_cents) / 100.0) * n
    w.capture_wins = n if capture_cents > 0 else 0
    return w


def test_drops_uncopyable_below_threshold():
    a = _cand("0xA", [100, 120, 90])
    b = _cand("0xB", [100, 120, 90])
    ll = {"0xA": _ll(+5.0), "0xB": _ll(-3.0)}
    rows, stats = combine_and_rank([a, b], ll, min_capture_cents=0.5,
                                   keep_unscored=False, top_k=10)
    addrs = [rw.address for rw, _ in rows]
    assert addrs == ["0xA"]                 # B's capture below threshold -> dropped
    assert stats["dropped_uncopyable"] == 1
    assert stats["dropped_unscored"] == 0
    assert stats["final"] == 1


def test_ranks_by_capture_descending():
    a = _cand("0xA", [100, 100])
    b = _cand("0xB", [100, 100])
    c = _cand("0xC", [100, 100])
    ll = {"0xA": _ll(+2.0), "0xB": _ll(+9.0), "0xC": _ll(+5.0)}
    rows, _ = combine_and_rank([a, b, c], ll, min_capture_cents=0.0,
                               keep_unscored=False, top_k=10)
    assert [rw.address for rw, _ in rows] == ["0xB", "0xC", "0xA"]


def test_unscored_dropped_by_default_kept_with_flag():
    a = _cand("0xA", [100, 100])
    b = _cand("0xB", [50, 50])           # lower t-stat, no lead-lag data
    ll = {"0xA": _ll(+3.0), "0xB": None}

    rows, stats = combine_and_rank([a, b], ll, min_capture_cents=0.0,
                                   keep_unscored=False, top_k=10)
    assert [rw.address for rw, _ in rows] == ["0xA"]
    assert stats["dropped_unscored"] == 1

    rows2, stats2 = combine_and_rank([a, b], ll, min_capture_cents=0.0,
                                     keep_unscored=True, top_k=10)
    # scored wallet ranks above unscored; unscored still present
    assert [rw.address for rw, _ in rows2] == ["0xA", "0xB"]
    assert rows2[1][1] is None
    assert stats2["dropped_unscored"] == 0


def test_top_k_caps_output():
    cands = [_cand(f"0x{i}", [100, 100]) for i in range(5)]
    ll = {f"0x{i}": _ll(float(i + 1)) for i in range(5)}  # captures 1..5¢
    rows, stats = combine_and_rank(cands, ll, min_capture_cents=0.0,
                                   keep_unscored=False, top_k=2)
    # highest captures kept: 0x4 (5¢), 0x3 (4¢)
    assert [rw.address for rw, _ in rows] == ["0x4", "0x3"]
    assert stats["final"] == 2


def test_unscored_among_kept_ordered_by_tstat():
    # two unscored wallets kept -> ordered by t-stat (more pnls, higher mean = higher t)
    a = _cand("0xHI", [100, 110, 105, 95])      # tight, high t-stat
    b = _cand("0xLO", [10, -200, 300])          # noisy, low t-stat
    ll = {"0xHI": None, "0xLO": None}
    rows, _ = combine_and_rank([b, a], ll, min_capture_cents=0.0,
                               keep_unscored=True, top_k=10)
    assert [rw.address for rw, _ in rows] == ["0xHI", "0xLO"]
