"""Bet-horizon profiling — the rule that splits Strategy 1 from Strategy 4.

A wallet is Strategy 4 (tracked separately) when its bet dollars are dominated by
positions placed far before resolution; Strategy 1 (the copy funnel) otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.copy_trading.horizon_profile import (
    HorizonProfile,
    classify_strategy,
    horizon_profile,
    long_horizon_eligible,
)


@dataclass
class _Buy:
    """Minimal stand-in for wallet_context.Buy (only the fields the rule reads)."""

    usd: float
    hours_before_resolution: Optional[float]


def _buy(usd, days):
    return _Buy(usd=usd, hours_before_resolution=None if days is None else days * 24.0)


# --------------------------------------------------------------------------- #
# horizon_profile
# --------------------------------------------------------------------------- #
def test_empty_profile_for_no_dated_buys():
    p = horizon_profile([_buy(100, None), _buy(50, None)])
    assert p == HorizonProfile()
    assert p.n_dated_buys == 0


def test_long_ratio_is_usd_weighted():
    # one big far-future bet + two small near-term: by COUNT it's near-term-heavy,
    # but by DOLLARS it's long-horizon dominated.
    buys = [_buy(9000, 300), _buy(100, 10), _buy(100, 5)]
    p = horizon_profile(buys, long_horizon_days=180)
    assert p.n_dated_buys == 3
    assert p.n_long == 1
    assert p.long_ratio == 9000 / 9200       # dollar-weighted, not 1/3
    assert p.max_horizon_days == 300


def test_threshold_boundary_is_inclusive():
    at = horizon_profile([_buy(100, 180)], long_horizon_days=180)
    just_below = horizon_profile([_buy(100, 179)], long_horizon_days=180)
    assert at.long_ratio == 1.0              # >= cutoff counts as long-horizon
    assert just_below.long_ratio == 0.0


def test_non_positive_horizon_treated_as_undated():
    # a bet at/after the end date (clock skew / post-close) carries no horizon
    p = horizon_profile([_buy(100, 0), _buy(100, -5), _buy(100, 200)],
                        long_horizon_days=180)
    assert p.n_dated_buys == 1               # only the +200d bet is dated
    assert p.long_ratio == 1.0


def test_mean_and_median_horizon():
    p = horizon_profile([_buy(100, 10), _buy(100, 20), _buy(100, 300)])
    assert p.median_horizon_days == 20
    assert abs(p.mean_horizon_days - (10 + 20 + 300) / 3) < 1e-9


def test_zero_usd_buys_ignored():
    p = horizon_profile([_buy(0, 300), _buy(100, 10)], long_horizon_days=180)
    assert p.n_dated_buys == 1
    assert p.long_ratio == 0.0


# --------------------------------------------------------------------------- #
# classify_strategy
# --------------------------------------------------------------------------- #
def test_classify_none_below_min_dated_buys():
    p = horizon_profile([_buy(100, 300)] * 3, long_horizon_days=180)
    assert classify_strategy(p, min_dated_buys=5) is None   # not enough evidence


def test_classify_long_horizon_is_strategy_4():
    p = horizon_profile([_buy(100, 300)] * 6, long_horizon_days=180)
    assert classify_strategy(p, min_dated_buys=5, long_ratio_threshold=0.5) == "4"


def test_classify_near_term_is_strategy_1():
    p = horizon_profile([_buy(100, 10)] * 6, long_horizon_days=180)
    assert classify_strategy(p, min_dated_buys=5, long_ratio_threshold=0.5) == "1"


def test_classify_at_ratio_threshold_is_strategy_4():
    # exactly half the dollars are long-horizon -> meets the >= threshold
    buys = [_buy(100, 300)] * 3 + [_buy(100, 10)] * 3
    p = horizon_profile(buys, long_horizon_days=180)
    assert p.long_ratio == 0.5
    assert classify_strategy(p, min_dated_buys=5, long_ratio_threshold=0.5) == "4"


def test_classify_thresholds_are_configurable():
    p = horizon_profile([_buy(100, 300)] * 2 + [_buy(100, 10)] * 8,
                        long_horizon_days=180)
    assert p.long_ratio == 0.2
    # lenient ratio bar flips a 20%-long wallet to Strategy 4
    assert classify_strategy(p, min_dated_buys=5, long_ratio_threshold=0.5) == "1"
    assert classify_strategy(p, min_dated_buys=5, long_ratio_threshold=0.15) == "4"


# --------------------------------------------------------------------------- #
# long_horizon_eligible — the dual-membership gate (NOT exclusive with copy)
# --------------------------------------------------------------------------- #
def test_long_horizon_eligible_counts_distinct_long_buys():
    # 3 long-horizon buys (>=180d) + many short ones: eligible at min_long_buys=3
    # even though the wallet is near-term-dominated by $ (so classify_strategy="1").
    buys = [_buy(1000, 10), _buy(1000, 20), _buy(1000, 30)] + [_buy(50, 400)] * 3
    p = horizon_profile(buys, long_horizon_days=180)
    assert p.n_long == 3
    assert classify_strategy(p, min_dated_buys=5, long_ratio_threshold=0.5) == "1"  # near-term by $
    assert long_horizon_eligible(p, min_long_buys=3) is True   # ...yet has a long book
    assert long_horizon_eligible(p, min_long_buys=4) is False  # not enough long bets


def test_long_horizon_ineligible_with_no_long_buys():
    p = horizon_profile([_buy(100, 10), _buy(100, 20)], long_horizon_days=180)
    assert p.n_long == 0
    assert long_horizon_eligible(p, min_long_buys=1) is False
