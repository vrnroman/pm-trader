"""Tests for the one-tap Telegram promote flow."""

from __future__ import annotations

import pytest

from src import telegram_bot
from src.copy_trading import promotion_state as ps

WALLET = "0x" + "a" * 40


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMOTED_WALLETS_STORE", str(tmp_path / "p.json"))
    monkeypatch.setenv("PROMOTION_OFFERS_STORE", str(tmp_path / "o.json"))
    ps.clear_cache()
    yield
    ps.clear_cache()


def test_callback_promote_adds_to_store(stores):
    toast, edited = telegram_bot._handle_callback(f"promo:{WALLET}")
    assert "Promoted" in toast
    assert ps.promoted_tier_of(WALLET) == "1b"
    assert ps.offer_status(WALLET) == "accepted"
    assert WALLET in edited


def test_callback_dismiss_records(stores):
    toast, _ = telegram_bot._handle_callback(f"dism:{WALLET}")
    assert toast == "Dismissed"
    assert ps.offer_status(WALLET) == "dismissed"
    assert ps.promoted_wallets() == []


def test_callback_unknown_action():
    toast, edited = telegram_bot._handle_callback("garbage:xyz")
    assert edited is None


def test_promote_command_full_address(stores, monkeypatch):
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
    telegram_bot._handle_promote(f"/promote {WALLET}")
    assert ps.promoted_tier_of(WALLET) == "1b"


def test_promote_command_prefix_resolves_offer(stores, monkeypatch):
    ps.record_offer(WALLET, status="offered")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
    telegram_bot._handle_promote("/promote 0xaaaa")     # unique prefix
    assert ps.promoted_tier_of(WALLET) == "1b"


def test_promote_command_ambiguous_prefix_no_op(stores, monkeypatch):
    ps.record_offer("0x" + "a" * 40, status="offered")
    ps.record_offer("0x" + "a" * 39 + "b", status="offered")  # same "0xaaa…" prefix
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda *a, **k: sent.append(a))
    telegram_bot._handle_promote("/promote 0xaaa")
    assert ps.promoted_wallets() == []                  # ambiguous -> nothing promoted


def test_send_promotion_offer_builds_buttons(monkeypatch):
    captured = {}

    def _fake(text, reply_markup=None, **k):
        captured["text"] = text
        captured["rm"] = reply_markup
        return True

    monkeypatch.setattr(telegram_bot, "send_message", _fake)
    ok = telegram_bot.send_promotion_offer(WALLET, 15, 0.2, 300.0, "1b")
    assert ok is True
    row = captured["rm"]["inline_keyboard"][0]
    assert row[0]["callback_data"] == f"promo:{WALLET}"
    assert row[1]["callback_data"] == f"dism:{WALLET}"
    assert WALLET in captured["text"]


def test_callback_wrong_chat_ignored(stores, monkeypatch):
    monkeypatch.setattr(telegram_bot.CONFIG, "telegram_chat_id", "111", raising=False)
    telegram_bot._process_callback({
        "id": "1", "data": f"promo:{WALLET}",
        "message": {"chat": {"id": "999"}, "message_id": 5},
    })
    assert ps.promoted_wallets() == []                  # foreign chat -> no effect
