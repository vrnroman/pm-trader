#!/usr/bin/env python3
"""The news bot: reads free news, judges it against Polymarket markets, and
paper-trades what is new before the price moves, at honest prices.

One process: the news runner (its own asyncio loop in a thread) and the
Telegram commands. Real money is not wired. The copy-trading bot this file
used to run was removed on 2026-10-27.

Usage:
  python main.py
"""

import logging
import os
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import CONFIG
from src.logger import logger

import src.telegram_bot as telegram_bot

_shutdown_event = threading.Event()


def _not_app_record(rec) -> bool:
    """Root handlers keep third-party records; BotLogger owns the app's."""
    return not (rec.name == "poly_poly_bot" or rec.name.startswith("poly_poly_bot."))


def _setup_logging():
    """Configure logging to console and file.

    The file handler must ROLL at UTC midnight: the old plain FileHandler
    baked the start date into the filename once, so a long container run
    appended everything (incl. all WARNINGs and urllib3 DEBUG) to the boot
    day's file — bot-2026-07-10.log grew to 99MB over six days while the
    per-day files stayed near-empty, and the 07-15 FUNNEL-STALLED warning
    "lived in" the 07-10 file (2026-07-16 RCA). Reuse the same rolling
    handler the BotLogger files use.
    """
    from src.logger import _DailyRotatingFileHandler, SecretScrubFormatter

    os.makedirs(CONFIG.logs_dir, exist_ok=True)

    # Scrubs the COMPLETE rendered record, traceback included — a
    # logger.exception around a Telegram-API failure renders the bot-token URL
    # in the traceback tail, and filter-level scrubs never see exc_info.
    fmt = SecretScrubFormatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler: third-party records only. The app logger propagates
    # to root, and without this filter every app line reached stdout twice
    # (once coloured from BotLogger, once plain from here), which doubled the
    # container log on the VM.
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)
    ch.addFilter(_not_app_record)

    # File handler — rolls to bot-<new-date>.log when the UTC date changes.
    # It shares that file with BotLogger's ops handler, and the app logger
    # ("poly_poly_bot") PROPAGATES to root — without the filter below every
    # app record would be written twice to the same file by two unsynchronized
    # handlers. Root keeps only third-party records (urllib3, web3, ...);
    # BotLogger already files the app's own records (bot- ops, signals- WARN+).
    fh = _DailyRotatingFileHandler(Path(CONFIG.logs_dir), "bot")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    fh.addFilter(_not_app_record)
    # Third-party records (urllib3 request lines) can carry credentials in
    # URLs — the 2026-07-16→25 Telegram-token leak walked in through exactly
    # this handler. Scrub before anything is written.
    from src.logger import SecretScrubFilter
    fh.addFilter(SecretScrubFilter())
    ch.addFilter(SecretScrubFilter())

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(ch)
    root.addHandler(fh)


# How long a stop may take before the process ends itself. docker stop sends
# SIGTERM and force-kills after 10 s; on 2026-09-24 both containers were
# force-killed on every deploy ("Container failed to exit within 10s of
# signal 15"), because a paper cycle or a blocking read outlives the grace
# period. Every state file here is written atomically, so ending the
# process is safe; ending it OURSELVES, with the still-running threads
# named in the log, is what makes the next stop readable.
SHUTDOWN_DEADLINE_S = float(os.environ.get("SHUTDOWN_DEADLINE_S", "8") or 8)


def _hard_exit() -> None:
    alive = sorted(t.name for t in threading.enumerate()
                   if t is not threading.current_thread() and t.name != "MainThread")
    logger.warning(f"[shutdown] {SHUTDOWN_DEADLINE_S:.0f}s deadline reached; ending the process "
                   f"with these threads still running: {', '.join(alive) or 'none'}")
    try:
        logging.shutdown()
    except Exception:
        pass
    os._exit(0)


def _signal_handler(sig, frame):
    logger.info(f"Received signal {sig}, shutting down...")
    _shutdown_event.set()
    t = threading.Timer(SHUTDOWN_DEADLINE_S, _hard_exit)
    t.daemon = True
    t.start()


def main() -> None:
    _setup_logging()
    logger.info("=" * 60)
    logger.info("News bot starting (paper only)")
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if telegram_bot.is_configured():
        telegram_bot.start_polling()
    else:
        logger.info("Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
    telegram_bot.send_message(telegram_bot.startup_text(), kind=telegram_bot.KIND_BOT)

    from src.newsbot import runner as news_runner
    t = threading.Thread(target=news_runner.run_forever, args=(_shutdown_event,),
                         daemon=True, name="news-bot")
    t.start()
    logger.info("[news] news bot started")
    while not _shutdown_event.is_set():
        _shutdown_event.wait(1.0)
        if not t.is_alive():
            logger.error("[news] the news runner thread ended; exiting so Docker restarts the container")
            break
    logger.info("Shutting down...")
    _shutdown_event.set()
    telegram_bot.stop_polling()
    t.join(timeout=5)
    logger.info("Goodbye.")


if __name__ == "__main__":
    main()
