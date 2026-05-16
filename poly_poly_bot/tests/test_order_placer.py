"""Tests for tennis order_placer's live-book + FAK pricing.

The bug we're guarding against: the previous implementation rounded
``ref_price * 1.02`` to cents and clamped to 0.99, which silently turned
into "limit at the same cent as ref" on cheap markets and "limit at 0.99
when ask is 0.994" on tick-0.001 markets. Both made the order rest in
the book and never fill.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

py_clob_client_v2 = pytest.importorskip("py_clob_client_v2")
from py_clob_client_v2 import OrderType  # noqa: E402

from src.tennis.order_placer import (  # noqa: E402
    _round_to_tick,
    _tick_size_str,
    place_buy_yes,
    place_sell_yes,
)


def _book(asks: list[tuple[float, float]], bids: list[tuple[float, float]], tick: float = 0.001):
    """Build a mock orderbook payload — asks descending, bids ascending."""
    return {
        "asks": [{"price": str(p), "size": str(s)} for p, s in asks],
        "bids": [{"price": str(p), "size": str(s)} for p, s in bids],
        "tick_size": str(tick),
    }


def _mock_client(book_response: dict, post_response=None):
    client = MagicMock()
    client.get_order_book.return_value = book_response
    client.create_order.return_value = MagicMock(name="SignedOrder")
    client.post_order.return_value = post_response or {"orderID": "0xabc123", "status": "matched"}
    return client


# --- helpers ---------------------------------------------------------------


def test_round_to_tick_quantizes_to_market_tick():
    assert _round_to_tick(0.4283, 0.01) == 0.43
    assert _round_to_tick(0.4283, 0.001) == 0.428
    assert _round_to_tick(0.99499, 0.001) == 0.995


def test_tick_size_str_picks_canonical_string():
    assert _tick_size_str(0.001) == "0.001"
    assert _tick_size_str(0.01) == "0.01"
    assert _tick_size_str(0.1) == "0.1"


# --- place_buy_yes ---------------------------------------------------------


def test_buy_crosses_ask_with_slippage_on_tick_0_001_market():
    """The Xi-Iran-meets failure: ask 0.994, tick 0.001. Limit must be > 0.994.

    At price=0.999, gcd(999, 1e5)=1 so shares must be integer multiples of 10
    (smallest cents-clean order is 10 shares = $9.99). Use a $20 budget so a
    valid order fits — this is independent of the price-computation we're testing.
    """
    client = _mock_client(_book(asks=[(0.995, 100), (0.994, 200)], bids=[(0.005, 100)], tick=0.001))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50  # 0.5%
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=20.0, ref_price=0.99)

    assert result is not None
    assert result.get("error") is None
    # ask=0.994, slip=max(0.994*0.005, 0.001)=0.00497, limit=0.99897 → tick 0.999
    assert result["order_price"] == pytest.approx(0.999, abs=1e-9)
    # shares quantized so price*shares is cents-clean (Polymarket maker_amount limit)
    maker_usd = result["order_price"] * result["shares"]
    assert maker_usd * 100 == pytest.approx(round(maker_usd * 100), abs=1e-6)
    # Must be FAK so unmatched portion cancels — never rests
    args, kwargs = client.post_order.call_args
    assert OrderType.FAK in args or kwargs.get("order_type") == OrderType.FAK


def test_buy_crosses_ask_on_tick_0_01_market():
    """Tennis-style market: tick 0.01, ask 0.55. Buffer must lift price above 0.55."""
    client = _mock_client(_book(asks=[(0.56, 100), (0.55, 200)], bids=[(0.45, 100)], tick=0.01))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50  # 0.5%
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=10.0, ref_price=0.50)

    # ask=0.55, slip=max(0.55*0.005, 0.01)=0.01, limit=0.56
    assert result["order_price"] == pytest.approx(0.56, abs=1e-9)
    # price*shares must round to cents (Polymarket maker_amount precision)
    maker_usd = result["order_price"] * result["shares"]
    assert maker_usd * 100 == pytest.approx(round(maker_usd * 100), abs=1e-6)


def test_buy_quantizes_to_cents_clean_maker_on_tiafoe_failure():
    """Regression: Tiafoe vs Pellegrino, ask=0.62, bet=$9, tick=0.01.

    Old code: shares = ceil_cents(9 / 0.63) = 14.29 → maker = 0.63 * 14.29
    = 9.0027 USDC → Polymarket rejected with "maker amount supports max 2
    decimals". Fix: quantize shares to 14 → maker = $8.82 cleanly.
    """
    client = _mock_client(_book(asks=[(0.63, 200), (0.62, 100)], bids=[(0.37, 100)], tick=0.01))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=9.0, ref_price=0.62)

    assert result.get("error") is None
    # ask=0.62, slip=max(0.62*0.005, 0.01)=0.01 → limit 0.63
    assert result["order_price"] == pytest.approx(0.63, abs=1e-9)
    # 9/0.63 = 14.2857 → with gcd(63, 10000)=1, step=10000 → shares must be integer.
    # Largest integer fitting $9 budget: 14 (= $8.82).
    assert result["shares"] == pytest.approx(14.0, abs=1e-9)
    maker_usd = result["order_price"] * result["shares"]
    assert maker_usd == pytest.approx(8.82, abs=1e-9)


def test_buy_skips_when_budget_too_small_for_clob_step():
    """At price 0.999 (coprime to 100), cents-clean orders need 10-share
    multiples = $9.99 minimum. A $5 budget can't produce a valid order; the
    bot must skip rather than send a malformed request to the CLOB.
    """
    client = _mock_client(_book(asks=[(0.998, 100)], bids=[(0.001, 100)], tick=0.001))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=5.0, ref_price=0.99)

    assert result["error"] == "notional_below_clob_step"
    client.post_order.assert_not_called()


def test_buy_uses_one_tick_when_slippage_bps_below_tick():
    """If 0.5% of ask is less than one tick, we still bump the price by one tick."""
    client = _mock_client(_book(asks=[(0.10, 100)], bids=[(0.05, 100)], tick=0.01))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50  # 0.5% of 0.10 = 0.0005, < tick 0.01
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=5.0, ref_price=0.10)

    # ask=0.10, slip=max(0.0005, 0.01)=0.01, limit=0.11
    assert result["order_price"] == pytest.approx(0.11, abs=1e-9)


def test_buy_caps_at_one_tick_below_one():
    """A near-100% market mustn't quote above 1 - tick (the CLOB rejects it)."""
    client = _mock_client(_book(asks=[(0.999, 100)], bids=[(0.001, 100)], tick=0.001))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=20.0, ref_price=0.99)

    # ask=0.999 + slip=0.005 = 1.004, capped at 1 - tick = 0.999
    assert result["order_price"] == pytest.approx(0.999, abs=1e-9)


def test_buy_returns_error_on_empty_book():
    client = _mock_client(_book(asks=[], bids=[], tick=0.01))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=5.0, ref_price=0.50)

    assert result == {"error": "empty_book"}
    client.post_order.assert_not_called()


def test_buy_propagates_book_fetch_error():
    client = MagicMock()
    client.get_order_book.side_effect = RuntimeError("connection reset")

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=5.0, ref_price=0.50)

    assert result is not None
    assert result["error"].startswith("book_fetch_failed:")


def test_buy_invalid_args_returns_none():
    assert place_buy_yes(clob_client=MagicMock(), token_id="", bet_size_usd=5.0, ref_price=0.5) is None
    assert place_buy_yes(clob_client=MagicMock(), token_id="T", bet_size_usd=0, ref_price=0.5) is None


# --- FAK no-fill detection (Batch 4) --------------------------------------


def test_buy_marks_unfilled_when_size_matched_zero():
    """FAK posted but matched 0 shares — caller (scan loop) uses unfilled=True
    to drive a single retry against a fresh book."""
    client = _mock_client(_book(asks=[(0.55, 100)], bids=[(0.45, 100)], tick=0.01))
    client.get_order.return_value = {"size_matched": 0, "price": "0.56"}
    client.get_trades.return_value = []

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=10.0, ref_price=0.50)

    assert result["unfilled"] is True
    # paper-book hygiene: filled_shares falls back to planned shares so a
    # later SELL doesn't see a 0-share position
    assert result["filled_shares"] == result["shares"]


def test_buy_not_unfilled_on_partial_fill():
    """size_matched > 0 → real fill → no retry."""
    client = _mock_client(_book(asks=[(0.55, 100)], bids=[(0.45, 100)], tick=0.01))
    client.get_order.return_value = {"size_matched": "10", "price": "0.56"}
    client.get_trades.return_value = []

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=10.0, ref_price=0.50)

    assert result["unfilled"] is False
    assert result["filled_shares"] == pytest.approx(10.0)


def test_buy_not_unfilled_when_get_order_errors():
    """get_order failure = unknown fill state. Must NOT mark unfilled
    because retrying could double exposure if the original actually filled."""
    client = _mock_client(_book(asks=[(0.55, 100)], bids=[(0.45, 100)], tick=0.01))
    client.get_order.side_effect = RuntimeError("api 503")

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_buy_yes(clob_client=client, token_id="T", bet_size_usd=10.0, ref_price=0.50)

    assert result["unfilled"] is False


# --- place_sell_yes --------------------------------------------------------


def test_sell_crosses_bid_with_slippage():
    """Symmetric SELL: cross the spread by lowering below best bid."""
    client = _mock_client(_book(asks=[(0.55, 100)], bids=[(0.45, 100), (0.50, 100)], tick=0.01))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_sell_yes(clob_client=client, token_id="T", shares=10.0, ref_price=0.55)

    # best_bid=0.50, slip=max(0.50*0.005, 0.01)=0.01, limit=0.49
    assert result["order_price"] == pytest.approx(0.49, abs=1e-9)
    args, kwargs = client.post_order.call_args
    assert OrderType.FAK in args or kwargs.get("order_type") == OrderType.FAK


def test_sell_floors_at_one_tick():
    """A near-zero bid mustn't push the limit below 1 tick (CLOB rejects 0)."""
    client = _mock_client(_book(asks=[(0.99, 100)], bids=[(0.005, 100)], tick=0.001))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_sell_yes(clob_client=client, token_id="T", shares=10.0, ref_price=0.10)

    # best_bid=0.005, slip=max(0.005*0.005, 0.001)=0.001, limit=0.004
    assert result["order_price"] >= 0.001


def test_sell_returns_error_on_empty_book():
    client = _mock_client(_book(asks=[(0.55, 100)], bids=[], tick=0.01))

    with patch("src.tennis.order_placer.CONFIG") as cfg:
        cfg.live_order_slippage_bps = 50
        result = place_sell_yes(clob_client=client, token_id="T", shares=10.0, ref_price=0.55)

    assert result == {"error": "empty_book"}
    client.post_order.assert_not_called()
