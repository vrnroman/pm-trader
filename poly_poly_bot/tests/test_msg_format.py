"""The phone grammar (owner, 2026-10-10: "what did we bet, etc, just make
everything more readable"): every deal message leads with the money, then
the market, then the pick, then plain numbers."""
from __future__ import annotations

import asyncio

from src.config import CONFIG
from src.copy_trading import msg_format as mf
from src.copy_trading import telegram_notifier as tn


def test_numbers_read_like_money():
    assert mf.cents(0.45) == "45¢" and mf.cents(0.995) == "99.5¢" and mf.cents(None) == "?"
    assert mf.usd(6.4) == "$6.40" and mf.usd(1234.5) == "$1,234"
    assert mf.signed_usd(7.8) == "+$7.80" and mf.signed_usd(-6.4) == "-$6.40" and mf.signed_usd(0) == "$0.00"
    assert mf.shares(14.0) == "14" and mf.shares(14.22) == "14.22"
    assert mf.wallet("0x5213eb85aaaaaaaaaaaaaaaaaaaaaaaaaaaa1234") == "0x5213…1234"
    assert mf.title_line("") == "<i>(market name unknown)</i>" and "&lt;b&gt;" in mf.title_line("<b>")
    assert mf.join("a", "", "b") == "a\nb"


def _capture(monkeypatch, live=True):
    sent: list = []

    async def cap(text, kind="deal"):
        sent.append(text)
        return True
    monkeypatch.setattr(tn, "_send_message", cap)
    monkeypatch.setattr(CONFIG, "preview_mode", not live)
    return sent


def test_a_placed_bet_says_stake_pick_price_payout_and_whom_we_copy(monkeypatch):
    sent = _capture(monkeypatch)
    asyncio.run(tn.TelegramNotifier().trade_placed(
        "Shanghai: Djokovic vs Fritz", "BUY", 6.40, 0.45, outcome="Djokovic",
        trader="0x5213eb85aaaaaaaaaaaaaaaaaaaaaaaaaaaa1234", their_price=0.44))
    assert sent[0] == ("🟢 [LIVE] <b>Bet placed: $6.40</b>\n<b>Shanghai: Djokovic vs Fritz</b>\n"
                       "Pick: <b>Djokovic</b>\nPrice 45¢, about 14.22 shares; pays about $14.22 if it wins\n"
                       "Copying 0x5213…1234 (they paid 44¢)")


def test_a_sell_a_failure_and_an_unfilled_order_read_plainly(monkeypatch):
    sent = _capture(monkeypatch)
    n = tn.TelegramNotifier()
    asyncio.run(n.trade_placed("M", "SELL", 8.52, 0.6, outcome="Yes", trader="0xabcdef0123456789abcd",
                               their_price=0.61))
    asyncio.run(n.trade_failed("M", "exchange refused (HTTP 400): not enough balance", outcome="Yes"))
    asyncio.run(n.trade_unfilled("M", outcome="Yes"))
    assert sent[0].startswith("🟠 [LIVE] <b>Selling: about $8.52</b>") and "Following 0xabcd…abcd (they sold at 61¢) out of this bet" in sent[0]
    assert sent[1] == "🔴 [LIVE] <b>Bet NOT placed</b>\n<b>M</b>\nPick: <b>Yes</b>\nWhy: exchange refused (HTTP 400): not enough balance"
    assert sent[2].startswith("⚪ [LIVE] <b>Bet not filled, cancelled</b>") and "No money spent." in sent[2]
    for t in sent:
        assert "—" not in t and "–" not in t
