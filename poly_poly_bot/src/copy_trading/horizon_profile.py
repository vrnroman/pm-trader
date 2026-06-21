"""Bet-horizon profiling — the rule that splits Strategy 1 from Strategy 4.

The whole copy/insider funnel (Strategy 1: trader_scoring, copy_replay, theories
1a..1j) scores a wallet on its **provably-closed** markets. That machinery is
blind to a wallet whose bets resolve far in the future: a trader who puts on 15
positions that each settle 6-12 months out has *no* closed markets to score, so
it looks "unproven" forever — and the few short-horizon trades it happens to
make get scored in isolation, which is noise. We'd only learn whether the patient
conviction paid off a year later, by which point following it is moot.

Strategy 4 carves these long-horizon bettors into their own track: we keep
*tracking* them (don't skip), but separately from the near-term copyable wallets,
because they need a different evaluation clock and a different risk model (a copy
locks capital up for months).

This module is the **pure rule** for telling the two apart, derived from how far
before resolution a wallet places its bets:

    horizon(buy) = (market endDate - buy timestamp)         [days]

A buy is *long-horizon* when that horizon is >= ``long_horizon_days`` (default
180 ≈ 6 months). USD-weighting the long-horizon share of a wallet's dated buys
gives ``long_ratio``; a wallet whose flow is long-horizon-dominated is Strategy 4,
otherwise Strategy 1. No network, no I/O — classification is a function of the
``Buy`` rows ``wallet_context`` already builds, so it's trivially unit-tested.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Optional

STRATEGY_NEAR_TERM = "1"   # near-term copyable flow — the existing funnel scores it
STRATEGY_LONG_HORIZON = "4"  # long-horizon conviction flow — tracked separately

# Defaults (overridable via Strategy4Config / env). 6 months ≈ the user's "bet
# something 6 months ahead"; a wallet is Strategy 4 when at least half its bet $
# (over enough dated bets) is placed that far before resolution.
DEFAULT_LONG_HORIZON_DAYS = 180.0
DEFAULT_LONG_RATIO_THRESHOLD = 0.5
DEFAULT_MIN_DATED_BUYS = 5


@dataclass(frozen=True)
class HorizonProfile:
    """USD-weighted distribution of how early a wallet bets before resolution.

    Only buys whose market end date is known ("dated" buys) count — an undated
    buy carries no horizon information. Zeros for a wallet with no dated buys.
    """

    n_dated_buys: int = 0
    n_long: int = 0                  # dated buys at/over the long-horizon cutoff
    long_ratio: float = 0.0          # share of dated buy $ that is long-horizon
    mean_horizon_days: float = 0.0   # USD-weighted average horizon over dated buys
    median_horizon_days: float = 0.0 # count-weighted median horizon over dated buys
    max_horizon_days: float = 0.0    # furthest-out single bet


def _horizon_days(buy) -> Optional[float]:
    """Days between a buy and its market's resolution, or None if undated.

    Reads ``hours_before_resolution`` (populated by ``wallet_context`` whenever
    the market end date is known — for *open* far-future markets as well as
    resolved ones). Negative/zero horizons (bet at or after the end date — clock
    skew or post-close trades) are treated as undated, not long-horizon.
    """
    hbr = getattr(buy, "hours_before_resolution", None)
    if hbr is None:
        return None
    days = float(hbr) / 24.0
    return days if days > 0 else None


def horizon_profile(
    buys: Iterable,
    *,
    long_horizon_days: float = DEFAULT_LONG_HORIZON_DAYS,
) -> HorizonProfile:
    """Build the USD-weighted bet-horizon profile from a wallet's ``Buy`` rows.

    Weights by dollars (not trade count) so one big far-future conviction bet
    isn't washed out by many small near-term ones — matching ``entry_profile``'s
    dollar-weighting. ``buys`` items need ``.usd`` and ``.hours_before_resolution``.
    """
    total = 0.0
    long_usd = 0.0
    weighted_days = 0.0
    n_long = 0
    days_list: list[float] = []
    max_days = 0.0
    for b in buys:
        days = _horizon_days(b)
        if days is None:
            continue
        usd = float(getattr(b, "usd", 0.0) or 0.0)
        if usd <= 0.0:
            continue
        total += usd
        weighted_days += days * usd
        days_list.append(days)
        if days > max_days:
            max_days = days
        if days >= long_horizon_days:
            long_usd += usd
            n_long += 1
    if total <= 0.0 or not days_list:
        return HorizonProfile()
    return HorizonProfile(
        n_dated_buys=len(days_list),
        n_long=n_long,
        long_ratio=long_usd / total,
        mean_horizon_days=weighted_days / total,
        median_horizon_days=statistics.median(days_list),
        max_horizon_days=max_days,
    )


def classify_strategy(
    profile: HorizonProfile,
    *,
    min_dated_buys: int = DEFAULT_MIN_DATED_BUYS,
    long_ratio_threshold: float = DEFAULT_LONG_RATIO_THRESHOLD,
) -> Optional[str]:
    """Label a wallet "4" (long-horizon) or "1" (near-term), or None if unknown.

    The rule distinguishing Strategy 1 from Strategy 4:
      * fewer than ``min_dated_buys`` dated buys  -> None (not enough horizon
        evidence to judge; the caller defaults such wallets to Strategy 1);
      * long-horizon buys are >= ``long_ratio_threshold`` of dated buy $  -> "4";
      * otherwise                                  -> "1".
    """
    if profile.n_dated_buys < min_dated_buys:
        return None
    if profile.long_ratio >= long_ratio_threshold:
        return STRATEGY_LONG_HORIZON
    return STRATEGY_NEAR_TERM
