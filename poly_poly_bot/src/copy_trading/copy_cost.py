"""Real-money execution cost model for copy-trading (pure, testable).

A paper book fills at a clean price and so hides the cost that decides whether a
thin edge is real money or a fee donation. On Polymarket the trading fee is ~0,
so the dominant round-trip cost is the **bid/ask spread**: we BUY at the ask and
later SELL or REDEEM at the bid, paying roughly the full spread over the round
trip, wider on thin/sports books than on liquid crypto/research. Polygon gas is
cents on a $50 ticket — ignored.

This module turns that into one number per market category, used two ways:

  * **Selection** — a (wallet, category) cell qualifies only if its measured
    copy-and-hold ROI/$ clears the category's cost plus a safety margin. An edge
    that can't beat the spread is not tradable with real capital, no matter how
    good it looks on paper. (See ``copy_replay.select_copyable_categories``.)
  * **Per-trade** — the live engine can skip a specific copy whose implied edge
    can't clear cost.

The defaults below were sampled from live Polymarket order books for the very
markets the paper book copied (median full-spread / mid, bucketed by category;
see ``scripts``/backtest). They are deliberately conservative: the empirical
median rounded up, so the floor errs toward *rejecting* marginal edges rather
than admitting fee-donor trades. Override per deployment via env.
"""

from __future__ import annotations

import os
from typing import Optional

# Round-trip cost per category (ROI-per-$1 = full bid/ask spread / mid). Anchored
# to a live order-book spread sample of the markets the paper book copied (most
# had already resolved by sampling time, leaving one live sports book at 12.2% —
# which sets the sports floor and matches the known ~10-12% thin-market spread);
# crypto/research are the liquid end (~5%). Deliberately conservative (rounded up)
# so the edge floor errs toward rejecting marginal edges over admitting fee-donor
# trades. Override per deployment via COPY_CATEGORY_COST.
DEFAULT_CATEGORY_COST: dict[str, float] = {
    "crypto": 0.05,
    "research": 0.06,
    "sports": 0.12,
    "other": 0.10,
}
# Used for any category not in the map (and as the conservative single fallback).
DEFAULT_FALLBACK_COST = 0.10

# Extra safety margin required ON TOP of cost before an edge is "tradable" — the
# edge must clear cost by this much, so we don't ship a cell that merely breaks
# even against the spread. Net-of-everything bar = cost(category) + this.
DEFAULT_EDGE_MARGIN = 0.03


def _parse_cost_env(raw: str) -> dict[str, float]:
    """Parse ``cat:cost,cat:cost`` (cost in ROI-per-$1, e.g. ``sports:0.12``)."""
    out: dict[str, float] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        cat, _, val = part.partition(":")
        try:
            out[cat.strip().lower()] = float(val)
        except ValueError:
            continue
    return out


class CostModel:
    """Round-trip execution cost per category + the tradable-edge bar.

    Pure and cheap to construct. ``cost_of(category)`` is the round-trip spread
    cost; ``edge_floor(category)`` is the ROI/$ a copy-and-hold cell must clear to
    be worth real capital (cost + margin)."""

    def __init__(
        self,
        category_cost: Optional[dict[str, float]] = None,
        fallback: float = DEFAULT_FALLBACK_COST,
        margin: float = DEFAULT_EDGE_MARGIN,
    ):
        self.category_cost = {k.lower(): float(v) for k, v in
                              (category_cost or DEFAULT_CATEGORY_COST).items()}
        self.fallback = float(fallback)
        self.margin = float(margin)

    def cost_of(self, category: str) -> float:
        """Round-trip execution cost (ROI-per-$1) for a market category."""
        return self.category_cost.get((category or "").lower(), self.fallback)

    def edge_floor(self, category: str) -> float:
        """Minimum copy-and-hold ROI/$ a cell must clear to be tradable on real
        money: round-trip cost plus the safety margin."""
        return self.cost_of(category) + self.margin

    def net_roi(self, gross_roi: float, category: str) -> float:
        """A gross copy-and-hold ROI/$ after deducting the category's cost."""
        return gross_roi - self.cost_of(category)

    @classmethod
    def from_env(cls) -> "CostModel":
        """Build from env, falling back to the sampled defaults.

        ``COPY_CATEGORY_COST`` = ``crypto:0.04,sports:0.10`` (ROI/$ per category),
        ``COPY_COST_FALLBACK`` = single fallback cost,
        ``COPY_EDGE_MARGIN``   = safety margin above cost.
        """
        cost = _parse_cost_env(os.environ.get("COPY_CATEGORY_COST", ""))
        def _f(name: str, default: float) -> float:
            v = os.environ.get(name, "").strip()
            try:
                return float(v) if v else default
            except ValueError:
                return default
        return cls(
            category_cost={**DEFAULT_CATEGORY_COST, **cost},
            fallback=_f("COPY_COST_FALLBACK", DEFAULT_FALLBACK_COST),
            margin=_f("COPY_EDGE_MARGIN", DEFAULT_EDGE_MARGIN),
        )
