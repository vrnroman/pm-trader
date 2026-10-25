"""CLOB market websocket -> best bid/ask ring buffers + the latest sorted ladder.

Probe facts (2026-10-25): ``wss://ws-subscriptions-clob.polymarket.com/ws/market``;
subscribe with ``{"assets_ids":[...], "type":"market"}``; send the text "PING"
every ~10 s; resubscribe on drop. Frames: ``book`` (full ladder), ``price_change``
(``price_changes``: [{asset_id, price, size, side, best_bid, best_ask}]) and
``last_trade_price``. Timestamps are milliseconds.

Standing rule: never trust the collection ordering. Bids are sorted descending
and asks ascending here, before anything takes the best of either.

Memory: one deque per token, capped at ``maxlen`` entries (default 2000, about
30 min of a busy market). Consecutive entries with an unchanged (bid, ask) are
not appended: ``mid_at`` asks for the nearest earlier entry, which the previous
one already answers, and ``best`` reads the latest timestamp from a separate
per-token field. That keeps a quiet market at a handful of entries.
"""
from __future__ import annotations

import asyncio
import json
import logging
from bisect import bisect_right
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, NamedTuple

import httpx

log = logging.getLogger("newsbot.tape.clob")

CLOB_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
CLOB_REST_BOOK = "https://clob.polymarket.com/book"
MAX_TOKENS_PER_CONNECTION = 500
PING_TEXT = "PING"


class Fill(NamedTuple):
    """What walking a ladder for our size would do. ``filled_usd < asked`` is a
    partial fill: the book was thinner than we are."""

    avg_price: float | None
    filled_usd: float
    levels: int

    @property
    def shares(self) -> float:
        return 0.0 if not self.avg_price else self.filled_usd / self.avg_price


@dataclass(slots=True)
class Ladder:
    """Sorted levels: bids best (highest) first, asks best (lowest) first."""

    bids: list[tuple[float, float]] = field(default_factory=list)
    asks: list[tuple[float, float]] = field(default_factory=list)
    ts_ms: int = 0

    @property
    def best_bid(self) -> float | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0][0] if self.asks else None

    def set_level(self, side: str, price: float, size: float) -> None:
        """Apply one price_change level: size 0 removes, else upsert, keeping order."""
        side = side.upper()
        levels = self.bids if side == "BUY" else self.asks
        for i, (p, _) in enumerate(levels):
            if p == price:
                if size <= 0:
                    del levels[i]
                else:
                    levels[i] = (price, size)
                return
        if size <= 0:
            return
        if side == "BUY":
            # bids descending: insert by negated price
            keys = [-p for p, _ in levels]
            levels.insert(bisect_right(keys, -price), (price, size))
        else:
            keys = [p for p, _ in levels]
            levels.insert(bisect_right(keys, price), (price, size))


def _levels(raw: Any) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for lvl in raw or []:
        try:
            if isinstance(lvl, dict):
                p, s = float(lvl["price"]), float(lvl["size"])
            else:
                p, s = float(lvl[0]), float(lvl[1])
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if 0.0 <= p <= 1.0 and s > 0:
            out.append((p, s))
    return out


def _ms(ts: Any) -> int:
    try:
        f = float(ts)
    except (TypeError, ValueError):
        return 0
    if 0 < f < 1e11:  # seconds slipped in
        f *= 1000.0
    return int(f)


def parse_ladder(obj: dict, ts_ms: int | None = None) -> Ladder:
    """Build a sorted ladder from a book frame or the REST /book body, in
    whatever order the server happened to send the levels."""
    bids = sorted(_levels(obj.get("bids")), key=lambda x: -x[0])
    asks = sorted(_levels(obj.get("asks")), key=lambda x: x[0])
    return Ladder(bids=bids, asks=asks, ts_ms=_ms(obj.get("timestamp")) if ts_ms is None else ts_ms)


def walk(levels: list[tuple[float, float]], usd: float) -> Fill:
    """Walk already-sorted levels (best first) spending up to ``usd``."""
    if usd <= 0 or not levels:
        return Fill(None, 0.0, 0)
    remaining = float(usd)
    spent = 0.0
    shares = 0.0
    n = 0
    for price, size in levels:
        if remaining <= 1e-12 or price <= 0:
            break
        take = min(size, remaining / price)
        if take <= 0:
            continue
        spent += take * price
        shares += take
        remaining -= take * price
        n += 1
    if shares <= 0:
        return Fill(None, 0.0, 0)
    return Fill(spent / shares, spent, n)


def walk_shares(levels: list[tuple[float, float]], shares: float) -> Fill:
    """Walk already-sorted levels selling/buying ``shares`` (an exit knows its size)."""
    if shares <= 0 or not levels:
        return Fill(None, 0.0, 0)
    remaining = float(shares)
    proceeds = 0.0
    done = 0.0
    n = 0
    for price, size in levels:
        if remaining <= 1e-12:
            break
        take = min(size, remaining)
        proceeds += take * price
        done += take
        remaining -= take
        n += 1
    if done <= 0:
        return Fill(None, 0.0, 0)
    return Fill(proceeds / done, proceeds, n)


class QuoteBook:
    """Per token: a ring buffer of (ts_ms, best_bid, best_ask, mid) and the
    latest full ladder. Bounded by ``maxlen`` entries per token and
    ``max_tokens`` tokens (least recently updated evicted first)."""

    def __init__(self, maxlen: int = 2000, max_tokens: int = 2000) -> None:
        self.maxlen = int(maxlen)
        self.max_tokens = int(max_tokens)
        self._hist: OrderedDict[str, deque[tuple[int, float | None, float | None, float | None]]] = OrderedDict()
        self._ladder: dict[str, Ladder] = {}
        self._seen_ms: dict[str, int] = {}
        self._last_trade: dict[str, tuple[int, float]] = {}
        self.frames = 0
        self.rejected = 0

    # ----- writes -----

    def _touch(self, token: str) -> deque:
        d = self._hist.get(token)
        if d is None:
            d = deque(maxlen=self.maxlen)
            self._hist[token] = d
            while len(self._hist) > self.max_tokens:
                old, _ = self._hist.popitem(last=False)
                self._ladder.pop(old, None)
                self._seen_ms.pop(old, None)
                self._last_trade.pop(old, None)
        else:
            self._hist.move_to_end(token)
        return d

    def record(self, token: str, ts_ms: int, bid: float | None, ask: float | None) -> None:
        """Append one best-quote observation (skipping an unchanged quote)."""
        token = str(token)
        d = self._touch(token)
        self._seen_ms[token] = max(ts_ms, self._seen_ms.get(token, 0))
        if d and d[-1][1] == bid and d[-1][2] == ask:
            return
        mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
        d.append((ts_ms, bid, ask, mid))

    def set_ladder(self, token: str, ladder: Ladder) -> None:
        token = str(token)
        self._ladder[token] = ladder
        self.record(token, ladder.ts_ms, ladder.best_bid, ladder.best_ask)

    def apply_book(self, frame: dict) -> None:
        token = frame.get("asset_id")
        if not token:
            self.rejected += 1
            return
        self.set_ladder(str(token), parse_ladder(frame))

    def apply_price_change(self, frame: dict) -> None:
        ts = _ms(frame.get("timestamp"))
        changes = frame.get("price_changes")
        if changes is None and "changes" in frame:  # older single-asset shape
            changes = [dict(c, asset_id=frame.get("asset_id")) for c in frame.get("changes") or []]
        applied = 0
        for ch in changes or []:
            if not isinstance(ch, dict):
                continue
            token = ch.get("asset_id")
            if not token:
                continue
            token = str(token)
            ladder = self._ladder.get(token)
            try:
                price, size = float(ch["price"]), float(ch["size"])
            except (KeyError, TypeError, ValueError):
                price = size = None
            if ladder is not None and price is not None and ch.get("side"):
                ladder.set_level(str(ch["side"]), price, size)
                ladder.ts_ms = max(ladder.ts_ms, ts)
            bid = _opt_float(ch.get("best_bid"))
            ask = _opt_float(ch.get("best_ask"))
            if bid is None and ladder is not None:
                bid = ladder.best_bid
            if ask is None and ladder is not None:
                ask = ladder.best_ask
            self.record(token, ts, bid, ask)
            applied += 1
        if not applied:
            self.rejected += 1

    def apply_last_trade(self, frame: dict) -> None:
        token = frame.get("asset_id")
        price = _opt_float(frame.get("price"))
        if token and price is not None:
            self._touch(str(token))
            self._last_trade[str(token)] = (_ms(frame.get("timestamp")), price)

    def apply_frame(self, raw: str | bytes) -> int:
        """Decode one websocket text frame (a dict or a list of dicts) and apply
        every event in it. Returns the number of events applied; malformed input
        counts as rejected and never raises (the socket loop must not die on a
        bad frame, 2026-10-25)."""
        if isinstance(raw, (bytes, bytearray)):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                self.rejected += 1
                return 0
        if not raw or raw.strip() in ("", "PONG"):
            return 0
        try:
            obj = json.loads(raw)
        except ValueError:
            self.rejected += 1
            return 0
        events = obj if isinstance(obj, list) else [obj]
        n = 0
        for ev in events:
            if not isinstance(ev, dict):
                self.rejected += 1
                continue
            et = ev.get("event_type")
            if et == "book":
                self.apply_book(ev)
            elif et == "price_change":
                self.apply_price_change(ev)
            elif et == "last_trade_price":
                self.apply_last_trade(ev)
            else:
                continue
            n += 1
            self.frames += 1
        return n

    # ----- reads -----

    def tokens(self) -> list[str]:
        return list(self._hist.keys())

    def __contains__(self, token: object) -> bool:
        return token in self._hist

    def history(self, token: str) -> list[tuple[int, float | None, float | None, float | None]]:
        """(ts_ms, bid, ask, mid) oldest first; a copy, so callers may iterate freely."""
        return list(self._hist.get(str(token), ()))

    def ladder(self, token: str) -> Ladder | None:
        return self._ladder.get(str(token))

    def last_trade(self, token: str) -> tuple[int, float] | None:
        return self._last_trade.get(str(token))

    def best(self, token: str) -> tuple[float | None, float | None, int] | None:
        """(bid, ask, ts_ms of the newest observation) or None when never quoted."""
        d = self._hist.get(str(token))
        if not d:
            return None
        _, bid, ask, _ = d[-1]
        return bid, ask, self._seen_ms.get(str(token), d[-1][0])

    def mid_at(self, token: str, ts_ms: int) -> float | None:
        """The mid of the nearest observation at or before ``ts_ms``; None when
        nothing that early is known (an earlier price we never saw is unknown,
        not the current one)."""
        d = self._hist.get(str(token))
        if not d:
            return None
        for entry_ts, _, _, mid in reversed(d):
            if entry_ts <= ts_ms:
                return mid
        return None

    def walk_ask(self, token: str, usd: float) -> Fill:
        """Buy ``usd`` worth at the honest ask: (avg_price, filled_usd, levels)."""
        ladder = self._ladder.get(str(token))
        return Fill(None, 0.0, 0) if ladder is None else walk(ladder.asks, usd)

    def walk_bid(self, token: str, usd: float | None = None, *, shares: float | None = None) -> Fill:
        """Sell into the bids: by ``usd`` notional, or by ``shares`` when the
        caller knows its position (an exit does)."""
        ladder = self._ladder.get(str(token))
        if ladder is None:
            return Fill(None, 0.0, 0)
        if shares is not None:
            return walk_shares(ladder.bids, shares)
        return walk(ladder.bids, usd or 0.0)


def _opt_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# The socket client
# --------------------------------------------------------------------------


def shard(token_ids: Iterable[Any], size: int = MAX_TOKENS_PER_CONNECTION) -> list[tuple[str, ...]]:
    """Deterministic shards of at most ``size`` ids (sorted, deduplicated)."""
    ids = sorted({str(t) for t in token_ids if t is not None and str(t) != ""})
    return [tuple(ids[i : i + size]) for i in range(0, len(ids), size)]


async def stream_quotes(
    token_ids_provider: Callable[[], Iterable[Any]],
    book: QuoteBook,
    *,
    connect: Callable[..., Any] | None = None,
    url: str = CLOB_WS_URL,
    ping_interval: float = 10.0,
    poll_interval: float = 5.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    stop: asyncio.Event | None = None,
    max_per_connection: int = MAX_TOKENS_PER_CONNECTION,
    backoff: tuple[float, float] = (1.0, 60.0),
) -> None:
    """Keep the CLOB market socket subscribed to whatever the provider returns.

    One connection per shard of ``max_per_connection`` ids. Every
    ``poll_interval`` the provider is re-read; a shard whose id set changed is
    torn down and reconnected with the new subscribe message (the public socket
    has no documented incremental subscribe, so a fresh connection is the
    resubscribe, 2026-10-25). Each connection sends the text PING every
    ``ping_interval`` seconds and reconnects with exponential backoff on drop.
    """
    if connect is None:
        import websockets

        connect = websockets.connect
    tasks: dict[tuple[str, ...], asyncio.Task] = {}

    def stopped() -> bool:
        return stop is not None and stop.is_set()

    try:
        while not stopped():
            try:
                wanted = set(shard(token_ids_provider(), max_per_connection))
            except Exception as e:  # noqa: BLE001 - a bad provider read keeps the current set
                log.warning("[news] tape clob token provider failed: %s", e)
                wanted = set(tasks)
            for key in list(tasks):
                if key not in wanted or tasks[key].done():
                    tasks.pop(key).cancel()
            for key in wanted:
                if key not in tasks:
                    tasks[key] = asyncio.create_task(
                        _run_shard(key, book, connect, url, ping_interval, sleep, stop, backoff),
                        name=f"clob-ws-shard-{len(key)}",
                    )
            await sleep(poll_interval)
    finally:
        for t in tasks.values():
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks.values(), return_exceptions=True)


async def _run_shard(
    ids: tuple[str, ...],
    book: QuoteBook,
    connect: Callable[..., Any],
    url: str,
    ping_interval: float,
    sleep: Callable[[float], Awaitable[None]],
    stop: asyncio.Event | None,
    backoff: tuple[float, float],
) -> None:
    delay = backoff[0]
    while not (stop is not None and stop.is_set()):
        pinger: asyncio.Task | None = None
        try:
            async with connect(url) as ws:
                await ws.send(json.dumps({"assets_ids": list(ids), "type": "market"}))
                pinger = asyncio.create_task(_ping_forever(ws, ping_interval, sleep))
                async for raw in ws:
                    delay = backoff[0]
                    book.apply_frame(raw)
            log.info("[news] tape clob shard(%d) closed; reconnecting in %.0fs", len(ids), delay)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("[news] tape clob shard(%d) error %s: %s; reconnecting in %.0fs", len(ids), type(e).__name__, e, delay)
        finally:
            if pinger is not None:
                pinger.cancel()
        if stop is not None and stop.is_set():
            break
        await sleep(delay)
        delay = min(delay * 2, backoff[1])


async def _ping_forever(ws: Any, interval: float, sleep: Callable[[float], Awaitable[None]]) -> None:
    try:
        while True:
            await sleep(interval)
            await ws.send(PING_TEXT)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the reader loop sees the same drop and reconnects
        return


async def fetch_book_rest(
    token_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 5.0,
    url: str = CLOB_REST_BOOK,
) -> Ladder | None:
    """GET /book?token_id=<id>; the REST fallback when the socket has no ladder
    yet. Returns a sorted Ladder or None on any failure (never raises)."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout)
    try:
        r = await client.get(url, params={"token_id": str(token_id)})
        if r.status_code != 200:
            log.warning("[news] tape rest book %s -> %s", token_id, r.status_code)
            return None
        body = r.json()
        if not isinstance(body, dict):
            return None
        return parse_ladder(body)
    except (httpx.HTTPError, ValueError) as e:
        log.warning("[news] tape rest book %s failed: %s", token_id, e)
        return None
    finally:
        if own:
            await client.aclose()
