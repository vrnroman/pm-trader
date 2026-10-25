"""The newsbot market tape: bounded buckets, the sorted quote book, the jump
detector and the two websocket clients against scripted connections
(2026-10-25). No wall clock anywhere: every ``now`` is a pinned epoch."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.newsbot.tape import clob_ws, jumps, livedata
from src.newsbot.tape.clob_ws import Fill, QuoteBook, fetch_book_rest, parse_ladder, shard, stream_quotes
from src.newsbot.tape.jumps import JumpDetector
from src.newsbot.tape.livedata import (
    Comment,
    CommentCounter,
    TradeBuckets,
    classify_frame,
    parse_comment,
    parse_trade,
    stream_trades,
)

T0 = 1_800_000_000.0  # 2027-01-15 08:00:00 UTC, on a minute boundary (1_800_000_000 % 60 == 0)
CID = "0xcond-a"


def _payload(price, size, ts, cid=CID, outcome="Yes", asset="tok-a", **extra):
    p = {
        "asset": asset,
        "conditionId": cid,
        "eventSlug": "ev",
        "slug": "mk",
        "title": "Will it?",
        "outcome": outcome,
        "price": price,
        "side": "BUY",
        "size": size,
        "timestamp": ts,
        "proxyWallet": "0xabc",
        "name": "someone",
        "transactionHash": "0xtx",
    }
    p.update(extra)
    return p


def _trade(price, size, ts, **kw):
    t = parse_trade(_payload(price, size, ts, **kw))
    assert t is not None
    return t


def _frame(payload, **top):
    return json.dumps({"connection_id": "c1", "payload": payload, **top})


# ---------------------------------------------------------------- parsing


def test_parse_trade_folds_the_no_leg_into_yes_space_and_normalises_ms():
    yes = parse_trade(_payload("0.40", "10", T0))
    no = parse_trade(_payload(0.55, 4, int(T0 * 1000), outcome="No"))
    assert yes.price == 0.40 and yes.yes_price == 0.40 and yes.ts == T0
    assert no.price == 0.55 and no.yes_price == pytest.approx(0.45) and no.ts == T0
    assert yes.notional == pytest.approx(4.0)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "nope",
        {},
        {"conditionId": CID, "price": "abc", "size": 1, "timestamp": T0},
        {"conditionId": CID, "price": 1.5, "size": 1, "timestamp": T0},
        {"conditionId": CID, "price": 0.5, "size": 1, "timestamp": "when?"},
        {"price": 0.5, "size": 1, "timestamp": T0},
    ],
)
def test_parse_trade_rejects_malformed_payloads(bad):
    assert parse_trade(bad) is None


def test_classify_frame_handles_empty_first_frame_keepalives_and_garbage():
    assert classify_frame("") is None
    assert classify_frame("{}") is None
    assert classify_frame(b"") is None
    assert classify_frame(json.dumps({"connection_id": "c1"})) is None
    assert classify_frame(json.dumps({"connection_id": "c1", "payload": {}})) is None
    assert classify_frame("not json at all") is None
    assert classify_frame("[1,2,3]") is None
    assert classify_frame(_frame(_payload(0.4, 1, T0)))[0] == "trade"
    assert classify_frame(_frame({"body": "hi", "parentEntityID": "ev-1", "createdAt": "2027-01-15T08:00:00Z"}))[0] == "comment"
    assert classify_frame(_frame({"body": "hi", "parentEntityID": "ev-1"}, topic="comments"))[0] == "comment"


def test_parse_comment_keeps_only_a_key_a_time_and_the_body_length():
    c = parse_comment({"body": "hello there", "parentEntityID": "ev-1", "createdAt": "2027-01-15T08:00:00Z"})
    assert c == Comment(market_key="ev-1", ts=T0, body_len=11)
    assert parse_comment({"body": "x"}) is None
    assert parse_comment({"body": "x", "conditionId": CID}) is None  # no time


# ---------------------------------------------------------------- buckets


def test_bucket_math_first_last_min_max_notional_and_delta():
    b = TradeBuckets(window_min=60)
    b.add(_trade(0.40, 10, T0 + 5))
    b.add(_trade(0.42, 5, T0 + 30))
    b.add(_trade(0.38, 2, T0 + 20))  # out of order inside the minute: not first, not last
    b.add(_trade(0.45, 4, T0 + 125))  # minute +2
    b.add(_trade(0.60, 3, T0 + 125, outcome="No"))  # 0.40 in YES space, same second: last wins by >=

    items = b.recent(CID, 5, now=T0 + 130)
    assert [m for m, _ in items] == [int(T0 // 60), int(T0 // 60) + 2]
    m0, m2 = items[0][1], items[1][1]
    assert (m0.n, m0.first_price, m0.last_price, m0.min, m0.max) == (3, 0.40, 0.42, 0.38, 0.42)
    assert m0.notional == pytest.approx(0.40 * 10 + 0.42 * 5 + 0.38 * 2)
    assert m2.n == 2 and m2.first_price == 0.45 and m2.last_price == pytest.approx(0.40)
    assert m2.notional == pytest.approx(0.45 * 4 + 0.60 * 3)  # notional is what was actually paid

    w = b.window(CID, 5, now=T0 + 130)
    assert w.n == 5 and w.minutes == 2 and w.first_price == 0.40 and w.last_price == pytest.approx(0.40)
    assert b.delta_cents(CID, 5, now=T0 + 130) == pytest.approx(0.0)
    # Narrow the window to the last minute only: 0.45 -> 0.40 is -5c.
    assert b.delta_cents(CID, 1, now=T0 + 130) == pytest.approx(-5.0)
    assert b.delta_cents("never", 5, now=T0) is None  # unknown is not zero


def test_buckets_default_now_is_the_tapes_own_clock_not_the_wall_clock():
    b = TradeBuckets(window_min=60)
    b.add(_trade(0.40, 1, T0))
    b.add(_trade(0.50, 1, T0 + 600))
    assert b.last_ts == T0 + 600
    assert b.delta_cents(CID, 11) == pytest.approx(10.0)  # window ends at the newest trade seen
    # A 5-min window ending at the newest print holds only that print: the T0 one is out.
    assert [m for m, _ in b.recent(CID, 5)] == [int((T0 + 600) // 60)]
    assert b.delta_cents(CID, 5) == pytest.approx(0.0)


def test_buckets_prune_and_per_market_window_drop_oldest_minutes_first():
    b = TradeBuckets(window_min=2)
    for k in range(5):
        b.add(_trade(0.5, 1, T0 + 60 * k))
    # Only minutes within 2 of the newest (minute 5-2=3 -> minutes 3,4; floor is newest-window => 2,3,4)
    assert [m - int(T0 // 60) for m, _ in b.recent(CID, 60, now=T0 + 300)] == [2, 3, 4]
    # A replayed print older than the window is dropped, not grown backwards.
    b.add(_trade(0.1, 1, T0))
    assert [m - int(T0 // 60) for m, _ in b.recent(CID, 60, now=T0 + 300)] == [2, 3, 4]
    assert b.trades_seen == 5
    # prune(now) with the clock moved on drops the market entirely once empty.
    assert b.prune(T0 + 60 * 8) == 3
    assert len(b) == 0 and b.recent(CID, 60, now=T0 + 480) == []


def test_buckets_cap_the_number_of_markets_lru():
    b = TradeBuckets(window_min=60, max_markets=3)
    for i in range(4):
        b.add(_trade(0.5, 1, T0 + i, cid=f"c{i}"))
    assert len(b) == 3 and "c0" not in b and b.evicted_keys == 1
    b.add(_trade(0.5, 1, T0 + 10, cid="c1"))  # touching c1 makes c2 the oldest
    b.add(_trade(0.5, 1, T0 + 11, cid="c9"))
    assert set(b.markets()) == {"c1", "c3", "c9"}
    assert b.markets(active_since=T0 + 10) == ["c1", "c9"]


def test_comment_counter_counts_per_minute_and_is_bounded():
    c = CommentCounter(window_min=10, max_markets=2)
    c.add(Comment("ev-2", T0 + 5, 1))
    for ts in (T0 + 1, T0 + 2, T0 + 61):
        c.add(Comment("ev-1", ts, 5))
    assert c.recent("ev-1", 5, now=T0 + 70) == 3
    assert c.per_minute("ev-1", 5, now=T0 + 70) == [(int(T0 // 60), 2), (int(T0 // 60) + 1, 1)]
    # Minute buckets cannot be split: a window includes every bucket it overlaps,
    # so "last 1 minute" at T0+70 still touches minute 0; at T0+125 it does not.
    assert c.recent("ev-1", 1, now=T0 + 70) == 3
    assert c.recent("ev-1", 1, now=T0 + 125) == 1
    c.add(Comment("ev-3", T0 + 6, 1))
    assert len(c) == 2 and "ev-2" not in c  # ev-2 was the least recently updated
    c.add(Comment("ev-1", T0 + 60 * 20, 1))  # 20 minutes on: the old minutes fall out of the 10-min window
    assert c.recent("ev-1", 60, now=T0 + 60 * 20) == 1


# ---------------------------------------------------------------- quote book


def _ladder_frame(token="tok-a", ts=T0 * 1000):
    # Deliberately the WRONG order: bids ascending, asks descending.
    return {
        "event_type": "book",
        "asset_id": token,
        "bids": [{"price": "0.40", "size": "100"}, {"price": "0.41", "size": "50"}, {"price": "0.42", "size": "3"}],
        "asks": [{"price": "0.50", "size": "100"}, {"price": "0.46", "size": "4"}, {"price": "0.45", "size": "5"}],
        "timestamp": str(int(ts)),
    }


def test_ladder_is_sorted_ourselves_and_best_is_taken_from_the_sorted_side():
    book = QuoteBook()
    book.apply_book(_ladder_frame())
    lad = book.ladder("tok-a")
    assert [p for p, _ in lad.bids] == [0.42, 0.41, 0.40]
    assert [p for p, _ in lad.asks] == [0.45, 0.46, 0.50]
    assert book.best("tok-a") == (0.42, 0.45, int(T0 * 1000))


def test_walk_ask_fills_our_size_across_levels_and_reports_partials():
    book = QuoteBook()
    book.apply_book(_ladder_frame())
    f = book.walk_ask("tok-a", 5.0)
    # 5 @0.45 = 2.25, 4 @0.46 = 1.84, remaining 0.91 -> 1.82 @0.50
    assert f.filled_usd == pytest.approx(5.0) and f.levels == 3
    assert f.shares == pytest.approx(5 + 4 + 0.91 / 0.50)
    assert f.avg_price == pytest.approx(5.0 / f.shares)
    # Thin book: only 2.25 + 1.84 available -> partial fill reported honestly.
    thin = _ladder_frame()
    thin["asks"] = thin["asks"][1:]
    book.apply_book(thin)
    p = book.walk_ask("tok-a", 5.0)
    assert p == Fill(pytest.approx((2.25 + 1.84) / 9), pytest.approx(4.09), 2)
    assert book.walk_ask("tok-zzz", 5.0) == Fill(None, 0.0, 0)
    assert book.walk_ask("tok-a", 0) == Fill(None, 0.0, 0)


def test_walk_bid_by_usd_and_by_shares_from_the_best_bid_down():
    book = QuoteBook()
    book.apply_book(_ladder_frame())
    f = book.walk_bid("tok-a", 2.0)  # 3 @0.42 = 1.26, remaining 0.74 -> 1.8049 @0.41
    assert f.levels == 2 and f.filled_usd == pytest.approx(2.0)
    assert f.avg_price == pytest.approx(2.0 / (3 + 0.74 / 0.41))
    s = book.walk_bid("tok-a", shares=10)  # 3 @0.42 + 7 @0.41
    assert s.levels == 2 and s.filled_usd == pytest.approx(3 * 0.42 + 7 * 0.41) and s.shares == pytest.approx(10)
    big = book.walk_bid("tok-a", shares=1000)  # more than the book holds: partial
    assert big.levels == 3 and big.shares == pytest.approx(153)


def test_ring_buffer_is_bounded_skips_unchanged_quotes_and_mid_at_is_nearest_earlier():
    book = QuoteBook(maxlen=5)
    for i in range(10):
        book.record("tok-a", 1000 * (i + 1), 0.40 + i / 100, 0.42 + i / 100)
    hist = book.history("tok-a")
    assert len(hist) == 5 and hist[0][0] == 6000 and hist[-1][0] == 10000
    assert book.mid_at("tok-a", 7500) == pytest.approx((0.46 + 0.48) / 2)  # the 7000 entry
    assert book.mid_at("tok-a", 7000) == pytest.approx((0.46 + 0.48) / 2)  # at-or-before
    assert book.mid_at("tok-a", 5999) is None  # fell off the ring: unknown, not the current mid
    assert book.mid_at("nope", 1) is None
    # An unchanged quote does not take a slot but does move the "seen" clock.
    book.record("tok-a", 11000, 0.49, 0.51)
    assert len(book.history("tok-a")) == 5 and book.best("tok-a") == (0.49, 0.51, 11000)


def test_price_change_frames_update_ladder_and_best_and_token_cap_is_lru():
    book = QuoteBook(max_tokens=2)
    book.apply_book(_ladder_frame("tok-a"))
    n = book.apply_frame(
        json.dumps(
            {
                "event_type": "price_change",
                "price_changes": [
                    {"asset_id": "tok-a", "price": "0.45", "size": "0", "side": "SELL", "best_bid": "0.42", "best_ask": "0.46"},
                    {"asset_id": "tok-a", "price": "0.43", "size": "7", "side": "BUY"},
                ],
                "timestamp": str(int(T0 * 1000) + 500),
            }
        )
    )
    assert n == 1
    lad = book.ladder("tok-a")
    assert [p for p, _ in lad.asks] == [0.46, 0.50]  # the 0.45 level was removed
    assert [p for p, _ in lad.bids] == [0.43, 0.42, 0.41, 0.40]  # inserted in order
    assert book.best("tok-a") == (0.43, 0.46, int(T0 * 1000) + 500)  # second change had no best_*: ladder answers
    # Malformed input never raises.
    assert book.apply_frame("not json") == 0 and book.rejected == 1
    assert book.apply_frame("PONG") == 0
    assert book.apply_frame(json.dumps([{"event_type": "weird"}, 7])) == 0
    assert book.apply_frame(json.dumps({"event_type": "last_trade_price", "asset_id": "tok-a", "price": "0.44", "timestamp": "1"})) == 1
    assert book.last_trade("tok-a") == (1000, 0.44)
    book.apply_book(_ladder_frame("tok-b"))
    book.apply_book(_ladder_frame("tok-c"))
    assert book.tokens() == ["tok-b", "tok-c"] and book.ladder("tok-a") is None


def test_shard_splits_sorted_unique_ids_into_connections_of_at_most_n():
    assert shard(["b", "a", "a", "c"], size=2) == [("a", "b"), ("c",)]
    assert shard([], size=500) == []
    assert len(shard(range(1001))) == 3


async def test_fetch_book_rest_sorts_the_rest_body_and_returns_none_on_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["token_id"] == "bad":
            return httpx.Response(500, text="boom")
        body = _ladder_frame()
        body.pop("event_type")
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        lad = await fetch_book_rest("tok-a", client=client)
        assert lad.best_bid == 0.42 and lad.best_ask == 0.45
        assert await fetch_book_rest("bad", client=client) is None


def test_parse_ladder_drops_junk_levels():
    lad = parse_ladder({"bids": [{"price": "x", "size": 1}, {"price": 0.3, "size": 0}, {"price": 0.3, "size": 2}], "asks": None})
    assert lad.bids == [(0.3, 2.0)] and lad.asks == [] and lad.best_ask is None


# ---------------------------------------------------------------- jumps


def test_jump_detector_reports_once_per_move_and_honours_exclude():
    b = TradeBuckets(window_min=60)
    b.add(_trade(0.40, 10, T0 + 10))
    b.add(_trade(0.50, 20, T0 + 70))
    b.add(_trade(0.40, 10, T0 + 10, cid="sports-1"))
    b.add(_trade(0.60, 10, T0 + 70, cid="sports-1"))
    b.add(_trade(0.40, 10, T0 + 10, cid="quiet"))
    b.add(_trade(0.44, 10, T0 + 70, cid="quiet"))
    b.add(_trade(0.10, 10, T0 + 10, cid="down"))
    b.add(_trade(0.01, 10, T0 + 70, cid="down"))
    b.add(_trade(0.90, 10, T0 + 70, cid="single-print"))

    det = JumpDetector(b, jump_cents=8, window_min=10, exclude=lambda cid: cid.startswith("sports"))
    found = {j.condition_id: j for j in det.scan(T0 + 100)}
    assert set(found) == {CID, "down"}
    j = found[CID]
    assert (j.delta_cents, j.from_price, j.to_price, j.n_trades, j.ts) == (10.0, 0.40, 0.50, 2, T0 + 70)
    assert j.notional == pytest.approx(0.40 * 10 + 0.50 * 20)
    assert found["down"].delta_cents == pytest.approx(-9.0)
    assert det.excluded == 1 and det.reported == 2

    # Same move, next scans inside the cooldown: nothing new.
    assert det.scan(T0 + 160) == [] and det.scan(T0 + 100 + 599) == []
    # After the cooldown the window no longer holds the old prints: still nothing.
    assert det.scan(T0 + 100 + 601) == []
    # A fresh move after the cooldown is a new row.
    b.add(_trade(0.50, 1, T0 + 800))
    b.add(_trade(0.62, 1, T0 + 820))
    again = det.scan(T0 + 830)
    assert [j.condition_id for j in again] == [CID] and again[0].delta_cents == pytest.approx(12.0)


def test_jump_detector_rejects_nonsense_knobs():
    with pytest.raises(ValueError):
        JumpDetector(TradeBuckets(), jump_cents=0, window_min=10)
    with pytest.raises(ValueError):
        TradeBuckets(window_min=0)


# ---------------------------------------------------------------- sockets


class _FakeWS:
    def __init__(self, frames, sent):
        self.frames = list(frames)
        self.sent = sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, msg):
        self.sent.append(msg)

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0)
        if not self.frames:
            raise StopAsyncIteration  # the server dropped us
        f = self.frames.pop(0)
        if isinstance(f, Exception):
            raise f
        return f


class _FakeConnect:
    """Each call hands out the next scripted connection; when the script is
    exhausted it sets ``stop`` and refuses, which is how the client is told to
    end without a wall clock."""

    def __init__(self, scripts, stop):
        self.scripts = [list(s) for s in scripts]
        self.stop = stop
        self.calls: list[tuple[str, dict]] = []
        self.sent: list[list[str]] = []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        if not self.scripts:
            self.stop.set()
            raise ConnectionRefusedError("script exhausted")
        sent: list[str] = []
        self.sent.append(sent)
        return _FakeWS(self.scripts.pop(0), sent)


def _fake_sleep(log):
    async def sleep(s):
        log.append(s)
        await asyncio.sleep(0)

    return sleep


async def test_stream_trades_handles_empty_first_frame_garbage_and_reconnects_with_backoff():
    stop = asyncio.Event()
    good = _frame(_payload(0.4, 2, T0))
    comment = _frame({"body": "nice", "parentEntityID": "ev-1", "createdAt": "2027-01-15T08:00:00Z"})
    conn1 = ["", "{}", json.dumps({"connection_id": "c1"}), good, "not json", _frame(_payload("abc", 1, T0)), comment]
    conn2 = []  # accepted then dropped without a frame: backoff must grow
    conn3 = [_frame(_payload(0.41, 1, T0 + 1)), RuntimeError("socket reset")]
    fake = _FakeConnect([conn1, conn2, conn3], stop)
    delays: list[float] = []
    trades, comments = [], []

    async def on_trade(t):  # async callbacks are awaited
        trades.append(t)

    def on_comment(c):
        comments.append(c)
        raise ValueError("a bad callback must not kill the tape")

    await asyncio.wait_for(
        stream_trades(on_trade, on_comment, connect=fake, sleep=_fake_sleep(delays), stop=stop, backoff=(1.0, 60.0)),
        timeout=5,
    )
    assert [t.price for t in trades] == [0.4, 0.41]
    assert len(comments) == 1 and comments[0].market_key == "ev-1"
    assert len(fake.calls) == 4  # three scripted connections + the refused one
    url, kw = fake.calls[0]
    assert url == livedata.LIVE_URL and kw["additional_headers"]["Origin"] == "https://polymarket.com"
    for sent in fake.sent:  # every connection subscribes to both topics first
        assert [json.loads(m) for m in sent[:2]] == [livedata.SUBSCRIBE_TRADES, livedata.SUBSCRIBE_COMMENTS]
    # conn1 got frames (delay reset) -> 1.0; conn2 got none -> 2.0; conn3 got a frame -> 1.0;
    # the refused call set stop, which is checked before sleeping, so no fourth delay.
    assert delays == [1.0, 2.0, 1.0]


async def test_stream_quotes_subscribes_pings_reconnects_and_resubscribes_on_set_change():
    stop = asyncio.Event()
    book = QuoteBook()
    pc = json.dumps(
        {
            "event_type": "price_change",
            "price_changes": [{"asset_id": "tok-a", "price": "0.45", "size": "1", "side": "SELL", "best_bid": "0.42", "best_ask": "0.47"}],
            "timestamp": str(int(T0 * 1000) + 1000),
        }
    )
    conn_a1 = [json.dumps(_ladder_frame("tok-a")), "PONG", pc]
    conn_a2 = [json.dumps(_ladder_frame("tok-b"))]
    conn_b1 = ["garbage", json.dumps(_ladder_frame("tok-c"))]
    fake = _FakeConnect([conn_a1, conn_a2, conn_b1], stop)
    delays: list[float] = []

    def provider():
        # Set A until the reconnected (second) connection has delivered its
        # tok-b ladder, then set B: the switch must not race the frame.
        return ["tok-c"] if "tok-b" in book else ["tok-b", "tok-a"]

    await asyncio.wait_for(
        stream_quotes(
            provider, book, connect=fake, sleep=_fake_sleep(delays), stop=stop, ping_interval=10.0, poll_interval=5.0
        ),
        timeout=5,
    )
    assert len(fake.calls) == 4 and fake.calls[0][0] == clob_ws.CLOB_WS_URL
    subs = [json.loads(s[0]) for s in fake.sent]
    assert subs[0] == {"assets_ids": ["tok-a", "tok-b"], "type": "market"}  # sorted, both ids
    assert subs[1] == subs[0]  # reconnect after the drop resubscribes the same set
    assert subs[2] == {"assets_ids": ["tok-c"], "type": "market"}  # the provider's set changed
    assert any("PING" in s[1:] for s in fake.sent)  # the pinger ran on an open connection
    assert 10.0 in delays and 5.0 in delays and 1.0 in delays  # ping interval, poll interval, backoff
    assert book.best("tok-a") == (0.42, 0.47, int(T0 * 1000) + 1000)
    assert book.best("tok-b")[:2] == (0.42, 0.45) and book.best("tok-c")[:2] == (0.42, 0.45)
    assert book.rejected == 1 and book.frames == 4  # "garbage" counted, "PONG" ignored


async def test_stream_quotes_shards_more_than_the_per_connection_cap():
    stop = asyncio.Event()
    book = QuoteBook()
    fake = _FakeConnect([[], []], stop)  # two shards, each accepted once then dropped
    ids = [f"t{i:03d}" for i in range(7)]
    await asyncio.wait_for(
        stream_quotes(lambda: ids, book, connect=fake, sleep=_fake_sleep([]), stop=stop, max_per_connection=5),
        timeout=5,
    )
    subs = sorted(len(json.loads(s[0])["assets_ids"]) for s in fake.sent)
    assert subs == [2, 5]


def test_package_exports_the_public_surface():
    from src.newsbot import tape

    assert tape.TradeBuckets is TradeBuckets and tape.QuoteBook is QuoteBook and tape.JumpDetector is JumpDetector
    assert jumps.Jump is tape.Jump
