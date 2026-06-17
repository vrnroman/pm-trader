"""Entry-price discipline (copy-selection quality gate).

A wallet's realized ROI doesn't say *where* it enters. Tail buys ($0.90+) are
un-copyable settlement-lag scooping (INSIDER_FINDINGS); the copyable edge lives
in the middle of the book. These tests pin the USD-weighted profile and the
discipline filter on hand-built activity.
"""

from __future__ import annotations

from src.copy_trading.entry_profile import (
    EntryProfile,
    entry_profile,
    is_copyable_entry,
)


def _buy(price, usd):
    return {"type": "TRADE", "side": "BUY", "price": price, "usdcSize": usd}


def test_is_copyable_entry_band():
    assert is_copyable_entry(0.5)
    assert is_copyable_entry(0.05) and is_copyable_entry(0.95)  # inclusive band
    assert not is_copyable_entry(0.98)   # near-certain tail — the user's example
    assert not is_copyable_entry(0.01)   # dust longshot


def test_profile_is_usd_weighted_not_count_weighted():
    # one huge tail bet + many tiny middle bets → tail dominates by dollars
    acts = [_buy(0.97, 10_000)] + [_buy(0.5, 100) for _ in range(5)]
    p = entry_profile(acts)
    assert p.n_buys == 6
    assert p.tail_ratio > 0.9                 # dollars, not the 1/6 count
    assert p.copyable_ratio < 0.1
    assert not p.is_disciplined()             # tail-dominated → rejected


def test_disciplined_wallet_passes():
    acts = [_buy(0.4, 1000), _buy(0.6, 1000), _buy(0.55, 2000)]
    p = entry_profile(acts)
    assert p.copyable_ratio == 1.0
    assert p.tail_ratio == 0.0
    assert abs(p.mean_entry - (0.4 * 1000 + 0.6 * 1000 + 0.55 * 2000) / 4000) < 1e-9
    assert p.is_disciplined()


def test_non_buy_and_dust_ignored():
    acts = [
        _buy(0.5, 1000),
        {"type": "TRADE", "side": "SELL", "price": 0.9, "usdcSize": 5000},  # not a buy
        {"type": "REDEEM", "price": 1.0, "usdcSize": 9000},                 # not a trade
        _buy(0.8, 50),                                                      # dust (min_usd)
    ]
    p = entry_profile(acts, min_usd=100)
    assert p.n_buys == 1
    assert p.mean_entry == 0.5


def test_empty_profile():
    assert entry_profile([]) == EntryProfile()
    assert not EntryProfile().is_disciplined()
