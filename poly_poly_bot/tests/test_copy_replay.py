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
