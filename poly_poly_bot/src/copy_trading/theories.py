"""Independent strategy theories (1a..1j) for copyable-wallet discovery.

Each theory is one hypothesis about what a wallet worth copying looks like, with
its own criteria and its own (backtest-calibrated) thresholds. They are
evaluated independently and OR'd: a wallet graduates to the paper watchlist if
*any* theory flags it, tagged with which one(s) and why. This deliberately
replaces the old single AND-gate — geo belongs to one theory, not all of them.

Every detector is a pure function of a ``WalletContext`` (see
``wallet_context.py``) plus a params dict, and returns a ``TheoryFlag`` (with a
human-readable ``reason``) or ``None``. No network, no I/O — so theories are
trivially unit-tested and backtested. Default params are first guesses;
``backtest/theory_backtest.py`` calibrates them to a ~1-2/day flag rate.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable, Optional

from src.copy_trading.entry_profile import is_copyable_entry
from src.copy_trading.wallet_context import WalletContext

_GEO_CATEGORIES = frozenset({"research"})  # classify_market buckets geo/politics here


@dataclass(frozen=True)
class TheoryFlag:
    theory: str          # "1a".."1j"
    score: float         # higher = stronger (used to rank/cap)
    reason: str          # human-readable "why follow this wallet"


# --------------------------------------------------------------------------- #
# 1a — news/geo early insider
# --------------------------------------------------------------------------- #
def theory_1a_news_early(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    hits = [b for b in ctx.buys
            if b.category in _GEO_CATEGORIES
            and b.usd >= p["min_bet"]
            and is_copyable_entry(b.price)
            and b.hours_before_resolution is not None
            and b.hours_before_resolution >= p["min_hours"]]
    if len(hits) < p["min_count"]:
        return None
    won = [h for h in hits if h.won]
    return TheoryFlag(
        "1a", float(len(hits)),
        f"news/geo early insider: {len(hits)} large (≥${p['min_bet']:.0f}) bet(s) "
        f"placed ≥{p['min_hours']:.0f}h pre-resolution at copyable prices"
        + (f", {len(won)} resolved YES" if any(h.won is not None for h in hits) else ""),
    )


# --------------------------------------------------------------------------- #
# 1b — consistent closed-position skill (validated core)
# --------------------------------------------------------------------------- #
def theory_1b_skill(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    m = ctx.metrics
    if m.capital < p["min_capital"] or m.n_closed < p["min_closed"]:
        return None
    if m.tstat < p["min_tstat"]:
        return None
    return TheoryFlag(
        "1b", m.tstat,
        f"consistent skill: t-stat {m.tstat:.1f}, ROI {m.roi:+.0%}, "
        f"hit {m.hit_rate:.0%} over {m.n_closed} closed markets (${m.capital:,.0f})",
    )


# --------------------------------------------------------------------------- #
# 1c — copyable lead-lag (price moves your way, survives the copy delay)
# --------------------------------------------------------------------------- #
def theory_1c_copyable(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    if ctx.n_capture < p["min_n"] or ctx.capture_cents < p["min_capture_cents"]:
        return None
    if ctx.metrics.tstat < p["min_tstat"]:
        return None
    return TheoryFlag(
        "1c", ctx.capture_cents,
        f"copyable lead-lag: capture {ctx.capture_cents:+.2f}¢/trade "
        f"(hit {ctx.capture_hit_rate:.0%}, n={ctx.n_capture}), t-stat {ctx.metrics.tstat:.1f}",
    )


# --------------------------------------------------------------------------- #
# 1d — steady compounder (PnL-curve shape; works past the /activity cap)
# --------------------------------------------------------------------------- #
def theory_1d_steady(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    c = ctx.curve
    if c.n < p["min_points"] or c.net_pnl <= p["min_net"]:
        return None
    if c.up_ratio < p["min_up_ratio"] or c.max_drawdown_frac > p["max_drawdown_frac"]:
        return None
    if c.sharpe < p["min_sharpe"]:
        return None
    return TheoryFlag(
        "1d", c.sharpe,
        f"steady compounder: PnL curve up {c.up_ratio:.0%} of periods, "
        f"maxDD {c.max_drawdown_frac:.0%}, sharpe {c.sharpe:+.2f}, net ${c.net_pnl:,.0f}",
    )


# --------------------------------------------------------------------------- #
# 1e — longshot calibration edge (buys underpriced longshots that resolve YES)
# --------------------------------------------------------------------------- #
def theory_1e_longshot(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    ls = [b for b in ctx.buys
          if b.won is not None and p["longshot_lo"] <= b.price <= p["longshot_hi"]]
    if len(ls) < p["min_n"]:
        return None
    realized = sum(1 for b in ls if b.won) / len(ls)
    implied = sum(b.price for b in ls) / len(ls)
    edge = realized - implied            # YES-rate beat vs the price they paid
    if edge < p["min_edge"]:
        return None
    return TheoryFlag(
        "1e", edge,
        f"longshot calibration edge: {len(ls)} longshot buys @ avg {implied:.2f} "
        f"resolved YES {realized:.0%} (edge {edge:+.0%} vs implied)",
    )


# --------------------------------------------------------------------------- #
# 1f — early-exit swing trader (takes profit into the move, doesn't hold to res)
# --------------------------------------------------------------------------- #
def theory_1f_swing(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    trips = [t for t in ctx.round_trips if t.entry_price > 0]
    if len(trips) < p["min_n"]:
        return None
    win_rate = sum(1 for t in trips if t.pnl > 0) / len(trips)
    mean_roi = statistics.mean(t.roi for t in trips)
    if win_rate < p["min_win_rate"] or mean_roi < p["min_mean_roi"]:
        return None
    avg_hold_h = statistics.mean(t.held_s for t in trips) / 3600.0
    return TheoryFlag(
        "1f", mean_roi * len(trips),
        f"early-exit swing: {len(trips)} round-trips, {win_rate:.0%} profitable, "
        f"avg ROI {mean_roi:+.0%}, avg hold {avg_hold_h:.0f}h (exits before resolution)",
    )


# --------------------------------------------------------------------------- #
# 1g — category specialist (edge concentrated in one segment)
# --------------------------------------------------------------------------- #
def theory_1g_specialist(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    if not ctx.closed:
        return None
    by_cat: dict[str, list] = {}
    for r in ctx.closed:
        by_cat.setdefault(r.category, []).append(r)
    total = len(ctx.closed)
    best = None
    for cat, rows in by_cat.items():
        if cat == "other" or len(rows) < p["min_n"]:
            continue
        capital = sum(r.capital for r in rows)
        roi = sum(r.pnl for r in rows) / capital if capital > 0 else 0.0
        frac = len(rows) / total
        if roi >= p["min_roi"] and frac >= p["min_frac"]:
            if best is None or roi > best[1]:
                best = (cat, roi, len(rows), frac)
    if best is None:
        return None
    cat, roi, n, frac = best
    return TheoryFlag(
        "1g", roi,
        f"{cat} specialist: ROI {roi:+.0%} over {n} closed {cat} markets "
        f"({frac:.0%} of their book)",
    )


# --------------------------------------------------------------------------- #
# 1h — catalyst follower / informed timing (entries precede big favorable moves)
# --------------------------------------------------------------------------- #
def theory_1h_catalyst(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    if ctx.n_capture < p["min_n"] or ctx.lead_cents < p["min_lead_cents"]:
        return None
    return TheoryFlag(
        "1h", ctx.lead_cents,
        f"informed timing: price moves {ctx.lead_cents:+.2f}¢ their way after entry "
        f"(n={ctx.n_capture}) — leads the move",
    )


# --------------------------------------------------------------------------- #
# 1i — low-variance whale (big capital, many small consistent edges)
# --------------------------------------------------------------------------- #
def theory_1i_whale(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    m = ctx.metrics
    if m.capital < p["min_capital"] or m.n_closed < p["min_closed"]:
        return None
    if m.hit_rate < p["min_hit_rate"] or m.concentration > p["max_concentration"]:
        return None
    if m.roi <= p["min_roi"]:
        return None
    return TheoryFlag(
        "1i", m.capital * m.roi,
        f"low-variance whale: ${m.capital:,.0f} deployed, hit {m.hit_rate:.0%} over "
        f"{m.n_closed} markets, concentration {m.concentration:.2f}, ROI {m.roi:+.0%}",
    )


# --------------------------------------------------------------------------- #
# 1j — fresh-account sniper (young account, big concentrated bet) — own theory
# --------------------------------------------------------------------------- #
def theory_1j_sniper(ctx: WalletContext, p: dict) -> Optional[TheoryFlag]:
    n_markets = len({b.condition_id for b in ctx.buys})
    if n_markets == 0 or n_markets > p["max_markets"]:
        return None
    max_bet = max((b.usd for b in ctx.buys), default=0.0)
    if max_bet < p["min_bet"]:
        return None
    return TheoryFlag(
        "1j", max_bet,
        f"fresh-account sniper: young wallet ({n_markets} market(s)) placing a "
        f"${max_bet:,.0f} bet",
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Theory:
    id: str
    fn: Callable[[WalletContext, dict], Optional[TheoryFlag]]
    defaults: dict
    desc: str
    needs_resolution: bool = False   # requires market-resolution data in the context
    needs_capture: bool = False      # requires the deep lead-lag stage


REGISTRY: dict[str, Theory] = {
    "1a": Theory("1a", theory_1a_news_early,
                 {"min_bet": 2000.0, "min_hours": 24.0, "min_count": 1},
                 "news/geo early insider", needs_resolution=True),
    "1b": Theory("1b", theory_1b_skill,
                 # calibration run1: tstat>=10 flagged 0; tstat~3 → +0.64 copy-ROI,
                 # 85% hit, ~0.9/day, +0.30 vs a survivorship-inflated baseline.
                 {"min_capital": 5000.0, "min_closed": 10, "min_tstat": 3.0},
                 "consistent closed-position skill"),
    "1c": Theory("1c", theory_1c_copyable,
                 {"min_capture_cents": 1.5, "min_n": 4, "min_tstat": 10.0},
                 "copyable lead-lag", needs_capture=True),
    "1d": Theory("1d", theory_1d_steady,
                 {"min_points": 14, "min_net": 0.0, "min_up_ratio": 0.5,
                  "max_drawdown_frac": 0.4, "min_sharpe": 0.1},
                 "steady compounder (PnL curve)"),
    "1e": Theory("1e", theory_1e_longshot,
                 {"longshot_lo": 0.05, "longshot_hi": 0.40, "min_n": 8, "min_edge": 0.05},
                 "longshot calibration edge", needs_resolution=True),
    "1f": Theory("1f", theory_1f_swing,
                 # run1 win.6: +0.55 copy-ROI, 84% hit, ~1.8/day, +0.20 vs baseline
                 {"min_n": 8, "min_win_rate": 0.60, "min_mean_roi": 0.08},
                 "early-exit swing trader"),
    "1g": Theory("1g", theory_1g_specialist,
                 # run1 roi.3: +0.79 copy-ROI, 85% hit, ~0.5/day, +0.45 (best theory)
                 {"min_n": 10, "min_roi": 0.30, "min_frac": 0.5},
                 "category specialist"),
    "1h": Theory("1h", theory_1h_catalyst,
                 {"min_lead_cents": 4.0, "min_n": 4},
                 "catalyst follower / informed timing", needs_capture=True),
    "1i": Theory("1i", theory_1i_whale,
                 {"min_capital": 50000.0, "min_closed": 20, "min_hit_rate": 0.60,
                  "max_concentration": 0.4, "min_roi": 0.02},
                 "low-variance whale"),
    "1j": Theory("1j", theory_1j_sniper,
                 {"max_markets": 8, "min_bet": 2000.0},
                 "fresh-account sniper"),
}


def evaluate_all(
    ctx: WalletContext,
    *,
    enabled: set[str] | None = None,
    params: dict[str, dict] | None = None,
) -> list[TheoryFlag]:
    """Run every enabled theory; return the flags that fired (strongest first).

    ``enabled`` defaults to all theories. ``params`` overrides each theory's
    defaults (merged), so the backtest can inject calibrated thresholds.
    """
    flags: list[TheoryFlag] = []
    for tid, theory in REGISTRY.items():
        if enabled is not None and tid not in enabled:
            continue
        p = dict(theory.defaults)
        if params and tid in params:
            p.update(params[tid])
        try:
            f = theory.fn(ctx, p)
        except Exception:
            f = None
        if f is not None:
            flags.append(f)
    flags.sort(key=lambda f: f.score, reverse=True)
    return flags
