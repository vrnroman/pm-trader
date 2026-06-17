"""Telegram command-dispatch + handler tests.

These cover the safety-critical Telegram surface — the user's only
real-time control over the bot. Each test goes through the public
``_handle_command`` entry point so dispatch (the startswith chain),
argument parsing, the CONFIRM-token gate, and state mutation are all
exercised together.

What we mock:
  - ``send_message``: captured into a list so we can assert what the user
    would have seen.
  - The handler callbacks (``on_refresh_clob_client``): set to MagicMock so
    we can confirm they fire without standing up the real subsystems.

We do NOT mock the modules the handlers operate on (``set_private_key``) —
those are pure in-process state changes and testing the real implementation
is the point.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def captured_messages(monkeypatch):
    """Replace telegram_bot.send_message; return the message buffer."""
    from src import telegram_bot
    buf: list[str] = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, **_kw: buf.append(text))
    return buf


@pytest.fixture
def mock_callbacks(monkeypatch):
    """Replace the on_* callbacks so handlers run without real subsystems."""
    from src import telegram_bot
    cbs = MagicMock()
    cbs.on_refresh_clob_client = MagicMock()
    monkeypatch.setattr(telegram_bot, "on_refresh_clob_client", cbs.on_refresh_clob_client)
    return cbs


@pytest.fixture(autouse=True)
def _reset_private_key(monkeypatch):
    """Snapshot/restore the in-memory private key around each test."""
    from src import config
    snap = config._private_key
    yield
    config._private_key = snap


# ------------------------------------------------------------------
# /setkey — second-line kill switch
# ------------------------------------------------------------------

def test_setkey_clear_wipes_key_and_calls_refresh(captured_messages, mock_callbacks):
    from src import config, telegram_bot
    config._private_key = "ab" * 32
    telegram_bot._handle_command("/setkey clear CONFIRM")
    assert config.get_private_key() == ""
    mock_callbacks.on_refresh_clob_client.assert_called_once()


def test_setkey_without_confirm_is_noop(captured_messages, mock_callbacks):
    from src import config, telegram_bot
    config._private_key = "ab" * 32
    telegram_bot._handle_command("/setkey clear")
    assert config.get_private_key() == "ab" * 32  # unchanged
    mock_callbacks.on_refresh_clob_client.assert_not_called()
    assert any("Usage" in m for m in captured_messages)


def test_setkey_invalid_hex_does_not_mutate(captured_messages, mock_callbacks):
    from src import config, telegram_bot
    config._private_key = "ab" * 32
    telegram_bot._handle_command("/setkey nothex CONFIRM")
    assert config.get_private_key() == "ab" * 32  # unchanged
    mock_callbacks.on_refresh_clob_client.assert_not_called()


def test_setkey_replaces_key_with_valid_hex(captured_messages, mock_callbacks):
    from src import config, telegram_bot
    config._private_key = "aa" * 32
    new_key = "bb" * 32
    telegram_bot._handle_command(f"/setkey {new_key} CONFIRM")
    assert config.get_private_key() == new_key
    mock_callbacks.on_refresh_clob_client.assert_called_once()
    # The success message should echo the derived EOA so user can sanity-check.
    assert any("EOA" in m for m in captured_messages)


def test_setkey_with_0x_prefix_normalized(captured_messages, mock_callbacks):
    from src import config, telegram_bot
    new_key = "cc" * 32
    telegram_bot._handle_command(f"/setkey 0x{new_key} CONFIRM")
    # Stored without the 0x prefix.
    assert config.get_private_key() == new_key


# ------------------------------------------------------------------
# /shutdown — last-resort kill switch
# ------------------------------------------------------------------

def test_shutdown_without_confirm_is_noop(captured_messages, mock_callbacks):
    """No CONFIRM token must NOT trigger a process exit."""
    from src import telegram_bot
    with patch("os._exit") as mexit:
        telegram_bot._handle_command("/shutdown")
        # Give the (non-existent) delayed-exit thread a tick to be sure it didn't fire.
        import time
        time.sleep(0.05)
        mexit.assert_not_called()
    assert any("Usage" in m for m in captured_messages)


def test_shutdown_with_confirm_schedules_exit(captured_messages, mock_callbacks):
    from src import telegram_bot
    with patch("os._exit") as mexit, patch("time.sleep"):
        telegram_bot._handle_command("/shutdown CONFIRM")
        # The delayed exit runs in a daemon thread; give it a moment to start.
        import time as _t
        _t.sleep(0.1)
        mexit.assert_called_once_with(0)
    assert any("Shutting down" in m for m in captured_messages)


# ==================================================================
# Full update-path tests (synthesized Telegram getUpdates payloads)
#
# These cover the layers between the Telegram-API and _handle_command:
#   - msg.chat.id extraction + chat-id filter (auth)
#   - msg.text extraction + "/" prefix filter
#   - the try/except wrapper around _handle_command (kill-switch
#     resilience: a handler crash must NOT kill the polling thread)
# A regression in any of these silently breaks the user's only
# real-time control over the bot, so they get their own tests.
# ==================================================================

CHAT_ID = "12345"
WRONG_CHAT_ID = 99999  # tg sends ints; bot stringifies before compare


@pytest.fixture
def configured_chat(monkeypatch):
    from src import telegram_bot
    monkeypatch.setattr(telegram_bot.CONFIG, "telegram_chat_id", CHAT_ID)


def _update(text: str, chat_id=CHAT_ID, update_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id}, "text": text},
    }


def test_update_from_wrong_chat_id_is_ignored(configured_chat, captured_messages, mock_callbacks):
    """A regression in the chat-id filter is the difference between a
    private bot and a public one. Pin it."""
    from src import telegram_bot
    telegram_bot._process_update(_update("/status", chat_id=WRONG_CHAT_ID))
    # No message sent — the command never reached a handler.
    assert captured_messages == []


def test_update_from_correct_chat_id_dispatches(configured_chat, captured_messages, mock_callbacks):
    from src import telegram_bot
    telegram_bot._process_update(_update("/status"))
    # /status always emits a status message.
    assert captured_messages != []


def test_update_with_non_command_text_ignored(configured_chat, captured_messages, mock_callbacks, monkeypatch):
    from src import telegram_bot
    spy = MagicMock()
    monkeypatch.setattr(telegram_bot, "_handle_command", spy)
    telegram_bot._process_update(_update("hello there, not a command"))
    spy.assert_not_called()


def test_update_with_no_message_object_ignored(configured_chat, captured_messages, mock_callbacks):
    from src import telegram_bot
    # Some update types (edited_message, callback_query) won't have ``message``.
    telegram_bot._process_update({"update_id": 5})
    assert captured_messages == []


def test_handler_exception_does_not_kill_polling(configured_chat, captured_messages, monkeypatch):
    """If a command handler raises, the wrapper must catch it and surface
    an error to the user — not let the exception bubble up and tear down
    the polling thread (which would silently break the kill switch)."""
    from src import telegram_bot

    def boom(_text):
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(telegram_bot, "_handle_command", boom)
    # No exception escapes:
    telegram_bot._process_update(_update("/anything"))
    assert any("Error" in m and "handler exploded" in m for m in captured_messages)


def test_update_with_string_chat_id_also_works(configured_chat, captured_messages, mock_callbacks):
    """Telegram sometimes sends chat.id as int, sometimes as str (bot
    libraries vary). The bot stringifies before compare — pin both."""
    from src import telegram_bot
    telegram_bot._process_update(_update("/status", chat_id=int(CHAT_ID)))
    assert captured_messages != []


# ------------------------------------------------------------------
# End-to-end: real Telegram payload → state mutation
# ------------------------------------------------------------------

def test_e2e_setkey_clear(configured_chat, captured_messages, mock_callbacks):
    """{"text":"/setkey clear CONFIRM"} must wipe the in-memory key."""
    from src import config, telegram_bot
    config._private_key = "ab" * 32
    telegram_bot._process_update(_update("/setkey clear CONFIRM"))
    assert config.get_private_key() == ""
    mock_callbacks.on_refresh_clob_client.assert_called_once()


def test_e2e_setkey_clear_without_confirm_no_op(configured_chat, captured_messages, mock_callbacks):
    """The CONFIRM token must be required even when the payload comes
    through the full update path."""
    from src import config, telegram_bot
    config._private_key = "ab" * 32
    telegram_bot._process_update(_update("/setkey clear"))
    assert config.get_private_key() == "ab" * 32  # unchanged
    mock_callbacks.on_refresh_clob_client.assert_not_called()


# ------------------------------------------------------------------
# Bot menu (setMyCommands) parity with the dispatcher
# ------------------------------------------------------------------

def test_bot_menu_command_names_are_valid():
    """Telegram rejects the entire setMyCommands batch if any name fails
    ^[a-z0-9_]{1,32}$. A typo here silently leaves the menu in its prior
    state — which is exactly how /test-live broke things in 86f9d4d.
    """
    import re
    from src import telegram_bot

    pattern = re.compile(r"^[a-z0-9_]{1,32}$")
    for entry in telegram_bot.BOT_MENU_COMMANDS:
        assert pattern.match(entry["command"]), (
            f"invalid Telegram command name: {entry['command']!r}"
        )
        assert 1 <= len(entry["description"]) <= 256


def test_bot_menu_matches_dispatcher():
    """Every command in the popup menu must be handled by ``_handle_command``,
    and every dispatched command (besides aliases) must appear in the menu.
    Catches drift when someone adds a handler but forgets to register it
    (or vice versa)."""
    import inspect
    import re
    from src import telegram_bot

    source = inspect.getsource(telegram_bot._handle_command)
    dispatched = set(re.findall(r'text\.startswith\("/([a-z0-9_-]+)"\)', source))

    # Aliases that intentionally don't get their own menu entry — they
    # share a description with the canonical command. (Empty for now.)
    aliases: set[str] = set()
    dispatched -= aliases

    menu = {entry["command"] for entry in telegram_bot.BOT_MENU_COMMANDS}
    # /start is registered in the menu but dispatched via the /help branch.
    menu_dispatched_via_help = {"start"}

    missing_from_menu = dispatched - menu
    missing_from_dispatch = menu - dispatched - menu_dispatched_via_help

    assert not missing_from_menu, (
        f"commands handled but not in menu: {sorted(missing_from_menu)}"
    )
    assert not missing_from_dispatch, (
        f"commands in menu but not handled: {sorted(missing_from_dispatch)}"
    )
