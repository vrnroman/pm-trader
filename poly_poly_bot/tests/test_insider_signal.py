"""Tests for the insider trade-shape signal (Strategy 1a)."""

from __future__ import annotations

import pytest

from src.copy_trading.insider_signal import (
    copy_pnl_per_dollar,
    hours_to_resolution,
    is_informed_early_bet,
    is_insider_shaped,
    prior_trade_count,
    trade_usd,
    wilson_interval,
)


def test_trade_usd_prefers_usdc_then_falls_back():
    assert trade_usd(50, 0.5, usdc_size=30) == 30          # explicit usdcSize
    assert trade_usd(50, 0.5, usdc_size=None) == 25.0      # fallback size*price
    assert trade_usd(50, 0.5, usdc_size=0) == 25.0         # null-ish usdc -> fallback


def test_prior_trade_count_only_counts_earlier_trades():
    acts = [
        {"type": "TRADE", "timestamp": 100},
        {"type": "TRADE", "timestamp": 200},
        {"type": "REDEEM", "timestamp": 150},   # not a trade
        {"type": "TRADE", "timestamp": 500},
    ]
    assert prior_trade_count(acts, before_ts=300) == 2
    assert prior_trade_count(acts, before_ts=100) == 0     # strictly before
    assert prior_trade_count(acts, before_ts=1000) == 3


def test_is_insider_shaped_requires_geo_size_and_youth():
    assert is_insider_shaped(prior_count=1, bet_usd=2000, is_geo=True)
    assert not is_insider_shaped(prior_count=1, bet_usd=2000, is_geo=False)   # not geo
    assert not is_insider_shaped(prior_count=50, bet_usd=2000, is_geo=True)   # veteran
    assert not is_insider_shaped(prior_count=1, bet_usd=100, is_geo=True)     # small


def test_is_insider_shaped_thresholds_configurable():
    assert is_insider_shaped(prior_count=8, bet_usd=600, is_geo=True,
                             max_prior=10, min_bet=500)
    assert not is_insider_shaped(prior_count=8, bet_usd=600, is_geo=True,
                                 max_prior=5, min_bet=500)


def test_hours_to_resolution():
    assert hours_to_resolution(1000.0, 1000.0 + 7200) == 2.0   # 2h before
    assert hours_to_resolution(1000.0, None) is None
    assert hours_to_resolution(1000.0, 0) is None
    assert hours_to_resolution(1000.0, 500.0) == pytest.approx(-0.1389, abs=1e-3)  # after


def test_is_informed_early_bet_drops_youth_and_geo_keeps_timing():
    # veteran (no prior_count arg at all), non-geo, large, mid-book, early → yes
    assert is_informed_early_bet(bet_usd=5000, entry_price=0.4,
                                 hours_before_resolution=72)
    # last-minute (settlement-lag scooping) → rejected even if large
    assert not is_informed_early_bet(bet_usd=5000, entry_price=0.4,
                                     hours_before_resolution=2)
    # tail entry (near-certain) → rejected even if early
    assert not is_informed_early_bet(bet_usd=5000, entry_price=0.97,
                                     hours_before_resolution=72)
    # too small → rejected
    assert not is_informed_early_bet(bet_usd=100, entry_price=0.4,
                                     hours_before_resolution=72)
    # unknown resolution time → can't confirm early → rejected
    assert not is_informed_early_bet(bet_usd=5000, entry_price=0.4,
                                     hours_before_resolution=None)


def test_is_informed_early_bet_thresholds_configurable():
    assert is_informed_early_bet(bet_usd=600, entry_price=0.5,
                                 hours_before_resolution=10,
                                 min_bet=500, min_hours=6)


def test_copy_pnl_per_dollar():
    # buy at 0.25 and win -> (1-0.25)/0.25 = 3.0 per $1
    assert abs(copy_pnl_per_dollar(0.25, True) - 3.0) < 1e-9
    assert copy_pnl_per_dollar(0.25, False) == -1.0
    # degenerate prices -> 0
    assert copy_pnl_per_dollar(0.0, True) == 0.0
    assert copy_pnl_per_dollar(1.0, True) == 0.0


def test_wilson_interval_bounds():
    lo, hi = wilson_interval(8, 10)
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0
    assert wilson_interval(0, 0) == (0.0, 0.0)
    # all wins -> upper bound 1.0, lower bound < 1
    lo, hi = wilson_interval(5, 5)
    assert hi == 1.0 and lo < 1.0
