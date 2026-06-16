"""Shared per-wallet feature bundle for the strategy theories (1a..1z).

The discovery funnel is moving from a single AND-gate to a registry of
*independent* detector theories (see ``theories.py``): a wallet graduates to
the paper watchlist if **any** theory flags it, tagged with which one and why.
Each theory is a different hypothesis about what a copyable trader looks like,
with its own backtest-calibrated thresholds.

To keep theories cheap to add and side-effect-free, all the raw feature
extraction happens once here. ``build_context`` reduces a wallet's ``/activity``
feed (plus optional market-resolution data and precomputed curve/lead-lag
signals) into a ``WalletContext`` the detectors read from — they never touch the
network or re-parse activity.

Crucially this models **early exits**: ``round_trips`` pairs BUYs with later
SELLs on the same outcome, so a trader who enters mispriced and sells into the
move *before* resolution is measured on the round-trip, not assumed to hold to
settlement.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from src.copy_trading.entry_profile import EntryProfile, entry_profile
from src.copy_trading.pnl_curve import CurveMetrics
from src.copy_trading.trader_scoring import (
    SHARE_EPSILON,
    MarketResult,
    WalletMetrics,
    classify_market,
    compute_wallet_metrics,
    realized_market_results,
)

_REWARD_TYPES = frozenset({"REWARD", "MAKER_REBATE", "YIELD"})


@dataclass(frozen=True)
class MarketResolution:
    """How a market settled (from the Gamma/markets API)."""

    winning_index: Optional[int]   # outcome index that resolved YES, or None if unknown
    end_ts: float = 0.0            # epoch seconds of resolution


@dataclass(frozen=True)
class Buy:
    """One BUY trade, enriched with resolution outcome + timing when known."""

    condition_id: str
    outcome_index: object
    token: str
    price: float
    usd: float
    ts: float
    title: str
    category: str
    won: Optional[bool] = None                 # did this outcome resolve YES?
    hours_before_resolution: Optional[float] = None


@dataclass(frozen=True)
class RoundTrip:
    """A fully-exited position (bought, then sold out before redeeming).

    These are the *early-exit* trades — the trader took profit (or cut losses)
    into the move rather than holding to resolution.
    """

    condition_id: str
    category: str
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    entry_ts: float
    exit_ts: float
    held_s: float

    @property
    def roi(self) -> float:
        cost = self.entry_price * self.shares
        return self.pnl / cost if cost > 0 else 0.0


@dataclass
class WalletContext:
    wallet: str
    now: float
    closed: list[MarketResult] = field(default_factory=list)
    metrics: WalletMetrics = field(default_factory=WalletMetrics)
    entry: EntryProfile = field(default_factory=EntryProfile)
    curve: CurveMetrics = field(default_factory=CurveMetrics)
    buys: list[Buy] = field(default_factory=list)
    round_trips: list[RoundTrip] = field(default_factory=list)
    # lead-lag copyability (filled by the deep stage; 0 if not computed)
    capture_cents: float = 0.0
    lead_cents: float = 0.0
    capture_hit_rate: float = 0.0
    n_capture: int = 0


def _build_buys(activity, resolutions, now) -> list[Buy]:
    out: list[Buy] = []
    for ev in activity:
        if ev.get("type") != "TRADE" or ev.get("side") != "BUY":
            continue
        cid = ev.get("conditionId")
        price = float(ev.get("price") or 0.0)
        if not cid or price <= 0.0:
            continue
        usd = float(ev.get("usdcSize") or 0.0) or float(ev.get("size") or 0.0) * price
        ts = float(ev.get("timestamp") or 0.0)
        oi = ev.get("outcomeIndex")
        res = resolutions.get(cid) if resolutions else None
        won = None
        hbr = None
        if res is not None and res.winning_index is not None and oi is not None:
            try:
                won = int(oi) == int(res.winning_index)
            except (TypeError, ValueError):
                won = None
        if res is not None and res.end_ts and ts:
            hbr = (res.end_ts - ts) / 3600.0
        out.append(Buy(
            condition_id=cid, outcome_index=oi, token=ev.get("asset") or "",
            price=price, usd=usd, ts=ts,
            title=ev.get("title") or "", category=classify_market(ev.get("title") or ""),
            won=won, hours_before_resolution=hbr,
        ))
    return out


def _build_round_trips(activity) -> list[RoundTrip]:
    """Pair BUYs and SELLs per (market, outcome); a fully-exited leg = a round trip.

    A position the wallet REDEEMED (held to resolution) is *not* a round trip —
    those are captured by the closed-ROI path. Round trips are specifically the
    early exits we want to mirror.
    """
    agg: dict[tuple, dict] = defaultdict(lambda: {
        "buy_usd": 0.0, "buy_sh": 0.0, "sell_usd": 0.0, "sell_sh": 0.0,
        "first_buy_ts": 0.0, "last_sell_ts": 0.0, "redeemed": False,
        "category": "other",
    })
    for ev in activity:
        cid = ev.get("conditionId")
        if not cid or ev.get("type") in _REWARD_TYPES:
            continue
        oi = ev.get("outcomeIndex")
        key = (cid, oi)
        a = agg[key]
        ts = float(ev.get("timestamp") or 0.0)
        usd = float(ev.get("usdcSize") or 0.0)
        sh = float(ev.get("size") or 0.0)
        if ev.get("title") and a["category"] == "other":
            a["category"] = classify_market(ev.get("title"))
        etype = ev.get("type")
        if etype == "TRADE" and ev.get("side") == "BUY":
            a["buy_usd"] += usd
            a["buy_sh"] += sh
            if a["first_buy_ts"] == 0.0 or ts < a["first_buy_ts"]:
                a["first_buy_ts"] = ts
        elif etype == "TRADE" and ev.get("side") == "SELL":
            a["sell_usd"] += usd
            a["sell_sh"] += sh
            a["last_sell_ts"] = max(a["last_sell_ts"], ts)
        elif etype == "REDEEM":
            a["redeemed"] = True

    trips: list[RoundTrip] = []
    for (cid, _oi), a in agg.items():
        if a["redeemed"] or a["buy_sh"] <= 0 or a["sell_sh"] <= 0:
            continue
        # fully exited: sold ~all the shares bought (and never redeemed)
        if a["sell_sh"] < a["buy_sh"] - SHARE_EPSILON:
            continue
        entry = a["buy_usd"] / a["buy_sh"]
        exit_ = a["sell_usd"] / a["sell_sh"]
        trips.append(RoundTrip(
            condition_id=cid, category=a["category"],
            entry_price=entry, exit_price=exit_, shares=a["buy_sh"],
            pnl=a["sell_usd"] - a["buy_usd"],
            entry_ts=a["first_buy_ts"], exit_ts=a["last_sell_ts"],
            held_s=max(0.0, a["last_sell_ts"] - a["first_buy_ts"]),
        ))
    return trips


def build_context(
    wallet: str,
    activity: Iterable[dict],
    *,
    now: float,
    resolutions: dict[str, MarketResolution] | None = None,
    lookback_ts: float = 0.0,
    category: str = "ALL",
    curve: CurveMetrics | None = None,
    capture_cents: float = 0.0,
    lead_cents: float = 0.0,
    capture_hit_rate: float = 0.0,
    n_capture: int = 0,
) -> WalletContext:
    """Reduce a wallet's activity into the shared feature bundle."""
    activity = list(activity)
    return WalletContext(
        wallet=wallet,
        now=now,
        closed=[r for r in realized_market_results(activity) if r.closed],
        metrics=compute_wallet_metrics(activity, start_ts=lookback_ts, category=category),
        entry=entry_profile(activity),
        curve=curve or CurveMetrics(),
        buys=_build_buys(activity, resolutions, now),
        round_trips=_build_round_trips(activity),
        capture_cents=capture_cents,
        lead_cents=lead_cents,
        capture_hit_rate=capture_hit_rate,
        n_capture=n_capture,
    )
