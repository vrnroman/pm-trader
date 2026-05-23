"""Polymarket RTDS WebSocket order-book mirror.

Maintains a thread-safe ``dict[token_id, OrderBook]`` mirror fed by the
Polymarket Real-Time Data Service WebSocket
(https://docs.polymarket.com/developers/RTDS/). The tennis event-driven
eval loop reads the mirror from another thread via :meth:`RTDSStream.get_book`
so that PM book prices are available with no per-scan REST roundtrip.

Design notes
------------
* The supervisor :meth:`RTDSStream.run` is a single long-lived coroutine.
  On any disconnect / exception it falls back to REST polling for a bounded
  period and then reconnects with exponential backoff (1→2→4→8→16s cap).
  It catches broadly and never crashes the host loop.
* All mirror mutations + reads take ``self._lock`` so the cross-thread
  reader sees consistent snapshots.
* REST fallback + periodic reconciliation guard against silent WS drift:
  if the WS mirror diverges from a fresh REST book by more than one tick
  we log a warning (we do NOT auto-correct from a single sample — that is
  left to ops, to avoid masking a systematic bug).

# ASSUMPTION: RTDS WS public/no-auth — confirm on first connect (§11).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from src.config import CONFIG

logger = logging.getLogger("strategy.tennis_arb.rtds")


@dataclass
class OrderBook:
    """A minimal CLOB order book: price/size levels + tick size.

    ``bids``/``asks`` are unordered lists of ``(price, size)`` tuples; the
    best-price properties scan rather than assume sort order so a delta can
    insert a level anywhere without us having to re-sort on every update.
    """

    bids: list[tuple[float, float]] = field(default_factory=list)  # (price, size)
    asks: list[tuple[float, float]] = field(default_factory=list)
    tick_size: float = 0.01

    @property
    def best_ask(self) -> float:
        """Lowest ask price, or 0.0 if there are no asks."""
        return min((p for p, _ in self.asks), default=0.0)

    @property
    def best_bid(self) -> float:
        """Highest bid price, or 0.0 if there are no bids."""
        return max((p for p, _ in self.bids), default=0.0)

    def as_tuple(self) -> tuple[float, float, float]:
        """Return ``(best_ask, best_bid, tick_size)`` — the eval loop's
        ``book_hint`` shape (matches ``order_placer._parse_book``)."""
        return (self.best_ask, self.best_bid, self.tick_size)


def _level_price_size(level) -> tuple[float, float]:
    """Coerce one book level (dict ``{"price","size"}`` or ``(price,size)``
    tuple) into a ``(price, size)`` float tuple."""
    if isinstance(level, dict):
        price = float(level.get("price") or 0.0)
        size = float(level.get("size") or 0.0)
        return price, size
    # tuple / list / sequence
    price = float(level[0] or 0.0)
    size = float(level[1] or 0.0) if len(level) > 1 else 0.0
    return price, size


class RTDSStream:
    """Thread-safe Polymarket RTDS book mirror with REST fallback.

    The mirror is fed by the RTDS WebSocket and read cross-thread by the
    eval loop. ``stop()`` is callable from any thread.
    """

    def __init__(
        self,
        *,
        discovery_cache=None,
        ws_url: Optional[str] = None,
        ws_connect=None,
        rest_book_fetcher=None,
        reconcile_interval_s: float = 30.0,
        rest_fallback_interval_s: float = 5.0,
        reconcile_sample_size: int = 5,
    ):
        self._discovery_cache = discovery_cache
        self._ws_url = ws_url if ws_url is not None else CONFIG.polymarket_rtds_ws_url
        self._ws_connect = ws_connect  # lazily defaulted in _connect
        self._rest_book_fetcher = rest_book_fetcher
        self._reconcile_interval_s = reconcile_interval_s
        self._rest_fallback_interval_s = rest_fallback_interval_s
        self._reconcile_sample_size = reconcile_sample_size

        self._books: dict[str, OrderBook] = {}
        self._book_ts: dict[str, float] = {}
        self._subscribed: set[str] = set()
        self._lock = threading.Lock()
        self._stopped = False

    # ------------------------------------------------------------------
    # Cross-thread read API
    # ------------------------------------------------------------------
    def get_book(self, token_id: str) -> tuple[Optional[OrderBook], Optional[float]]:
        """Return ``(OrderBook, last_update_ts)`` for ``token_id``, or
        ``(None, None)`` if we have never seen it. Lock-guarded."""
        with self._lock:
            book = self._books.get(token_id)
            if book is None:
                return None, None
            return book, self._book_ts.get(token_id)

    def stop(self) -> None:
        """Signal the supervisor loop to exit. Settable from any thread."""
        self._stopped = True

    # ------------------------------------------------------------------
    # Desired-subscription set
    # ------------------------------------------------------------------
    def _desired_token_ids(self) -> set[str]:
        """Collect the non-empty CLOB token ids we want subscribed.

        Pulls every active discovery-cache entry (``require_link=False`` so
        we still mirror orphan markets we may want to price) and gathers its
        YES/NO token ids. Returns an empty set when there is no cache.
        """
        if self._discovery_cache is None:
            return set()
        out: set[str] = set()
        try:
            entries = self._discovery_cache.active_set(require_link=False)
        except Exception as exc:  # never let a cache hiccup crash the loop
            logger.warning(f"RTDS: discovery active_set failed: {exc}")
            return out
        for e in entries:
            for key in ("token_id_yes", "token_id_no"):
                tok = (e.get(key) or "").strip()
                if tok:
                    out.add(tok)
        return out

    # ------------------------------------------------------------------
    # Mirror mutation
    # ------------------------------------------------------------------
    def _apply_book_snapshot(self, token_id: str, bids, asks, tick_size) -> None:
        """Replace the full book for ``token_id`` from a snapshot frame."""
        ob = OrderBook(
            bids=[_level_price_size(b) for b in (bids or [])],
            asks=[_level_price_size(a) for a in (asks or [])],
            tick_size=float(tick_size or 0.01),
        )
        with self._lock:
            self._books[token_id] = ob
            self._book_ts[token_id] = time.time()

    def _apply_delta(self, token_id: str, side: str, price: float, size: float) -> None:
        """Apply a single price-change delta. Replaces (or, on size 0,
        removes) the level at ``price`` on the appropriate side. Seeds an
        empty book if we have not seen ``token_id`` yet."""
        price = float(price)
        size = float(size)
        is_bid = str(side).lower() in ("buy", "bid")
        with self._lock:
            ob = self._books.get(token_id)
            if ob is None:
                ob = OrderBook()
                self._books[token_id] = ob
            levels = ob.bids if is_bid else ob.asks
            # Drop any existing level at this price first.
            kept = [(p, s) for (p, s) in levels if p != price]
            if size > 0:
                kept.append((price, size))
            if is_bid:
                ob.bids = kept
            else:
                ob.asks = kept
            self._book_ts[token_id] = time.time()

    # ------------------------------------------------------------------
    # Frame parsing
    # ------------------------------------------------------------------
    def _handle_message(self, raw) -> None:
        """Parse and apply one RTDS frame (raw JSON str or pre-decoded dict).

        Recognised types:
          * ``book``         — full snapshot
          * ``price_change`` — list of per-level deltas
        Unknown / unparseable frames are ignored.

        # ASSUMPTION: RTDS schema — confirm at
        # docs.polymarket.com/developers/RTDS (§11)
        """
        if isinstance(raw, (str, bytes, bytearray)):
            import json

            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                return
        else:
            msg = raw
        if not isinstance(msg, dict):
            return

        mtype = msg.get("type")
        token_id = (msg.get("asset_id") or "").strip()
        if not token_id:
            return

        if mtype == "book":
            self._apply_book_snapshot(
                token_id,
                msg.get("bids"),
                msg.get("asks"),
                msg.get("tick_size"),
            )
        elif mtype == "price_change":
            for ch in msg.get("changes") or []:
                if not isinstance(ch, dict):
                    continue
                self._apply_delta(
                    token_id,
                    ch.get("side", ""),
                    ch.get("price") or 0.0,
                    ch.get("size") or 0.0,
                )
        # else: unknown type → ignore

    # ------------------------------------------------------------------
    # Subscription framing
    # ------------------------------------------------------------------
    def _subscribe_message(self, token_ids) -> str:
        """Build the subscribe frame for ``token_ids``.

        # ASSUMPTION: RTDS subscribe frame shape — confirm at
        # docs.polymarket.com/developers/RTDS (§11)
        """
        import json

        return json.dumps(
            {
                "type": "subscribe",
                "channel": "book",
                "market_ids": sorted(token_ids),
            }
        )

    async def subscribe_tokens(self, ws, token_ids) -> None:
        """Send a subscribe frame for ``token_ids`` and record them."""
        token_ids = set(token_ids)
        if not token_ids:
            return
        await ws.send(self._subscribe_message(token_ids))
        with self._lock:
            self._subscribed = set(token_ids)

    # ------------------------------------------------------------------
    # REST fallback + reconciliation
    # ------------------------------------------------------------------
    async def _fetch_rest_book(self, token_id: str) -> Optional[OrderBook]:
        """Call ``rest_book_fetcher`` (sync or async), returning its
        ``OrderBook`` or ``None``."""
        if self._rest_book_fetcher is None:
            return None
        result = self._rest_book_fetcher(token_id)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def _reconcile_once(self) -> None:
        """Sample a few subscribed tokens, REST-fetch each, and warn when
        the WS mirror's best ask/bid diverges by more than one tick. Never
        raises."""
        if self._rest_book_fetcher is None:
            return
        with self._lock:
            subscribed = list(self._subscribed)
        if not subscribed:
            return
        sample = (
            random.sample(subscribed, self._reconcile_sample_size)
            if len(subscribed) > self._reconcile_sample_size
            else subscribed
        )
        for token_id in sample:
            try:
                rest = await self._fetch_rest_book(token_id)
                if rest is None:
                    continue
                mirror, _ = self.get_book(token_id)
                if mirror is None:
                    continue
                tick = mirror.tick_size or rest.tick_size or 0.01
                ask_div = abs(mirror.best_ask - rest.best_ask)
                bid_div = abs(mirror.best_bid - rest.best_bid)
                if ask_div > tick or bid_div > tick:
                    logger.warning(
                        "RTDS reconcile divergence token=%s "
                        "ws=(ask=%.4f,bid=%.4f) rest=(ask=%.4f,bid=%.4f) tick=%.4f",
                        token_id,
                        mirror.best_ask,
                        mirror.best_bid,
                        rest.best_ask,
                        rest.best_bid,
                        tick,
                    )
            except Exception as exc:
                logger.warning(f"RTDS reconcile failed for {token_id}: {exc}")

    async def _rest_fallback_once(self) -> None:
        """REST-fetch every subscribed token and refresh the mirror. Used
        while the WS is down. Never raises."""
        if self._rest_book_fetcher is None:
            return
        with self._lock:
            subscribed = list(self._subscribed)
        for token_id in subscribed:
            try:
                rest = await self._fetch_rest_book(token_id)
                if rest is None:
                    continue
                with self._lock:
                    self._books[token_id] = rest
                    self._book_ts[token_id] = time.time()
            except Exception as exc:
                logger.warning(f"RTDS REST fallback failed for {token_id}: {exc}")

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------
    def _connect(self, url: str):
        """Return the async context manager yielding a websocket. Defaults
        to lazily importing ``websockets`` so tests never touch the network."""
        connect = self._ws_connect
        if connect is None:
            import websockets  # local import: keeps module import network-free

            connect = lambda u, **kw: websockets.connect(u, **kw)  # noqa: E731
            self._ws_connect = connect
        return connect(url)

    # ------------------------------------------------------------------
    # Supervisor
    # ------------------------------------------------------------------
    async def run(self) -> None:
        """Long-lived supervisor: connect, subscribe, consume frames; on
        disconnect, REST-fall-back then reconnect with exponential backoff.

        Catches broadly and never crashes the host loop. Exits when
        ``stop()`` is called.
        """
        backoff = 1.0
        max_backoff = 16.0
        while not self._stopped:
            try:
                async with self._connect(self._ws_url) as ws:
                    backoff = 1.0  # healthy connection → reset backoff
                    await self.subscribe_tokens(ws, self._desired_token_ids())
                    last_sub_check = time.monotonic()
                    last_reconcile = time.monotonic()
                    while not self._stopped:
                        raw = await ws.recv()
                        self._handle_message(raw)

                        now = time.monotonic()
                        # Periodically re-check the desired set and resubscribe.
                        if now - last_sub_check >= 5.0:
                            last_sub_check = now
                            desired = self._desired_token_ids()
                            with self._lock:
                                current = set(self._subscribed)
                            if desired and desired != current:
                                await self.subscribe_tokens(ws, desired)
                        # Periodic reconciliation.
                        if now - last_reconcile >= self._reconcile_interval_s:
                            last_reconcile = now
                            await self._reconcile_once()
            except Exception as exc:
                if self._stopped:
                    break
                logger.warning(f"RTDS connection lost ({exc}); REST fallback + backoff")
                # Bounded REST-fallback polling before reconnecting. We poll
                # for roughly one backoff window so the eval loop keeps fresh
                # prices while the socket is down.
                deadline = time.monotonic() + backoff
                while not self._stopped and time.monotonic() < deadline:
                    try:
                        await self._rest_fallback_once()
                    except Exception:  # defensive; _rest_fallback_once already guards
                        pass
                    await asyncio.sleep(self._rest_fallback_interval_s)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
