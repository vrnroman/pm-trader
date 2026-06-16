"""Forward paper-copy harness for Strategy 1b (execution-drag measurement).

The backtest (`backtest/trader_scoring_backtest.py`) shows that selecting copy
targets by realized closed-position ROI has strong out-of-sample edge — but it
assumes you fill at the target's price. In reality you see their trade *after*
it prints, the price has already moved, and you pay the spread to chase it.

This harness measures how much of that edge survives realistic execution. It
watches a watchlist of target wallets; when a target opens a BUY, it simulates a
copy entry against the *current* live order book (not their price), tracks the
paper position to resolution, and records both the realized PnL and the
execution drag (our entry price − their price). It places no real orders.

The core (fill simulation, PnL, dedup, ledger) is pure and unit tested; live
data access is injected so tests run without the network. A wallet graduates to
real capital only once its *copied* PnL is positive in this ledger.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional


# --------------------------------------------------------------------------- #
# Fill simulation (pure)
# --------------------------------------------------------------------------- #

@dataclass
class FillSim:
    avg_price: float      # our realised average entry price (0 if unfilled)
    spent: float          # USDC deployed
    shares: float         # shares acquired
    drag_bps: int         # (avg_price - their_price) in bps of their_price


def simulate_copy_fill(
    their_price: float,
    asks: list[tuple[float, float]],
    copy_usd: float,
    *,
    max_slippage_bps: int = 200,
) -> FillSim:
    """Simulate copying a BUY by walking the live asks book.

    We deploy up to ``copy_usd``, taking ask levels in ascending price until the
    budget is filled or the price exceeds ``their_price * (1 + max_slippage)``
    (we don't chase beyond that). Captures the realistic adverse-selection cost
    of acting after the target.
    """
    if their_price <= 0 or copy_usd <= 0 or not asks:
        return FillSim(0.0, 0.0, 0.0, 0)
    max_price = their_price * (1 + max_slippage_bps / 10000.0)
    spent = shares = 0.0
    for price, size in sorted(asks):
        if price > max_price or price >= 1.0 or size <= 0:
            break
        take_usd = min(copy_usd - spent, price * size)
        if take_usd <= 1e-9:
            break
        spent += take_usd
        shares += take_usd / price
        if spent >= copy_usd - 1e-9:
            break
    if shares <= 0:
        return FillSim(0.0, 0.0, 0.0, 0)
    avg = spent / shares
    drag = int(round((avg - their_price) / their_price * 10000)) if their_price else 0
    return FillSim(avg_price=avg, spent=spent, shares=shares, drag_bps=drag)


# --------------------------------------------------------------------------- #
# Paper position + ledger
# --------------------------------------------------------------------------- #

@dataclass
class PaperPosition:
    copy_id: str            # dedup key: {their_tx}-{token}
    target: str             # copied wallet
    condition_id: str
    token_id: str
    outcome_index: int
    category: str
    their_price: float
    entry_price: float      # our realised avg
    shares: float
    spent: float
    drag_bps: int
    opened_ts: float
    # filled on resolution OR on following the target's exit:
    closed: bool = False
    won: Optional[bool] = None
    pnl: float = 0.0
    ideal_pnl: float = 0.0  # PnL had we filled at their_price (drag-free)
    closed_ts: float = 0.0
    exited_early: bool = False  # closed by mirroring the target's SELL, not resolution

    def realize(self, won: bool, now: Optional[float] = None) -> None:
        payout = self.shares if won else 0.0
        self.won = won
        self.pnl = payout - self.spent
        ideal_cost = self.shares * self.their_price
        self.ideal_pnl = payout - ideal_cost
        self.closed = True
        self.closed_ts = now if now is not None else time.time()

    def realize_exit(self, exit_price: float, now: Optional[float] = None) -> None:
        """Close by mirroring the target's early SELL, at our achievable exit price.

        Traders don't always hold to resolution — when the target sells, we sell
        too, booking PnL at the price we could actually get rather than waiting
        for (and gambling on) settlement.
        """
        proceeds = self.shares * exit_price
        self.pnl = proceeds - self.spent
        self.ideal_pnl = proceeds - self.shares * self.their_price
        self.won = self.pnl > 0
        self.closed = True
        self.exited_early = True
        self.closed_ts = now if now is not None else time.time()


class PaperCopyLedger:
    """Append-only JSON ledger of paper-copy positions (open + closed)."""

    def __init__(self, path: str):
        self.path = path
        self.positions: dict[str, PaperPosition] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                self.positions[d["copy_id"]] = PaperPosition(**d)

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            for p in self.positions.values():
                f.write(json.dumps(asdict(p)) + "\n")
        os.replace(tmp, self.path)

    def has(self, copy_id: str) -> bool:
        return copy_id in self.positions

    def add(self, pos: PaperPosition) -> None:
        self.positions[pos.copy_id] = pos
        self._persist()

    def open_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions.values() if not p.closed]

    def closed_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions.values() if p.closed]

    def save(self) -> None:
        self._persist()


# --------------------------------------------------------------------------- #
# Engine (I/O injected)
# --------------------------------------------------------------------------- #

# detector() -> list of new target BUY trades, each a dict with keys:
#   copy_id, target, condition_id, token_id, outcome_index, category,
#   their_price, their_usd
DetectFn = Callable[[], list[dict]]
# book_fetcher(token_id) -> list[(price, size)] asks
BookFn = Callable[[str], list[tuple[float, float]]]
# resolver(condition_id) -> winning outcome_index, or None if unresolved
ResolveFn = Callable[[str], Optional[int]]


@dataclass
class CycleSummary:
    detected: int = 0
    opened: int = 0
    skipped_unfilled: int = 0
    resolved: int = 0
    exited: int = 0  # closed by following the target's SELL


class CopyPaperEngine:
    def __init__(
        self,
        ledger: PaperCopyLedger,
        detector: DetectFn,
        book_fetcher: BookFn,
        resolver: ResolveFn,
        *,
        copy_pct: float = 1.0,
        max_copy_usd: float = 50.0,
        max_slippage_bps: int = 200,
        exit_detector: Optional[DetectFn] = None,
        bid_fetcher: Optional[BookFn] = None,
    ):
        self.ledger = ledger
        self.detector = detector
        self.book_fetcher = book_fetcher
        self.resolver = resolver
        self.copy_pct = copy_pct
        self.max_copy_usd = max_copy_usd
        self.max_slippage_bps = max_slippage_bps
        # exit_detector() -> target SELLs: {target, token_id, their_price};
        # bid_fetcher(token_id) -> [(bid_price, size)] for our achievable exit.
        self.exit_detector = exit_detector
        self.bid_fetcher = bid_fetcher

    def run_cycle(self, now: Optional[float] = None) -> CycleSummary:
        now = now if now is not None else time.time()
        s = CycleSummary()

        for tr in self.detector():
            s.detected += 1
            cid = tr["copy_id"]
            if self.ledger.has(cid):
                continue
            copy_usd = min(self.max_copy_usd, tr.get("their_usd", 0) * self.copy_pct)
            fill = simulate_copy_fill(
                tr["their_price"], self.book_fetcher(tr["token_id"]),
                copy_usd, max_slippage_bps=self.max_slippage_bps,
            )
            if fill.shares <= 0:
                s.skipped_unfilled += 1
                continue
            self.ledger.add(PaperPosition(
                copy_id=cid, target=tr["target"], condition_id=tr["condition_id"],
                token_id=tr["token_id"], outcome_index=int(tr["outcome_index"]),
                category=tr.get("category", "other"), their_price=tr["their_price"],
                entry_price=fill.avg_price, shares=fill.shares, spent=fill.spent,
                drag_bps=fill.drag_bps, opened_ts=now,
            ))
            s.opened += 1

        # exit-following: if the target sold something we hold, sell too (at our
        # achievable bid), before falling through to the resolution path.
        if self.exit_detector is not None:
            held = {(p.target, p.token_id): p for p in self.ledger.open_positions()}
            for ex in self.exit_detector():
                pos = held.get((ex.get("target"), ex.get("token_id")))
                if pos is None:
                    continue
                exit_price = ex.get("their_price")
                if self.bid_fetcher is not None:
                    book = self.bid_fetcher(pos.token_id)
                    if book:
                        exit_price = book[0][0]  # best bid
                if exit_price is None:
                    continue
                pos.realize_exit(float(exit_price), now=now)
                s.exited += 1

        for pos in self.ledger.open_positions():
            winner = self.resolver(pos.condition_id)
            if winner is None:
                continue
            pos.realize(won=(winner == pos.outcome_index), now=now)
            s.resolved += 1
        if s.resolved or s.exited:
            self.ledger.save()
        return s


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def report(ledger: PaperCopyLedger) -> dict:
    closed = ledger.closed_positions()
    spent = sum(p.spent for p in closed)
    pnl = sum(p.pnl for p in closed)
    ideal = sum(p.ideal_pnl for p in closed)
    wins = sum(1 for p in closed if p.won)
    drags = [p.drag_bps for p in closed]
    return {
        "open": len(ledger.open_positions()),
        "closed": len(closed),
        "capital_deployed": round(spent, 2),
        "realized_pnl": round(pnl, 2),
        "realized_roi": round(pnl / spent, 4) if spent else 0.0,
        "ideal_pnl_no_drag": round(ideal, 2),
        "execution_drag_cost": round(ideal - pnl, 2),
        "avg_drag_bps": round(sum(drags) / len(drags), 1) if drags else 0.0,
        "hit_rate": round(wins / len(closed), 4) if closed else 0.0,
    }
