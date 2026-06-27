"""Tests for the copy-replay selection scorer (the ROI-leak fix).

Selection must measure the SAME action the live harness takes — copy a wallet's
copyable BUYs and hold to resolution — not the wallet's own closed-position ROI.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.copy_trading.copy_replay import (
    CopyReplayScore,
    copy_and_hold_rois,
    exit_follow_rois,
    forward_copy_rois,
    proven_negative,
    proven_positive,
    score_copy_replay,
)


def _buy(cid="C", oi=0, price=0.5, usd=1000.0, won=None, ts=1.0):
    return SimpleNamespace(condition_id=cid, outcome_index=oi, price=price,
                           usd=usd, won=won, ts=ts)


def _trip(entry=0.50, exit=0.60):
    return SimpleNamespace(entry_price=entry, exit_price=exit)


# --------------------------------------------------------------------------- #
# copy_and_hold_rois
# --------------------------------------------------------------------------- #

def test_hold_win_pays_inverse_price():
    # buy at 0.50, won -> ROI/$ = 1/0.50 - 1 = +1.0
    assert copy_and_hold_rois([_buy(price=0.50, won=True)]) == [1.0]


def test_hold_loss_is_minus_one():
    assert copy_and_hold_rois([_buy(price=0.50, won=False)]) == [-1.0]


def test_unresolved_buys_skipped():
    assert copy_and_hold_rois([_buy(won=None)]) == []


def test_non_copyable_band_skipped():
    # 0.97 is a near-lock (settlement-lag scoop) — outside the copyable band
    assert copy_and_hold_rois([_buy(price=0.97, won=True)]) == []
    # 0.02 is a dust longshot
    assert copy_and_hold_rois([_buy(price=0.02, won=True)]) == []


def test_min_usd_filter():
    assert copy_and_hold_rois([_buy(usd=100.0, won=True)], min_usd=500.0) == []


def test_first_entry_only_dedups_adds():
    # two buys into the same (market, outcome); only the FIRST entry counts
    buys = [_buy(cid="C", oi=0, price=0.50, won=True, ts=1.0),
            _buy(cid="C", oi=0, price=0.80, won=True, ts=2.0)]
    assert copy_and_hold_rois(buys, first_entry_only=True) == [1.0]   # 1/0.50-1
    # with the dedup off, both count
    assert len(copy_and_hold_rois(buys, first_entry_only=False)) == 2


def test_first_entry_keeps_distinct_markets():
    buys = [_buy(cid="A", won=True, ts=1.0), _buy(cid="B", won=False, ts=2.0)]
    assert sorted(copy_and_hold_rois(buys)) == [-1.0, 1.0]


# --------------------------------------------------------------------------- #
# exit_follow_rois
# --------------------------------------------------------------------------- #

def test_exit_follow_roi():
    (roi,) = exit_follow_rois([_trip(0.50, 0.60)])   # 0.60/0.50 - 1
    assert abs(roi - 0.2) < 1e-9


def test_exit_follow_skips_tail_entry():
    assert exit_follow_rois([_trip(0.97, 0.99)]) == []


# --------------------------------------------------------------------------- #
# score_copy_replay + verdicts
# --------------------------------------------------------------------------- #

def test_score_aggregates_and_tstats():
    buys = [_buy(cid="A", price=0.50, won=True, ts=1),
            _buy(cid="B", price=0.50, won=True, ts=2),
            _buy(cid="D", price=0.50, won=False, ts=3)]
    s = score_copy_replay(buys, [_trip(0.5, 0.6)], min_usd=500.0)
    assert s.n == 3
    assert abs(s.hit_rate - 2 / 3) < 1e-3   # rounded to 4dp
    # rois = [1.0, 1.0, -1.0] -> mean +1/3
    assert abs(s.mean_roi - (1.0 / 3)) < 1e-3
    assert s.exit_n == 1
    assert abs(s.exit_mean_roi - 0.2) < 1e-3


def test_proven_negative_favorite_scalper():
    # the failure mode: mostly losing copies held to resolution
    buys = [_buy(cid=str(i), price=0.6, won=(i < 4), ts=i) for i in range(20)]
    s = score_copy_replay(buys, min_usd=500.0)
    assert s.n == 20
    assert s.is_proven_negative(min_n=12, min_roi=0.0) is True
    assert proven_positive(s.n, s.mean_roi, min_n=12, min_roi=0.0) is False
    assert s.fade_label(min_n=12, fade_roi=-0.10) == "FADE"


def test_proven_edge_winner():
    buys = [_buy(cid=str(i), price=0.5, won=(i % 2 == 0), ts=i) for i in range(20)]
    s = score_copy_replay(buys, min_usd=500.0)
    # 10 wins @ +1.0, 10 losses @ -1.0 -> mean 0.0; bar at -0.01 -> validated
    assert proven_positive(s.n, s.mean_roi, min_n=12, min_roi=-0.01) is True
    assert proven_negative(s.n, s.mean_roi, min_n=12, min_roi=-0.01) is False


def test_thin_sample_is_neither_proven():
    s = score_copy_replay([_buy(cid="A", won=True)], min_usd=500.0)
    assert s.n == 1
    assert s.is_proven_negative(min_n=12, min_roi=0.0) is False
    assert proven_positive(s.n, s.mean_roi, min_n=12, min_roi=0.0) is False


def test_empty_score_is_zero():
    assert score_copy_replay([], []) == CopyReplayScore()


# --------------------------------------------------------------------------- #
# forward_copy_rois (raw activity; shared with the backtest)
# --------------------------------------------------------------------------- #

def _res(idx):
    return SimpleNamespace(winning_index=idx)


def test_forward_resolution_fallback_when_held():
    acts = [{"type": "TRADE", "side": "BUY", "conditionId": "C", "outcomeIndex": 0,
             "price": 0.50, "usdcSize": 1000, "timestamp": 1}]
    rois = forward_copy_rois(acts, {"C": _res(0)}, min_usd=100.0)
    assert rois == [1.0]   # held to resolution, won


def test_forward_exit_following_closes_on_sell():
    acts = [
        {"type": "TRADE", "side": "BUY", "conditionId": "C", "outcomeIndex": 0,
         "price": 0.50, "usdcSize": 1000, "timestamp": 1},
        {"type": "TRADE", "side": "SELL", "conditionId": "C", "outcomeIndex": 0,
         "price": 0.60, "size": 100, "timestamp": 5},
    ]
    rois = forward_copy_rois(acts, {}, min_usd=100.0)
    assert abs(rois[0] - 0.2) < 1e-9   # exit at 0.60 / entry 0.50


def test_forward_follow_exits_false_uses_resolution():
    acts = [
        {"type": "TRADE", "side": "BUY", "conditionId": "C", "outcomeIndex": 0,
         "price": 0.50, "usdcSize": 1000, "timestamp": 1},
        {"type": "TRADE", "side": "SELL", "conditionId": "C", "outcomeIndex": 0,
         "price": 0.60, "size": 100, "timestamp": 5},
    ]
    # ignore the exit; score on resolution (won)
    rois = forward_copy_rois(acts, {"C": _res(0)}, min_usd=100.0, follow_exits=False)
    assert rois == [1.0]


def test_forward_slippage_makes_entry_worse():
    acts = [{"type": "TRADE", "side": "BUY", "conditionId": "C", "outcomeIndex": 0,
             "price": 0.50, "usdcSize": 1000, "timestamp": 1}]
    rois = forward_copy_rois(acts, {"C": _res(0)}, min_usd=100.0, slippage_bps=200)
    # entry 0.50*1.02 = 0.51 -> 1/0.51 - 1 ~ +0.9608, less than the drag-free +1.0
    assert rois[0] < 1.0 and rois[0] > 0.9


# --------------------------------------------------------------------------- #
# Per-(wallet, category) selection — "winning markets only" (item A)
# --------------------------------------------------------------------------- #

from src.copy_trading.copy_cost import CostModel  # noqa: E402
from src.copy_trading.copy_replay import (  # noqa: E402
    approved_category_set,
    copy_and_hold_rois_by_category,
    select_copyable_categories,
)


def _cbuy(cid, cat, price=0.5, won=True, usd=1000.0, oi=0, ts=1.0):
    return SimpleNamespace(condition_id=cid, outcome_index=oi, price=price,
                           usd=usd, won=won, ts=ts, category=cat)


def test_rois_bucketed_by_category():
    buys = [_cbuy("A", "crypto", price=0.5, won=True),
            _cbuy("B", "sports", price=0.5, won=False)]
    out = copy_and_hold_rois_by_category(buys)
    assert out == {"crypto": [1.0], "sports": [-1.0]}


def test_missing_category_defaults_to_other():
    b = SimpleNamespace(condition_id="A", outcome_index=0, price=0.5, usd=1000.0,
                        won=True, ts=1.0)  # no category attr
    assert copy_and_hold_rois_by_category([b]) == {"other": [1.0]}


def _winning_buys(cat, n, price=0.5):
    # n winning copies in `cat`, each its own market -> mean ROI = 1/price - 1
    return [_cbuy(f"{cat}{i}", cat, price=price, won=True) for i in range(n)]


def test_category_approved_when_edge_clears_floor_and_n():
    cost = CostModel(category_cost={"crypto": 0.05}, fallback=0.10, margin=0.03)
    # 10 crypto wins at 0.5 -> mean ROI +1.0, floor = 0.05+0.03 = 0.08 -> approved
    edges = select_copyable_categories(_winning_buys("crypto", 10), cost, min_n=8)
    assert edges["crypto"].approved is True
    assert edges["crypto"].n == 10
    assert edges["crypto"].net_roi > 0


def test_category_rejected_when_sample_too_small():
    # the n=10-crypto-trap guard: a tiny lucky category is NOT promotable
    cost = CostModel(fallback=0.10, margin=0.03)
    edges = select_copyable_categories(_winning_buys("crypto", 5), cost, min_n=8)
    assert edges["crypto"].n == 5
    assert edges["crypto"].approved is False   # below min_n


def test_category_rejected_when_edge_below_cost():
    # buys at 0.95 -> win ROI = 1/0.95-1 ~= +0.053, below sports floor 0.12+0.03
    cost = CostModel(category_cost={"sports": 0.12}, margin=0.03)
    edges = select_copyable_categories(_winning_buys("sports", 12, price=0.95), cost, min_n=8)
    assert edges["sports"].n == 12
    assert edges["sports"].approved is False   # edge can't clear the spread


def test_approved_set_filters_to_winners():
    cost = CostModel(category_cost={"crypto": 0.05, "sports": 0.12}, margin=0.03)
    buys = _winning_buys("crypto", 10) + _winning_buys("sports", 10, price=0.95)
    edges = select_copyable_categories(buys, cost, min_n=8)
    assert approved_category_set(edges) == frozenset({"crypto"})


def test_losing_category_not_approved():
    cost = CostModel(fallback=0.10, margin=0.03)
    losers = [_cbuy(f"s{i}", "sports", price=0.5, won=False) for i in range(12)]
    edges = select_copyable_categories(losers, cost, min_n=8)
    assert edges["sports"].mean_roi == -1.0
    assert edges["sports"].approved is False
