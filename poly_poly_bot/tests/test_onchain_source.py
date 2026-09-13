"""On-chain trade detection: the stamped side is the TRACKED WALLET's side.

OrderFilled carries maker/taker asset ids and amounts. makerAssetId == 0 means
the MAKER is paying USDC (buying outcome tokens) and the taker is selling. The
old code stamped the maker's side on the DetectedTrade regardless of which
role the tracked wallet played — a tracked taker hitting a resting bid was
mirrored as a BUY of the thing it had just SOLD.
"""

from __future__ import annotations

import time

from src.copy_trading.onchain_source import OnchainSource, _determine_side, _tracked_side, _trade_legs

TRACKED = "0xAAAA00000000000000000000000000000000aaAA"
OTHER = "0xBBBB00000000000000000000000000000000bbBB"


class _Event:
    def __init__(self, maker, taker, maker_asset_id, taker_asset_id,
                 maker_amount, taker_amount):
        self._d = {
            "args": {
                "maker": maker,
                "taker": taker,
                "makerAssetId": maker_asset_id,
                "takerAssetId": taker_asset_id,
                "makerAmountFilled": maker_amount,
                "takerAmountFilled": taker_amount,
            },
            "transactionHash": type("H", (), {"hex": lambda self: "0xtx"})(),
            "blockNumber": 1,
        }

    def __getitem__(self, k):
        return self._d[k]


def _source():
    s = OnchainSource()
    s._tracked_addresses = {TRACKED.lower()}
    s._get_block_timestamp = lambda n: int(time.time())
    return s


def test_determine_side_is_the_makers_side():
    """makerAssetId == 0 → the maker pays USDC → the MAKER buys."""
    assert _determine_side(0, 123) == "BUY"
    assert _determine_side(123, 0) == "SELL"


def test_tracked_side_flips_with_the_role():
    assert _tracked_side(0, tracked_is_maker=True) == "BUY"
    assert _tracked_side(0, tracked_is_maker=False) == "SELL"
    assert _tracked_side(123, tracked_is_maker=True) == "SELL"
    assert _tracked_side(123, tracked_is_maker=False) == "BUY"


def test_legs_come_from_the_asset_ids_not_the_side():
    # Maker pays 100 USDC for 200 shares.
    assert _trade_legs(0, 123, 100, 200) == ("123", 100, 200)
    # Taker pays 100 USDC for 200 shares.
    assert _trade_legs(123, 0, 200, 100) == ("123", 100, 200)


def test_a_tracked_taker_selling_is_a_sell_not_a_buy():
    """The bug: this exact event was stamped BUY. The resting maker is the
    USDC side (a buyer), so the tracked taker is SELLING into it."""
    ev = _Event(maker=OTHER, taker=TRACKED, maker_asset_id=0, taker_asset_id=123,
                maker_amount=100_000_000, taker_amount=200_000_000)
    trades = _source()._process_events([ev], "ctf")
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "SELL"
    assert t.token_id == "123"
    assert t.size == 100.0          # the USDC leg, whichever side holds it
    assert abs(t.price - 0.5) < 1e-9


def test_a_tracked_taker_buying_is_a_buy():
    """Taker pays USDC (takerAssetId == 0) → the tracked wallet buys."""
    ev = _Event(maker=OTHER, taker=TRACKED, maker_asset_id=123, taker_asset_id=0,
                maker_amount=200_000_000, taker_amount=100_000_000)
    trades = _source()._process_events([ev], "ctf")
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "BUY"
    assert t.token_id == "123"
    assert t.size == 100.0
    assert abs(t.price - 0.5) < 1e-9


def test_a_tracked_maker_still_reads_right():
    ev = _Event(maker=TRACKED, taker=OTHER, maker_asset_id=0, taker_asset_id=123,
                maker_amount=100_000_000, taker_amount=200_000_000)
    (t,) = _source()._process_events([ev], "ctf")
    assert t.side == "BUY" and t.token_id == "123" and t.size == 100.0
