"""Scalpers are not copyable at our latency (2026-09-24 requirements, part 2 D2).

A wallet whose exits routinely follow its entries within minutes has no
copyable edge for a copier that is told ~30 s late and cannot follow the
exit: on 2026-09-23 the bot bought Spain "No" that the target had left one
second after entering, and ate the full loss. The measure is the share of
the wallet's round trips (a buy, then a sell of the same market) closed
within COPY_FLIP_WINDOW_S; above COPY_FLIP_MAX_FRAC on at least
FLIP_MIN_TRIPS trips the wallet is a scalper. Stated defaults, not measured
optima; the paper books can calibrate them later.

One definition, read by the form rail (a Z wallet is benched), the Z gate
(a candidate is refused) and discovery (theory 1f's "early-exit swing"
profile never reaches the watchlist). A leaf: no imports from the bot.
"""
from __future__ import annotations

import os
from typing import Iterable


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


FLIP_WINDOW_S = _env_f("COPY_FLIP_WINDOW_S", 600.0)
MAX_FLIP_FRAC = _env_f("COPY_FLIP_MAX_FRAC", 0.20)
FLIP_MIN_TRIPS = int(_env_f("COPY_FLIP_MIN_TRIPS", 10))


def flip_stats_from_trips(round_trips: Iterable[object], *, window_s: float = FLIP_WINDOW_S) -> tuple[int, int]:
    """``(exits, flips)`` over ``RoundTrip`` rows (``entry_ts``, ``exit_ts``)."""
    exits = flips = 0
    for t in round_trips:
        try:
            held = float(getattr(t, "exit_ts", 0.0) or 0.0) - float(getattr(t, "entry_ts", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        exits += 1
        if 0.0 <= held <= window_s:
            flips += 1
    return (exits, flips)


def flip_stats_from_acts(acts: Iterable[dict], *, since: float, floor: float = 0.0,
                         window_s: float = FLIP_WINDOW_S) -> tuple[int, int]:
    """``(exits, flips)`` from raw /activity rows: per market, the first BUY
    at or above ``floor`` from ``since`` and the first SELL after it."""
    first_buy: dict = {}
    first_sell: dict = {}
    for a in acts:
        if a.get("type") != "TRADE":
            continue
        cid = str(a.get("conditionId") or "")
        if not cid:
            continue
        try:
            ts = float(a.get("timestamp") or 0)
            usd = float(a.get("usdcSize") or 0)
        except (TypeError, ValueError):
            continue
        if ts < since:
            continue
        if a.get("side") == "BUY" and usd >= floor:
            first_buy[cid] = min(first_buy.get(cid, ts), ts)
        elif a.get("side") == "SELL":
            first_sell.setdefault(cid, []).append(ts)
    exits = flips = 0
    for cid, b in first_buy.items():
        later = [s for s in first_sell.get(cid, []) if s >= b]
        if not later:
            continue
        exits += 1
        if min(later) - b <= window_s:
            flips += 1
    return (exits, flips)


def is_scalper(exits: int, flips: int, *, max_frac: float = MAX_FLIP_FRAC,
               min_trips: int = FLIP_MIN_TRIPS, window_s: float = FLIP_WINDOW_S) -> tuple[bool, str]:
    """``(scalper, reason)``. Under ``min_trips`` exits nothing is said."""
    if exits < min_trips:
        return (False, f"{exits} exit(s) in the window, under the {min_trips} that would say")
    frac = flips / exits
    if frac > max_frac:
        return (True, f"scalper: {frac:.0%} of exits within {window_s / 60:.0f} min; uncopyable at our latency")
    return (False, f"{frac:.0%} of {exits} exits within {window_s / 60:.0f} min")
