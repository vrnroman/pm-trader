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


# --------------------------------------------------------------------------- #
# Two clocks (s-qbzbrw): one id with the api, set Z tracked, shadow first
# --------------------------------------------------------------------------- #

def test_the_chain_id_matches_the_api_id_for_the_same_fill():
    """hexbytes 2 / web3 8 hand back hex() WITHOUT 0x; the api has it. Before
    the normaliser the same fill had two ids and hybrid would copy it twice."""
    from src.copy_trading.onchain_source import _canonical_trade_id as chain_id
    from src.copy_trading.trade_monitor import _canonical_trade_id as api_id
    class H:
        def hex(self):
            return "deadbeef"
    assert chain_id(H(), "55", "BUY") == api_id("0xDEADBEEF", "55", "BUY") == "0xdeadbeef-55-BUY"


def test_processed_events_carry_the_normalised_id():
    s = _source()
    trades = s._process_events([_Event(TRACKED, OTHER, 0, 123, 500_000, 1_000_000)], "CTF")
    assert len(trades) == 1 and trades[0].id.startswith("0x") and trades[0].id.endswith("-123-BUY")


def test_tracked_set_is_set_z_refreshed_each_poll(monkeypatch):
    from src.copy_trading import zset
    from src.config import CONFIG
    monkeypatch.setattr(CONFIG, "user_addresses", ["0xSTATIC00000000000000000000000000000000ff"])
    monkeypatch.setattr(zset, "wallets", lambda: ["0xZZZZ00000000000000000000000000000000zzZZ"])
    s = OnchainSource()
    s._refresh_tracked()
    assert s._tracked_addresses == {"0xstatic00000000000000000000000000000000ff", "0xzzzz00000000000000000000000000000000zzzz"}
    monkeypatch.setattr(zset, "wallets", lambda: [])
    s._refresh_tracked()
    assert s._tracked_addresses == {"0xstatic00000000000000000000000000000000ff"}, "an eviction takes effect next pass"
    def boom():
        raise OSError("disk")
    monkeypatch.setattr(zset, "wallets", boom)
    prev = set(s._tracked_addresses)
    s._refresh_tracked()
    assert s._tracked_addresses == prev, "an unreadable Z keeps the last list, never an empty one"


def test_shadow_mode_stamps_the_clock_and_never_enqueues(tmp_path, monkeypatch):
    """The poll body, driven directly: with the chain a shadow, a tracked fill
    lands in the two-clocks rows and nowhere near the queue."""
    import asyncio
    from src.config import CONFIG
    from src.copy_trading import two_clocks, trade_queue, trade_store
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(two_clocks.CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(two_clocks, "_FORCE", "")
    enq: list = []
    monkeypatch.setattr(trade_queue, "enqueue_trade", lambda q: enq.append(q))
    monkeypatch.setattr(trade_store, "is_seen_trade", lambda tid: False)
    monkeypatch.setattr(trade_store, "is_max_retries", lambda tid: False)

    s = _source()
    s._running = True
    calls = {"n": 0}

    class _Eth:
        block_number = 10
        def get_block(self, n):
            return {"timestamp": int(time.time())}

    class _W3:
        eth = _Eth()
    s._w3 = _W3()
    monkeypatch.setattr("src.copy_trading.onchain_source._load_cursor", lambda: 5)
    monkeypatch.setattr("src.copy_trading.onchain_source._save_cursor", lambda b: None)
    monkeypatch.setattr(s, "_refresh_tracked", lambda: None)

    def fetch(from_block, to_block):
        calls["n"] += 1
        if calls["n"] > 1:
            s._running = False
            return []
        return s._process_events([_Event(TRACKED, OTHER, 0, 123, 500_000, 1_000_000)], "CTF")
    monkeypatch.setattr(s, "_fetch_events_range", fetch)
    monkeypatch.setattr("src.copy_trading.onchain_source.POLL_INTERVAL_S", 0.0)
    monkeypatch.setattr("src.copy_trading.trade_store.record_poll_ok", lambda: None)

    asyncio.run(s.start())
    rows = two_clocks.load_rows()
    assert len(rows) == 1 and rows[0]["source"] == "onchain" and rows[0]["id"].endswith("-123-BUY")
    assert enq == [], "a shadow stamps, it does not copy"

    # ...and once primary, the same fill is enqueued with source=onchain
    two_clocks.set_primary({"test": True})
    s._running = True
    calls["n"] = 0
    asyncio.run(s.start())
    assert len(enq) == 1 and enq[0].source == "onchain" and enq[0].trade.id.endswith("-123-BUY")


def test_events_are_read_with_the_web3_7_keyword_names():
    """web3 8 (deployed) rejects create_filter(fromBlock=...); the read goes
    through get_logs(from_block=..., to_block=...). A fake contract that only
    accepts the new names is the mutation check."""
    s = _source()
    seen = {}

    class _Ev:
        def get_logs(self, *, from_block, to_block):
            seen["range"] = (from_block, to_block)
            return [_Event(TRACKED, OTHER, 0, 123, 500_000, 1_000_000)]

        def create_filter(self, **kw):
            raise AssertionError("create_filter is the web3 6 API; get_logs is the read")

    class _Events:
        OrderFilled = _Ev()

    class _Contract:
        events = _Events()

    s._ctf_contract = _Contract()
    s._neg_risk_contract = _Contract()
    trades = s._fetch_events_range(100, 108)
    assert seen["range"] == (100, 108)
    assert len(trades) == 2 and all(t.id.endswith("-123-BUY") for t in trades)


# --------------------------------------------------------------------------- #
# The v2 exchanges (s-qbzbrw, 2026-09-22): the ABI is the live one
# --------------------------------------------------------------------------- #

def test_the_order_filled_abi_is_the_v2_event_the_chain_actually_emits():
    """Measured on the VM 2026-09-22: every OrderFilled log on the v2
    exchanges carries topic0 0xd543adfd...; the hand-written fragment hashed
    to 0x0879b055..., a signature no contract emits, so the reader decoded
    nothing for as long as it existed."""
    from web3 import Web3
    from src.constants import ORDER_FILLED_ABI, ORDER_FILLED_ABI_V1
    ev = ORDER_FILLED_ABI[0]
    sig = "OrderFilled(" + ",".join(i["type"] for i in ev["inputs"]) + ")"
    assert Web3.keccak(text=sig).hex().lstrip("0x").startswith("d543adfd945773f1")
    assert [i["name"] for i in ev["inputs"]][:5] == ["orderHash", "maker", "taker", "side", "tokenId"]
    v1 = ORDER_FILLED_ABI_V1[0]
    sig1 = "OrderFilled(" + ",".join(i["type"] for i in v1["inputs"]) + ")"
    assert Web3.keccak(text=sig1).hex().lstrip("0x").startswith("d0a08e8c493f9c94")


class _EventV2(_Event):
    """A v2-shaped log: side (the maker order's), one tokenId, amounts."""
    def __init__(self, maker, taker, side, token_id, maker_amount, taker_amount, tx="0xtx"):
        self._d = {
            "args": {"maker": maker, "taker": taker, "side": side, "tokenId": token_id,
                     "makerAmountFilled": maker_amount, "takerAmountFilled": taker_amount,
                     "fee": 0, "builder": b"\x00" * 32, "metadata": b"\x00" * 32},
            "transactionHash": type("H", (), {"hex": lambda self: tx.lstrip("0x")})(),
            "blockNumber": 1,
        }


def test_a_v2_maker_buy_by_the_tracked_wallet_is_a_buy_of_that_token():
    s = _source()
    trades = s._process_events([_EventV2(TRACKED, OTHER, 0, 777, 500_000, 1_000_000)], "CTF")
    assert len(trades) == 1
    t = trades[0]
    assert (t.side, t.token_id, t.size, t.price) == ("BUY", "777", 0.5, 0.5)
    assert t.trader_address == TRACKED.lower() and t.id == "0xtx-777-BUY"


def test_a_v2_maker_sell_taken_by_the_tracked_wallet_is_a_buy():
    """The tracked wallet lifts a resting SELL: the maker gives tokens, the
    tracked taker gives USDC and receives the token."""
    s = _source()
    trades = s._process_events([_EventV2(OTHER, TRACKED, 1, 777, 1_000_000, 500_000)], "CTF")
    assert len(trades) == 1
    t = trades[0]
    assert (t.side, t.token_id, t.size, t.price) == ("BUY", "777", 0.5, 0.5)


def test_a_v2_maker_sell_by_the_tracked_wallet_is_a_sell():
    s = _source()
    trades = s._process_events([_EventV2(TRACKED, OTHER, 1, 777, 1_000_000, 500_000)], "CTF")
    assert len(trades) == 1 and trades[0].side == "SELL" and trades[0].token_id == "777"


def test_v1_shaped_logs_still_decode_through_the_same_rule():
    from src.copy_trading.onchain_source import _legs_from_args
    assert _legs_from_args({"makerAssetId": 0, "takerAssetId": 9, "makerAmountFilled": 5, "takerAmountFilled": 10}) == (0, 9, 5, 10)
    assert _legs_from_args({"side": 0, "tokenId": 9, "makerAmountFilled": 5, "takerAmountFilled": 10}) == (0, 9, 5, 10)
    assert _legs_from_args({"side": 1, "tokenId": 9, "makerAmountFilled": 10, "takerAmountFilled": 5}) == (9, 0, 10, 5)
