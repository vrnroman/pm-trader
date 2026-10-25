"""The tape rule in all four states, over synthetic quotes and prints with a
pinned clock (2026-10-25)."""
from __future__ import annotations

import pytest

from src.newsbot.freshness import verdict
from src.newsbot.tape.clob_ws import QuoteBook
from src.newsbot.tape.livedata import TradeBuckets, parse_trade

NOW = 1_800_000_000.0
TOK, CID = "tok-yes", "0xcond"


def _quotes(book: QuoteBook, points: list[tuple[float, float, float]]) -> None:
    """points: (seconds before NOW, bid, ask)."""
    for ago, bid, ask in points:
        book.record(TOK, int((NOW - ago) * 1000), bid, ask)


def _prints(buckets: TradeBuckets, points: list[tuple[float, float]]) -> None:
    for ago, price in points:
        buckets.add(parse_trade({"conditionId": CID, "asset": TOK, "price": price, "size": 1, "timestamp": NOW - ago, "outcome": "Yes"}))


def _verdict(book, buckets, **kw):
    kw.setdefault("fresh_cents", 3)
    kw.setdefault("fresh_min", 15)
    return verdict(book, buckets, TOK, CID, NOW, **kw)


def test_unknown_when_no_quotes_and_no_trades():
    state, detail = _verdict(QuoteBook(), TradeBuckets())
    assert state == "unknown" and detail == "no quotes and no trades yet"


def test_fresh_when_quotes_and_prints_are_flat_and_ask_sits_on_the_pre_window_mid():
    book, b = QuoteBook(), TradeBuckets()
    _quotes(book, [(25 * 60, 0.40, 0.42), (16 * 60, 0.40, 0.43), (9 * 60, 0.41, 0.43), (60, 0.40, 0.42)])
    _prints(b, [(14 * 60, 0.41), (7 * 60, 0.42), (90, 0.415)])
    state, detail = _verdict(book, b)
    assert state == "fresh"
    assert detail.startswith("quiet 15m: quotes 1.0c, trades 1.0c n=3; ask 0.420 vs pre-mid(15m) 0.415 (+0.5c)")


def test_moving_when_the_move_is_inside_the_last_three_minutes():
    book, b = QuoteBook(), TradeBuckets()
    _quotes(book, [(20 * 60, 0.40, 0.42), (60, 0.50, 0.52)])
    state, detail = _verdict(book, b)
    assert state == "moving"
    assert detail == "move in last 3m: quotes 10.0c, trades - n=0"


def test_moving_from_prints_alone_when_the_book_has_no_quotes_yet():
    b = TradeBuckets()
    _prints(b, [(10 * 60, 0.30), (100, 0.30), (30, 0.39)])
    state, detail = _verdict(QuoteBook(), b)
    assert state == "moving" and "trades 9.0c n=2" in detail


def test_late_when_the_jump_happened_earlier_in_the_window_and_is_now_flat():
    book, b = QuoteBook(), TradeBuckets()
    _quotes(book, [(20 * 60, 0.40, 0.42), (8 * 60, 0.50, 0.52), (4 * 60, 0.50, 0.52)])
    _prints(b, [(8 * 60 + 5, 0.41), (8 * 60 - 20, 0.51), (5 * 60, 0.51)])
    state, detail = _verdict(book, b)
    assert state == "late"
    assert detail == "moved earlier in last 15m: quotes 10.0c, trades 10.0c n=3; last 3m quiet"


def test_late_when_the_window_is_quiet_but_the_ask_already_left_the_pre_window_mid():
    book, b = QuoteBook(), TradeBuckets()
    _quotes(book, [(20 * 60, 0.40, 0.42), (10 * 60, 0.50, 0.52)])
    state, detail = _verdict(book, b, fresh_min=5)
    assert state == "late"
    assert detail.startswith("ask already away from quotes 0.0c, trades - n=0; ask 0.520 vs pre-mid(15m) 0.410 (+11.0c)")


def test_unknown_when_only_quiet_prints_exist_because_the_ask_cannot_be_checked():
    b = TradeBuckets()
    _prints(b, [(10 * 60, 0.30), (30, 0.31)])
    state, detail = _verdict(QuoteBook(), b)
    assert state == "unknown" and detail == "no quotes yet; trades 1.0c n=2 in 15m"


def test_fresh_with_a_young_book_names_the_baseline_age():
    book = QuoteBook()
    _quotes(book, [(4 * 60, 0.40, 0.42), (30, 0.40, 0.42)])
    state, detail = _verdict(book, TradeBuckets())
    assert state == "fresh" and "oldest mid (4.0m old) 0.410 (+1.0c)" in detail


def test_the_three_minute_edge_is_seeded_with_the_mid_just_before_it():
    # The only quote inside the last 3 min is flat, but it sits 10c above the
    # quote from 3.5 min ago: that is a move in progress, not a calm market.
    book = QuoteBook()
    _quotes(book, [(30 * 60, 0.40, 0.42), (3.5 * 60, 0.40, 0.42), (2 * 60, 0.50, 0.52)])
    state, _ = _verdict(book, TradeBuckets())
    assert state == "moving"


def test_no_ask_on_the_book_is_unknown():
    book = QuoteBook()
    book.record(TOK, int((NOW - 60) * 1000), 0.40, None)
    state, detail = _verdict(book, TradeBuckets())
    assert (state, detail) == ("unknown", "no ask on the book")


@pytest.mark.parametrize("fresh_cents,expected", [(3, "late"), (12, "fresh")])
def test_fresh_cents_is_the_knob(fresh_cents, expected):
    book = QuoteBook()
    _quotes(book, [(20 * 60, 0.40, 0.42), (8 * 60, 0.50, 0.52)])
    state, _ = _verdict(book, TradeBuckets(), fresh_cents=fresh_cents)
    assert state == expected
