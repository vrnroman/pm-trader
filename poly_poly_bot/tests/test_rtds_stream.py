"""Tests for RTDSStream: book mirror, deltas, reconciliation, REST fallback.

Everything is mocked — no live HTTP/WebSocket. The fake-WS pattern mirrors
the FakeResponse style used elsewhere: a class with async send/recv and
async context-manager protocol; recv pops a deque and raises FakeClosed
when empty so we can deterministically drive a reconnect.
"""

import asyncio
import json
import logging
from collections import deque

import pytest

from src.polymarket.rtds_stream import OrderBook, RTDSStream


# ----------------------------------------------------------------------
# Test doubles
# ----------------------------------------------------------------------
class FakeClosed(Exception):
    """Raised by FakeWS.recv when its frame deque is exhausted."""


class FakeWS:
    """Minimal async websocket double.

    ``send`` records frames; ``recv`` pops the next seeded frame and raises
    FakeClosed once drained (simulating a dropped connection).
    """

    def __init__(self, frames=None):
        self._frames = deque(frames or [])
        self.sent: list[str] = []

    async def send(self, msg):
        self.sent.append(msg)

    async def recv(self):
        if not self._frames:
            raise FakeClosed("ws drained")
        return self._frames.popleft()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _make_ws_connect(*fakes):
    """Return a ws_connect callable that yields successive FakeWS instances
    on each connect (to simulate reconnects)."""
    it = iter(fakes)

    def _connect(url, **kwargs):
        return next(it)

    return _connect


class FakeCache:
    """Duck-typed PMDiscoveryCache: active_set returns successive entry
    lists from a queue."""

    def __init__(self, *entry_lists):
        self._lists = deque(entry_lists)
        self._last = []

    def active_set(self, *, require_link=True, **kwargs):
        if self._lists:
            self._last = self._lists.popleft()
        return self._last


def _entry(yes="", no=""):
    return {"token_id_yes": yes, "token_id_no": no}


# ----------------------------------------------------------------------
# 1. OrderBook
# ----------------------------------------------------------------------
def test_orderbook_best_prices_and_as_tuple():
    ob = OrderBook(
        bids=[(0.40, 100.0), (0.38, 50.0)],
        asks=[(0.45, 80.0), (0.47, 30.0)],
        tick_size=0.01,
    )
    assert ob.best_ask == 0.45  # min ask
    assert ob.best_bid == 0.40  # max bid
    assert ob.as_tuple() == (0.45, 0.40, 0.01)


def test_orderbook_empty_sides_yield_zero():
    ob = OrderBook()
    assert ob.best_ask == 0.0
    assert ob.best_bid == 0.0
    assert ob.as_tuple() == (0.0, 0.0, 0.01)


# ----------------------------------------------------------------------
# 2. Book merge: snapshot then deltas
# ----------------------------------------------------------------------
def test_handle_message_book_then_price_change():
    stream = RTDSStream(ws_url="ws://x")
    book_frame = json.dumps(
        {
            "type": "book",
            "asset_id": "TOK1",
            "bids": [{"price": "0.40", "size": "100"}],
            "asks": [{"price": "0.45", "size": "80"}, {"price": "0.50", "size": "20"}],
            "tick_size": "0.01",
        }
    )
    stream._handle_message(book_frame)

    book, ts = stream.get_book("TOK1")
    assert book is not None
    assert ts is not None
    assert book.best_bid == 0.40
    assert book.best_ask == 0.45

    # Delta: improve the bid to 0.42 (new level).
    stream._handle_message(
        {
            "type": "price_change",
            "asset_id": "TOK1",
            "changes": [{"side": "buy", "price": 0.42, "size": 70}],
        }
    )
    book, _ = stream.get_book("TOK1")
    assert book.best_bid == 0.42

    # Delta: size 0 removes the 0.45 ask → best ask falls back to 0.50.
    stream._handle_message(
        {
            "type": "price_change",
            "asset_id": "TOK1",
            "changes": [{"side": "sell", "price": 0.45, "size": 0}],
        }
    )
    book, _ = stream.get_book("TOK1")
    assert book.best_ask == 0.50


def test_handle_message_unknown_type_ignored_and_get_book_none():
    stream = RTDSStream(ws_url="ws://x")
    stream._handle_message({"type": "heartbeat", "asset_id": "TOK1"})
    assert stream.get_book("TOK1") == (None, None)
    assert stream.get_book("NOPE") == (None, None)


def test_apply_delta_seeds_unknown_token():
    stream = RTDSStream(ws_url="ws://x")
    stream._apply_delta("NEW", "buy", 0.30, 10)
    book, ts = stream.get_book("NEW")
    assert book is not None and ts is not None
    assert book.best_bid == 0.30


# ----------------------------------------------------------------------
# 3. Reconciliation logs on divergence
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reconcile_once_logs_divergence(caplog):
    # Mirror best_ask = 0.45; REST says 0.55 → diverges by 0.10 > one tick.
    rest_book = OrderBook(bids=[(0.40, 1)], asks=[(0.55, 1)], tick_size=0.01)
    stream = RTDSStream(
        ws_url="ws://x",
        rest_book_fetcher=lambda tok: rest_book,
        reconcile_sample_size=5,
    )
    stream._apply_book_snapshot(
        "TOK1", [{"price": 0.40, "size": 1}], [{"price": 0.45, "size": 1}], 0.01
    )
    with stream._lock:
        stream._subscribed = {"TOK1"}

    with caplog.at_level(logging.WARNING):
        await stream._reconcile_once()  # must not raise

    assert any("divergence" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_reconcile_once_no_divergence_no_warning(caplog):
    rest_book = OrderBook(bids=[(0.40, 1)], asks=[(0.45, 1)], tick_size=0.01)
    stream = RTDSStream(ws_url="ws://x", rest_book_fetcher=lambda tok: rest_book)
    stream._apply_book_snapshot(
        "TOK1", [{"price": 0.40, "size": 1}], [{"price": 0.45, "size": 1}], 0.01
    )
    with stream._lock:
        stream._subscribed = {"TOK1"}
    with caplog.at_level(logging.WARNING):
        await stream._reconcile_once()
    assert not any("divergence" in r.message.lower() for r in caplog.records)


# ----------------------------------------------------------------------
# 4. REST fallback populates mirror
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rest_fallback_once_populates_mirror():
    books = {
        "A": OrderBook(bids=[(0.30, 1)], asks=[(0.35, 1)], tick_size=0.01),
        "B": OrderBook(bids=[(0.60, 1)], asks=[(0.65, 1)], tick_size=0.01),
    }

    async def _fetch(tok):  # async fetcher exercises the awaitable path
        return books.get(tok)

    stream = RTDSStream(ws_url="ws://x", rest_book_fetcher=_fetch)
    with stream._lock:
        stream._subscribed = {"A", "B"}

    await stream._rest_fallback_once()

    ba, _ = stream.get_book("A")
    bb, _ = stream.get_book("B")
    assert ba.best_ask == 0.35
    assert bb.best_bid == 0.60


# ----------------------------------------------------------------------
# 5. Desired-token-id set reflects cache changes
# ----------------------------------------------------------------------
def test_desired_token_ids_reflects_cache_change():
    cache = FakeCache(
        [_entry(yes="A", no="B")],
        [_entry(yes="A", no="B"), _entry(yes="C", no="")],
    )
    stream = RTDSStream(ws_url="ws://x", discovery_cache=cache)
    assert stream._desired_token_ids() == {"A", "B"}
    assert stream._desired_token_ids() == {"A", "B", "C"}


def test_desired_token_ids_empty_without_cache():
    stream = RTDSStream(ws_url="ws://x")
    assert stream._desired_token_ids() == set()


# ----------------------------------------------------------------------
# 5b. run() integration with a fake WS (seed frames, then FakeClosed)
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_consumes_frames_then_stops(monkeypatch):
    book_frame = json.dumps(
        {
            "type": "book",
            "asset_id": "A",
            "bids": [{"price": "0.40", "size": "100"}],
            "asks": [{"price": "0.45", "size": "80"}],
            "tick_size": "0.01",
        }
    )
    ws = FakeWS(frames=[book_frame])
    book_applied = asyncio.Event()
    cache = FakeCache([_entry(yes="A", no="B")])
    stream = RTDSStream(
        ws_url="ws://x",
        discovery_cache=cache,
        ws_connect=_make_ws_connect(ws),
        rest_fallback_interval_s=0.0,
    )

    # Patch sleep to (a) yield control to the loop so the watcher runs and
    # (b) stop the stream as soon as run() reaches its backoff path after the
    # socket drains — keeps the test deterministic without wall-clock waits.
    real_sleep = asyncio.sleep

    async def _instant(_delay):
        if stream.get_book("A")[0] is not None:
            book_applied.set()
            stream.stop()
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _instant)

    await asyncio.wait_for(stream.run(), 2.0)
    assert book_applied.is_set()

    # Subscribe frame was sent for the desired tokens.
    assert ws.sent, "expected a subscribe frame"
    sub = json.loads(ws.sent[0])
    assert sub["type"] == "subscribe"
    assert set(sub["market_ids"]) == {"A", "B"}
    # The book frame was applied to the mirror before the socket dropped.
    book, _ = stream.get_book("A")
    assert book is not None
    assert book.best_ask == 0.45
