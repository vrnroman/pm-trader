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
BOOKS = ("llm", "tape-first", "headline-any", "random")


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def stake_usd() -> float:
    return _env_f("NEWS_STAKE_USD", 5.0)


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

    def open_rows(self) -> list[PaperRow]:
        return [r for r in self.rows.values() if not r.closed]

    def fires_on_day(self, day: str) -> int:
        return sum(1 for r in self.rows.values()
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
                 now: Callable[[], float] = time.time):
        assert book in BOOKS, book
        self.book = book
        self.ledger = ledger or PaperLedger(book)
        self._ask = ask_ladder
        self._bid = bid_ladder
        self._fee = fee_bps
        self._now = now

    def fire(self, *, item_id: str, source: str, domains: tuple, market_id: str,
             condition_id: str, token_id: str, outcome: str, question: str,
             published_ts: float, seen_ts: float, decided_ts: float,
             freshness: str, confidence: float, why: str) -> Optional[PaperRow]:
        """Book a BUY at the honest ask. Returns the row, or None when the
        row exists already (idempotent on restart) or the ask could not be
        read (logged as unquotable, never booked at a made-up price)."""
        row_id = f"{self.book}:{item_id or 'random'}:{token_id}"
        if self.ledger.has(row_id):
            return None
        stake = stake_usd()
        try:
            ladder = self._ask(token_id)
        except Exception as exc:  # noqa: BLE001
            logger.warn(f"[news-paper] {self.book}: ask ladder unreadable for {token_id[:12]}: {exc}")
            ladder = None
        fill = walk(ladder or [], stake, "ask")
        if fill.avg_price is None:
            logger.info(f"[news-paper] {self.book}: unquotable {token_id[:12]} ({question[:40]}): not booked")
            return None
        bps = None
        try:
            bps = self._fee(token_id)
        except Exception:  # noqa: BLE001
            bps = None
        rate = (bps or 0) / 10000.0
        p = fill.avg_price
        fee_usd = round(fill.filled_usd * rate * (1.0 - p), 4)
        row = PaperRow(
            row_id=row_id, book=self.book, item_id=item_id, source=source, domains=tuple(domains),
            market_id=market_id, condition_id=condition_id, token_id=token_id, outcome=outcome,
            question=question[:160], published_ts=published_ts, seen_ts=seen_ts,
            decided_ts=decided_ts, quote_ts=self._now(), freshness=freshness,
            confidence=float(confidence), why=str(why)[:300],
            ask_top=fill.top, entry_price=p, stake=stake, filled_usd=fill.filled_usd,
            fee_bps=bps, fee_usd=fee_usd, shares=round(fill.filled_usd / p, 4),
        )
        self.ledger.add(row)
        logger.info(f"[news-paper] {self.book}: BUY ${fill.filled_usd:.2f} '{question[:40]}' "
                    f"[{outcome}] @ {p:.3f} (top {fill.top:.3f}, {fill.levels} level(s), "
                    f"fee {fee_usd:.3f}) {freshness} conf {confidence:.2f}")
        return row

    def mark(self, now: Optional[float] = None) -> int:
        """Book every horizon that has come due on every open row, at the
        honest bid walked for our size. Idempotent: a horizon already marked
        is never re-marked, so a restart changes nothing."""
        now = self._now() if now is None else now
        n = 0
        changed = False
        for row in self.ledger.open_rows():
            due = [h for h, s in HORIZONS_S.items()
                   if now >= row.quote_ts + s and h not in row.marks]
            if not due:
                continue
            try:
                ladder = self._bid(row.token_id)
            except Exception as exc:  # noqa: BLE001
                logger.warn(f"[news-paper] bid ladder unreadable for {row.token_id[:12]}: {exc}")
                ladder = None
            fill = walk(ladder or [], row.filled_usd, "bid")
            for h in due:
                if fill.avg_price is None:
                    row.marks[h] = {"bid_top": None, "exit_price": None, "ts": now, "pnl": None}
                else:
                    row.marks[h] = {"bid_top": fill.top, "exit_price": fill.avg_price,
                                    "ts": now, "pnl": row.exit_pnl(fill.avg_price)}
                n += 1
            changed = True
            # 24h is the last horizon; the row then waits only for resolution
        if changed:
            self.ledger.save()
        return n

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
    plus resolution. Every number carries n; empty is n=0, never a zero."""
    out: dict = {"book": ledger.book, "rows": len(ledger.rows), "horizons": {}}
    import math
    for h in HORIZONS_S:
        rs = [(r, r.marks[h]) for r in ledger.rows.values() if h in r.marks and r.marks[h].get("pnl") is not None]
        n = len(rs)
        if not n:
            out["horizons"][h] = {"n": 0}
            continue
        pnl = sum(m["pnl"] for _, m in rs)
        spent = sum(r.filled_usd + r.fee_usd for r, _ in rs)
        rois = [m["pnl"] / max(r.filled_usd + r.fee_usd, 1e-9) for r, m in rs]
        sd = math.sqrt(sum(x * x for x in rois) / n) / math.sqrt(n)
        out["horizons"][h] = {"n": n, "pnl": round(pnl, 2), "roi": round(pnl / spent, 4) if spent else None,
                              "sd": round(sd, 4), "unquotable": sum(1 for r in ledger.rows.values()
                                                                    if h in r.marks and r.marks[h].get("pnl") is None)}
    res = [r for r in ledger.rows.values() if r.resolution_pnl is not None]
    out["resolution"] = {"n": len(res), "won": sum(1 for r in res if r.resolved),
                         "pnl": round(sum(r.resolution_pnl for r in res), 2)} if res else {"n": 0}
    return out
