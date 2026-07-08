#!/usr/bin/env python3
"""Polymarket copy-trading bot (Strategy #1).

Manages:
- Strategy #1 (Copy Trading): runs natively via asyncio
- Copy-paper validation harness (Strategy 1b): forward paper-copy measurement
- Wallet discovery: continuously hunts copyable wallets -> paper watchlist
- Unified Telegram bot for all commands

Usage:
  python main.py              # Run with defaults from .env
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
    import time
    from src.copy_trading import governance
    from src.copy_trading.copy_paper import format_resolution_telegram, report
    from src.copy_trading.copy_paper_live import (
        TradeFeed, make_feed_detector, make_feed_exit_detector)
    from src.copy_trading.copy_paper_runner import CopyPaperRunner
    from src.copy_trading.outcome_names import DEFAULT_RESOLVER

    # Advisory Claude promotion review (annotates the offer; never blocks it).
    _promo_review = None
    if CONFIG.copy_promote_llm_review:
        from src.copy_trading.llm_review import review_promotion as _promo_review
    # promotion-gate-history lives beside the discovery gate-history log.
    _promo_history = os.path.join(
        os.path.dirname(CONFIG.wallet_discovery_state), "promotion-gate-history.jsonl")

    def _load_replay_by_wallet():
        """Per-wallet own-history copy-replay stats from the discovery watchlist,
        for the probation fast-track. Defensive: {} on any read/parse failure."""
        try:
            import json
            with open(CONFIG.copy_paper_watchlist, encoding="utf-8") as f:
                data = json.load(f)
            out = {}
            for row in (data.get("targets") or []):
                w = (row.get("wallet") or "").lower()
                if w:
                    out[w] = {"copy_roi": row.get("copy_roi", 0.0),
                              "copy_n": row.get("copy_n", 0),
                              "copy_tstat": row.get("copy_tstat", 0.0)}
            return out
        except Exception as e:
            # Fail safe to "no fast-track this cycle" on a missing/corrupt/wrong-shape
            # watchlist — but NOT silently: a persistent parse failure would disable
            # the probation path invisibly, so log it (RCA-visible) rather than swallow.
            logger.debug(f"[PROMOTE-GATE] fast-track replay read failed ({e}) — "
                         f"no probation this cycle")
            return {}

    def _governance(ledger):
        """Auto promote-offer / demote off the System-B paper ledger each cycle."""
        if not CONFIG.copy_governance_enabled:
            return
        try:
            governance.run_governance_cycle(
                ledger.positions.values(),
                now=time.time(),
                promote_min_n=CONFIG.copy_promote_min_settled,
                promote_min_roi=CONFIG.copy_promote_min_roi,
                promote_min_tstat=CONFIG.copy_promote_min_tstat,
                promote_min_second_half_roi=CONFIG.copy_promote_min_second_half_roi,
                promote_min_conditions=CONFIG.copy_promote_min_conditions,
                promote_min_categories=CONFIG.copy_promote_min_categories,
                demote_min_n=CONFIG.copy_demote_min_settled,
                demote_max_roi=CONFIG.copy_demote_max_roi,
                demote_min_abs_loss=CONFIG.copy_demote_min_abs_loss,
                demote_max_wilson=CONFIG.copy_demote_max_wilson,
                cooldown_s=CONFIG.copy_demote_cooldown_days * 86400.0,
                default_tier=CONFIG.promote_default_tier,
                review_fn=_promo_review,
                llm_model=CONFIG.wallet_discovery_llm_model,
                history_path=_promo_history,
                send_offer=lambda o: telegram_bot.send_promotion_offer(
                    o["wallet"], o["n_closed"], o["roi"], o["net_pnl"],
                    o.get("tier", "1b"), extras=o),
                send_demotion=lambda d: telegram_bot.send_message(
                    f"⛔ <b>Auto-demoted</b> <code>{d['wallet']}</code> — "
                    f"{d['n_closed']} settled copies, ROI {d['roi'] * 100:+.0f}% "
                    f"(≤ {CONFIG.copy_demote_max_roi * 100:+.0f}%). "
                    f"Dropped from the watchlist for "
                    f"{CONFIG.copy_demote_cooldown_days:.0f}d."),
                # probation fast-track (rec 2a): strong own-history replay + a small
                # agreeing forward sample -> an early "probation"-tier offer.
                replay_by_wallet=_load_replay_by_wallet(),
                probation_enabled=CONFIG.copy_probation_enabled,
                probation_min_settled=CONFIG.copy_probation_min_settled,
                probation_min_replay_n=CONFIG.copy_probation_min_replay_n,
                probation_min_replay_roi=CONFIG.copy_probation_min_replay_roi,
                probation_min_replay_tstat=CONFIG.copy_probation_min_replay_tstat,
                # dead-band time-box (rec 2b): neutrally retire stuck wallets.
                time_box_enabled=CONFIG.copy_time_box_enabled,
                time_box_window_s=CONFIG.copy_time_box_window_days * 86400.0,
                retire_cooldown_s=CONFIG.copy_retire_cooldown_days * 86400.0,
                send_retirement=lambda r: telegram_bot.send_message(
                    f"🗄️ <b>Retired (inconclusive)</b> <code>{r['wallet']}</code> — "
                    f"{r['n_closed']} settled, ROI {r['roi'] * 100:+.0f}%, "
                    f"{r['age_days']:.0f}d on paper with no verdict. Removed from the "
                    f"watchlist (re-discoverable), not blacklisted."),
            )
        except Exception as e:
            logger.warning(f"[COPY-PAPER] governance cycle failed: {e}")

    # Dead-funnel alarm (starvation RCA 2026-07): paper opens/day fell 12→0 and
    # nothing said so — promotion evidence only accrues while copies open, so a
    # silent stall re-starves the funnel invisibly. Baseline falls back to boot
    # time on an empty ledger so a fresh install doesn't alarm instantly; alerts
    # re-arm every alarm window (daily heartbeat, not a one-shot), and any new
    # open resets the clock via the ledger itself (restart-proof).
    _stall = {"last_alert": 0.0, "boot": time.time()}

    def _stall_check(ledger):
        hours = CONFIG.copy_paper_stall_alarm_hours
        if hours <= 0:
            return
        now = time.time()
        last_open = max((getattr(p, "opened_ts", 0.0) or 0.0
                         for p in ledger.positions.values()), default=0.0)
        baseline = max(last_open, _stall["boot"])
        if now - baseline < hours * 3600.0:
            return
        if now - _stall["last_alert"] < hours * 3600.0:
            return  # already alerted this window
        n_watch = len(runner.wallets())
        if n_watch == 0:
            return  # empty watchlist is its own (already-logged) condition
        _stall["last_alert"] = now
        stalled_h = (now - baseline) / 3600.0
        logger.warning(
            f"[COPY-PAPER] FUNNEL STALLED — no paper opens in {stalled_h:.0f}h "
            f"with {n_watch} wallets on the watchlist; promotion evidence is "
            f"not accruing")
        telegram_bot.send_message(
            f"🚱 <b>Copy funnel stalled</b> — no paper copies opened in "
            f"{stalled_h:.0f}h with {n_watch} wallets watched. Evidence toward "
            f"promotion is not accruing; check the watchlist's trade activity "
            f"and the guardrail-skip mix.")

    def _on_cycle(summary, ledger):
        if summary.opened or summary.resolved:
            logger.info(
                f"[COPY-PAPER] opened={summary.opened} resolved={summary.resolved} "
                f"open={len(ledger.open_positions())} closed={len(ledger.closed_positions())}"
            )
        skips = (summary.skipped_fill_gate + summary.skipped_not_first_entry
                 + summary.skipped_slate_cap + summary.skipped_category_gate)
        if skips:
            logger.info(
                f"[COPY-PAPER] guardrail skips: fill-gate={summary.skipped_fill_gate} "
                f"first-entry={summary.skipped_not_first_entry} "
                f"slate-cap={summary.skipped_slate_cap} "
                # the winning-markets gate is default-ON and the biggest behaviour
                # change — log it so a quieted book always shows a reason.
                f"category-gate={summary.skipped_category_gate}"
            )
        if summary.resolved:
            telegram_bot.send_message(
                format_resolution_telegram(summary.resolved_positions, report(ledger),
                                           resolver=DEFAULT_RESOLVER)
            )
        try:
            _stall_check(ledger)
        except Exception as e:  # the alarm must never break the copy cycle
            logger.debug(f"[COPY-PAPER] stall check failed ({e})")
        _governance(ledger)

    # A cap <= 0 disables that guardrail (engine treats None as off).
    def _cap(v):
        return v if v and v > 0 else None

    # Shared-feed detection (item 4): one global /trades poll per cycle, filtered
    # to watched wallets — detection cost is flat in the wallet count, so the
    # watchlist scales to hundreds. Falls back to per-wallet polling when off.
    detector_factory = None
    exit_detector_factory = None
    if CONFIG.copy_paper_feed_detection:
        _feed = TradeFeed()
        _feed_min = CONFIG.copy_paper_feed_min_usd

        def detector_factory(wallets, max_age_s, min_usd, flagged_by_map=None, **kw):
            return make_feed_detector(wallets, max_age_s, min_usd, flagged_by_map,
                                      feed=_feed, feed_min_usd=_feed_min, **kw)

        def exit_detector_factory(wallets, max_age_s):
            return make_feed_exit_detector(wallets, max_age_s,
                                           feed=_feed, feed_min_usd=_feed_min)

    runner = CopyPaperRunner(
        ledger_path=CONFIG.copy_paper_ledger,
        watchlist_path=CONFIG.copy_paper_watchlist,
        max_copy_usd=CONFIG.copy_paper_max_usd,
        copy_pct=CONFIG.copy_paper_copy_pct,
        max_slippage_bps=CONFIG.copy_paper_max_slippage_bps,
        max_age_s=CONFIG.copy_paper_max_age_s,
        min_usd=CONFIG.copy_paper_min_usd,
        cycle_interval_s=CONFIG.copy_paper_interval_s,
        fill_gate_bps=_cap(CONFIG.copy_paper_fill_gate_bps),
        first_entry_only=CONFIG.copy_paper_first_entry_only,
        max_copies_per_wallet_day=_cap(CONFIG.copy_paper_max_per_wallet_day),
        max_copies_per_category_day=_cap(CONFIG.copy_paper_max_per_category_day),
        # evidence-throughput levers (starvation RCA): route the daily caps to
        # the coldest wallets + paper-only category-cap relief under the
        # evidence floor (fills stamped over_real_cap for promotion audit).
        starved_priority=CONFIG.copy_paper_starved_priority,
        relief_evidence_n=_cap(CONFIG.copy_paper_relief_evidence_n),
        relief_max_per_category_day=_cap(CONFIG.copy_paper_relief_max_per_category_day),
        # winning-markets-only gate (item A) + conviction sizing (item C)
        category_gate=CONFIG.copy_paper_category_gate,
        conviction_base_usd=(CONFIG.copy_paper_conviction_base_usd
                             if CONFIG.copy_paper_conviction_base_usd > 0 else None),
        conviction_min=CONFIG.copy_paper_conviction_min,
        conviction_max=CONFIG.copy_paper_conviction_max,
        # When Strategy 4 is on, this near-term book stops short-copying far-future
        # bets — they would lock paper capital for months and belong to the S4
        # book instead. Off => horizon-blind, so behaviour is unchanged.
        max_horizon_days=(CONFIG.strategy_4_long_horizon_days
                          if CONFIG.strategy_4_enabled else None),
        # NB: no mark_fetcher here on purpose. The near-term book cycles every
        # ~60s; marking in-cycle would (a) fire a full ledger re-serialize every
        # cycle (s.marked>0) and (b) burst N synchronous CLOB /book fetches,
        # stalling trade detection. Near-term opens are instead marked on-read in
        # /pnl (telegram_bot._compute_unified), exactly like System-A opens — the
        # mark only needs to be fresh when the owner looks. S4 (long-horizon, slow
        # cycle, months to resolution) still marks in-cycle below.
        detector_factory=detector_factory,
        exit_detector_factory=exit_detector_factory,
        on_cycle=_on_cycle,
    )
    n = len(runner.wallets())
    logger.info(
        f"Copy-paper harness started (wallets={n}, interval={CONFIG.copy_paper_interval_s}s, "
        f"feed-detection={CONFIG.copy_paper_feed_detection}, "
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


def _s4_paper_loop():
    """Strategy 4: paper book for long-horizon bets, marked to market.

    Watches both the copy watchlist and the long-horizon watchlist (S1 ∪ S4
    wallets) and opens a paper position only on bets whose market resolves at or
    beyond the horizon cut — the far-future conviction bets the near-term copier
    now skips. Holds to resolution, marking each open position to the live mid so
    /pnl shows a running unrealized P&L instead of a blank for months. NO orders.
    """
    from src.copy_trading.copy_paper_live import fetch_mid
    from src.copy_trading.copy_paper_runner import CopyPaperRunner

    def _on_cycle(summary, ledger):
        if summary.opened or summary.resolved or summary.marked:
            logger.info(
                f"[S4-PAPER] opened={summary.opened} resolved={summary.resolved} "
                f"marked={summary.marked} skipped_horizon={summary.skipped_horizon} "
                f"open={len(ledger.open_positions())} closed={len(ledger.closed_positions())}"
            )

    runner = CopyPaperRunner(
        ledger_path=CONFIG.strategy_4_paper_ledger,
        watchlist_path=CONFIG.copy_paper_watchlist,
        extra_watchlist_paths=[CONFIG.wallet_discovery_long_horizon_watchlist],
        max_copy_usd=CONFIG.strategy_4_paper_max_usd,
        copy_pct=CONFIG.copy_paper_copy_pct,
        max_slippage_bps=CONFIG.copy_paper_max_slippage_bps,
        max_age_s=CONFIG.copy_paper_max_age_s,
        min_usd=CONFIG.strategy_4_paper_min_usd,
        cycle_interval_s=CONFIG.strategy_4_paper_interval_s,
        # this book takes ONLY long-horizon bets, marks them to market, and stamps
        # them strategy "4" for per-strategy P&L.
        min_horizon_days=CONFIG.strategy_4_long_horizon_days,
        mark_fetcher=fetch_mid,
        strategy="4",
        on_cycle=_on_cycle,
    )
    n = len(runner.wallets())
    logger.info(
        f"S4 long-horizon paper book started (wallets={n}, "
        f"interval={CONFIG.strategy_4_paper_interval_s}s, "
        f"horizon≥{CONFIG.strategy_4_long_horizon_days:.0f}d, "
        f"max ${CONFIG.strategy_4_paper_max_usd:.0f}/bet, PREVIEW measurement only)"
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
        res_cache_dir=CONFIG.wallet_discovery_res_cache,
        copy_replay_gate=CONFIG.wallet_discovery_copy_replay_gate,
        min_copy_replay_n=CONFIG.wallet_discovery_min_copy_replay_n,
        min_copy_replay_roi=CONFIG.wallet_discovery_min_copy_replay_roi,
        fade_roi=CONFIG.wallet_discovery_fade_roi,
        max_tail_ratio=CONFIG.wallet_discovery_max_tail_ratio,
        max_curve_drawdown=CONFIG.wallet_discovery_max_curve_drawdown,
        max_hit_rate=CONFIG.wallet_discovery_max_hit_rate,
        min_curve_n=CONFIG.wallet_discovery_min_curve_n,
        s4_enabled=CONFIG.strategy_4_enabled,
        s4_long_horizon_days=CONFIG.strategy_4_long_horizon_days,
        s4_min_long_ratio=CONFIG.strategy_4_min_long_ratio,
        s4_min_dated_buys=CONFIG.strategy_4_min_dated_buys,
        s4_min_long_buys=CONFIG.strategy_4_min_long_buys,
        long_horizon_cap=CONFIG.strategy_4_cap,
        consensus_enabled=CONFIG.consensus_enabled,
        consensus_min_wallets=CONFIG.consensus_min_wallets,
        consensus_window_s=CONFIG.consensus_window_hours * 3600.0,
        consensus_min_usd=CONFIG.consensus_min_usd,
        consensus_cooldown_s=CONFIG.consensus_cooldown_hours * 3600.0,
    )
    runner = DiscoveryRunner(
        config=cfg,
        watchlist_path=CONFIG.copy_paper_watchlist,   # feeds the paper harness
        state_path=CONFIG.wallet_discovery_state,
        long_horizon_watchlist_path=CONFIG.wallet_discovery_long_horizon_watchlist,
        cache_dir=CONFIG.wallet_discovery_cache_dir,
        activity_ttl_s=CONFIG.wallet_discovery_activity_ttl_s,
        cycle_interval_s=CONFIG.wallet_discovery_interval_s,
        notify=lambda msg: telegram_bot.send_message(msg),
        llm_review_enabled=CONFIG.wallet_discovery_llm_review_enabled,
        llm_review_top_n=CONFIG.wallet_discovery_llm_review_top_n,
        llm_model=CONFIG.wallet_discovery_llm_model,
        holdout_frac=CONFIG.gate_holdout_frac,
        holdout_max_per_sweep=CONFIG.gate_holdout_max_per_sweep,
        # Paper-evidence retention override (starvation RCA): None disables.
        paper_ledger_path=(CONFIG.copy_paper_ledger
                           if CONFIG.paper_proven_retention_enabled else None),
        paper_proven_min_n=CONFIG.paper_proven_min_n,
        paper_proven_min_roi=CONFIG.paper_proven_min_roi,
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

        # Strategy 4: the long-horizon paper book runs alongside the near-term
        # copier (same measurement-only guarantee), taking the far-future bets the
        # copier now skips. Gated on both copy-paper AND strategy_4 being enabled.
        if CONFIG.strategy_4_enabled:
            s4_paper_thread = threading.Thread(
                target=_s4_paper_loop, daemon=True, name="s4-paper"
            )
            s4_paper_thread.start()
            logger.info("S4 long-horizon paper book thread started")
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
