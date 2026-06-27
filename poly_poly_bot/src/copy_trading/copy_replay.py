"""Copy-replay scoring — score a wallet by the realized ROI of *our* copy action.

The validated selection metric (a wallet's own closed-position ROI / t-stat in
``trader_scoring``) measures a *different game* than copy-trading. It credits the
wallet's whole book — including the near-lock favorites it buys at $0.90+ and the
early exits it takes on round trips. But the forward paper harness only copies
BUYs in the copyable band (0.05–0.95) and **holds them to resolution**. A
favorite-buyer / round-trip scalper can post a 96% historical hit rate yet lose
money when we copy only that middle slice and hold it — which is exactly what the
live paper ledger showed: −25% ROI, 40.6% hit vs a 57% entry-price-implied rate.

This module scores a wallet on the SAME action the harness takes: replay each
qualifying BUY as a copy *held to resolution* and aggregate the per-copy ROI, its
t-stat (edge per unit of noise), and hit rate. It also reports the
exit-following ROI as a **two-horizon diagnostic** — how much of the wallet's
edge lives in the exit we don't take. Selection then measures what we actually
do, so wallets whose edge is only in near-locks/exits score badly and drop out.

Pure: it operates on a ``WalletContext``'s already-extracted ``buys`` /
``round_trips`` (no network, no re-parsing), so discovery can gate+rank on it and
it unit-tests offline. A separate ``forward_copy_rois`` helper replays raw
activity (used by the calibration backtest) so both paths share one definition of
"what a copy earns".
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from src.copy_trading.entry_profile import is_copyable_entry
from src.copy_trading.trader_scoring import tstat


def proven_negative(n: int, mean_roi: float, *, min_n: int, min_roi: float) -> bool:
    """Enough resolved replayed copies AND a copy-and-hold edge below the bar —
    a wallet we should NOT follow regardless of which theory flagged it. The
    single definition of the drop rule, shared by the score and the discovery
    gate so the two never drift."""
    return n >= min_n and mean_roi < min_roi


def proven_positive(n: int, mean_roi: float, *, min_n: int, min_roi: float) -> bool:
    """Enough resolved replayed copies AND a copy-and-hold edge at/above the bar
    — a copy-validated wallet (ranked first). Mirror of ``proven_negative``."""
    return n >= min_n and mean_roi >= min_roi


def _copy_hold_rois(
    buys: Iterable[object],
    *,
    min_usd: float,
    first_entry_only: bool,
):
    """Yield ``(category, roi)`` for each qualifying copy held to resolution.

    The single definition of the per-copy filter (copyable band, ``min_usd``,
    resolved-only, first-entry-per-(market,outcome)) and the win/loss payoff,
    shared by the flat ``copy_and_hold_rois`` and the per-category bucketer so the
    whole-wallet replay and the category gate can never score on different buy
    sets. ``category`` is the ``Buy``'s ``.category`` (``"other"`` if absent)."""
    seen: set = set()
    for b in sorted(buys, key=lambda x: getattr(x, "ts", 0.0) or 0.0):
        price = float(getattr(b, "price", 0.0) or 0.0)
        if not is_copyable_entry(price):
            continue
        if float(getattr(b, "usd", 0.0) or 0.0) < min_usd:
            continue
        won = getattr(b, "won", None)
        if won is None:
            continue
        if first_entry_only:
            key = (getattr(b, "condition_id", None), getattr(b, "outcome_index", None))
            if key in seen:
                continue
            seen.add(key)
        yield (getattr(b, "category", None) or "other",
               (1.0 / price - 1.0) if won else -1.0)


def copy_and_hold_rois(
    buys: Iterable[object],
    *,
    min_usd: float = 500.0,
    first_entry_only: bool = True,
) -> list[float]:
    """Per-copy ROI-per-$1 of copying each qualifying BUY and holding to resolution.

    ``buys`` are ``WalletContext.Buy`` rows (need ``.condition_id``,
    ``.outcome_index``, ``.price``, ``.usd``, ``.won``, ``.ts``). A copy is
    scored only when the market resolved (``won`` known); unresolved buys are
    skipped (we can't yet say what holding them earns). Entries outside the
    copyable band or below ``min_usd`` are ignored — they match the live
    detector's filters. With ``first_entry_only`` the wallet's *first* entry into
    a (market, outcome) counts and later add-to-position buys are dropped, since
    the harness copies the opening trade, not averaging-down adds.
    """
    return [roi for _cat, roi in _copy_hold_rois(
        buys, min_usd=min_usd, first_entry_only=first_entry_only)]


def exit_follow_rois(round_trips: Iterable[object]) -> list[float]:
    """Per-trip ROI-per-$1 of mirroring the wallet's round trips (buy then sell).

    ``round_trips`` are ``WalletContext.RoundTrip`` rows. This is the
    *exit-following* horizon: the wallet entered and took profit/cut into the
    move before resolution. Comparing this to ``copy_and_hold_rois`` shows how
    much of a wallet's edge lives in the exit we don't currently take.
    """
    rois: list[float] = []
    for t in round_trips:
        entry = float(getattr(t, "entry_price", 0.0) or 0.0)
        exit_ = float(getattr(t, "exit_price", 0.0) or 0.0)
        if entry <= 0.0 or not is_copyable_entry(entry):
            continue
        rois.append(exit_ / entry - 1.0)
    return rois


@dataclass(frozen=True)
class CopyReplayScore:
    """How a wallet scores under our actual copy action (hold-to-resolution).

    ``mean_roi`` is the mean per-copy ROI-per-$1; ``tstat`` is its t-stat (edge
    per unit of noise — repeatable beats lucky); ``hit_rate`` the share of copies
    that won. ``exit_*`` are the two-horizon diagnostic (round-trip / exit-follow
    ROI), recorded but NOT used to gate, since the live harness holds to
    resolution.
    """

    n: int = 0
    mean_roi: float = 0.0
    tstat: float = 0.0
    hit_rate: float = 0.0
    exit_n: int = 0
    exit_mean_roi: float = 0.0

    def is_proven_negative(self, *, min_n: int, min_roi: float) -> bool:
        """Enough resolved copies but the copy-and-hold edge is below the bar —
        a wallet we should NOT follow regardless of which theory flagged it."""
        return proven_negative(self.n, self.mean_roi, min_n=min_n, min_roi=min_roi)

    def fade_label(self, *, min_n: int, fade_roi: float) -> Optional[str]:
        """A 'FADE' tag for a wallet whose copies lose badly enough to note
        (diagnostic only — we do not open inverse positions)."""
        if self.n >= min_n and self.mean_roi <= fade_roi:
            return "FADE"
        return None


def score_copy_replay(
    buys: Iterable[object],
    round_trips: Iterable[object] = (),
    *,
    min_usd: float = 500.0,
    first_entry_only: bool = True,
) -> CopyReplayScore:
    """Aggregate a wallet's copy-and-hold replay into a ``CopyReplayScore``."""
    rois = copy_and_hold_rois(buys, min_usd=min_usd, first_entry_only=first_entry_only)
    exits = exit_follow_rois(round_trips)
    if not rois:
        return CopyReplayScore(
            exit_n=len(exits),
            exit_mean_roi=round(statistics.mean(exits), 4) if exits else 0.0,
        )
    wins = sum(1 for r in rois if r > 0)
    return CopyReplayScore(
        n=len(rois),
        mean_roi=round(statistics.mean(rois), 4),
        tstat=round(tstat(rois), 3),
        hit_rate=round(wins / len(rois), 4),
        exit_n=len(exits),
        exit_mean_roi=round(statistics.mean(exits), 4) if exits else 0.0,
    )


# --------------------------------------------------------------------------- #
# Per-(wallet, category) copy-and-hold selection — "winning markets only"
# --------------------------------------------------------------------------- #
#
# The lag-sweep kill-test (backtest/copy_lag_backtest.py) showed that copying a
# skilled wallet's BUYs and holding to resolution is structurally −EV *in
# aggregate* even at zero lag — but the loss is categorical: a wallet that is
# +EV-to-copy in one market type (e.g. crypto) bleeds in another (sports). So we
# don't follow a wallet wholesale; we follow it only in the categories where its
# copy-and-hold edge clears real-money cost on enough resolved bets. This is the
# "define each wallet's winning markets and copy only those" rule, measured on
# the exact action the harness takes.


@dataclass(frozen=True)
class CategoryEdge:
    """A wallet's copy-and-hold edge within one market category.

    ``net_roi`` deducts the category's round-trip execution cost from the gross
    copy-and-hold ROI/$. ``approved`` is the gate: enough resolved copies AND a
    net edge clearing the tradable-edge floor (cost + margin). ``required`` is the
    floor it had to beat (the gross ROI bar), available to callers building a
    why-string; ``tstat``/``hit_rate`` are diagnostics. Discovery persists the
    compact ``(category, n, net_roi, approved)`` rows to the watchlist."""

    category: str
    n: int = 0
    mean_roi: float = 0.0
    tstat: float = 0.0
    hit_rate: float = 0.0
    net_roi: float = 0.0
    required: float = 0.0
    approved: bool = False


def copy_and_hold_rois_by_category(
    buys: Iterable[object],
    *,
    min_usd: float = 500.0,
    first_entry_only: bool = True,
) -> dict[str, list[float]]:
    """``copy_and_hold_rois`` bucketed by each buy's market category.

    Shares ``_copy_hold_rois``'s per-copy filter (copyable band, ``min_usd``,
    resolved-only, first-entry-per-(market,outcome)) with ``copy_and_hold_rois``
    — just keyed by the ``category`` carried on each ``Buy`` so a wallet's edge
    can be read one market type at a time, never on a different buy set than the
    whole-wallet replay."""
    out: dict[str, list[float]] = defaultdict(list)
    for cat, roi in _copy_hold_rois(
            buys, min_usd=min_usd, first_entry_only=first_entry_only):
        out[cat].append(roi)
    return dict(out)


def select_copyable_categories(
    buys: Iterable[object],
    cost_model,
    *,
    min_n: int = 8,
    min_usd: float = 500.0,
    first_entry_only: bool = True,
) -> dict[str, CategoryEdge]:
    """Per-category copy-and-hold edge for one wallet, each tagged approved/not.

    ``cost_model`` is a ``copy_cost.CostModel`` (provides ``edge_floor`` and
    ``net_roi`` per category). A category is **approved** when it has at least
    ``min_n`` resolved copies AND its cost-adjusted ROI/$ clears the category's
    tradable-edge floor — i.e. the edge survives real-money spread plus margin.
    The ``min_n`` bar is load-bearing: it stops a lucky 3-bet category (the n=10
    crypto trap) from being promoted to real capital."""
    by_cat = copy_and_hold_rois_by_category(
        buys, min_usd=min_usd, first_entry_only=first_entry_only)
    out: dict[str, CategoryEdge] = {}
    for cat, rois in by_cat.items():
        n = len(rois)
        mean = statistics.mean(rois) if rois else 0.0
        net = cost_model.net_roi(mean, cat)
        floor = cost_model.edge_floor(cat)
        out[cat] = CategoryEdge(
            category=cat,
            n=n,
            mean_roi=round(mean, 4),
            tstat=round(tstat(rois), 3),
            hit_rate=round(sum(1 for r in rois if r > 0) / n, 4) if n else 0.0,
            net_roi=round(net, 4),
            required=round(floor, 4),
            approved=(n >= min_n and mean >= floor),
        )
    return out


def approved_category_set(edges: dict[str, CategoryEdge]) -> frozenset:
    """The set of categories a wallet is cleared to be copied in."""
    return frozenset(c for c, e in edges.items() if e.approved)


# --------------------------------------------------------------------------- #
# Activity-based replay (shared with the calibration backtest)
# --------------------------------------------------------------------------- #

def forward_copy_rois(
    forward_acts: Iterable[dict],
    resolutions: dict,
    *,
    min_usd: float = 100.0,
    slippage_bps: float = 0.0,
    follow_exits: bool = True,
) -> list[float]:
    """Replay copying each forward BUY from a raw /activity slice.

    Single source of truth for "what a copy earns", shared with
    ``backtest/theory_backtest.py``. With ``follow_exits`` a copied BUY is closed
    at the target's later SELL (the round trip); otherwise — and as the fallback
    when they held — it pays the resolution payoff. ``slippage_bps`` models
    execution drag (fill worse on entry, sell into a worse bid). Buys outside the
    copyable band or below ``min_usd`` are skipped, matching the live detector.
    """
    slip = slippage_bps / 10000.0
    sells: dict[tuple, list] = {}
    buys: list[tuple] = []
    for ev in forward_acts:
        if ev.get("type") != "TRADE":
            continue
        cid, oi = ev.get("conditionId"), ev.get("outcomeIndex")
        price = float(ev.get("price") or 0.0)
        if not cid or price <= 0:
            continue
        ts = float(ev.get("timestamp") or 0.0)
        size = float(ev.get("size") or 0.0)
        if ev.get("side") == "SELL":
            sells.setdefault((cid, oi), []).append((ts, price, size))
        elif ev.get("side") == "BUY":
            usd = float(ev.get("usdcSize") or 0.0) or size * price
            if usd >= min_usd and is_copyable_entry(price):
                buys.append((cid, oi, ts, price))

    rois: list[float] = []
    for cid, oi, ts, price in buys:
        entry = min(0.99, price * (1.0 + slip))   # we fill worse than they did
        later = [s for s in sells.get((cid, oi), []) if s[0] >= ts] if follow_exits else []
        if later:  # exit-following: close when the target sells (into a worse bid)
            tot_sz = sum(s[2] for s in later) or 1.0
            exit_price = sum(s[1] * s[2] for s in later) / tot_sz * (1.0 - slip)
            rois.append(exit_price / entry - 1.0)
            continue
        res = resolutions.get(cid)
        if res is not None and getattr(res, "winning_index", None) is not None:
            won = (oi is not None and int(oi) == int(res.winning_index))
            rois.append((1.0 / entry - 1.0) if won else -1.0)
        # else: unresolved and not exited — can't score, skip
    return rois
