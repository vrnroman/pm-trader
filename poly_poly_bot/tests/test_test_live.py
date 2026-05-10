"""Tests for the /test-live market picker.

Covers eligibility filtering: price threshold, resolution window,
empty-book rejection, and YES/NO favourite-side classification.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from src.test_live import (
    MIN_FAVOURITE_PRICE,
    RESOLUTION_WINDOW_HOURS,
    _classify_favourite,
    find_test_market,
)


def _market(
    *,
    condition_id: str = "0xCID",
    question: str = "Will X happen?",
    end_iso: str = "",
    yes_price: float = 0.95,
    no_price: float | None = None,
    yes_token: str = "TOKEN_YES",
    no_token: str = "TOKEN_NO",
    best_ask: float = 0.96,
    best_bid: float = 0.94,
    closed: bool = False,
    active: bool = True,
) -> dict:
    if no_price is None:
        no_price = round(1.0 - yes_price, 4)
    return {
        "conditionId": condition_id,
        "question": question,
        "endDate": end_iso,
        "outcomePrices": json.dumps([str(yes_price), str(no_price)]),
        "clobTokenIds": json.dumps([yes_token, no_token]),
        "bestAsk": str(best_ask),
        "bestBid": str(best_bid),
        "closed": closed,
        "active": active,
    }


def _event(markets: list[dict], *, slug: str = "ev-1", title: str = "Event 1") -> dict:
    return {"slug": slug, "title": title, "markets": markets}


def _iso_at(now_ts: float, hours_ahead: float) -> str:
    from datetime import datetime, timezone
    return (
        datetime.fromtimestamp(now_ts + hours_ahead * 3600, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


# --- _classify_favourite ----------------------------------------------------


def test_classify_favourite_picks_yes_when_yes_above_threshold():
    side, price, token = _classify_favourite([0.95, 0.05], ["YT", "NT"])
    assert side == "YES"
    assert price == 0.95
    assert token == "YT"


def test_classify_favourite_picks_no_when_no_above_threshold():
    side, price, token = _classify_favourite([0.05, 0.95], ["YT", "NT"])
    assert side == "NO"
    assert price == 0.95
    assert token == "NT"


def test_classify_favourite_returns_none_when_neither_side_dominant():
    assert _classify_favourite([0.55, 0.45], ["YT", "NT"]) is None
    assert _classify_favourite([0.89, 0.11], ["YT", "NT"]) is None


def test_classify_favourite_handles_short_arrays():
    assert _classify_favourite([0.95], ["YT"]) is None
    assert _classify_favourite([], []) is None


# --- find_test_market filtering --------------------------------------------


def test_find_test_market_picks_first_eligible():
    now = time.time()
    events = [
        _event([
            _market(
                condition_id="0xWINNER",
                question="Will A win by tomorrow?",
                end_iso=_iso_at(now, 12),
                yes_price=0.93,
            )
        ])
    ]
    result = find_test_market(now_ts=now, events=events)
    assert result is not None
    assert result.condition_id == "0xWINNER"
    assert result.favourite_side == "YES"
    assert result.favourite_token_id == "TOKEN_YES"
    assert result.favourite_price >= MIN_FAVOURITE_PRICE


def test_find_test_market_skips_low_price_markets():
    now = time.time()
    events = [
        _event([
            _market(end_iso=_iso_at(now, 5), yes_price=0.65),
            _market(end_iso=_iso_at(now, 5), yes_price=0.85),
        ])
    ]
    assert find_test_market(now_ts=now, events=events) is None


def test_find_test_market_skips_already_resolved_markets():
    now = time.time()
    events = [
        _event([_market(end_iso=_iso_at(now, -2), yes_price=0.95)])
    ]
    assert find_test_market(now_ts=now, events=events) is None


def test_find_test_market_skips_too_far_out_markets():
    now = time.time()
    events = [
        _event([
            _market(
                end_iso=_iso_at(now, RESOLUTION_WINDOW_HOURS + 5),
                yes_price=0.95,
            )
        ])
    ]
    assert find_test_market(now_ts=now, events=events) is None


def test_find_test_market_skips_closed_markets():
    now = time.time()
    events = [
        _event([_market(end_iso=_iso_at(now, 5), yes_price=0.95, closed=True)])
    ]
    assert find_test_market(now_ts=now, events=events) is None


def test_find_test_market_skips_inactive_markets():
    now = time.time()
    events = [
        _event([_market(end_iso=_iso_at(now, 5), yes_price=0.95, active=False)])
    ]
    assert find_test_market(now_ts=now, events=events) is None


def test_find_test_market_skips_zero_ask_book():
    now = time.time()
    # YES favourite with zero ask is unbuyable — must be rejected.
    events = [
        _event([
            _market(
                end_iso=_iso_at(now, 5),
                yes_price=0.95,
                best_ask=0.0,
                best_bid=0.94,
            )
        ])
    ]
    assert find_test_market(now_ts=now, events=events) is None


def test_find_test_market_no_side_picks_via_inverted_bid():
    now = time.time()
    # NO is the favourite at 95c. To buy NO we need bestBid (YES side) > 0
    # so that (1 - bestBid) gives a real NO ask.
    events = [
        _event([
            _market(
                end_iso=_iso_at(now, 5),
                yes_price=0.04,
                no_price=0.96,
                best_ask=0.05,
                best_bid=0.04,
            )
        ])
    ]
    result = find_test_market(now_ts=now, events=events)
    assert result is not None
    assert result.favourite_side == "NO"
    assert result.favourite_token_id == "TOKEN_NO"
    # NO ask = 1 - YES bid = 1 - 0.04 = 0.96
    assert result.best_ask == pytest.approx(0.96, abs=1e-6)


def test_find_test_market_picks_first_event_when_multiple_eligible():
    now = time.time()
    events = [
        _event(
            [_market(condition_id="0xFIRST", end_iso=_iso_at(now, 6), yes_price=0.92)],
            slug="ev-a",
            title="First Event",
        ),
        _event(
            [_market(condition_id="0xSECOND", end_iso=_iso_at(now, 8), yes_price=0.93)],
            slug="ev-b",
            title="Second Event",
        ),
    ]
    result = find_test_market(now_ts=now, events=events)
    assert result is not None
    assert result.condition_id == "0xFIRST"
    assert result.event_slug == "ev-a"


def test_find_test_market_returns_none_for_empty_input():
    assert find_test_market(now_ts=time.time(), events=[]) is None


def test_find_test_market_handles_malformed_events_field():
    assert find_test_market(now_ts=time.time(), events="not a list") is None  # type: ignore[arg-type]
