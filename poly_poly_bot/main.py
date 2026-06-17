#!/usr/bin/env python3
"""Polymarket copy-trading bot (Strategy #1).

Manages:
- Strategy #1 (Copy Trading): runs natively via asyncio
- Copy-paper validation harness (Strategy 1b): forward paper-copy measurement
- Wallet discovery: continuously hunts copyable wallets -> paper watchlist
- Unified Telegram bot for all commands

Usage:
  python main.py              # Run with defaults from .env

Note: the Weather (#2) and Tennis Arb (#3) strategies were decommissioned on
2026-06-17. See DECOMMISSIONED.md for how to restore them from git history.
"""

import asyncio
import os
import sys
import signal
import logging
import threading
from datetime import datetime

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import CONFIG
from src.logger import logger

import src.telegram_bot as telegram_bot

_shutdown_event = threading.Event()


def refresh_clob_client() -> None:
    """Rebuild the singleton CLOB client after the in-memory key changes.

    Called by the Telegram /setkey command. Drops the cached singleton and
    rebuilds it so a fresh key validates; Strategy #1's running loops hold the
    client reference obtained at startup, so a rotated key fully takes effect on
    the next container restart (which reloads PRIVATE_KEY from .env).
    """
    from src.copy_trading.clob_client import create_clob_client, reset_clob_client

    reset_clob_client()
    create_clob_client()  # may be None if key was cleared


def _copy_paper_loop():
    """Strategy 1b validation: forward paper-copy of watchlist wallets.

    Measures execution-realistic copy PnL (entries against the live book, net of
    drag) and tracks it to resolution. Places NO real orders — it is a
    measurement harness whose ledger gates whether any wallet earns real capital.
    """
    from src.copy_trading.copy_paper import format_resolution_telegram, report
    from src.copy_trading.copy_paper_runner import CopyPaperRunner

    def _on_cycle(summary, ledger):
        if summary.opened or summary.resolved:
            logger.info(
                f"[COPY-PAPER] opened={summary.opened} resolved={summary.resolved} "
                f"open={len(ledger.open_positions())} closed={len(ledger.closed_positions())}"
            )
        if summary.resolved:
            telegram_bot.send_message(
                format_resolution_telegram(summary.resolved_positions, report(ledger))
            )

    runner = CopyPaperRunner(
        ledger_path=CONFIG.copy_paper_ledger,
        watchlist_path=CONFIG.copy_paper_watchlist,
        max_copy_usd=CONFIG.copy_paper_max_usd,
        copy_pct=CONFIG.copy_paper_copy_pct,
        max_slippage_bps=CONFIG.copy_paper_max_slippage_bps,
        max_age_s=CONFIG.copy_paper_max_age_s,
        min_usd=CONFIG.copy_paper_min_usd,
        cycle_interval_s=CONFIG.copy_paper_interval_s,
        on_cycle=_on_cycle,
    )
    n = len(runner.wallets())
    logger.info(
        f"Copy-paper harness started (wallets={n}, interval={CONFIG.copy_paper_interval_s}s, "
        f"max ${CONFIG.copy_paper_max_usd:.0f}/copy, PREVIEW measurement only)"
    )
    if n == 0:
        wl = CONFIG.copy_paper_watchlist
        logger.warning(
            f"[COPY-PAPER] no watchlist wallets at {wl} — generate one with "
            f"`python -m backtest.two_stage_watchlist --cache-dir data/wcache "
            f"--output {wl}` (skill ∩ copyability)"
        )
    runner.run_forever(_shutdown_event)


def _discovery_loop():
    """Continuously hunt for copyable wallets and feed them to the paper harness.

    Runs the funnel (universe -> robust skill -> lead-lag copyability) on a
    schedule. Each new qualifier is Telegram-pinged and written to the paper
    watchlist (auto-paper) so measurement starts while you analyze. Never places
    real orders and never edits the live `.env` tiers — promotion stays manual.
    """
    from src.copy_trading.discovery import DiscoveryConfig
    from src.copy_trading.discovery_runner import DiscoveryRunner

    cfg = DiscoveryConfig(
        category=CONFIG.wallet_discovery_category,
        universe=CONFIG.wallet_discovery_universe,
        skill_pool=CONFIG.wallet_discovery_skill_pool,
        watchlist_cap=CONFIG.wallet_discovery_cap,
        min_capture_cents=CONFIG.wallet_discovery_min_capture_cents,
        min_tstat=CONFIG.wallet_discovery_min_tstat,
        drop_capture_cents=CONFIG.wallet_discovery_drop_capture_cents,
        auto_remove=CONFIG.wallet_discovery_auto_remove,
        enabled_theories=frozenset(
            t.strip() for t in CONFIG.wallet_discovery_theories.split(",") if t.strip()),
    )
    runner = DiscoveryRunner(
        config=cfg,
        watchlist_path=CONFIG.copy_paper_watchlist,   # feeds the paper harness
        state_path=CONFIG.wallet_discovery_state,
        cache_dir=CONFIG.wallet_discovery_cache_dir,
        activity_ttl_s=CONFIG.wallet_discovery_activity_ttl_s,
        cycle_interval_s=CONFIG.wallet_discovery_interval_s,
        notify=lambda msg: telegram_bot.send_message(msg),
        llm_review_enabled=CONFIG.wallet_discovery_llm_review_enabled,
        llm_review_top_n=CONFIG.wallet_discovery_llm_review_top_n,
        llm_model=CONFIG.wallet_discovery_llm_model,
    )
    runner.run_forever(_shutdown_event)


# -- Main --

def _setup_logging():
    """Configure logging to console and file."""
    os.makedirs(CONFIG.logs_dir, exist_ok=True)
    log_file = os.path.join(CONFIG.logs_dir,
                             f"bot-{datetime.now().strftime('%Y-%m-%d')}.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(log_file)
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(ch)
    root.addHandler(fh)


def _signal_handler(sig, frame):
    logger.info(f"Received signal {sig}, shutting down...")
    _shutdown_event.set()


async def main():
    """Main entry point — runs Strategy #1 plus its measurement harnesses."""
    _setup_logging()

    logger.info("=" * 60)
    logger.info("  Polymarket Copy-Trading Bot")
    logger.info(f"  Strategy #1 (Copy Trading): {'ENABLED' if CONFIG.strategy1_enabled else 'DISABLED'}")
    logger.info(f"  Preview mode: {CONFIG.preview_mode}")
    logger.info("=" * 60)

    # Register CLOB-client refresher so /setkey can rotate the in-memory
    # private key and have the singleton rebuilt.
    telegram_bot.on_refresh_clob_client = refresh_clob_client

    # Signal handlers
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Start Telegram polling
    if telegram_bot.is_configured():
        telegram_bot.start_polling()
        logger.info("Telegram bot started")
    else:
        logger.info("Telegram not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")

    # Startup notification
    telegram_bot.send_message(
        "<b>Bot Started</b>\n"
        f"Strategy #1 (Copy): {'ON' if CONFIG.strategy1_enabled else 'OFF'}\n"
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}"
    )

    # Start the copy-paper validation harness (Strategy 1b) in a thread.
    # Measurement only — never places real orders — so it is always safe to run.
    if CONFIG.copy_paper_enabled:
        copy_paper_thread = threading.Thread(
            target=_copy_paper_loop, daemon=True, name="copy-paper"
        )
        copy_paper_thread.start()
        logger.info("Copy-paper harness thread started")
    else:
        logger.info("Copy-paper harness disabled (set COPY_PAPER_ENABLED=true)")

    # Start the continuous wallet-discovery hunter (feeds the paper watchlist).
    # Measurement/selection only — never places real orders or edits live tiers.
    if CONFIG.wallet_discovery_enabled:
        discovery_thread = threading.Thread(
            target=_discovery_loop, daemon=True, name="wallet-discovery"
        )
        discovery_thread.start()
        logger.info("Wallet-discovery thread started")
    else:
        logger.info("Wallet discovery disabled (set WALLET_DISCOVERY_ENABLED=true)")

    # Start Strategy #1 (Copy Trading) natively via asyncio
    s1_crashed = False
    if CONFIG.strategy1_enabled:
        logger.info("Starting Strategy #1 (Copy Trading) via asyncio...")
        from src.copy_trading.runner import run_copy_trading
        try:
            # Run copy trading as the main async task; it blocks until shutdown.
            # The copy-paper and discovery harnesses run in daemon threads.
            await run_copy_trading()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(f"Strategy #1 crashed: {e}")
            telegram_bot.send_message(f"Strategy #1 crashed: <code>{e}</code>\n<i>Bot continues — paper/discovery harnesses still running.</i>")
            s1_crashed = True
    else:
        logger.info("Strategy #1 disabled, skipping copy-trader bot")

    # Keep alive whenever Strategy #1 isn't the main task — either it's
    # disabled, or it crashed. The copy-paper and discovery harnesses run in
    # daemon threads and need the main thread to stay up so the container
    # doesn't exit.
    if not CONFIG.strategy1_enabled or s1_crashed:
        try:
            while not _shutdown_event.is_set():
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

    # Shutdown
    logger.info("Shutting down...")
    _shutdown_event.set()
    telegram_bot.send_message("Bot shutting down.")
    telegram_bot.stop_polling()
    logger.info("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
