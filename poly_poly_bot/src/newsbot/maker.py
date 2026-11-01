"""The resting-order book (``llm-maker``): post at the bid instead of lifting
the ask, and count a fill only when the market proves it would have come to us.

Why (run s-wj4gnb, 2026-11-01). The first week's llm book lost about the
spread on every bet with no measurable signal; crossing the book is the
whole cost. The 2026-10-18 copy-trading verdict named the next question:
our targets were makers, we were takers. This book asks it of our own
calls, on paper: on every llm fire, a $STAKE BUY rests at the best bid.

The fill rule is the conservative one. Our order would sit at the BACK of
the queue at its price, so touching the price is not a fill. Filled means:
the best ask came down to our limit or below (every bid at our price was
consumed, ours included), seen in the socket's quote history after we
posted or in a fresh book read; or a trade printed BELOW our limit. An
order that does neither within NEWS_MAKER_TTL_MIN is cancelled.

Adverse selection is the known way this fails: only the losers fill. So
every order, filled or not, records the mid at post and at +2h/+24h;
the summary prints the move for filled and unfilled side by side.
A filled order becomes a normal row in the ``llm-maker`` paper book at the
limit price, maker fee zero, exited at the walked bid like every book.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Callable, Optional

from src.logger import logger
from src.newsbot.paper import PaperBook, ledger_dir, price_band

MID_MARKS_S = {"2h": 7200, "24h": 86400}


def ttl_s() -> float:
    try:
        return float(os.environ.get("NEWS_MAKER_TTL_MIN", "") or 30) * 60.0
    except ValueError:
        return 1800.0


@dataclass
class Order:
    order_id: str
    token_id: str
    condition_id: str
    question: str
    event: str
    limit: float
    mid_post: Optional[float]
    posted_ts: float
    ttl_s: float
    common: dict                      # the fire's arguments, replayed on fill
    state: str = "resting"            # resting | filled | expired
    filled_ts: Optional[float] = None
    fill_how: str = ""                # ask<=limit (history|book) | trade<limit
    mid_marks: dict = field(default_factory=dict)   # "2h"/"24h" -> mid or None


class MakerDesk:
    def __init__(self, book: PaperBook, *, path: Optional[str] = None):
        assert book.book == "llm-maker", book.book
        self.book = book
        self.path = path or os.path.join(ledger_dir(), "maker-orders.jsonl")
        self.orders: dict[str, Order] = {}
        self._lock = threading.Lock()
        self.skipped = {"no-bid": 0, "band": 0, "held": 0}
        self._load()

    # ---- ledger ----
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        names = {f.name for f in fields(Order)}
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                d = {k: v for k, v in d.items() if k in names}
                try:
                    self.orders[d["order_id"]] = Order(**d)
                except TypeError:
                    continue

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with self._lock:
            with open(tmp, "w", encoding="utf-8") as f:
                for o in self.orders.values():
                    f.write(json.dumps(asdict(o)) + "\n")
            os.replace(tmp, self.path)

    # ---- post ----
    def post(self, common: dict, *, bid: Optional[float], ask: Optional[float], now: float,
             event: str = "") -> Optional[Order]:
        """Rest a BUY at the best bid. None when there is no bid, the price
        is outside the entry band, the order exists, or the book already
        holds the market."""
        oid = f"llm-maker:{common['item_id']}:{common['token_id']}"
        if oid in self.orders:
            return None
        cid = str(common.get("condition_id") or "")
        if cid and (self.book.holds(cid) or any(o.condition_id == cid and o.state == "resting"
                                                for o in self.orders.values())):
            self.skipped["held"] += 1
            return None
        if bid is None or bid <= 0:
            self.skipped["no-bid"] += 1
            return None
        lo, hi = price_band()
        if not lo <= bid <= hi:
            self.skipped["band"] += 1
            return None
        mid = (bid + ask) / 2 if ask is not None else None
        o = Order(order_id=oid, token_id=str(common["token_id"]), condition_id=cid,
                  question=str(common.get("question", ""))[:160], event=str(event or "")[:120],
                  limit=float(bid), mid_post=mid, posted_ts=float(now), ttl_s=ttl_s(), common=dict(common))
        with self._lock:
            self.orders[oid] = o
        self.save()
        logger.info(f"[news-maker] rest BUY ${self.book_stake():.2f} '{o.question[:40]}' @ {o.limit:.3f} "
                    f"(mid {mid if mid is None else round(mid, 3)}), ttl {o.ttl_s / 60:.0f}m")
        return o

    def book_stake(self) -> float:
        from src.newsbot.paper import stake_usd
        return stake_usd()

    # ---- the tape decides ----
    def check(self, now: float, *, history: Callable[[str], list], last_trade: Callable[[str], Optional[tuple]],
              ladder: Callable[[str], Optional[tuple]], mid_now: Callable[[str], Optional[float]],
              budget: Optional[dict] = None) -> int:
        """Fill, expire and mid-mark every order. ``history(token)`` is the
        socket's (ts_ms, bid, ask, mid) list; ``last_trade(token)`` is
        (ts_ms, price); ``ladder(token)`` is (best_bid, best_ask) from a
        current book. Idempotent: a filled or expired order never changes
        state again; a mid mark is written once."""
        changed = 0
        for o in list(self.orders.values()):
            if o.state == "resting":
                hit = self._filled_by_tape(o, now, history, last_trade)
                if hit is None and (budget is None or budget.get("left", 0) > 0):
                    if budget is not None:
                        budget["left"] -= 1
                    try:
                        q = ladder(o.token_id)
                    except Exception:  # noqa: BLE001
                        q = None
                    if q and q[1] is not None and q[1] <= o.limit and now <= o.posted_ts + o.ttl_s:
                        hit = (now, "ask<=limit (book)", (q[0] + q[1]) / 2 if q[0] is not None else None)
                if hit is not None:
                    o.state, o.filled_ts, o.fill_how = "filled", hit[0], hit[1]
                    self.book.fire(**{**o.common, "event": o.event}, entry=(o.limit, hit[0], hit[2]))
                    logger.info(f"[news-maker] FILLED '{o.question[:40]}' @ {o.limit:.3f} by {hit[1]} "
                                f"{(hit[0] - o.posted_ts) / 60:.0f}m after posting")
                    changed += 1
                elif now > o.posted_ts + o.ttl_s:
                    o.state = "expired"
                    logger.info(f"[news-maker] expired unfilled '{o.question[:40]}' @ {o.limit:.3f}")
                    changed += 1
            for h, secs in MID_MARKS_S.items():
                if h in o.mid_marks or now < o.posted_ts + secs:
                    continue
                if budget is not None:
                    if budget.get("left", 0) <= 0:
                        continue
                    budget["left"] -= 1
                try:
                    o.mid_marks[h] = mid_now(o.token_id)
                except Exception:  # noqa: BLE001
                    o.mid_marks[h] = None
                changed += 1
        if changed:
            self.save()
        return changed

    @staticmethod
    def _filled_by_tape(o: Order, now: float, history, last_trade) -> Optional[tuple]:
        end_ms = (o.posted_ts + o.ttl_s) * 1000
        start_ms = o.posted_ts * 1000
        try:
            for ts, _bid, ask, mid in history(o.token_id) or []:
                if start_ms < ts <= end_ms and ask is not None and ask <= o.limit:
                    return (ts / 1000.0, "ask<=limit (history)", mid)
        except Exception:  # noqa: BLE001
            pass
        try:
            lt = last_trade(o.token_id)
        except Exception:  # noqa: BLE001
            lt = None
        if lt and start_ms < lt[0] <= end_ms and lt[1] < o.limit:
            return (lt[0] / 1000.0, "trade<limit", None)
        return None

    # ---- what it says ----
    def summary(self) -> dict:
        """Fill rate, and the mid's move our way at +2h for filled vs
        unfilled orders (over the limit price): adverse selection in one
        line. Every number with its n."""
        done = [o for o in self.orders.values() if o.state != "resting"]
        filled = [o for o in done if o.state == "filled"]

        def move(os_):
            xs = [(o.mid_marks["2h"] - o.mid_post) / o.limit for o in os_
                  if o.mid_marks.get("2h") is not None and o.mid_post is not None and o.limit]
            return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)
        return {"posted": len(self.orders), "resting": len(self.orders) - len(done), "done": len(done),
                "filled": len(filled), "move_filled": move(filled),
                "move_unfilled": move([o for o in done if o.state == "expired"])}


def summary_line(s: dict) -> str:
    if not s["done"]:
        return f"llm-maker orders: {s['posted']} posted, none finished yet (collecting)"

    def mv(x):
        m, n = x
        return "n=0" if m is None else f"{m * 100:+.1f}% (n={n})"
    return (f"llm-maker orders: {s['filled']} of {s['done']} filled ({s['filled'] / s['done'] * 100:.0f}%), "
            f"{s['resting']} resting; mid at 2h, filled {mv(s['move_filled'])} vs unfilled {mv(s['move_unfilled'])}")
