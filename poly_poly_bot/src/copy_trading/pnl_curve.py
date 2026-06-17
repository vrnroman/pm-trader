"""Wallet PnL-curve metrics from the user-pnl endpoint (Strategy 1b feeder).

The data-API ``/activity`` feed caps at ~3,500 records, so a heavy trader's full
history cannot be replayed trade-by-trade. The user-pnl endpoint instead returns
the wallet's *cumulative* PnL as a time series over its whole lifetime, which
lets us judge the long-arc question copy-trading actually cares about: is this a
steady, low-drawdown earner, or a high-variance gambler whose ROI is one lucky
spike?

Metrics here are deliberately *shape-based* (trend, drawdown, up-period ratio,
consistency) rather than absolute dollars: absolute PnL is dominated by account
size and survivorship, whereas the shape of the curve is what distinguishes a
repeatable edge from noise. This complements — does not replace — the realized
closed-position t-stat (``trader_scoring``), which remains the validated core.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import requests

# Sharpe sentinel for a zero-variance curve: a perfectly steady drift is the
# *most* consistent case, so map it to a large finite value (not ``inf``, which
# isn't valid JSON and this metric may be serialized into watchlist meta).
_MAX_SHARPE = 1e3

PNL_API = os.environ.get("PNL_API_URL", "https://user-pnl-api.polymarket.com")
DATA_API = os.environ.get("DATA_API_URL", "https://data-api.polymarket.com")


def _get(session: requests.Session, base: str, path: str, **params):
    for _ in range(3):
        try:
            r = session.get(base + path, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if 400 <= r.status_code < 500 and r.status_code != 429:
                return None
        except requests.RequestException:
            pass
    return None


def fetch_pnl_curve(
    wallet: str,
    interval: str = "all",
    fidelity: str = "1d",
    session: requests.Session | None = None,
) -> list[tuple[float, float]]:
    """Cumulative PnL time series ``[(t, p), ...]`` sorted by time (oldest first).

    Returns ``[]`` on any error or empty history so callers can treat "no curve"
    uniformly.
    """
    s = session or requests.Session()
    j = _get(s, PNL_API, "/user-pnl", user_address=wallet,
             interval=interval, fidelity=fidelity)
    pts: list[tuple[float, float]] = []
    for row in j or []:
        t, p = row.get("t"), row.get("p")
        if t is not None and p is not None:
            pts.append((float(t), float(p)))
    pts.sort()
    return pts


def fetch_portfolio_value(
    wallet: str, session: requests.Session | None = None
) -> float | None:
    """Current portfolio value in USDC, or ``None`` if unavailable."""
    s = session or requests.Session()
    j = _get(s, DATA_API, "/value", user=wallet)
    if isinstance(j, list) and j:
        v = j[0].get("value")
        return float(v) if v is not None else None
    if isinstance(j, dict) and "value" in j:
        return float(j["value"])
    return None


@dataclass(frozen=True)
class CurveMetrics:
    """Shape descriptors of a cumulative-PnL curve. All zero for an empty curve."""

    n: int = 0                    # number of points
    net_pnl: float = 0.0          # last − first cumulative value
    peak: float = 0.0             # max cumulative value reached
    max_drawdown: float = 0.0     # largest peak→trough drop ($)
    max_drawdown_frac: float = 0.0  # that drop as a fraction of the peak [0..1]
    up_ratio: float = 0.0         # fraction of periods with a positive change
    slope_per_period: float = 0.0  # least-squares slope of value vs index
    sharpe: float = 0.0           # mean period change / std of period changes

    def is_steady_earner(
        self,
        *,
        min_net: float = 0.0,
        max_drawdown_frac: float = 0.5,
        min_up_ratio: float = 0.5,
        min_sharpe: float = 0.0,
    ) -> bool:
        """A profitable, up-trending, not-too-drawdown-y, mostly-winning curve.

        Defaults are intentionally permissive (a filter, not a ranker); tune per
        caller. A wallet with too few points to judge (``n < 3``) is rejected.
        """
        if self.n < 3:
            return False
        return (
            self.net_pnl > min_net
            and self.slope_per_period > 0
            and self.max_drawdown_frac <= max_drawdown_frac
            and self.up_ratio >= min_up_ratio
            and self.sharpe >= min_sharpe
        )


def curve_metrics(points: list[tuple[float, float]]) -> CurveMetrics:
    """Compute shape descriptors from a cumulative-PnL time series."""
    vals = [p for _, p in points]
    n = len(vals)
    if n == 0:
        return CurveMetrics()
    if n == 1:
        return CurveMetrics(n=1, peak=max(vals[0], 0.0))

    net_pnl = vals[-1] - vals[0]

    # max drawdown on the cumulative curve (largest peak→trough decline)
    peak = vals[0]
    max_dd = 0.0
    peak_at_max_dd = peak
    for v in vals:
        if v > peak:
            peak = v
        dd = peak - v
        if dd > max_dd:
            max_dd = dd
            peak_at_max_dd = peak
    overall_peak = max(vals)
    dd_frac = (max_dd / peak_at_max_dd) if peak_at_max_dd > 0 else 0.0

    # period-over-period changes
    deltas = [vals[i + 1] - vals[i] for i in range(n - 1)]
    up_ratio = sum(1 for d in deltas if d > 0) / len(deltas)
    mean_d = sum(deltas) / len(deltas)
    var_d = sum((d - mean_d) ** 2 for d in deltas) / len(deltas)
    std_d = math.sqrt(var_d)
    if std_d > 1e-12:
        sharpe = max(-_MAX_SHARPE, min(_MAX_SHARPE, mean_d / std_d))
    elif mean_d > 0:
        sharpe = _MAX_SHARPE      # steady positive drift, zero variance → best
    elif mean_d < 0:
        sharpe = -_MAX_SHARPE
    else:
        sharpe = 0.0              # flat line

    # least-squares slope of value vs index
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(vals) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, vals))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    slope = (cov / var_x) if var_x > 0 else 0.0

    return CurveMetrics(
        n=n,
        net_pnl=net_pnl,
        peak=overall_peak,
        max_drawdown=max_dd,
        max_drawdown_frac=dd_frac,
        up_ratio=up_ratio,
        slope_per_period=slope,
        sharpe=sharpe,
    )
