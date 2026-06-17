"""Unified per-strategy + per-wallet P&L aggregation across both copy systems.

Two independent copy systems accrue P&L:

  * **System A — tiered live executor.** Realized rows in ``realized-pnl.jsonl``
    (each now stamped with ``tier`` 1a/1b/1c and the followed ``trader_address``)
    plus open inventory positions marked to market (``OpenPositionPnl``).

  * **System B — discovery → paper-copy harness.** ``PaperPosition`` rows in
    ``copy_paper_ledger.jsonl``: every position carries its ``target`` wallet and
    the discovery strategy theories (1a..1j) that ``flagged_by`` it. Closed
    positions are realized (resolution or exit-following); open ones are not
    marked to market.

This module is **pure** — rows/positions/price-derived inputs are injected, so it
unit-tests without network or disk. It produces, per strategy and overall, the
realized/unrealized/net P&L and a per-wallet breakdown ranked for the
promote-to-real-money / drop decision.

Attribution & double-counting rules (see ``build_unified``):
  * One ``WalletPnl`` per (system, wallet). A System-B wallet flagged by several
    theories is listed under *each* theory's ``StrategyPnl`` but counted **once**
    in the grand total.
  * ROI denominator is *measured* capital: System A counts realized cost + priced
    open cost; System B counts only closed (realized) ``spent`` — open paper bets
    have no mark, so they don't drag ROI, they just show as open count/capital.
  * Rows/positions with no attribution land in ``untagged-A`` / ``untagged-B`` so
    the grand total always reconciles.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from src.copy_trading.copy_paper import PaperPosition, is_dust_fill
from src.copy_trading.pnl import OpenPositionPnl

_UNKNOWN_WALLET = "(unknown)"
UNTAGGED_A = "untagged-A"
UNTAGGED_B = "untagged-B"

# Resolved-sample maturity bands — "is there enough *settled* paper data to
# judge this wallet/theory yet?" A freshly-enabled theory (1a/1e/1j) looks like
# noise until enough of its copies resolve, so we annotate by settled count.
MATURITY_THIN = 5      # below this: too few resolved bets to read the ROI as signal
MATURITY_READY = 15    # at/above this: enough settled data to consider promoting


def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> Optional[float]:
    """Lower bound of the Wilson score interval for a hit-rate over ``n``
    resolved bets (None when n==0). Honest about small samples: 3/3 wins gives
    ~0.44, not 1.0 — so a tiny lucky streak doesn't read as a proven edge. The
    band tightens toward the point estimate as ``n`` grows."""
    if n <= 0:
        return None
    phat = wins / n
    denom = 1.0 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def maturity_tag(n_closed: int) -> str:
    """A glyph for how much *settled* data backs a wallet/theory's numbers."""
    if n_closed < MATURITY_THIN:
        return "\U0001f9ca"   # 🧊 thin — too few resolved bets to trust
    if n_closed < MATURITY_READY:
        return "\U0001f331"   # 🌱 building
    return "✅"           # ✅ enough settled data


def promotion_verdict(net_pnl: float, n_closed: int) -> tuple[str, str]:
    """(verdict, reason) for the promote-paper-wallet-to-real-money decision.

    Gates on *settled sample size* + *positive measured PnL* — deliberately NOT
    on hit-rate, because a +EV longshot theory (e.g. 1e) wins well under 50% of
    the time by design and a hit-rate gate would wrongly hold it. Advisory only;
    promotion stays a manual ``.env`` edit the owner makes."""
    if n_closed < MATURITY_READY:
        return ("HOLD", f"only {n_closed} resolved (need ≥{MATURITY_READY})")
    if net_pnl <= 0:
        return ("HOLD", "paper PnL not positive")
    return ("PROMOTE-READY", f"{n_closed} resolved, ${net_pnl:+.0f} paper")


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #

@dataclass
class WalletPnl:
    wallet: str
    system: str                       # "A" or "B"
    strategies: tuple = ()            # labels this wallet contributes under, e.g. ("B:1b","B:1f")
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0       # System A only; always 0 for B
    cost_basis: float = 0.0           # ROI denominator — measured capital (see module docstring)
    open_cost: float = 0.0            # capital in still-open positions (display only)
    n_open: int = 0
    n_closed: int = 0
    wins: int = 0
    losses: int = 0

    @property
    def net_pnl(self) -> float:
        return round(self.realized_pnl + self.unrealized_pnl, 2)

    @property
    def roi(self) -> Optional[float]:
        return (self.net_pnl / self.cost_basis) if self.cost_basis > 0 else None

    @property
    def hit_rate(self) -> Optional[float]:
        n = self.wins + self.losses
        return (self.wins / n) if n else None


@dataclass
class StrategyPnl:
    label: str                        # "A:1a".."A:1c", "B:1a".."B:1j", or an untagged bucket
    system: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    cost_basis: float = 0.0
    open_cost: float = 0.0
    n_open: int = 0
    n_closed: int = 0
    wins: int = 0
    losses: int = 0
    wallets: list = field(default_factory=list)   # list[WalletPnl]

    @property
    def net_pnl(self) -> float:
        return round(self.realized_pnl + self.unrealized_pnl, 2)

    @property
    def roi(self) -> Optional[float]:
        return (self.net_pnl / self.cost_basis) if self.cost_basis > 0 else None

    @property
    def n_wallets(self) -> int:
        return len(self.wallets)

    def _add(self, w: WalletPnl) -> None:
        self.realized_pnl += w.realized_pnl
        self.unrealized_pnl += w.unrealized_pnl
        self.cost_basis += w.cost_basis
        self.open_cost += w.open_cost
        self.n_open += w.n_open
        self.n_closed += w.n_closed
        self.wins += w.wins
        self.losses += w.losses
        self.wallets.append(w)


@dataclass
class BestWorst:
    by_pnl_best: list = field(default_factory=list)
    by_pnl_worst: list = field(default_factory=list)
    by_roi_best: list = field(default_factory=list)
    by_roi_worst: list = field(default_factory=list)


@dataclass
class UnifiedPnl:
    strategies: list = field(default_factory=list)   # list[StrategyPnl], ordered
    total_realized: float = 0.0
    total_unrealized: float = 0.0

    @property
    def total_net(self) -> float:
        return round(self.total_realized + self.total_unrealized, 2)


# --------------------------------------------------------------------------- #
# System A aggregation
# --------------------------------------------------------------------------- #

def aggregate_system_a(
    realized_rows: list[dict],
    open_positions: list[OpenPositionPnl],
    tier_of: Optional[Callable[[str], Optional[str]]] = None,
) -> list[WalletPnl]:
    """Per-wallet P&L for the tiered executor.

    ``tier_of`` (e.g. ``strategy_config.get_wallet_tier``) is a fallback for rows
    written before tier-stamping landed; ``None`` skips the fallback.
    """
    acc: dict[str, WalletPnl] = {}

    def _wp(wallet: str) -> WalletPnl:
        key = wallet or _UNKNOWN_WALLET
        wp = acc.get(key)
        if wp is None:
            wp = WalletPnl(wallet=key, system="A")
            acc[key] = wp
        return wp

    def _label(tier: str) -> str:
        return f"A:{tier}" if tier else UNTAGGED_A

    def _resolve_tier(stamped: str, wallet: str) -> str:
        if stamped:
            return stamped
        if wallet and tier_of is not None:
            return tier_of(wallet) or ""
        return ""

    for r in realized_rows:
        wallet = (r.get("trader_address") or "").lower()
        tier = _resolve_tier(r.get("tier") or "", wallet)
        wp = _wp(wallet)
        pnl = float(r.get("pnl", 0.0) or 0.0)
        cost = float(r.get("cost_basis", 0.0) or 0.0)
        wp.realized_pnl += pnl
        wp.cost_basis += cost
        wp.n_closed += 1
        won = r.get("won")
        if won is True or (won is None and pnl > 0):
            wp.wins += 1
        elif won is False or (won is None and pnl < 0):
            wp.losses += 1
        _add_label(wp, _label(tier))

    for p in open_positions:
        wallet = (p.trader_address or "").lower()
        tier = _resolve_tier(p.tier or "", wallet)
        wp = _wp(wallet)
        wp.open_cost += p.cost
        wp.n_open += 1
        if p.unrealized_pnl is not None:
            wp.unrealized_pnl += p.unrealized_pnl
            wp.cost_basis += p.cost        # only priced (measured) open cost feeds ROI
        _add_label(wp, _label(tier))

    _round(acc.values())
    return list(acc.values())


# --------------------------------------------------------------------------- #
# System B aggregation
# --------------------------------------------------------------------------- #

def aggregate_system_b(
    paper_positions: list[PaperPosition],
    flagged_by_now: Optional[dict] = None,
) -> list[WalletPnl]:
    """Per-wallet P&L for the paper-copy harness.

    ``flagged_by_now`` (lowercased wallet -> theory list, e.g. from the current
    watchlist) is a fallback for positions opened before ``flagged_by`` was
    stamped. Dust fills are excluded to match ``copy_paper.report``.
    """
    flagged_by_now = {k.lower(): v for k, v in (flagged_by_now or {}).items()}
    acc: dict[str, WalletPnl] = {}

    for p in paper_positions:
        if is_dust_fill(p):
            continue
        wallet = (p.target or "").lower() or _UNKNOWN_WALLET
        wp = acc.get(wallet)
        if wp is None:
            wp = WalletPnl(wallet=wallet, system="B")
            acc[wallet] = wp

        theories = list(p.flagged_by) or flagged_by_now.get(wallet, [])
        labels = [f"B:{t}" for t in theories] if theories else [UNTAGGED_B]

        if p.closed:
            wp.realized_pnl += p.pnl
            wp.cost_basis += p.spent       # realized capital feeds ROI
            wp.n_closed += 1
            if p.won:
                wp.wins += 1
            else:
                wp.losses += 1
        else:
            wp.open_cost += p.spent
            wp.n_open += 1

        for lbl in labels:
            _add_label(wp, lbl)

    _round(acc.values())
    return list(acc.values())


# --------------------------------------------------------------------------- #
# Unification + ranking
# --------------------------------------------------------------------------- #

def build_unified(a_wallets: list[WalletPnl], b_wallets: list[WalletPnl]) -> UnifiedPnl:
    """Combine per-wallet lists into ordered per-strategy blocks + grand totals.

    Grand totals are summed over the **unique** wallet list (never over strategy
    blocks), so a multi-theory wallet isn't counted twice.
    """
    all_wallets = list(a_wallets) + list(b_wallets)

    strat: dict[str, StrategyPnl] = {}
    for wp in all_wallets:
        for lbl in wp.strategies:
            sp = strat.get(lbl)
            if sp is None:
                sp = StrategyPnl(label=lbl, system=("A" if lbl.startswith("A:") or lbl == UNTAGGED_A else "B"))
                strat[lbl] = sp
            sp._add(wp)

    ordered = sorted(strat.values(), key=lambda s: _label_sort_key(s.label))
    for sp in ordered:
        sp.realized_pnl = round(sp.realized_pnl, 2)
        sp.unrealized_pnl = round(sp.unrealized_pnl, 2)
        sp.cost_basis = round(sp.cost_basis, 2)
        sp.open_cost = round(sp.open_cost, 2)

    total_realized = round(sum(w.realized_pnl for w in all_wallets), 2)
    total_unrealized = round(sum(w.unrealized_pnl for w in all_wallets), 2)
    return UnifiedPnl(
        strategies=ordered,
        total_realized=total_realized,
        total_unrealized=total_unrealized,
    )


def best_worst(wallets: list, k: int = 3) -> BestWorst:
    """Top-k / bottom-k wallets by net P&L and by ROI.

    ROI rankings include only wallets with a defined ROI (non-zero measured
    capital), so a wallet with nothing realized yet isn't ranked on ROI.
    """
    by_net = sorted(wallets, key=lambda w: w.net_pnl)
    with_roi = [w for w in wallets if w.roi is not None]
    by_roi = sorted(with_roi, key=lambda w: w.roi)
    return BestWorst(
        by_pnl_best=list(reversed(by_net[-k:])),
        by_pnl_worst=by_net[:k],
        by_roi_best=list(reversed(by_roi[-k:])),
        by_roi_worst=by_roi[:k],
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _add_label(wp: WalletPnl, label: str) -> None:
    if label not in wp.strategies:
        wp.strategies = wp.strategies + (label,)


def _round(wps) -> None:
    for wp in wps:
        wp.realized_pnl = round(wp.realized_pnl, 2)
        wp.unrealized_pnl = round(wp.unrealized_pnl, 2)
        wp.cost_basis = round(wp.cost_basis, 2)
        wp.open_cost = round(wp.open_cost, 2)


def _label_sort_key(label: str):
    """Order: System A strategies, then System B, then untagged buckets last.

    Within a system, natural theory order (1a, 1b, ... 1j)."""
    if label == UNTAGGED_A:
        return (2, "")
    if label == UNTAGGED_B:
        return (3, "")
    system, _, name = label.partition(":")
    return (0 if system == "A" else 1, name)
