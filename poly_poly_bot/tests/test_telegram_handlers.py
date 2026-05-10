"""Telegram command-dispatch + handler tests.

These cover the safety-critical Telegram surface — the user's only
real-time control over the bot. Each test goes through the public
``_handle_command`` entry point so dispatch (the startswith chain),
argument parsing, the CONFIRM-token gate, and state mutation are all
exercised together.

What we mock:
  - ``send_message``: captured into a list so we can assert what the user
    would have seen.
  - The handler callbacks (``on_tennis_scan_request``,
    ``on_refresh_clob_client``): set to MagicMock so we can confirm they
    fire without standing up the real subsystems.

We do NOT mock the modules the handlers operate on (``runtime_state``,
``set_private_key``) — those are pure in-process state changes and
testing the real implementation is the point.
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
    cbs.on_tennis_scan_request = MagicMock(return_value=[])
    cbs.on_refresh_clob_client = MagicMock()
    cbs.on_predict_request = MagicMock(return_value=[])
    monkeypatch.setattr(telegram_bot, "on_tennis_scan_request", cbs.on_tennis_scan_request)
    monkeypatch.setattr(telegram_bot, "on_refresh_clob_client", cbs.on_refresh_clob_client)
    monkeypatch.setattr(telegram_bot, "on_predict_request", cbs.on_predict_request)
    return cbs


@pytest.fixture(autouse=True)
def _reset_runtime_state(tmp_path, monkeypatch):
    """Point runtime_state at a tmp file and reset its in-memory cache."""
    from src import runtime_state
    monkeypatch.setattr(runtime_state, "_path", lambda: str(tmp_path / "rs.json"))
    runtime_state._state = None
    yield
    runtime_state._state = None


@pytest.fixture(autouse=True)
def _reset_private_key(monkeypatch):
    """Snapshot/restore the in-memory private key around each test."""
    from src import config
    snap = config._private_key
    yield
    config._private_key = snap


# ------------------------------------------------------------------
# Mode toggle (the most user-facing safety lever)
# ------------------------------------------------------------------

def test_preview_3_switches_to_preview(captured_messages, mock_callbacks):
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, False)  # start in live
    telegram_bot._handle_command("/preview 3")
    assert runtime_state.is_preview(3) is True
    assert any("PREVIEW" in m for m in captured_messages)


def test_live_3_requires_confirm(captured_messages, mock_callbacks):
    """Without CONFIRM, the strategy must NOT flip live."""
    from src import runtime_state, telegram_bot
    telegram_bot._handle_command("/live 3")
    assert runtime_state.is_preview(3) is True  # unchanged
    assert any("CONFIRM" in m for m in captured_messages)


def test_live_3_with_confirm_flips_live(captured_messages, mock_callbacks):
    from src import runtime_state, telegram_bot
    telegram_bot._handle_command("/live 3 CONFIRM")
    assert runtime_state.is_preview(3) is False
    assert any("LIVE" in m for m in captured_messages)


def test_live_other_strategy_rejected(captured_messages, mock_callbacks):
    """Only Strategy #3 is exposed; /live 1 and /live 2 must be rejected."""
    from src import runtime_state, telegram_bot
    telegram_bot._handle_command("/live 1 CONFIRM")
    assert runtime_state.is_preview(1) is True  # unchanged


def test_mode_command_lists_strategies(captured_messages, mock_callbacks):
    from src import telegram_bot
    telegram_bot._handle_command("/mode")
    out = "\n".join(captured_messages)
    assert "#1" in out and "#2" in out and "#3" in out


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


# ------------------------------------------------------------------
# Dispatch ordering regression
# ------------------------------------------------------------------

def test_tennis_pnl_dispatched_before_tennis(captured_messages, mock_callbacks, monkeypatch):
    """The /tennis_pnl handler must win over /tennis since startswith matches both."""
    from src import telegram_bot
    pnl_called = MagicMock()
    tennis_called = MagicMock()
    monkeypatch.setattr(telegram_bot, "_handle_tennis_pnl", pnl_called)
    monkeypatch.setattr(telegram_bot, "_handle_tennis", tennis_called)
    telegram_bot._handle_command("/tennis_pnl")
    pnl_called.assert_called_once()
    tennis_called.assert_not_called()
