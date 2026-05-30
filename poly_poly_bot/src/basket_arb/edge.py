"""Depth-aware basket-arbitrage edge math (Strategy 3).

In a mutually-exclusive, exhaustive set of binary outcomes (a Polymarket
neg-risk event, e.g. "World Cup Winner" with N teams), exactly one outcome
resolves YES ($1) and the rest resolve NO ($0). Therefore buying one share of
*every* outcome guarantees a $1 payout. If the total cost of assembling that
basket is < $1 (net of fees), the difference is risk-free profit.

The naive check — "sum of best asks < 1" — overstates the opportunity because
each leg's top-of-book holds only a few shares. This module walks the real
order books so the reported edge reflects the size you could actually fill.

Pure functions only (synthetic books in, numbers out) so the logic is unit
tested without touching the network. The live scanner lives in
`scripts/basket_arb_scan.py`.

Book convention: a leg's asks are a list of ``(price, size)`` levels. Order is
normalised internally (cheapest first), so callers may pass either order.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BasketEdge:
    """Result of evaluating a buy-all-outcomes basket."""

    n_legs: int
    best_size: float        # shares of each outcome to buy (the basket quantity)
    cost: float             # total USDC to assemble best_size baskets
    payout: float           # guaranteed payout net of fees (best_size * (1-fee))
    profit: float           # payout - cost
    roi: float              # profit / cost
    feasible: bool          # were all legs fillable for at least a tiny size?

    @property
    def per_basket_cost(self) -> float:
        return self.cost / self.best_size if self.best_size > 0 else 0.0


def _cum_levels(asks: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return cumulative (shares, cost) breakpoints, cheapest level first."""
    levels = sorted((float(p), float(s)) for p, s in asks if s and s > 0)
    cum: list[tuple[float, float]] = []
    cs = cc = 0.0
    for price, size in levels:
        cs += size
        cc += price * size
        cum.append((cs, cc))
    return cum


def _cost_to_buy(cum: list[tuple[float, float]], q: float) -> float | None:
    """USDC cost to buy ``q`` shares given cumulative breakpoints.

    Returns None if the book lacks the depth for ``q``.
    """
    if q <= 0:
        return 0.0
    prev_shares = prev_cost = 0.0
    for cs, cc in cum:
        if q <= cs:
            # partial fill within this level: marginal price = level slope
            level_shares = cs - prev_shares
            level_cost = cc - prev_cost
            price = level_cost / level_shares if level_shares > 0 else 0.0
            return prev_cost + price * (q - prev_shares)
        prev_shares, prev_cost = cs, cc
    return None  # insufficient depth


def basket_buy_edge(
    leg_asks: list[list[tuple[float, float]]],
    *,
    fee_rate: float = 0.0,
) -> BasketEdge:
    """Best risk-free profit from buying one share of every outcome.

    ``leg_asks``: one asks book per mutually-exclusive outcome.
    ``fee_rate``: taker fee applied to the $1 resolution payout (e.g. 0.0 for
    0bp markets, 0.02 for 200bp). Conservative: fee reduces payout, not cost.

    Profit at basket size ``q`` is ``q*(1-fee) - sum_i cost_i(q)``. This is
    piecewise-linear and concave in ``q`` (marginal cost rises as books are
    consumed), so the optimum sits at one of the cumulative-depth breakpoints.
    """
    n = len(leg_asks)
    cums = [_cum_levels(a) for a in leg_asks]
    if n == 0 or any(not c for c in cums):
        return BasketEdge(n, 0.0, 0.0, 0.0, 0.0, 0.0, feasible=False)

    # Max fillable basket size = min depth across legs.
    max_q = min(c[-1][0] for c in cums)
    if max_q <= 0:
        return BasketEdge(n, 0.0, 0.0, 0.0, 0.0, 0.0, feasible=False)

    # Candidate sizes: every breakpoint across all legs, clipped to max_q.
    candidates = {max_q}
    for c in cums:
        for cs, _cc in c:
            if 0 < cs <= max_q:
                candidates.add(cs)

    best = BasketEdge(n, 0.0, 0.0, 0.0, 0.0, 0.0, feasible=True)
    for q in sorted(candidates):
        total = 0.0
        ok = True
        for c in cums:
            cost = _cost_to_buy(c, q)
            if cost is None:
                ok = False
                break
            total += cost
        if not ok:
            continue
        payout = q * (1.0 - fee_rate)
        profit = payout - total
        if profit > best.profit:
            best = BasketEdge(
                n_legs=n, best_size=q, cost=total, payout=payout,
                profit=profit, roi=(profit / total if total > 0 else 0.0),
                feasible=True,
            )
    return best


def top_of_book_sum(leg_asks: list[list[tuple[float, float]]]) -> float:
    """Naive indicator: sum of best (lowest) asks across legs.

    < 1.0 hints at a buy-basket opportunity, but use :func:`basket_buy_edge`
    for the depth-aware, fee-adjusted, actually-fillable number.
    """
    total = 0.0
    for asks in leg_asks:
        prices = [float(p) for p, s in asks if s and s > 0]
        if not prices:
            return float("inf")
        total += min(prices)
    return total
