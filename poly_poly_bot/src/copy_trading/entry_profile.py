"""Entry-price discipline for copy selection (Strategy 1b/1c quality gate).

Two wallets with the same realized ROI are not equally copyable. The
INSIDER_FINDINGS result showed that large bets on near-certain ($0.90+)
outcomes are *settlement-lag scooping*: real money, but capacity-zero and
un-copyable — by the time the trade prints we'd be paying ~$1 for a $1 payoff.
There is likewise no edge to copy in *selling* a longshot down to $0.02.

So beyond "did they make money", we ask "where do they enter?". A wallet whose
profit comes from buying mispriced outcomes in the copyable middle of the book
is worth following; one whose flow is dominated by tail prices is not. This
module derives that entry-price profile from the raw /activity feed (no market
resolution needed) and centralises the tail-price guard the lead-lag fetch uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# Copyable price band: outside it there is no edge a delayed copier can ride.
# Entries at/above MAX are near-certain outcomes (settlement-lag scooping);
# at/below MIN are dust longshots. Matches the band fetch_recent_buys used.
MIN_ENTRY = 0.05
MAX_ENTRY = 0.95


def is_copyable_entry(price: float, min_entry: float = MIN_ENTRY,
                      max_entry: float = MAX_ENTRY) -> bool:
    """True if a BUY at ``price`` is in the copyable band (not a tail entry)."""
    return min_entry <= price <= max_entry


@dataclass(frozen=True)
class EntryProfile:
    """Distribution of a wallet's BUY entry prices. Zeros for no qualifying buys."""

    n_buys: int = 0
    mean_entry: float = 0.0       # USD-weighted average entry price
    tail_ratio: float = 0.0       # share of buy $ entered at/above tail_price
    longshot_ratio: float = 0.0   # share of buy $ entered at/below longshot
    copyable_ratio: float = 0.0   # share of buy $ inside the copyable band

    def is_disciplined(self, *, max_tail_ratio: float = 0.5,
                       min_copyable_ratio: float = 0.5) -> bool:
        """Reject tail-dominated flow (un-copyable settlement-lag scoopers)."""
        if self.n_buys == 0:
            return False
        return (self.tail_ratio <= max_tail_ratio
                and self.copyable_ratio >= min_copyable_ratio)


def entry_profile(
    activity: Iterable[dict],
    *,
    tail_price: float = 0.90,
    longshot: float = 0.10,
    min_usd: float = 0.0,
) -> EntryProfile:
    """Build the USD-weighted entry-price profile from BUY trades.

    Weights by dollars (not trade count) so a single huge tail bet isn't hidden
    by many small disciplined ones. ``min_usd`` ignores dust trades.
    """
    total = 0.0
    weighted_price = 0.0
    tail = 0.0
    longshot_usd = 0.0
    copyable = 0.0
    n = 0
    for ev in activity:
        if ev.get("type") != "TRADE" or ev.get("side") != "BUY":
            continue
        price = float(ev.get("price") or 0.0)
        if price <= 0.0:
            continue
        usd = float(ev.get("usdcSize") or 0.0) or float(ev.get("size") or 0.0) * price
        if usd < min_usd or usd <= 0.0:
            continue
        n += 1
        total += usd
        weighted_price += price * usd
        if price >= tail_price:
            tail += usd
        if price <= longshot:
            longshot_usd += usd
        if is_copyable_entry(price):
            copyable += usd
    if total <= 0.0:
        return EntryProfile()
    return EntryProfile(
        n_buys=n,
        mean_entry=weighted_price / total,
        tail_ratio=tail / total,
        longshot_ratio=longshot_usd / total,
        copyable_ratio=copyable / total,
    )
