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
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, False)
    telegram_bot._process_update(_update("/preview 3", chat_id=WRONG_CHAT_ID))
    # State unchanged, no message sent.
    assert runtime_state.is_preview(3) is False
    assert captured_messages == []


def test_update_from_correct_chat_id_dispatches(configured_chat, captured_messages, mock_callbacks):
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, False)
    telegram_bot._process_update(_update("/preview 3"))
    assert runtime_state.is_preview(3) is True


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
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, False)
    telegram_bot._process_update(_update("/preview 3", chat_id=int(CHAT_ID)))
    assert runtime_state.is_preview(3) is True


# ------------------------------------------------------------------
# End-to-end: real Telegram payload → state mutation
# These are the exact scenarios the user originally specified.
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


def test_e2e_preview_3_flips_runtime_state(configured_chat, captured_messages, mock_callbacks):
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, False)
    telegram_bot._process_update(_update("/preview 3"))
    assert runtime_state.is_preview(3) is True


def test_e2e_live_3_requires_confirm_via_full_path(configured_chat, captured_messages, mock_callbacks):
    from src import runtime_state, telegram_bot
    telegram_bot._process_update(_update("/live 3"))
    assert runtime_state.is_preview(3) is True  # unchanged: no CONFIRM


# ==================================================================
# /tennis_pnl — report shape, mode filter, recent-window filter,
# stale-void safety net
# ==================================================================


@pytest.fixture
def tennis_pnl_env(monkeypatch, tmp_path):
    """Stand up a paper book on disk and wire telegram_bot to read from it.

    Returns (book, captured) — the live ``TennisPaperBook`` so tests can
    backdate timestamps directly, and a list of strings the handler tried
    to send (so each test can grep the rendered output).
    """
    from src import telegram_bot
    from src.tennis.paper_book import TennisPaperBook

    monkeypatch.setattr(telegram_bot.CONFIG, "strategy3_enabled", True)
    monkeypatch.setattr(telegram_bot.CONFIG, "data_dir", str(tmp_path))

    captured: list[str] = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, **_kw: captured.append(text))
    # Skip live midpoint fetches — tests don't have network and we want
    # determinism. ``None`` means the handler treats unrealized as zero,
    # which is fine for shape/filter assertions.
    monkeypatch.setattr(telegram_bot, "_fetch_midpoint", lambda _tid: None)
    # Default: no resolve callback wired (tests can override).
    monkeypatch.setattr(telegram_bot, "on_tennis_resolve_request", None)

    book = TennisPaperBook(data_dir=str(tmp_path))
    return book, captured


def _open_signal(**kw):
    """Build a minimal signal dict the paper book accepts."""
    base = {
        "strategy": "tennis_arb",
        "condition_id": "0xMATCH1",
        "token_id": "TOKA",
        "market_id": "M1",
        "polymarket_price": 0.40,
        "bet_size": 10.0,
        "player_a": "Alpha",
        "player_b": "Bravo",
        "target_player": "Alpha",
        "outcome_label": "Alpha",
        "sharp_prob": 0.65,
        "divergence": 0.15,
        "event_title": "Atp Test Cup",
        "event_slug": "test-cup-2026",
        "polymarket_url": "https://polymarket.com/event/test-cup-2026",
        "tournament": "Atp Test",
        "match_time": "2026-05-06T14:00:00+00:00",
        "side": "A",
        "live": False,
    }
    base.update(kw)
    return base


def test_tennis_pnl_shows_single_total_no_realized_unrealized_breakdown(tennis_pnl_env):
    """The top of the message must show a single Total PnL number.

    The previous report listed Realized / Unrealized / Net separately;
    the user now wants just one headline figure.
    """
    book, captured = tennis_pnl_env
    book.process_signal(_open_signal())  # one open position
    from src import telegram_bot
    telegram_bot._handle_command("/tennis_pnl")
    out = "\n".join(captured)
    assert "Total PnL:" in out
    # No standalone "Realized:" / "Unrealized:" / "Net:" labels at the
    # top-of-message summary. (R/U breakdown still appears per-event,
    # which is fine — those labels are different lines.)
    assert "Realized:" not in out
    assert "Unrealized:" not in out
    assert "\nNet:" not in out


def test_tennis_pnl_calls_resolve_callback_first(tennis_pnl_env, monkeypatch):
    """Before reading the book, the handler must trigger a force-resolve
    so any markets that settled since the last scheduled tick are picked
    up. Otherwise the report shows stale OPEN rows for finished matches.
    """
    book, captured = tennis_pnl_env
    book.process_signal(_open_signal())
    resolve_cb = MagicMock()
    from src import telegram_bot
    monkeypatch.setattr(telegram_bot, "on_tennis_resolve_request", resolve_cb)
    telegram_bot._handle_command("/tennis_pnl")
    resolve_cb.assert_called_once()


def test_tennis_pnl_voids_stale_open_positions(tennis_pnl_env):
    """A position open for >3 days with no resolution must be voided so
    /tennis_pnl stops reporting it as OPEN."""
    from datetime import datetime, timedelta, timezone
    book, captured = tennis_pnl_env
    book.process_signal(_open_signal())
    pid = book.open_positions()[0]["id"]
    old = datetime.now(timezone.utc) - timedelta(days=10)
    book._state["open_positions"][pid]["opened_at"] = old.isoformat()
    book._save()

    from src import telegram_bot
    telegram_bot._handle_command("/tennis_pnl")

    # Re-read state from disk (the handler instantiates its own book).
    from src.tennis.paper_book import TennisPaperBook
    book2 = TennisPaperBook(data_dir=telegram_bot.CONFIG.data_dir)
    assert book2.open_position_count() == 0
    assert any(p["exit_reason"] == "STALE_VOID" for p in book2.closed_positions())


def test_tennis_pnl_hides_old_closed_events(tennis_pnl_env):
    """Closed positions older than the recent-window must NOT appear in
    the breakdown. Active OPEN positions are always shown, but a long
    history of resolved events shouldn't clutter the report."""
    from datetime import datetime, timedelta, timezone
    book, captured = tennis_pnl_env
    # An old closed position from a different event.
    book.process_signal(_open_signal(
        condition_id="0xOLD", token_id="OLD_A",
        event_title="Old Tournament 2025",
    ))
    book.resolve("0xOLD", winning_token_id="OLD_A")
    closed = book.closed_positions()[0]
    old_time = datetime.now(timezone.utc) - timedelta(days=30)
    closed["closed_at"] = old_time.isoformat()
    book._state["closed_positions"][0] = closed
    book._save()

    from src import telegram_bot
    telegram_bot._handle_command("/tennis_pnl")
    out = "\n".join(captured)
    assert "Old Tournament 2025" not in out


def test_tennis_pnl_shows_recently_closed_events(tennis_pnl_env):
    """A position closed within the recent window must appear."""
    book, captured = tennis_pnl_env
    book.process_signal(_open_signal(
        condition_id="0xNEW", token_id="NEW_A",
        event_title="Recent Tournament",
    ))
    book.resolve("0xNEW", winning_token_id="NEW_A")  # closed_at = now

    from src import telegram_bot
    telegram_bot._handle_command("/tennis_pnl")
    out = "\n".join(captured)
    assert "Recent Tournament" in out


def test_tennis_pnl_live_mode_excludes_preview_positions(tennis_pnl_env):
    """When Strategy #3 is in LIVE mode, ``live=False`` (preview) deals
    must not appear. The point: in live trading the user only cares about
    real placed orders' PnL, not the paper-only signals."""
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, False)  # live mode

    book, captured = tennis_pnl_env
    book.process_signal(_open_signal(
        condition_id="0xPREV", token_id="PREV_A",
        event_title="Preview Only Event",
        live=False,
    ))
    book.process_signal(_open_signal(
        condition_id="0xLIVE", token_id="LIVE_A",
        event_title="Real Live Event",
        live=True,
    ))

    telegram_bot._handle_command("/tennis_pnl")
    out = "\n".join(captured)
    assert "Real Live Event" in out
    assert "Preview Only Event" not in out
    assert "Mode: LIVE" in out


def test_tennis_pnl_preview_mode_includes_all_positions(tennis_pnl_env):
    """In PREVIEW mode, paper signals are the whole point — show them."""
    from src import runtime_state, telegram_bot
    runtime_state.set_preview(3, True)

    book, captured = tennis_pnl_env
    book.process_signal(_open_signal(
        condition_id="0xPREV", token_id="PREV_A",
        event_title="Preview Only Event",
        live=False,
    ))

    telegram_bot._handle_command("/tennis_pnl")
    out = "\n".join(captured)
    assert "Preview Only Event" in out
    assert "Mode: PREVIEW" in out
