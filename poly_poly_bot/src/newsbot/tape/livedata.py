"""Polymarket live-data websocket -> per-market per-minute trade buckets.

Probe facts (2026-10-25): ``wss://ws-live-data.polymarket.com`` wants an
``Origin: https://polymarket.com`` header; subscribe with
``{"action":"subscribe","subscriptions":[{"topic":"activity","type":"trades"}]}``
(and ``{"topic":"comments","type":"*"}``); frames look like
``{"connection_id":..., "payload": {asset, conditionId, eventSlug, slug, title,
outcome, price, side, size, timestamp, proxyWallet, name, transactionHash}}``
at ~35 trades/s across every market, 5-minute crypto included. The first frame
may be empty. Nothing here keeps a frame: a trade is parsed into a slotted
``Trade``, handed to the callback, and folded into a bucket; the structures are
bounded by market count and by minute window.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterator

log = logging.getLogger("newsbot.tape.livedata")

LIVE_URL = "wss://ws-live-data.polymarket.com"
ORIGIN = "https://polymarket.com"
SUBSCRIBE_TRADES = {"action": "subscribe", "subscriptions": [{"topic": "activity", "type": "trades"}]}
SUBSCRIBE_COMMENTS = {"action": "subscribe", "subscriptions": [{"topic": "comments", "type": "*"}]}

# Outcomes that are the complement leg of a binary market. A NO print at 0.70
# is the market saying YES is 0.30; folding both legs into one YES-space series
# is what lets a single bucket per conditionId carry a meaningful delta
# (2026-10-25). Team-name outcomes (sports) are not folded; the detector's
# exclude predicate drops those markets anyway.
_COMPLEMENT_OUTCOMES = frozenset({"no", "down"})


@dataclass(slots=True, frozen=True)
class Trade:
    condition_id: str
    asset: str
    price: float  # as printed, for the leg that traded
    yes_price: float  # folded into the first-outcome (YES) frame
    size: float
    ts: float  # seconds, UTC epoch
    side: str
    outcome: str
    title: str
    slug: str

    @property
    def notional(self) -> float:
        return self.price * self.size


@dataclass(slots=True, frozen=True)
class Comment:
    market_key: str  # conditionId when present, else the parent entity id / event slug
    ts: float
    body_len: int  # length only: the body itself is never kept


def _as_seconds(ts: Any) -> float | None:
    """Live-data timestamps arrive as seconds, milliseconds or ISO strings
    depending on topic; normalise to seconds and refuse anything unparseable."""
    if ts is None:
        return None
    if isinstance(ts, str):
        s = ts.strip()
        if not s:
            return None
        try:
            ts = float(s)
        except ValueError:
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
            except ValueError:
                return None
    try:
        f = float(ts)
    except (TypeError, ValueError):
        return None
    if f > 1e11:  # milliseconds
        f /= 1000.0
    if f <= 0:
        return None
    return f


def parse_trade(payload: Any) -> Trade | None:
    """A tolerant parse: any missing or non-numeric core field drops the trade."""
    if not isinstance(payload, dict):
        return None
    cid = payload.get("conditionId") or payload.get("condition_id")
    if not cid:
        return None
    try:
        price = float(payload.get("price"))
        size = float(payload.get("size"))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= price <= 1.0) or size < 0:
        return None
    ts = _as_seconds(payload.get("timestamp"))
    if ts is None:
        return None
    outcome = str(payload.get("outcome") or "")
    yes_price = 1.0 - price if outcome.strip().lower() in _COMPLEMENT_OUTCOMES else price
    return Trade(
        condition_id=str(cid),
        asset=str(payload.get("asset") or ""),
        price=price,
        yes_price=yes_price,
        size=size,
        ts=ts,
        side=str(payload.get("side") or ""),
        outcome=outcome,
        title=str(payload.get("title") or ""),
        slug=str(payload.get("slug") or ""),
    )


def parse_comment(payload: Any) -> Comment | None:
    if not isinstance(payload, dict):
        return None
    key = (
        payload.get("conditionId")
        or payload.get("parentEntityID")
        or payload.get("parentEntityId")
        or payload.get("eventSlug")
        or payload.get("slug")
    )
    if not key:
        return None
    ts = _as_seconds(payload.get("timestamp") or payload.get("createdAt"))
    if ts is None:
        return None
    body = payload.get("body")
    return Comment(market_key=str(key), ts=ts, body_len=len(body) if isinstance(body, str) else 0)


def classify_frame(raw: str | bytes) -> tuple[str, Any] | None:
    """Return ("trade"|"comment", payload) or None for empty/keepalive/malformed.

    The topic is taken from the frame when present and inferred from the payload
    shape otherwise, because the probe saw frames with only ``connection_id`` and
    ``payload`` (2026-10-25)."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not raw or not raw.strip():
        return None
    try:
        frame = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(frame, dict):
        return None
    payload = frame.get("payload")
    if not isinstance(payload, dict) or not payload:
        return None
    topic = str(frame.get("topic") or payload.get("topic") or "").lower()
    if topic == "comments" or ("body" in payload and "price" not in payload):
        return ("comment", payload)
    if topic == "activity" or ("price" in payload and "size" in payload):
        return ("trade", payload)
    return None


async def stream_trades(
    on_trade: Callable[[Trade], Any],
    on_comment: Callable[[Comment], Any] | None = None,
    *,
    connect: Callable[..., Any] | None = None,
    url: str = LIVE_URL,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    stop: asyncio.Event | None = None,
    backoff: tuple[float, float] = (1.0, 60.0),
) -> None:
    """Run the live-data socket until ``stop`` is set, reconnecting forever.

    Backoff doubles from ``backoff[0]`` to ``backoff[1]`` and resets only once a
    frame has actually been received on the new connection, so a server that
    accepts and immediately drops us does not turn into a tight loop. Callbacks
    may be sync or async; an exception inside one is logged and does not kill
    the stream (the tape must outlive a bad frame, 2026-10-25).
    """
    if connect is None:
        import websockets

        connect = websockets.connect
    delay = backoff[0]
    while not (stop is not None and stop.is_set()):
        try:
            async with connect(url, additional_headers={"Origin": ORIGIN}) as ws:
                await ws.send(json.dumps(SUBSCRIBE_TRADES))
                await ws.send(json.dumps(SUBSCRIBE_COMMENTS))
                async for raw in ws:
                    delay = backoff[0]
                    kind = classify_frame(raw)
                    if kind is None:
                        continue
                    topic, payload = kind
                    if topic == "trade":
                        trade = parse_trade(payload)
                        if trade is not None:
                            await _call(on_trade, trade)
                    elif on_comment is not None:
                        comment = parse_comment(payload)
                        if comment is not None:
                            await _call(on_comment, comment)
            log.info("[news] tape live-data closed; reconnecting in %.0fs", delay)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - every socket failure is a reconnect
            log.warning("[news] tape live-data error %s: %s; reconnecting in %.0fs", type(e).__name__, e, delay)
        if stop is not None and stop.is_set():
            break
        await sleep(delay)
        delay = min(delay * 2, backoff[1])


async def _call(cb: Callable[..., Any], arg: Any) -> None:
    try:
        r = cb(arg)
        if asyncio.iscoroutine(r):
            await r
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("[news] tape callback %s failed: %s", getattr(cb, "__name__", cb), e)


# --------------------------------------------------------------------------
# Bounded minute tables
# --------------------------------------------------------------------------


class Bucket:
    """One market, one UTC minute. ``first``/``last`` follow trade timestamps,
    not arrival order, because the socket can deliver a minute's prints out of
    order after a reconnect. Prices are in YES space (see ``Trade.yes_price``)."""

    __slots__ = ("n", "notional", "first_price", "last_price", "min", "max", "first_ts", "last_ts")

    def __init__(self, price: float, size: float, ts: float, notional: float) -> None:
        self.n = 1
        self.notional = notional
        self.first_price = self.last_price = self.min = self.max = price
        self.first_ts = self.last_ts = ts

    def add(self, price: float, size: float, ts: float, notional: float) -> None:
        self.n += 1
        self.notional += notional
        if ts < self.first_ts:
            self.first_ts, self.first_price = ts, price
        if ts >= self.last_ts:
            self.last_ts, self.last_price = ts, price
        if price < self.min:
            self.min = price
        if price > self.max:
            self.max = price

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Bucket(n={self.n}, ${self.notional:.2f}, {self.first_price:.3f}->{self.last_price:.3f})"


@dataclass(slots=True, frozen=True)
class WindowStats:
    n: int
    notional: float
    first_price: float
    last_price: float
    min: float
    max: float
    first_ts: float
    last_ts: float
    minutes: int  # how many minute buckets had trades

    @property
    def delta_cents(self) -> float:
        return round((self.last_price - self.first_price) * 100.0, 2)

    @property
    def range_cents(self) -> float:
        return round((self.max - self.min) * 100.0, 2)


class _MinuteTable:
    """key -> OrderedDict[minute -> value], bounded two ways: at most
    ``max_keys`` keys (least recently updated evicted first) and, per key, only
    minutes inside ``window_min`` of the newest minute that key has seen (oldest
    minute dropped first). Both bounds hold on every ``add`` so memory never
    depends on ``prune`` being called."""

    def __init__(self, window_min: int, max_keys: int) -> None:
        if window_min < 1 or max_keys < 1:
            raise ValueError("window_min and max_keys must be >= 1")
        self.window_min = int(window_min)
        self.max_keys = int(max_keys)
        self._t: OrderedDict[str, OrderedDict[int, Any]] = OrderedDict()
        self.last_ts: float = 0.0  # the tape's own clock: newest timestamp seen
        self.evicted_keys = 0

    def __len__(self) -> int:
        return len(self._t)

    def __contains__(self, key: object) -> bool:
        return key in self._t

    def keys(self) -> Iterator[str]:
        return iter(list(self._t.keys()))

    def _minutes(self, key: str) -> OrderedDict[int, Any] | None:
        return self._t.get(key)

    def _slot(self, key: str, ts: float) -> tuple[OrderedDict[int, Any] | None, int, bool]:
        """Return (minute table for key, minute index, created) with both
        bounds enforced for this key. The table is None when ``ts`` is older
        than the key's window (a replayed print after a reconnect): the caller
        drops it rather than growing the structure backwards."""
        minute = int(ts // 60)
        table = self._t.get(key)
        if table is None:
            table = OrderedDict()
            self._t[key] = table
            while len(self._t) > self.max_keys:
                self._t.popitem(last=False)
                self.evicted_keys += 1
        else:
            self._t.move_to_end(key)
        if ts > self.last_ts:
            self.last_ts = ts
        if minute in table:
            return table, minute, False
        if table and minute < next(reversed(table)) - self.window_min:
            return None, minute, False
        table[minute] = None
        if len(table) > 1:
            # Keep minute order so the oldest is always at the front.
            if minute < next(reversed(table)):
                for k in sorted(table):
                    table.move_to_end(k)
            floor = next(reversed(table)) - self.window_min
            while table and next(iter(table)) < floor:
                table.popitem(last=False)
        return table, minute, True

    def _now(self, now: float | None) -> float:
        # The tape's own clock, never the wall clock: callers that have a real
        # ``now`` pass it; tests and replays stay deterministic (2026-10-25).
        return self.last_ts if now is None else float(now)

    def window_items(self, key: str, minutes: int, now: float | None = None) -> list[tuple[int, Any]]:
        table = self._t.get(key)
        if not table:
            return []
        now_s = self._now(now)
        lo = int((now_s - minutes * 60) // 60)
        hi = int(now_s // 60)
        return [(m, v) for m, v in table.items() if lo <= m <= hi]

    def prune(self, now: float) -> int:
        """Drop minutes older than the window as of ``now`` and keys left empty.
        Returns the number of minute buckets dropped."""
        floor = int(now // 60) - self.window_min
        dropped = 0
        for key in list(self._t.keys()):
            table = self._t[key]
            while table and next(iter(table)) < floor:
                table.popitem(last=False)
                dropped += 1
            if not table:
                del self._t[key]
        return dropped


class TradeBuckets(_MinuteTable):
    """Per conditionId per UTC minute: n, notional, first/last/min/max price.

    Default bounds: 60 minutes, 20k markets (a few hundred bytes each). The
    jump detector and the freshness rule read it; nothing else writes it.
    """

    def __init__(self, window_min: int = 60, max_markets: int = 20_000) -> None:
        super().__init__(window_min, max_markets)
        self.trades_seen = 0

    def add(self, trade: Trade) -> None:
        table, minute, created = self._slot(trade.condition_id, trade.ts)
        if table is None:
            return
        notional = trade.price * trade.size
        if created or table[minute] is None:
            table[minute] = Bucket(trade.yes_price, trade.size, trade.ts, notional)
        else:
            table[minute].add(trade.yes_price, trade.size, trade.ts, notional)
        self.trades_seen += 1

    def markets(self, active_since: float | None = None) -> list[str]:
        """Markets with at least one bucket; ``active_since`` keeps only those
        whose newest trade is at or after that timestamp (what a scan needs)."""
        if active_since is None:
            return list(self._t.keys())
        out = []
        for cid, table in self._t.items():
            if table and next(reversed(table.values())).last_ts >= active_since:
                out.append(cid)
        return out

    def recent(self, condition_id: str, minutes: int, now: float | None = None) -> list[tuple[int, Bucket]]:
        """Minute buckets inside the last ``minutes`` as of ``now`` (default: the
        newest trade timestamp seen on the whole tape), oldest first."""
        return self.window_items(condition_id, minutes, now)

    def window(self, condition_id: str, minutes: int, now: float | None = None) -> WindowStats | None:
        items = self.recent(condition_id, minutes, now)
        if not items:
            return None
        buckets = [b for _, b in items]
        first = min(buckets, key=lambda b: b.first_ts)
        last = max(buckets, key=lambda b: b.last_ts)
        return WindowStats(
            n=sum(b.n for b in buckets),
            notional=sum(b.notional for b in buckets),
            first_price=first.first_price,
            last_price=last.last_price,
            min=min(b.min for b in buckets),
            max=max(b.max for b in buckets),
            first_ts=first.first_ts,
            last_ts=last.last_ts,
            minutes=len(buckets),
        )

    def delta_cents(self, condition_id: str, minutes: int, now: float | None = None) -> float | None:
        """last - first price over the window, in cents; None when no trades
        (unknown is not zero on a ledger)."""
        w = self.window(condition_id, minutes, now)
        return None if w is None else w.delta_cents


class CommentCounter(_MinuteTable):
    """Comments per market per minute, bounded exactly like the trade buckets."""

    def __init__(self, window_min: int = 60, max_markets: int = 20_000) -> None:
        super().__init__(window_min, max_markets)
        self.comments_seen = 0

    def add(self, comment: Comment) -> None:
        table, minute, created = self._slot(comment.market_key, comment.ts)
        if table is None:
            return
        table[minute] = 1 if (created or table[minute] is None) else table[minute] + 1
        self.comments_seen += 1

    def recent(self, market_key: str, minutes: int, now: float | None = None) -> int:
        return sum(v for _, v in self.window_items(market_key, minutes, now))

    def per_minute(self, market_key: str, minutes: int, now: float | None = None) -> list[tuple[int, int]]:
        return self.window_items(market_key, minutes, now)
