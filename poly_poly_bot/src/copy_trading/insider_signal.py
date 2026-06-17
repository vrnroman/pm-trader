"""Insider trade-shape signal for Strategy 1a (pure, testable helpers).

The copy-trading edge (Strategy 1b) is about *who* trades; the insider edge is
about the *shape* of a single trade regardless of the trader's track record: a
young/first-time account placing a large, concentrated bet on a
news/geopolitical market is the classic informed-trader fingerprint on
Polymarket.

These helpers are deliberately dependency-light (no network) so the insider
backtest and the live detector can share one tested code path. Market
classification reuses `pattern_detector.is_geopolitical_market`.
"""

from __future__ import annotations

import math
from typing import Iterable

from src.copy_trading.entry_profile import MAX_ENTRY, MIN_ENTRY, is_copyable_entry
from src.copy_trading.pattern_detector import is_geopolitical_market


def trade_usd(size: float, price: float, usdc_size: float | None = None) -> float:
    """USDC notional of a trade. ``/trades`` often returns null usdcSize, so
    fall back to size*price."""
    if usdc_size is not None:
        try:
            v = float(usdc_size)
            if v > 0:
                return v
        except (ValueError, TypeError):
            pass
    return float(size) * float(price)


def prior_trade_count(activity: Iterable[dict], before_ts: float) -> int:
    """How many TRADE events the wallet had strictly before ``before_ts``.

    This is the account's "experience" at the moment of the candidate trade —
    the basis for the new-account / first-ever-bet insider shape.
    """
    n = 0
    for a in activity:
        if a.get("type") != "TRADE":
            continue
        if float(a.get("timestamp") or 0) < before_ts:
            n += 1
    return n


def is_insider_shaped(
    *,
    prior_count: int,
    bet_usd: float,
    is_geo: bool,
    max_prior: int = 5,
    min_bet: float = 1000.0,
) -> bool:
    """A large, concentrated bet from a young account on a news/geo market.

    Legacy Strategy-1a shape. Retained for the backtest and the alert-only
    detector, but see INSIDER_FINDINGS: youth turned out to be an *anti*-signal
    (veterans outperformed). Prefer ``is_informed_early_bet`` for live scoring.
    """
    return is_geo and bet_usd >= min_bet and prior_count <= max_prior


def hours_to_resolution(trade_ts: float, resolution_ts: float | None) -> float | None:
    """Hours between a trade and the market's resolution, or ``None`` if unknown."""
    if not resolution_ts or resolution_ts <= 0:
        return None
    return (resolution_ts - trade_ts) / 3600.0


def is_informed_early_bet(
    *,
    bet_usd: float,
    entry_price: float,
    hours_before_resolution: float | None,
    min_bet: float = 1000.0,
    min_hours: float = 24.0,
    min_entry: float = MIN_ENTRY,
    max_entry: float = MAX_ENTRY,
) -> bool:
    """Track-record-agnostic informed-positioning shape.

    A large, copyable-priced bet placed *early* — well before resolution — which
    is what genuine informed money looks like and what settlement-lag scooping is
    not. Deliberately drops the two parts of ``is_insider_shaped`` the
    INSIDER_FINDINGS backtest discredited:

      * **account age** — youth was an anti-signal (veterans outperformed), so a
        seasoned consistent earner placing such a bet is *more* interesting, not
        less;
      * **the geo-only restriction** — informed timing isn't confined to
        geopolitics.

    The decisive filters that remain are size, a non-tail entry price (no point
    copying a near-certain $0.95+ outcome), and **early timing** — the single
    discriminator the old signal lacked, since ~98% of large bets land within
    24h of resolution.
    """
    if bet_usd < min_bet:
        return False
    if not is_copyable_entry(entry_price, min_entry, max_entry):
        return False
    if hours_before_resolution is None or hours_before_resolution < min_hours:
        return False
    return True


def copy_pnl_per_dollar(price: float, won: bool) -> float:
    """Realized PnL per $1 staked buying ``price`` and holding to resolution.

    Win pays $1/share for (1/price) shares -> (1-price)/price; loss -> -1.
    """
    if price <= 0 or price >= 1:
        return 0.0
    return (1.0 - price) / price if won else -1.0


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (small-sample safe)."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


# Re-exported for callers that want the geo classifier without importing the
# heavier pattern_detector module directly.
__all__ = [
    "trade_usd", "prior_trade_count", "is_insider_shaped",
    "hours_to_resolution", "is_informed_early_bet",
    "copy_pnl_per_dollar", "wilson_interval", "is_geopolitical_market",
]
