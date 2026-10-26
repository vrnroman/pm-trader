"""Telegram for the news bot: push messages and the owner's commands.

  /pnl     the experiment's P&L: what the paper bets won or lost, against controls
  /news    today's funnel: what was read, judged, bought, and which sources lead
  /status  is it up, are the sources reading, how much of the model budget is used
  /help    this list

The copy-trading commands went with the copy bot (2026-10-27). A message
that is not a command is handed to the news bot as a source (a forwarded
post, a link): the owner's own thumb.
"""

from __future__ import annotations

import logging
import threading
import time

import requests

from src.config import CONFIG

logger = logging.getLogger("telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"

KIND_BOT = "bot"
KIND_NEWS = "news"
_KIND_PREFIX = {KIND_BOT: "🤖 BOT", KIND_NEWS: "📰 NEWS"}

# Every name here is dispatched in _handle_command (tests hold the parity);
# Telegram rejects the whole batch if one name breaks ^[a-z0-9_]{1,32}$.
BOT_MENU_COMMANDS: list[dict] = [
    {"command": "pnl", "description": "News bot P&L: paper bets won or lost, against the controls"},
    {"command": "news", "description": "Today's funnel: read, judged, bought; which sources lead"},
    {"command": "status", "description": "Up? Sources reading? Model budget used?"},
    {"command": "help", "description": "What each command shows"},
]

_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()
# Set by the news runner at boot: (text, message) -> None. None = ignored.
on_owner_text = None


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def is_configured() -> bool:
    return bool(CONFIG.telegram_bot_token) and bool(CONFIG.telegram_chat_id)


def no_dashes(text: str) -> str:
    """The owner reads every word; an em or en dash is the one typographic
    tell he has named. Scrubbed at the seam."""
    return (text.replace(" — ", ": ").replace(" – ", ": ")
                .replace("—", "-").replace("–", "-"))


def _is_parse_error(resp) -> bool:
    try:
        return resp.status_code == 400 and "parse entities" in (resp.text or "")
    except Exception:  # noqa: BLE001
        return False


def send_message(text: str, parse_mode: str = "HTML", kind: str | None = None) -> bool:
    """Send to the owner's chat. ``kind`` (KIND_NEWS, KIND_BOT) marks a push
    the owner did not ask for; a reply to his command has none. True iff
    delivered. A message Telegram cannot parse as HTML is resent as plain
    text: the content always lands."""
    if not is_configured():
        return False
    prefix = _KIND_PREFIX.get(kind or "")
    if prefix:
        text = f"<b>[{prefix}]</b> {text}"
    text = no_dashes(text)
    url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/sendMessage"
    payload = {"chat_id": CONFIG.telegram_chat_id, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.ok:
            return True
        logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
        if parse_mode and _is_parse_error(resp):
            payload.pop("parse_mode", None)
            retry = requests.post(url, json=payload, timeout=10)
            if retry.ok:
                logger.warning("Telegram: HTML parse failed, delivered as plain text")
            return bool(retry.ok)
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Telegram send error: {e}")
        return False


def send_long(text: str, kind: str | None = None, chunk_size: int = 3800) -> bool:
    """Send a long reply in pieces split on line boundaries, never inside a
    <pre> block (its tags would tear). The kind prefix rides the first piece."""
    if len(text) <= chunk_size:
        return send_message(text, kind=kind)
    ok, buf, cur, first, in_pre = True, [], 0, True, False
    for line in text.split("\n"):
        if buf and not in_pre and cur + len(line) + 1 > chunk_size:
            ok = send_message("\n".join(buf), kind=kind if first else None) and ok
            buf, cur, first = [], 0, False
        buf.append(line)
        cur += len(line) + 1
        if "<pre>" in line:
            in_pre = True
        if "</pre>" in line:
            in_pre = False
    if buf:
        ok = send_message("\n".join(buf), kind=kind if first else None) and ok
    return ok


def startup_text() -> str:
    return ("<b>News bot started</b>\n"
            "Paper only: news bets are simulated at the real prices, never placed\n"
            "Real money: not wired (this build cannot sign an order)\n"
            "/pnl for the money, /news for the funnel")


def help_text() -> str:
    lines = ["<b>News bot</b> (paper trading on free news)"]
    lines += [f"/{c['command']}: {_esc(c['description'])}" for c in BOT_MENU_COMMANDS]
    lines.append("")
    lines.append("Send or forward any post or link: it becomes a source, judged like the others.")
    return "\n".join(lines)


def _handle_command(text: str) -> None:
    head = text.split(None, 1)[0].split("@", 1)[0].lower()
    from src.newsbot import runner as news_runner
    if head == "/pnl":
        send_long(news_runner.pnl_text(text))
    elif head == "/news":
        send_long(news_runner.news_text(text))
    elif head == "/status":
        send_long(news_runner.status_text())
    elif head in ("/help", "/start"):
        send_message(help_text())
    else:
        send_message(f"Unknown command {_esc(head)}. The copy bot's commands were removed "
                     f"on 2026-10-27.\n\n" + help_text())


def _process_update(update: dict) -> None:
    msg = update.get("message", {}) or {}
    if str(msg.get("chat", {}).get("id", "")) != CONFIG.telegram_chat_id:
        return
    text = msg.get("text", "") or ""
    if not text:
        return
    if not text.startswith("/"):
        if on_owner_text is not None:
            try:
                on_owner_text(text, msg)
            except Exception as e:  # noqa: BLE001
                logger.exception(f"owner text handler error: {e}")
        return
    logger.info(f"Telegram command: {text[:80]}")
    try:
        _handle_command(text)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Command handler error: {e}")
        send_message(f"Error: <code>{_esc(str(e))}</code>")


def _poll_loop() -> None:
    base = TELEGRAM_API.format(token=CONFIG.telegram_bot_token)
    last = 0
    try:
        r = requests.get(f"{base}/getUpdates", params={"offset": -1, "timeout": 0}, timeout=10)
        if r.ok and r.json().get("result"):
            last = r.json()["result"][-1]["update_id"] + 1
    except Exception:  # noqa: BLE001
        pass
    logger.info("Telegram polling started")
    while not _stop_event.is_set():
        try:
            r = requests.get(f"{base}/getUpdates", params={"offset": last, "timeout": 10,
                                                           "allowed_updates": '["message"]'}, timeout=15)
            if not r.ok:
                time.sleep(5)
                continue
            for update in r.json().get("result", []):
                last = update["update_id"] + 1
                _process_update(update)
        except requests.exceptions.Timeout:
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Telegram poll error: {e}")
            time.sleep(5)


def register_menu() -> None:
    """Replace the popup menu with the news commands. Scoped lists that
    would shadow the default one are cleared first."""
    base = TELEGRAM_API.format(token=CONFIG.telegram_bot_token)
    for scope in ({"type": "all_private_chats"}, {"type": "all_group_chats"},
                  {"type": "all_chat_administrators"}):
        try:
            requests.post(f"{base}/deleteMyCommands", json={"scope": scope}, timeout=10)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"deleteMyCommands {scope['type']} error: {e}")
    try:
        r = requests.post(f"{base}/setMyCommands", json={"commands": BOT_MENU_COMMANDS}, timeout=10)
        body = r.json() if r.ok else {}
        if body.get("ok"):
            logger.info("Telegram menu: registered %d commands", len(BOT_MENU_COMMANDS))
        else:
            logger.error(f"Telegram setMyCommands rejected: {r.text[:200]}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Telegram setMyCommands error: {e}")


def start_polling() -> None:
    global _poll_thread
    if not is_configured():
        logger.info("Telegram not configured, skipping poll")
        return
    register_menu()
    _stop_event.clear()
    _poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="telegram-poll")
    _poll_thread.start()


def stop_polling() -> None:
    _stop_event.set()
    if _poll_thread:
        _poll_thread.join(timeout=15)
