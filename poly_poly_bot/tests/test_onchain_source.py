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
OTHER2 = "0xCCCC00000000000000000000000000000000ccCC"
EXCHANGE = "0xEEEE00000000000000000000000000000000eeEE"


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


def test_a_tracked_taker_order_is_one_trade_read_from_its_own_leg():
    """Trading.sol emits, in one matchOrders tx, an OrderFilled per maker
    leg (taker = the tracked wallet) AND one for the wallet's own order
    (maker = the tracked wallet, taker = the exchange). Before: the maker
    legs became inverted phantom trades beside the real one. Now: one trade,
    the own leg's side and the whole fill, the maker legs dropped."""
    evs = [
        _Event(maker=OTHER, taker=TRACKED, maker_asset_id=0, taker_asset_id=123,
               maker_amount=60_000_000, taker_amount=120_000_000),
        _Event(maker=OTHER2, taker=TRACKED, maker_asset_id=0, taker_asset_id=123,
               maker_amount=40_000_000, taker_amount=80_000_000),
        _Event(maker=TRACKED, taker=EXCHANGE, maker_asset_id=123, taker_asset_id=0,
               maker_amount=200_000_000, taker_amount=100_000_000),
    ]
    trades = _source()._process_events(evs, "ctf")
    assert len(trades) == 1
    (t,) = trades
    assert t.side == "SELL" and t.token_id == "123"
    assert t.size == 100.0 and abs(t.price - 0.5) < 1e-9


def test_a_mint_match_reads_the_tracked_wallets_own_token_and_side():
    """MINT match: the tracked wallet buys YES; the maker leg is another
    wallet buying NO. Read from the maker leg the trade would be a SELL of
    NO — a token the wallet never touched. The own leg wins."""
    evs = [
        _Event(maker=OTHER, taker=TRACKED, maker_asset_id=0, taker_asset_id=456,
               maker_amount=50_000_000, taker_amount=100_000_000),
        _Event(maker=TRACKED, taker=EXCHANGE, maker_asset_id=0, taker_asset_id=123,
               maker_amount=50_000_000, taker_amount=100_000_000),
    ]
    (t,) = _source()._process_events(evs, "ctf")
    assert t.side == "BUY" and t.token_id == "123" and t.size == 50.0


def test_maker_legs_without_an_own_leg_are_summed_into_one_order():
    """Defensive: the contract always emits the own leg, but if a batch ever
    carried only the maker legs they are one order, not two half-orders."""
    evs = [
        _Event(maker=OTHER, taker=TRACKED, maker_asset_id=0, taker_asset_id=123,
               maker_amount=60_000_000, taker_amount=120_000_000),
        _Event(maker=OTHER2, taker=TRACKED, maker_asset_id=0, taker_asset_id=123,
               maker_amount=40_000_000, taker_amount=80_000_000),
    ]
    (t,) = _source()._process_events(evs, "ctf")
    assert t.side == "SELL" and t.size == 100.0 and abs(t.price - 0.5) < 1e-9
