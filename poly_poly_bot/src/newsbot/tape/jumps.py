"""The jump detector: a market whose traded price moved more than JUMP_CENTS
inside JUMP_WINDOW_MIN, read off the trade buckets.

Who consumes it: the lead-time ledger (which free source, if any, mentioned
the market before the move, else "dark") and the surprise pings. Dedup is a
per-market cooldown of ``window_min`` from the moment a jump is reported, so
one move produces one row even though the window keeps containing it for the
next ``window_min`` scans. The exclude predicate comes from the caller: the
index knows which conditionIds are sports or 5-minute up/down markets; the
tape does not (2026-10-25).
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from .livedata import TradeBuckets


@dataclass(slots=True, frozen=True)
class Jump:
    condition_id: str
    ts: float  # timestamp of the last trade in the move (seconds)
    delta_cents: float  # last - first over the window, YES space, signed
    from_price: float
    to_price: float
    notional: float  # USD traded inside the window
    n_trades: int


class JumpDetector:
    def __init__(
        self,
        buckets: TradeBuckets,
        *,
        jump_cents: float,
        window_min: int,
        exclude: Callable[[str], bool] = lambda cid: False,
        min_trades: int = 2,
        min_notional: float = 0.0,
        max_tracked: int = 20_000,
    ) -> None:
        if jump_cents <= 0 or window_min < 1:
            raise ValueError("jump_cents must be > 0 and window_min >= 1")
        self.buckets = buckets
        self.jump_cents = float(jump_cents)
        self.window_min = int(window_min)
        self.exclude = exclude
        # A single print cannot be a move; two is the floor for first != last
        # to mean anything (a sample count counts independent observations).
        self.min_trades = int(min_trades)
        # Bid-ask bounce on a thin book is not a move: the Student List 50%
        # market "jumped" five times in 40 minutes between 0.2 and 0.4 on
        # $60-130 a window, the Israel bloc market +14c on two trades and $12.
        self.min_notional = float(min_notional)
        self.below_bar = 0  # windows over the cents bar but under the money or trade bar
        self.max_tracked = int(max_tracked)
        self._fired: OrderedDict[str, float] = OrderedDict()  # cid -> ts reported
        self.reported = 0
        self.excluded = 0

    def in_cooldown(self, condition_id: str, now: float) -> bool:
        t = self._fired.get(condition_id)
        return t is not None and now - t < self.window_min * 60

    def scan(self, now: float) -> list[Jump]:
        """Report every market whose window delta reached ``jump_cents`` and
        that is not excluded or cooling down. ``now`` is the caller's clock."""
        out: list[Jump] = []
        self._expire(now)
        for cid in self.buckets.markets(active_since=now - self.window_min * 60):
            if self.in_cooldown(cid, now):
                continue
            w = self.buckets.window(cid, self.window_min, now)
            if w is None:
                continue
            delta = w.delta_cents
            if abs(delta) < self.jump_cents:
                continue
            if w.n < self.min_trades or w.notional < self.min_notional:
                self.below_bar += 1
                continue
            if self.exclude(cid):
                self.excluded += 1
                self._fired[cid] = now  # no need to re-evaluate it every scan
                continue
            out.append(
                Jump(
                    condition_id=cid,
                    ts=w.last_ts,
                    delta_cents=delta,
                    from_price=w.first_price,
                    to_price=w.last_price,
                    notional=round(w.notional, 2),
                    n_trades=w.n,
                )
            )
            self._fired[cid] = now
            self._fired.move_to_end(cid)
            self.reported += 1
        while len(self._fired) > self.max_tracked:
            self._fired.popitem(last=False)
        return out

    def _expire(self, now: float) -> None:
        horizon = self.window_min * 60
        for cid in [c for c, t in self._fired.items() if now - t >= horizon]:
            del self._fired[cid]
