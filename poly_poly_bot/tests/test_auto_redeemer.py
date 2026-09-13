"""Auto-redeemer realized-P&L persistence.

The redeemer is the only place a copy position is closed, so it must persist
the realized P&L (previously it computed P&L only for a one-off Telegram
notification and discarded it, leaving /pnl with no realized data to report).
We mock web3 + the positions fetch so the test runs without a chain or network.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.fixture
def redeem_env(monkeypatch, tmp_path):
    from src.config import CONFIG
    monkeypatch.setattr(CONFIG, "data_dir", str(tmp_path))
    monkeypatch.setattr(CONFIG, "proxy_wallet", "0xproxy")
    return tmp_path


def _mock_web3():
    """A Web3 stand-in whose call chain yields a successful redemption.

    The mocked signer address is the SAME address as the configured proxy:
    `redeemPositions` redeems for msg.sender, so redemption is only possible
    at all when the signer is the holder, and the redeemer now refuses
    outright when it is not (run s-yr3unh).
    """
    w3 = MagicMock()
    w3.eth.fee_history.return_value = {"baseFeePerGas": [100]}
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.send_raw_transaction.return_value = MagicMock()
    w3.eth.wait_for_transaction_receipt.return_value = {"status": 1}
    w3.eth.account.from_key.return_value.address = "0xproxy"

    Web3 = MagicMock()
    Web3.return_value = w3
    Web3.to_checksum_address.side_effect = lambda a: a
    Web3.to_bytes.return_value = b""
    Web3.to_wei.return_value = 1
    return Web3


def test_successful_redemption_persists_realized_pnl(redeem_env):
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl

    winning_position = {
        "conditionId": "0xcond",
        "tokenId": "tok-1",
        "shares": 100.0,
        "avgPrice": 0.40,
        "curPrice": 1.0,   # > 0.5 -> won
        "title": "Will A happen?",
        "negRisk": False,
        "outcomeCount": 2,
    }

    with patch.object(auto_redeemer, "Web3", _mock_web3()), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions",
                      AsyncMock(return_value=[winning_position])):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))

    assert result.count == 1

    rows = s1pnl.load_realized()
    assert len(rows) == 1
    row = rows[0]
    assert row["condition_id"] == "0xcond"
    assert row["cost_basis"] == pytest.approx(40.0)
    assert row["returned"] == pytest.approx(100.0)
    assert row["pnl"] == pytest.approx(60.0)
    assert row["won"] is True


def test_losing_redemption_records_negative_pnl(redeem_env):
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl

    losing_position = {
        "conditionId": "0xcond2",
        "tokenId": "tok-2",
        "shares": 50.0,
        "avgPrice": 0.60,
        "curPrice": 0.0,   # < 0.5 -> lost
        "title": "Will B happen?",
        "negRisk": False,
        "outcomeCount": 2,
    }

    with patch.object(auto_redeemer, "Web3", _mock_web3()), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions",
                      AsyncMock(return_value=[losing_position])):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))

    assert result.count == 1
    rows = s1pnl.load_realized()
    assert len(rows) == 1
    assert rows[0]["pnl"] == pytest.approx(-30.0)
    assert rows[0]["won"] is False


def test_a_refunded_market_books_the_half_payout_not_a_total_loss(redeem_env):
    """A cancelled Polymarket market resolves 50/50: redeemPositions pays
    $0.50 per share for EITHER outcome. curPrice is 0.5 there, and the old
    `won = cur_price > 0.5; returned = shares if won else 0` booked the
    refund as a realized loss of the entire cost basis."""
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl

    refunded_position = {
        "conditionId": "0xcond3",
        "tokenId": "tok-3",
        "shares": 80.0,
        "avgPrice": 0.60,
        "curPrice": 0.5,   # cancelled/refunded: the CTF pays half per share
        "title": "Will C happen?",
        "negRisk": False,
        "outcomeCount": 2,
    }

    with patch.object(auto_redeemer, "Web3", _mock_web3()), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions",
                      AsyncMock(return_value=[refunded_position])):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))

    assert result.count == 1
    rows = s1pnl.load_realized()
    assert len(rows) == 1
    row = rows[0]
    assert row["cost_basis"] == pytest.approx(48.0)
    assert row["returned"] == pytest.approx(40.0), "half of 80 shares, not zero"
    assert row["pnl"] == pytest.approx(-8.0)
    assert row["won"] is False


def test_a_winner_reported_below_one_still_books_the_full_payout(redeem_env):
    """The refund band must not narrow the win band: the API may report a
    resolved winner at a last-trade price short of 1.0, and `>= 0.99` would
    have turned that win into a booked total loss — a worse error than the
    one the refund band fixes. Anything above the refund band is a win."""
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl

    winner = {
        "conditionId": "0xcond4",
        "tokenId": "tok-4",
        "shares": 50.0,
        "avgPrice": 0.40,
        "curPrice": 0.97,
        "title": "Will D happen?",
        "negRisk": False,
        "outcomeCount": 2,
    }

    with patch.object(auto_redeemer, "Web3", _mock_web3()), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions",
                      AsyncMock(return_value=[winner])):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))

    assert result.count == 1
    (row,) = s1pnl.load_realized()
    assert row["returned"] == pytest.approx(50.0)
    assert row["pnl"] == pytest.approx(30.0)
    assert row["won"] is True


def test_negrisk_position_skipped_and_not_recorded(redeem_env):
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl

    neg_risk = {
        "conditionId": "0xcond3",
        "tokenId": "tok-3",
        "shares": 10.0,
        "avgPrice": 0.5,
        "curPrice": 1.0,
        "title": "Neg risk market",
        "negRisk": True,
        "outcomeCount": 2,
    }

    with patch.object(auto_redeemer, "Web3", _mock_web3()), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions",
                      AsyncMock(return_value=[neg_risk])):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))

    assert result.count == 0
    assert s1pnl.load_realized() == []


# ---- issue #32: resolved positions this bot does not redeem are booked from the API ----

def _inventory_with(monkeypatch, positions: dict):
    from src.copy_trading import inventory
    monkeypatch.setattr(inventory, "_positions", positions)
    monkeypatch.setattr(inventory, "_save_inventory", lambda: None)
    return inventory


def _redeemable(token, cond, shares, avg, cur, neg_risk=False, title="Will X?"):
    return {"conditionId": cond, "tokenId": token, "shares": shares, "avgPrice": avg,
            "curPrice": cur, "title": title, "negRisk": neg_risk, "outcomeCount": 2,
            "currentValue": shares * cur}


def test_a_signer_that_is_not_the_proxy_books_its_own_copies_from_the_api(redeem_env, monkeypatch):
    """Production: the bot signs as a different address, sends no redeem, and
    Polymarket's own claim pays the wallet; nothing ever reached the realized
    ledger. The copies this bot made (attributed at buy time) are booked from
    the API's resolution; the legacy tickets with no attribution are not."""
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl
    inv = _inventory_with(monkeypatch, {
        "tok-win": {"shares": 20.0, "avg_price": 0.4, "market": "Will X?", "market_key": "0xcw",
                    "tier": "1a", "trader_address": "0xWALLET"},
        "tok-legacy": {"shares": 970.0, "avg_price": 0.26, "market": "", "market_key": "0xcl",
                       "tier": "", "trader_address": ""},
    })
    web3 = _mock_web3()
    web3.return_value.eth.account.from_key.return_value.address = "0xsomeoneelse"
    notes: list = []
    rows = [_redeemable("tok-win", "0xcw", 20.0, 0.4, 1.0),
            _redeemable("tok-legacy", "0xcl", 970.0, 0.26, 0.0)]
    with patch.object(auto_redeemer, "Web3", web3), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions", AsyncMock(return_value=rows)):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32, notify=notes.append))
    assert result.count == 0, "nothing sent on-chain"
    assert result.settled == 1 and result.settled_details[0].returned == 20.0
    web3.return_value.eth.send_raw_transaction.assert_not_called()
    (row,) = s1pnl.load_realized()
    assert row["token_id"] == "tok-win" and row["source"] == "redeemer" and row["settlement"] == "api"
    assert row["returned"] == 20.0 and row["pnl"] == pytest.approx(12.0) and row["won"] is True
    assert row["tier"] == "1a" and row["trader_address"] == "0xWALLET"
    assert row["redeemed_onchain"] is False
    assert "tok-win" not in inv._positions and "tok-legacy" in inv._positions
    assert notes and "settled" in notes[0] and "+12.00" in notes[0]


def test_a_settled_position_is_booked_once(redeem_env, monkeypatch):
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl
    _inventory_with(monkeypatch, {
        "tok-a": {"shares": 10.0, "avg_price": 0.5, "market": "m", "market_key": "0xca",
                  "tier": "1b", "trader_address": "0xW"}})
    web3 = _mock_web3()
    web3.return_value.eth.account.from_key.return_value.address = "0xsomeoneelse"
    rows = [_redeemable("tok-a", "0xca", 10.0, 0.5, 0.0)]
    with patch.object(auto_redeemer, "Web3", web3), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions", AsyncMock(return_value=rows)):
        first = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))
        # the inventory sync re-adds an API row; still booked once
        from src.copy_trading import inventory
        inventory._positions["tok-a"] = {"shares": 10.0, "avg_price": 0.5, "tier": "1b",
                                         "trader_address": "0xW", "market_key": "0xca", "market": "m"}
        second = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))
    assert first.settled == 1 and second.settled == 0
    assert len(s1pnl.load_realized()) == 1
    assert s1pnl.load_realized()[0]["pnl"] == pytest.approx(-5.0)


def test_a_neg_risk_winner_is_booked_from_the_api_not_sent_to_the_ctf(redeem_env, monkeypatch):
    """The signer IS the proxy here, so plain positions go on-chain; the
    neg-risk one is not sent (a different adapter) but no longer vanishes
    from the ledger either."""
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl
    _inventory_with(monkeypatch, {
        "tok-nr": {"shares": 30.0, "avg_price": 0.3, "market": "NR?", "market_key": "0xnr",
                   "tier": "1a", "trader_address": "0xW"}})
    web3 = _mock_web3()
    rows = [_redeemable("tok-nr", "0xnr", 30.0, 0.3, 1.0, neg_risk=True, title="NR?")]
    with patch.object(auto_redeemer, "Web3", web3), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions", AsyncMock(return_value=rows)):
        result = _run(auto_redeemer.check_and_redeem_positions("aa" * 32))
    assert result.count == 0 and result.settled == 1
    web3.return_value.eth.send_raw_transaction.assert_not_called()
    (row,) = s1pnl.load_realized()
    assert row["neg_risk"] is True and row["returned"] == 30.0 and row["pnl"] == pytest.approx(21.0)


def test_a_refunded_position_settles_at_half(redeem_env, monkeypatch):
    from src.copy_trading import auto_redeemer
    from src.copy_trading import pnl as s1pnl
    _inventory_with(monkeypatch, {
        "tok-r": {"shares": 80.0, "avg_price": 0.6, "market": "R?", "market_key": "0xr",
                  "tier": "1a", "trader_address": "0xW"}})
    web3 = _mock_web3()
    web3.return_value.eth.account.from_key.return_value.address = "0xsomeoneelse"
    rows = [_redeemable("tok-r", "0xr", 80.0, 0.6, 0.5)]
    with patch.object(auto_redeemer, "Web3", web3), \
         patch.object(auto_redeemer, "_fetch_redeemable_positions", AsyncMock(return_value=rows)):
        _run(auto_redeemer.check_and_redeem_positions("aa" * 32))
    (row,) = s1pnl.load_realized()
    assert row["returned"] == 40.0 and row["refunded"] is True and row["won"] is False
