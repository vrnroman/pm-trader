"""The news bot's Telegram: only news commands, a menu that matches them,
no copy-bot words anywhere a message can come from."""

import os
import re

import pytest

import src.telegram_bot as tb


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(tb, "send_message", lambda text, parse_mode="HTML", kind=None: out.append((kind, text)) or True)
    return out


def test_menu_matches_the_dispatcher_and_names_are_valid(sent, monkeypatch):
    from src.newsbot import runner
    monkeypatch.setattr(runner, "pnl_text", lambda c="": "PNL")
    monkeypatch.setattr(runner, "news_text", lambda c="": "NEWS")
    monkeypatch.setattr(runner, "status_text", lambda: "STATUS")
    for c in tb.BOT_MENU_COMMANDS:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", c["command"])
        sent.clear()
        tb._handle_command("/" + c["command"])
        assert sent and "Unknown command" not in sent[0][1], c["command"]
    assert {c["command"] for c in tb.BOT_MENU_COMMANDS} == {"pnl", "news", "status", "help"}


def test_copy_bot_commands_are_gone(sent):
    for old in ("/wallets", "/zset", "/live", "/real", "/gate", "/canary", "/setkey"):
        sent.clear()
        tb._handle_command(old)
        assert "Unknown command" in sent[0][1] and "/pnl" in sent[0][1]


def test_owner_text_is_a_source_and_other_chats_are_ignored(monkeypatch, sent):
    got = []
    monkeypatch.setattr(tb, "on_owner_text", lambda text, msg: got.append(text))
    monkeypatch.setattr(tb.CONFIG.__class__, "telegram_chat_id", "42", raising=False)
    object.__setattr__(tb.CONFIG, "telegram_chat_id", "42")
    tb._process_update({"message": {"chat": {"id": 42}, "text": "Kremlin confirms summit"}})
    tb._process_update({"message": {"chat": {"id": 7}, "text": "spam"}})
    assert got == ["Kremlin confirms summit"]


def test_boot_line_says_paper_and_nothing_about_copying():
    t = tb.startup_text()
    assert "News bot started" in t and "Paper only" in t and "not wired" in t
    for word in ("Copy", "Strategy #1", "LIVE"):
        assert word not in t


def test_long_replies_never_split_inside_a_pre_block(monkeypatch):
    parts = []
    monkeypatch.setattr(tb, "send_message", lambda text, parse_mode="HTML", kind=None: parts.append(text) or True)
    body = "\n".join(["x" * 50] * 60) + "\n<pre>\n" + "\n".join(["y" * 50] * 30) + "\n</pre>\nend"
    assert tb.send_long(body, chunk_size=1000)
    for p in parts:
        assert p.count("<pre>") == p.count("</pre>")


def test_no_copy_bot_module_is_left():
    root = os.path.join(os.path.dirname(__file__), "..")
    assert not os.path.exists(os.path.join(root, "src", "copy_trading"))
    src = open(os.path.join(root, "main.py"), encoding="utf-8").read()
    assert "copy_trading" not in src and "telegram_bot.startup_text()" in src


def test_socket_libraries_never_log_below_warning():
    # websockets DEBUG frames were 96% of the bot log on 2026-10-27
    import logging
    import src.logger  # noqa: F401  (configures the levels on import)
    for name in ("websockets", "websockets.client", "telethon", "twscrape", "urllib3", "httpx"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING, name
