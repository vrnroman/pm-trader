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

# Floor on a credible fill price, as a fraction of the target's price. A
# same-side ask far below what the target just paid is stale/erroneous book
# data (a real CLOB ask under the market is arbitraged instantly), so we don't
# fill there. Shared by the live fill simulator and the dust-position guard.
MIN_FILL_FRAC = 0.5


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
    min_fill_frac: float = MIN_FILL_FRAC,
) -> FillSim:
    """Simulate copying a BUY by walking the live asks book.

    We deploy up to ``copy_usd``, taking ask levels in ascending price until the
    budget is filled or the price exceeds ``their_price * (1 + max_slippage)``
    (we don't chase beyond that). Captures the realistic adverse-selection cost
    of acting after the target.

    Levels priced below ``their_price * min_fill_frac`` are skipped as stale or
    erroneous book data: a credible same-side ask can't sit far under the price
    the target just paid (a real CLOB ask below the market would be arbitraged
    instantly). Without this floor a single dust ask (e.g. 0.001 under a 0.62
    market) gets swept, inflating the share count and producing a nonsensical
    favourable "drag" of tens of thousands of dollars.
    """
    if their_price <= 0 or copy_usd <= 0 or not asks:
        return FillSim(0.0, 0.0, 0.0, 0)
    max_price = their_price * (1 + max_slippage_bps / 10000.0)
    min_price = their_price * min_fill_frac
    spent = shares = 0.0
    for price, size in sorted(asks):
        if price < min_price:
            continue  # non-credible deep-discount level — skip, don't sweep it
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
    # human-readable context for notifications (optional; default-safe so old
    # ledger lines that predate these keys still load):
    title: str = ""         # market question, e.g. "Will BTC hit $100k in 2025?"
    slug: str = ""          # PM event slug -> polymarket.com/event/<slug>
    # Discovery strategy theories that flagged the target wallet (e.g. ("1b","1f")),
    # stamped at open so per-strategy P&L attribution is stable even as the
    # watchlist re-flags the wallet later. Default-safe: old ledger lines load as ().
    flagged_by: tuple = ()
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
    # guardrail skips (why a detected BUY was NOT copied):
    skipped_fill_gate: int = 0          # our fill would chase too far above their price
    skipped_not_first_entry: int = 0    # averaging-down / re-entry into a copied market
    skipped_slate_cap: int = 0          # per-(wallet|category)-day concentration cap hit
    resolved: int = 0
    exited: int = 0  # closed by following the target's SELL
    # the positions that resolved *this* cycle, so callers can name them in a
    # notification instead of only reporting cumulative ledger aggregates.
    resolved_positions: list["PaperPosition"] = field(default_factory=list)


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
        # --- entry guardrails (all default-OFF so the bare engine is unchanged;
        # the live runner switches them on from config) ---
        # fill-gate: skip a copy whose achievable fill is more than this many bps
        # ABOVE the target's price — i.e. don't chase a moved book (None = off).
        fill_gate_bps: Optional[int] = None,
        # only copy a wallet's FIRST entry into a (market, outcome); skip its
        # averaging-down / re-entry buys (the harness copies the opening trade).
        first_entry_only: bool = False,
        # slate circuit-breaker: cap copies opened per UTC day per wallet and per
        # category, so one correlated same-day slate can't dominate (None = off).
        max_copies_per_wallet_day: Optional[int] = None,
        max_copies_per_category_day: Optional[int] = None,
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
        self.fill_gate_bps = fill_gate_bps
        self.first_entry_only = first_entry_only
        self.max_copies_per_wallet_day = max_copies_per_wallet_day
        self.max_copies_per_category_day = max_copies_per_category_day

    def run_cycle(self, now: Optional[float] = None) -> CycleSummary:
        now = now if now is not None else time.time()
        s = CycleSummary()

        # Guardrail state, seeded from the existing ledger so caps/dedup persist
        # across cycles and restarts, then updated as we open within this cycle.
        day = int(now // 86400)
        entered_tokens = {(p.target, p.token_id) for p in self.ledger.positions.values()}
        wallet_day: dict[str, int] = {}
        cat_day: dict[str, int] = {}
        for p in self.ledger.positions.values():
            if int((p.opened_ts or 0) // 86400) == day:
                wallet_day[p.target] = wallet_day.get(p.target, 0) + 1
                cat_day[p.category] = cat_day.get(p.category, 0) + 1

        for tr in self.detector():
            s.detected += 1
            cid = tr["copy_id"]
            if self.ledger.has(cid):
                continue
            target = tr["target"]
            token = tr["token_id"]
            category = tr.get("category", "other")
            # first-entry-only: skip averaging-down / re-entry into a market we
            # already copied from this target (we copy the opening trade only).
            if self.first_entry_only and (target, token) in entered_tokens:
                s.skipped_not_first_entry += 1
                continue
            # slate circuit-breaker: cap correlated same-day copies per wallet
            # and per category before we even price the book.
            if (self.max_copies_per_wallet_day is not None
                    and wallet_day.get(target, 0) >= self.max_copies_per_wallet_day):
                s.skipped_slate_cap += 1
                continue
            if (self.max_copies_per_category_day is not None
                    and cat_day.get(category, 0) >= self.max_copies_per_category_day):
                s.skipped_slate_cap += 1
                continue
            copy_usd = min(self.max_copy_usd, tr.get("their_usd", 0) * self.copy_pct)
            fill = simulate_copy_fill(
                tr["their_price"], self.book_fetcher(tr["token_id"]),
                copy_usd, max_slippage_bps=self.max_slippage_bps,
            )
            if fill.shares <= 0:
                s.skipped_unfilled += 1
                continue
            # fill-gate: don't chase a moved book — skip when our achievable fill
            # is more than fill_gate_bps above the target's price.
            if self.fill_gate_bps is not None and fill.drag_bps > self.fill_gate_bps:
                s.skipped_fill_gate += 1
                continue
            self.ledger.add(PaperPosition(
                copy_id=cid, target=target, condition_id=tr["condition_id"],
                token_id=token, outcome_index=int(tr["outcome_index"]),
                category=category, their_price=tr["their_price"],
                title=tr.get("title", ""), slug=tr.get("slug", ""),
                flagged_by=tuple(tr.get("flagged_by", ())),
                entry_price=fill.avg_price, shares=fill.shares, spent=fill.spent,
                drag_bps=fill.drag_bps, opened_ts=now,
            ))
            s.opened += 1
            entered_tokens.add((target, token))
            wallet_day[target] = wallet_day.get(target, 0) + 1
            cat_day[category] = cat_day.get(category, 0) + 1

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
            s.resolved_positions.append(pos)
        if s.resolved or s.exited:
            self.ledger.save()
        return s


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def is_dust_fill(p: PaperPosition, min_fill_frac: float = MIN_FILL_FRAC) -> bool:
    """True if a position's recorded entry is an implausible deep-discount fill.

    These can only exist in ledgers written before ``simulate_copy_fill`` grew
    its price floor — a $50 budget swept a stale ~0.001 ask into ~50k shares,
    which is what made the cumulative drag read ``-$30000``. Excluding them keeps
    the cumulative stats and notifications honest without rewriting history.
    """
    return (
        p.their_price > 0
        and 0 < p.entry_price < p.their_price * min_fill_frac
    )


def report(ledger: PaperCopyLedger) -> dict:
    open_all = ledger.open_positions()
    closed_all = ledger.closed_positions()
    open_pos = [p for p in open_all if not is_dust_fill(p)]
    closed = [p for p in closed_all if not is_dust_fill(p)]
    quarantined = (len(open_all) - len(open_pos)) + (len(closed_all) - len(closed))
    spent = sum(p.spent for p in closed)
    pnl = sum(p.pnl for p in closed)
    ideal = sum(p.ideal_pnl for p in closed)
    wins = sum(1 for p in closed if p.won)
    drags = [p.drag_bps for p in closed]
    return {
        "open": len(open_pos),
        "closed": len(closed),
        # positions excluded as pre-fix dust fills (0 once the ledger is clean):
        "quarantined": quarantined,
        "capital_deployed": round(spent, 2),
        "realized_pnl": round(pnl, 2),
        "realized_roi": round(pnl / spent, 4) if spent else 0.0,
        "ideal_pnl_no_drag": round(ideal, 2),
        "execution_drag_cost": round(ideal - pnl, 2),
        "avg_drag_bps": round(sum(drags) / len(drags), 1) if drags else 0.0,
        "hit_rate": round(wins / len(closed), 4) if closed else 0.0,
    }


# --------------------------------------------------------------------------- #
# Telegram formatting (presentation; HTML parse mode)
# --------------------------------------------------------------------------- #

def _esc(s: str) -> str:
    """Minimal HTML escape for Telegram (parse_mode=HTML)."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _short_wallet(w: str) -> str:
    w = w or ""
    return f"{w[:6]}…{w[-4:]}" if len(w) > 12 else (w or "—")


def _signed_usd(x: float) -> str:
    """'+$69' / '-$50' — sign before the dollar sign so it reads as money."""
    return f"{'+' if x >= 0 else '-'}${abs(x):,.0f}"


def format_resolution_telegram(resolved: list[PaperPosition], rep: dict) -> str:
    """Build the human-readable Telegram message for resolved paper copies.

    One block per market that just settled — what it was (the question), whether
    the copy won or lost, the cost→payout economics, the execution drag we ate,
    and a link to dig deeper on Polymarket — followed by a single labelled line
    of cumulative-ledger context. Replaces the old cryptic one-liner that mixed
    a per-cycle event count with whole-ledger aggregates.
    """
    # Skip pre-fix dust fills: a stale open position can still resolve after the
    # fix deploys, and its garbage entry price would render a nonsensical block.
    shown = [p for p in resolved if not is_dust_fill(p)]
    stale = len(resolved) - len(shown)
    n = len(shown)
    plural = "s" if n != 1 else ""
    lines = [f"📋 <b>Paper-copy</b> — {n} market{plural} resolved"]

    for p in shown:
        won = p.won
        verdict = "✅ WON" if won else "❌ LOST"
        title = _esc(p.title) or f"({p.category} market)"
        payout = p.spent + p.pnl  # = shares if won else 0
        roi = (p.pnl / p.spent * 100.0) if p.spent else 0.0
        lines.append("")  # blank line separates blocks
        lines.append(f'{verdict} · "{title}"')
        lines.append(
            f"copied <code>{_short_wallet(p.target)}</code> · "
            f"${p.spent:,.0f} → ${payout:,.0f} ({_signed_usd(p.pnl)}, {roi:+.0f}%) · "
            f"entry {p.entry_price:.3f} vs their {p.their_price:.3f} ({p.drag_bps:+d}bps drag)"
        )
        if p.slug:
            lines.append(f"🔗 https://polymarket.com/event/{p.slug}")

    if stale:
        lines.append("")
        lines.append(
            f"⚠️ {stale} stale dust-fill position{'s' if stale != 1 else ''} "
            "excluded (pre-fix data)"
        )

    lines.append("")
    lines.append(
        "📊 <b>Ledger:</b> "
        f"{rep['closed']} closed · realized {_signed_usd(rep['realized_pnl'])} "
        f"(ROI {rep['realized_roi'] * 100:+.0f}%) · hit {rep['hit_rate'] * 100:.0f}% · "
        f"avg drag {rep['avg_drag_bps']:+.0f}bps · {rep['open']} open"
    )
    return "\n".join(lines)
