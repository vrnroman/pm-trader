"""Lead-lag / informed-money analysis (pure, testable).

Two questions about a wallet's trades, answered from price series rather than
from final outcomes:

1. Lead-lag (informed money): after this wallet BUYS, does the market price move
   *its way* over the next N minutes? A wallet that consistently leads the price
   is informed — and unlike final-outcome ROI, this measures whether their
   *timing* carries information a copier could ride.

2. Delayed-copy edge: if we copy at the price M minutes *after* the wallet's
   trade (realistic latency) and exit H minutes later (or hold to resolution),
   what do we capture? This is the edge that survives acting after the fact —
   the thing the naive ROI backtest ignores.

Everything here is pure: callers pass a price series (list of (ts, price)) and
trades; no network. The live/backtest shells fetch CLOB price-history and feed
it in.
"""

from __future__ import annotations

from dataclasses import dataclass


def price_at(series: list[tuple[float, float]], ts: float) -> float | None:
    """Price at time ``ts`` using the last observation at or before ``ts``.

    ``series`` is (timestamp, price) sorted ascending. Returns None if ``ts``
    precedes the first observation (no information yet).
    """
    if not series or ts < series[0][0]:
        return None
    lo, hi, ans = 0, len(series) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if series[mid][0] <= ts:
            ans = series[mid][1]
            lo = mid + 1
        else:
            hi = mid - 1
    return ans


@dataclass
class LeadLagResult:
    """How a single BUY's price evolved afterward."""

    entry_price: float          # price at (or just before) the trade
    delayed_price: float        # price M minutes later (our realistic entry)
    future_price: float         # price H minutes after the delayed entry
    # signed move *in the wallet's favour* (they bought, so up = good):
    lead_move: float            # future_price - entry_price (informed-money)
    capture_move: float         # future_price - delayed_price (copier captures)
    slippage: float             # delayed_price - entry_price (latency cost)


def analyze_buy(
    series: list[tuple[float, float]],
    trade_ts: float,
    *,
    delay_s: float = 900.0,        # 15 min: realistic copy latency
    horizon_s: float = 14400.0,    # 4 h: how long the move plays out
) -> LeadLagResult | None:
    """Measure the price path around one BUY. None if data is insufficient."""
    entry = price_at(series, trade_ts)
    delayed = price_at(series, trade_ts + delay_s)
    future = price_at(series, trade_ts + delay_s + horizon_s)
    if entry is None or delayed is None or future is None:
        return None
    return LeadLagResult(
        entry_price=entry,
        delayed_price=delayed,
        future_price=future,
        lead_move=future - entry,
        capture_move=future - delayed,
        slippage=delayed - entry,
    )


@dataclass
class WalletLeadLag:
    """Aggregated lead-lag stats for a wallet across its BUYs."""

    n: int = 0
    lead_sum: float = 0.0          # sum of signed informed-money moves
    capture_sum: float = 0.0       # sum of signed copier-capturable moves
    slippage_sum: float = 0.0
    lead_wins: int = 0             # trades where price moved their way (lead>0)
    capture_wins: int = 0          # trades a delayed copy would have profited on

    def add(self, r: LeadLagResult, side_sign: int = 1) -> None:
        """Accumulate one trade. ``side_sign`` = +1 for BUY YES (price up =
        good), -1 if you ever feed a directional SELL (price down = good)."""
        self.n += 1
        self.lead_sum += side_sign * r.lead_move
        self.capture_sum += side_sign * r.capture_move
        self.slippage_sum += side_sign * r.slippage
        if side_sign * r.lead_move > 0:
            self.lead_wins += 1
        if side_sign * r.capture_move > 0:
            self.capture_wins += 1

    @property
    def avg_lead(self) -> float:
        return self.lead_sum / self.n if self.n else 0.0

    @property
    def avg_capture(self) -> float:
        return self.capture_sum / self.n if self.n else 0.0

    @property
    def avg_slippage(self) -> float:
        return self.slippage_sum / self.n if self.n else 0.0

    @property
    def lead_hit_rate(self) -> float:
        return self.lead_wins / self.n if self.n else 0.0

    @property
    def capture_hit_rate(self) -> float:
        return self.capture_wins / self.n if self.n else 0.0

    @property
    def informed_score(self) -> float:
        """Headline metric: average per-trade price move in cents the wallet's
        timing predicts (positive = leads the market = informed)."""
        return self.avg_lead
