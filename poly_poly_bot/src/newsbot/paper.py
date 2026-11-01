"""The paper book: a $5 copy of a news call at the HONEST ask, exited at the
honest bid, fees charged, every exit horizon booked on every row.

Why it looks like this (2026-10-25). The copy bot's paper books scored copies
at the target's own price and read +24% while real money lost 15-25%: the
honest book at the real quote was -9.7% on 50k signals. This book never
writes a price the market did not show us: the entry walks the live ask
ladder for our size, every mark walks the bid ladder for our size, and a
ladder we could not read is "unknown", never a number.

Four books ride the same tickets so the LLM has to beat doing nothing
clever: ``llm`` (fires on the judge's call with a fresh tape), ``tape-first``
(a jump the lead ledger explained by a headline within five minutes),
``headline-any`` (every mapped item, no freshness rule) and ``random`` (one
fire per llm fire, on a random active market). Flat stake, all four
horizons on every row, "best exit" printed as an estimate downstream.
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Callable, Optional

from src.logger import logger

HORIZONS_S = {"5m": 300, "30m": 1800, "2h": 7200, "24h": 86400}
BOOKS = ("llm", "llm-inverse", "llm-tight", "llm-maker", "tape-first", "headline-any", "random")


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def stake_usd() -> float:
    return _env_f("NEWS_STAKE_USD", 5.0)


def price_band() -> tuple[float, float]:
    """Entries only between these prices. At 98.6c the most a win can make is
    1.4c a share and the spread is wider than that; the first live night
    bought "Machado enters Venezuela" at 0.986 and Iotova at 0.91 (owner,
    2026-10-27). Below 5c a $5 stake is a lottery ticket that the control
    book then has to match."""
    return _env_f("NEWS_MIN_PRICE", 0.05), _env_f("NEWS_MAX_PRICE", 0.95)


def max_mark_age_s() -> float:
    """A mark walks a book no older than this. The first week's marks walked
    the ladder cached at ENTRY for any token the watch set had evicted: the
    bid at 5m equalled the bid at 2h on 54 of 56 llm rows while Polymarket's
    own price history moved on 31 of them, so the "2h exit" was the spread
    paid at entry (run s-wj4gnb, 2026-11-01)."""
    return _env_f("NEWS_MARK_MAX_AGE_S", 120.0)


def mark_late_s() -> float:
    """A mark read this long after its horizon is not that horizon's exit
    (downtime, a deferred tick): unknown, with how late it was."""
    return _env_f("NEWS_MARK_LATE_S", 300.0)


def ledger_dir() -> str:
    return os.environ.get("NEWS_DATA_DIR", "data/news")


@dataclass
class Fill:
    """What the ladder gave us for our size. ``filled_usd`` under the stake
    means the book was too thin; ``avg_price`` None means no ladder."""
    avg_price: Optional[float]
    filled_usd: float
    levels: int
    top: Optional[float]          # best price on that side before walking


@dataclass
class PaperRow:
    row_id: str                   # f"{book}:{item_id}:{token_id}"
    book: str                     # llm | headline-any | random
    item_id: str                  # "" for the random book
    source: str
    domains: tuple
    market_id: str
    condition_id: str
    token_id: str
    outcome: str
    question: str
    published_ts: float           # the source's clock (0 for random)
    seen_ts: float
    decided_ts: float
    quote_ts: float               # when the ask was read
    freshness: str                # fresh | moving | late | unknown | n/a
    confidence: float
    why: str
    # the entry, honest
    ask_top: Optional[float]
    entry_price: Optional[float]  # avg over the walked ladder
    stake: float
    filled_usd: float
    fee_bps: Optional[int]
    fee_usd: float
    shares: float
    # marks at the horizons: bid walked for our size; None = not yet / no ladder
    marks: dict = field(default_factory=dict)      # horizon -> {"bid_top","exit_price","ts","pnl"}
    resolved: Optional[bool] = None                # won / lost at resolution
    resolution_pnl: Optional[float] = None
    closed: bool = False
    # A row that should never have been a decision (one post booked twice
    # through two routes, a byte-identical repost): kept with its reason,
    # left out of every count and number (verifier round 7, 2026-10-25).
    void: str = ""
    # The book at entry, both sides: the spread we paid is ask_top - bid_top,
    # and the signal is how the mid moved from mid_entry (run s-wj4gnb).
    bid_top: Optional[float] = None
    mid_entry: Optional[float] = None
    # True when every mark on this row reads a book no older than
    # NEWS_MARK_MAX_AGE_S. Rows from before 2026-11-01 are False: their marks
    # may be the entry book replayed, so /pnl leaves them out of the clean era.
    fresh_marks: bool = False
    # The event the market belongs to: the Serbian turnout night put six
    # threshold markets of one event in the llm book, which is one
    # observation, not six (run s-wj4gnb). Empty on old rows.
    event: str = ""

    def exit_pnl(self, exit_price: float) -> float:
        """Sell everything at ``exit_price`` (the walked bid), fee on the way out
        at the same market rate: shares x p x rate x (1-p)."""
        proceeds = self.shares * exit_price
        rate = (self.fee_bps or 0) / 10000.0
        out_fee = self.shares * exit_price * rate * (1.0 - exit_price)
        return round(proceeds - out_fee - self.filled_usd - self.fee_usd, 4)


class PaperLedger:
    """Append-on-change JSONL per book under data/news/. Rows rewritten whole
    on change (the file is small: tens of rows a day)."""

    def __init__(self, book: str, path: Optional[str] = None):
        self.book = book
        self.path = path or os.path.join(ledger_dir(), f"paper-{book}.jsonl")
        self.rows: dict[str, PaperRow] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        names = {f.name for f in fields(PaperRow)}
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d = {k: v for k, v in d.items() if k in names}
                d["domains"] = tuple(d.get("domains") or ())
                self.rows[d["row_id"]] = PaperRow(**d)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with self._lock:
            with open(tmp, "w", encoding="utf-8") as f:
                for r in self.rows.values():
                    f.write(json.dumps(asdict(r)) + "\n")
            os.replace(tmp, self.path)

    def has(self, row_id: str) -> bool:
        return row_id in self.rows

    def add(self, row: PaperRow) -> None:
        with self._lock:
            self.rows[row.row_id] = row
        self.save()

    def void(self, row_id: str, reason: str) -> bool:
        """Flag a row void, never delete it. False when there is no such row."""
        with self._lock:
            r = self.rows.get(row_id)
            if r is None:
                return False
            r.void = str(reason) or "void"
        self.save()
        return True

    def live_rows(self) -> list[PaperRow]:
        return [r for r in self.rows.values() if not r.void]

    def open_rows(self) -> list[PaperRow]:
        return [r for r in self.rows.values() if not r.closed]

    def fires_on_day(self, day: str) -> int:
        return sum(1 for r in self.live_rows()
                   if time.strftime("%Y-%m-%d", time.gmtime(r.decided_ts)) == day)


def walk(ladder: list[tuple[float, float]], usd: float, side: str) -> Fill:
    """Walk a ladder of (price, size_shares) for ``usd`` of notional. The
    ladder is SORTED HERE (asks ascending, bids descending): the CLOB returns
    bids ascending and asks descending, so a caller's ``[0]`` is the worst
    price on each side (project rule)."""
    rows = [(float(p), float(s)) for p, s in (ladder or []) if float(p) > 0 and float(s) > 0]
    if not rows:
        return Fill(None, 0.0, 0, None)
    rows.sort(key=lambda x: x[0], reverse=(side == "bid"))
    top = rows[0][0]
    left = float(usd)
    spent = 0.0
    shares = 0.0
    levels = 0
    for p, s in rows:
        if left <= 1e-9:
            break
        take_usd = min(left, p * s)
        shares += take_usd / p
        spent += take_usd
        left -= take_usd
        levels += 1
    if shares <= 0:
        return Fill(None, 0.0, 0, top)
    return Fill(round(spent / shares, 6), round(spent, 4), levels, top)


class PaperBook:
    """One book. ``ask_ladder(token_id)`` and ``bid_ladder(token_id)`` are
    injected: live they read the CLOB websocket book with a REST fallback;
    in tests they are lists. ``fee_bps(token_id)`` likewise."""

    def __init__(self, book: str, *, ask_ladder: Callable, bid_ladder: Callable,
                 fee_bps: Callable[[str], Optional[int]], ledger: Optional[PaperLedger] = None,
                 now: Callable[[], float] = time.time,
                 book_ts: Optional[Callable[[str], Optional[float]]] = None):
        assert book in BOOKS, book
        self.book = book
        self.ledger = ledger or PaperLedger(book)
        self._ask = ask_ladder
        self._bid = bid_ladder
        self._fee = fee_bps
        self._now = now
        # When the ladder the last read returned was taken (epoch seconds);
        # None when the caller cannot say (plain lists in tests).
        self._book_ts = book_ts
        self.skipped = {"held": 0, "band": 0}

    def holds(self, condition_id: str) -> bool:
        """An open, not void row on this market already: one position per
        market per book. The first live night bought the same Serbian
        turnout YES six times, once per turnout update (2026-10-26)."""
        return any(r.condition_id == condition_id and not r.void for r in self.ledger.open_rows())

    def fire(self, *, item_id: str, source: str, domains: tuple, market_id: str,
             condition_id: str, token_id: str, outcome: str, question: str,
             published_ts: float, seen_ts: float, decided_ts: float,
             freshness: str, confidence: float, why: str, event: str = "",
             entry: Optional[tuple] = None) -> Optional[PaperRow]:
        """Book a BUY at the honest ask. Returns the row, or None when the
        row exists already (idempotent on restart) or the ask could not be
        read (logged as unquotable, never booked at a made-up price)."""
        row_id = f"{self.book}:{item_id or 'random'}:{token_id}"
        if self.ledger.has(row_id):
            return None
        if condition_id and self.holds(condition_id):
            self.skipped["held"] += 1
            logger.info(f"[news-paper] {self.book}: already holds '{question[:40]}': not booked again")
            return None
        stake = stake_usd()
        if entry is not None:
            fill = Fill(float(entry[0]), stake, 1, float(entry[0]))
        else:
            try:
                ladder = self._ask(token_id)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news-paper] {self.book}: ask ladder unreadable for {token_id[:12]}: {exc}")
                ladder = None
            age = self._age(token_id, self._now())
            if age is not None and age > max_mark_age_s():
                # the same rule as a mark: an old book is no price (verifier,
                # s-wj4gnb: a failed REST read booked Lula Yes at 0.20 from a
                # two-day-old ladder while the market stood at 0.99)
                logger.info(f"[news-paper] {self.book}: book for {token_id[:12]} is {age:.0f}s old: not booked")
                ladder = None
            fill = walk(ladder or [], stake, "ask")
        if fill.avg_price is None:
            logger.info(f"[news-paper] {self.book}: unquotable {token_id[:12]} ({question[:40]}): not booked")
            return None
        lo, hi = price_band()
        if not lo <= fill.avg_price <= hi:
            self.skipped["band"] += 1
            logger.info(f"[news-paper] {self.book}: '{question[:40]}' at {fill.avg_price:.3f} is outside "
                        f"{lo:.2f}-{hi:.2f}: not booked")
            return None
        bps = None
        try:
            bps = self._fee(token_id)
        except Exception:  # noqa: BLE001
            bps = None
        if entry is not None:
            bps_in = 0          # a resting order that was hit pays no taker fee
        else:
            bps_in = bps
        rate = (bps_in or 0) / 10000.0
        p = fill.avg_price
        fee_usd = round(fill.filled_usd * rate * (1.0 - p), 4)
        bid_top = _best(self._bid, token_id, "bid") if entry is None else p
        mid = round((fill.top + bid_top) / 2, 6) if (bid_top is not None and fill.top is not None) else None
        if entry is not None:
            mid = float(entry[2]) if len(entry) > 2 and entry[2] is not None else None
        row = PaperRow(
            row_id=row_id, book=self.book, item_id=item_id, source=source, domains=tuple(domains),
            market_id=market_id, condition_id=condition_id, token_id=token_id, outcome=outcome,
            question=question[:160], published_ts=published_ts, seen_ts=seen_ts,
            decided_ts=decided_ts, quote_ts=self._now() if entry is None else float(entry[1]),
            freshness=freshness,
            confidence=float(confidence), why=str(why)[:300],
            ask_top=fill.top, entry_price=p, stake=stake, filled_usd=fill.filled_usd,
            fee_bps=bps, fee_usd=fee_usd, shares=round(fill.filled_usd / p, 4),
            bid_top=bid_top, mid_entry=mid, fresh_marks=True, event=str(event or "")[:120],
        )
        self.ledger.add(row)
        logger.info(f"[news-paper] {self.book}: BUY ${fill.filled_usd:.2f} '{question[:40]}' "
                    f"[{outcome}] @ {p:.3f} (top {fill.top:.3f}, {fill.levels} level(s), "
                    f"fee {fee_usd:.3f}) {freshness} conf {confidence:.2f}")
        return row

    def mark(self, now: Optional[float] = None, budget: Optional[dict] = None) -> int:
        """Book every horizon that has come due on every open row, at the
        honest bid walked for our size. Idempotent: a horizon already marked
        is never re-marked, so a restart changes nothing. ``budget`` is a
        shared {"left": n} of book reads this tick; a row past it stays due
        for the next tick (a fresh book can cost a REST read)."""
        now = self._now() if now is None else now
        n = 0
        changed = False
        for row in self.ledger.open_rows():
            due = [h for h, s in HORIZONS_S.items()
                   if now >= row.quote_ts + s and h not in row.marks]
            if not due:
                continue
            if budget is not None:
                if budget.get("left", 0) <= 0:
                    break
                budget["left"] -= 1
            try:
                ladder = self._bid(row.token_id)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news-paper] bid ladder unreadable for {row.token_id[:12]}: {exc}")
                ladder = None
            age = self._age(row.token_id, now)
            if age is not None and age > max_mark_age_s():
                # an old book is not a price at this horizon: unknown, said
                logger.info(f"[news-paper] {self.book}: book for {row.token_id[:12]} is {age:.0f}s old: "
                            f"{','.join(due)} marked unknown")
                ladder = None
            fill = walk(ladder or [], row.filled_usd, "bid")
            ask_top = _best(self._ask, row.token_id, "ask") if fill.avg_price is not None else None
            mid = round((fill.top + ask_top) / 2, 6) if (ask_top is not None and fill.top is not None) else None
            for h in due:
                late = now - (row.quote_ts + HORIZONS_S[h])
                if late > mark_late_s():
                    row.marks[h] = {"bid_top": None, "exit_price": None, "ts": now, "pnl": None,
                                    "mid": None, "age_s": age, "late_s": round(late, 1)}
                elif fill.avg_price is None:
                    row.marks[h] = {"bid_top": None, "exit_price": None, "ts": now, "pnl": None,
                                    "mid": None, "age_s": age}
                else:
                    row.marks[h] = {"bid_top": fill.top, "exit_price": fill.avg_price,
                                    "ts": now, "pnl": row.exit_pnl(fill.avg_price),
                                    "mid": mid, "age_s": age}
                n += 1
            changed = True
            # 24h is the last horizon; the row then waits only for resolution
        if changed:
            self.ledger.save()
        return n

    def _age(self, token_id: str, now: float) -> Optional[float]:
        if self._book_ts is None:
            return None
        try:
            ts = self._book_ts(token_id)
        except Exception:  # noqa: BLE001
            return None
        # a reader that cannot date its book has an old book (review, s-wj4gnb)
        return float("inf") if not ts else max(0.0, now - float(ts))

    def settle(self, resolver: Callable[[str], Optional[object]], now: Optional[float] = None) -> int:
        """Close rows whose market resolved. ``resolver(condition_id)`` returns
        the winning token id, "REFUND", or None while open."""
        now = self._now() if now is None else now
        n = 0
        for row in self.ledger.open_rows():
            if "24h" not in row.marks:
                continue  # every horizon first, then resolution
            try:
                w = resolver(row.condition_id)
            except Exception:  # noqa: BLE001
                w = None
            if w is None:
                continue
            if w == "REFUND":
                payout = row.shares * 0.5
                row.resolved = False
            else:
                row.resolved = (str(w) == str(row.token_id))
                payout = row.shares if row.resolved else 0.0
            row.resolution_pnl = round(payout - row.filled_usd - row.fee_usd, 4)
            row.closed = True
            n += 1
        if n:
            self.ledger.save()
        return n


def _best(read: Callable, token_id: str, side: str) -> Optional[float]:
    """The best price on one side, sorted here (project rule), None unread."""
    try:
        lad = read(token_id)
    except Exception:  # noqa: BLE001
        return None
    ps = [float(p) for p, s in (lad or []) if float(p) > 0 and float(s) > 0]
    if not ps:
        return None
    return max(ps) if side == "bid" else min(ps)


def pick_random_market(candidates: list, rng: random.Random) -> Optional[tuple]:
    """For the random book: (market_id, condition_id, token_id, outcome, question)
    from the index's active rows with a readable price; the caller passes the
    list it already has."""
    rows = [c for c in candidates if getattr(c, "token_ids", None)]
    if not rows:
        return None
    c = rng.choice(rows)
    i = rng.randrange(len(c.token_ids))
    return (str(c.market_id), str(c.condition_id), str(c.token_ids[i]),
            str(c.outcomes[i]) if i < len(c.outcomes) else "", str(c.question))


def summary(ledger: PaperLedger) -> dict:
    """Per horizon: n marked, pnl sum, roi on filled dollars, +/- 1 SD of roi;
    plus resolution. Every number carries n; empty is n=0, never a zero.
    The clean era only (``fresh_marks``), like /pnl; ``stale`` counts the rest."""
    rows = [r for r in ledger.live_rows() if r.fresh_marks]
    out: dict = {"book": ledger.book, "rows": len(rows), "void": sum(1 for r in ledger.rows.values() if r.void),
                 "stale": sum(1 for r in ledger.live_rows() if not r.fresh_marks), "horizons": {}}
    import math
    for h in HORIZONS_S:
        rs = [(r, r.marks[h]) for r in rows if h in r.marks and r.marks[h].get("pnl") is not None]
        n = len(rs)
        if not n:
            out["horizons"][h] = {"n": 0}
            continue
        pnl = sum(m["pnl"] for _, m in rs)
        spent = sum(r.filled_usd + r.fee_usd for r, _ in rs)
        rois = [m["pnl"] / max(r.filled_usd + r.fee_usd, 1e-9) for r, m in rs]
        # +/- 1 SD of the MEAN ROI: the population standard deviation over
        # sqrt(n). The first cut used the root mean square, which printed +/-5
        # on four identical +10% rows (verifier, 2026-10-25).
        mean = sum(rois) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in rois) / n) / math.sqrt(n)
        out["horizons"][h] = {"n": n, "pnl": round(pnl, 2), "roi": round(pnl / spent, 4) if spent else None,
                              "sd": round(sd, 4), "unquotable": sum(1 for r in rows
                                                                    if h in r.marks and r.marks[h].get("pnl") is None)}
    res = [r for r in rows if r.resolution_pnl is not None]
    out["resolution"] = {"n": len(res), "won": sum(1 for r in res if r.resolved),
                         "pnl": round(sum(r.resolution_pnl for r in res), 2)} if res else {"n": 0}
    return out
