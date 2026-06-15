#!/usr/bin/env python3
"""Unified Polymarket Trading Bot — all three strategies in Python.

Manages all strategies:
- Strategy #1 (Copy Trading): runs natively via asyncio
- Strategy #2 (Weather Betting): scheduled daily at configured SGT time
- Strategy #3 (Tennis Arb): periodic scans every N seconds
- Unified Telegram bot for all commands

Usage:
  python main.py              # Run with defaults from .env
  python main.py --once       # Run Strategy #2 once and exit
"""

import asyncio
import os
import sys
import signal
import logging
import threading
import argparse
import json
from datetime import datetime, timedelta, timezone

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import CONFIG
from src.logger import logger

import src.telegram_bot as telegram_bot

SGT = timezone(timedelta(hours=8))

_shutdown_event = threading.Event()


# -- Strategy #2: Weather Betting --

def run_strategy2(target_date: datetime) -> list[dict]:
    """Run a single Strategy #2 prediction cycle."""
    from src.weather.weather_data import fetch_all_weather
    from src.weather.weather_predictor import WeatherPredictor
    from src.weather.polymarket_fetcher import fetch_markets_for_cities_and_dates
    from src.weather.cities import CITIES
    import pandas as pd

    cities_list = [c.strip() for c in CONFIG.cities_to_bet.split(",")]
    date_str = target_date.strftime("%Y-%m-%d")
    logger.info(f"Strategy #2: Running prediction for {date_str}")

    os.makedirs(CONFIG.cache_dir, exist_ok=True)

    # Fetch weather history
    weather_df = fetch_all_weather(cities_list, CONFIG.cache_dir)
    if len(weather_df) == 0:
        logger.error("No weather data available")
        return []

    # Fetch Polymarket markets
    markets_df = fetch_markets_for_cities_and_dates(cities_list, [target_date])
    if len(markets_df) == 0:
        logger.warn(f"No Polymarket markets found for {date_str}")
        return []

    # Predict
    predictor = WeatherPredictor(weather_df, window_days=15, recency_halflife=4.0)

    # Polymarket fee
    polymarket_fee = float(os.getenv("POLYMARKET_FEE", "0.02"))

    signals = []
    for city_key in cities_list:
        city_info = CITIES.get(city_key, {})
        if not city_info:
            continue
        city_name = city_info.get("name", city_key)
        unit = city_info.get("unit", "fahrenheit")

        city_markets = markets_df[
            (markets_df["city"] == city_key) &
            (markets_df["target_date"] == pd.Timestamp(target_date))
        ]
        if len(city_markets) == 0:
            continue

        buckets = []
        for _, m in city_markets.iterrows():
            buckets.append({
                "temp": m["bucket_temp"],
                "temp_high": m.get("temp_high", m["bucket_temp"]),
                "is_lower": m["is_lower"],
                "is_upper": m["is_upper"],
                "label": m["bucket_label"],
            })

        probs, dist = predictor.predict_buckets(city_key, target_date, buckets)

        city_signals = []
        for _, m in city_markets.iterrows():
            label = m["bucket_label"]
            market_price = m["yes_price"]
            if market_price is None or market_price <= 0.01 or market_price >= 0.95:
                continue

            model_prob = probs.get(label, 0.0)
            edge = model_prob - market_price

            if edge >= CONFIG.min_edge:
                ev = (model_prob * (CONFIG.bet_size / market_price - CONFIG.bet_size * (1 + polymarket_fee))
                      + (1 - model_prob) * (-CONFIG.bet_size * (1 + polymarket_fee)))
                city_signals.append({
                    "city": city_key,
                    "city_name": city_name,
                    "target_date": date_str,
                    "bucket_label": label,
                    "bucket_temp": m["bucket_temp"],
                    "market_price": round(market_price, 4),
                    "model_prob": round(model_prob, 4),
                    "edge": round(edge, 4),
                    "bet_size": CONFIG.bet_size,
                    "expected_pnl": round(ev, 2),
                    "clob_token_yes": m.get("clob_token_yes"),
                    "market_id": m.get("market_id"),
                    "unit": unit,
                })

        # Take top N by edge
        city_signals.sort(key=lambda x: x["edge"], reverse=True)
        signals.extend(city_signals[:CONFIG.max_bets_per_city])

    # Log signals
    if signals:
        logger.info(f"Strategy #2: {len(signals)} signal(s) for {date_str}")
        for s in signals:
            deg = "\u00b0F" if s["unit"] == "fahrenheit" else "\u00b0C"
            logger.info(f"  {s['city_name']} {s['bucket_label']}{deg} "
                        f"model={s['model_prob']:.1%} market={s['market_price']:.1%} "
                        f"edge={s['edge']:+.1%}")
    else:
        logger.info(f"Strategy #2: No signals for {date_str}")

    # Save signals
    os.makedirs(CONFIG.results_dir, exist_ok=True)
    if signals:
        import pandas as pd
        sig_path = os.path.join(CONFIG.results_dir,
                                 f"signals_{date_str.replace('-', '')}.csv")
        pd.DataFrame(signals).to_csv(sig_path, index=False)

    # Record to trade history (for PnL tracking)
    polymarket_fee = float(os.getenv("POLYMARKET_FEE", "0.02"))
    os.makedirs(CONFIG.data_dir, exist_ok=True)
    history_path = os.path.join(CONFIG.data_dir, "weather_trades.jsonl")
    with open(history_path, "a") as f:
        for s in signals:
            record = {
                **s,
                "timestamp": datetime.now(SGT).isoformat(),
                "preview": CONFIG.preview_mode,
                "resolved": False,
                "won": None,
                "pnl": None,
                "cost": CONFIG.bet_size * (1 + polymarket_fee),
            }
            f.write(json.dumps(record) + "\n")

    return signals


# -- Strategy #3: Tennis Odds Arbitrage --

_tennis_strategy = None
_tennis_engine = None


def _init_tennis_strategy():
    """Initialize the Tennis Arb strategy instance."""
    global _tennis_strategy
    from src.tennis.tennis_arb import TennisArbStrategy
    from src.tennis.discovery_cache import PMDiscoveryCache
    from src.copy_trading.clob_client import create_clob_client

    tennis_tournaments = [t.strip() for t in CONFIG.tennis_tournaments.split(",")]

    # Share the same singleton CLOB client used by Strategy #1 so we don't
    # derive API creds twice. Returns None when no PRIVATE_KEY is set, in
    # which case live tennis BUY/SELL just gets skipped at scan time.
    clob_client = create_clob_client()

    _tennis_strategy = TennisArbStrategy(
        min_divergence=CONFIG.tennis_min_divergence,
        max_bet_size=CONFIG.tennis_max_bet_size,
        kelly_fraction=CONFIG.tennis_kelly_fraction,
        tournaments=tennis_tournaments,
        min_volume=CONFIG.tennis_min_polymarket_volume,
        min_liquidity=CONFIG.tennis_min_polymarket_liquidity,
        preview_mode=CONFIG.preview_mode,
        data_dir=CONFIG.data_dir,
        take_profit_ratio=CONFIG.tennis_take_profit_ratio,
        min_bet_size=CONFIG.min_order_size_usd,
        clob_client=clob_client,
        revalidation_min_divergence=CONFIG.tennis_revalidation_min_divergence,
    )

    # Background discovery cache. Hydrated immediately on .start(); the
    # per-scan loop in Batch 3 will read its active_set() instead of
    # calling Gamma directly. For Batch 2 the cache is observable via
    # logs but not yet consumed.
    _tennis_strategy.discovery_cache = PMDiscoveryCache(
        smarkets_provider=_tennis_strategy._provider,
        tours=tennis_tournaments,
        max_event_date_delta_days=_tennis_strategy.max_event_date_delta_days,
        refresh_interval_s=600.0,
    )
    _tennis_strategy.discovery_cache.start()

    return _tennis_strategy


def run_strategy3() -> list[dict]:
    """Run a single Strategy #3 scan."""
    global _tennis_strategy
    if _tennis_strategy is None:
        _init_tennis_strategy()
    return _tennis_strategy.scan()


def force_resolve_tennis() -> None:
    """Force-run paper-book resolution; called by /tennis_pnl on demand."""
    global _tennis_strategy
    if _tennis_strategy is None:
        _init_tennis_strategy()
    _tennis_strategy.force_resolve_open_positions()


def refresh_tennis_clob_client() -> None:
    """Rebuild the singleton CLOB client and re-bind it to the tennis strategy.

    Called by the Telegram /setkey command. After the in-memory private key
    has changed, the CLOB client cached on TennisArbStrategy points at an
    auth context built from the old key; updating the reference here lets
    the change take effect on the next scan without a process restart.
    """
    global _tennis_strategy
    from src.copy_trading.clob_client import create_clob_client, reset_clob_client

    reset_clob_client()
    new_client = create_clob_client()  # may be None if key was cleared
    if _tennis_strategy is not None:
        _tennis_strategy.clob_client = new_client


def _tennis_scanner_loop():
    """Periodically scan for tennis arb opportunities at TENNIS_SCAN_INTERVAL.

    The discovery cache + per-scan active-set filter handles "are there live
    matches right now" — if not, scan returns empty almost instantly. So we
    don't need a match-windows gate any more; a steady 20s cadence is the
    intended baseline.
    """
    global _tennis_strategy
    if _tennis_strategy is None:
        _init_tennis_strategy()

    logger.info(f"Tennis arb scanner started (interval={CONFIG.tennis_scan_interval}s)")

    while not _shutdown_event.is_set():
        try:
            signals = _tennis_strategy.scan()
            if signals:
                telegram_bot.send_tennis_signals(signals)
        except Exception as e:
            logger.error(f"Tennis arb scan failed: {e}")
            telegram_bot.send_message(f"[TENNIS] Scan failed: <code>{e}</code>")

        _shutdown_event.wait(CONFIG.tennis_scan_interval)


def _copy_paper_loop():
    """Strategy 1b validation: forward paper-copy of watchlist wallets.

    Measures execution-realistic copy PnL (entries against the live book, net of
    drag) and tracks it to resolution. Places NO real orders — it is a
    measurement harness whose ledger gates whether any wallet earns real capital.
    """
    from src.copy_trading.copy_paper import report
    from src.copy_trading.copy_paper_runner import CopyPaperRunner

    def _on_cycle(summary, ledger):
        if summary.opened or summary.resolved:
            logger.info(
                f"[COPY-PAPER] opened={summary.opened} resolved={summary.resolved} "
                f"open={len(ledger.open_positions())} closed={len(ledger.closed_positions())}"
            )
        if summary.resolved:
            r = report(ledger)
            telegram_bot.send_message(
                f"[COPY-PAPER] {summary.resolved} resolved | "
                f"realized ${r['realized_pnl']:+.2f} ROI {r['realized_roi']:+.1%} "
                f"(drag ${r['execution_drag_cost']:.2f}, hit {r['hit_rate']:.0%}, "
                f"n={r['closed']})"
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
    )
    runner = DiscoveryRunner(
        config=cfg,
        watchlist_path=CONFIG.copy_paper_watchlist,   # feeds the paper harness
        state_path=CONFIG.wallet_discovery_state,
        cache_dir=CONFIG.wallet_discovery_cache_dir,
        activity_ttl_s=CONFIG.wallet_discovery_activity_ttl_s,
        cycle_interval_s=CONFIG.wallet_discovery_interval_s,
        notify=lambda msg: telegram_bot.send_message(msg),
    )
    runner.run_forever(_shutdown_event)


def _tennis_stream_mode() -> str:
    """Decide between the event-driven stream and the legacy scan loop.

    Returns "stream" only when RTDS is on AND at least one streaming sharp
    provider is fully configured AND the RTDS WS URL is set. Otherwise
    "legacy" — the proven scan loop. This is the fail-safe: deploying before
    the BetsAPI/Pinnacle/RTDS creds are set leaves prod behaviour unchanged.
    """
    if not CONFIG.polymarket_use_rtds:
        return "legacy"  # non-negotiable kill switch (§4)
    mode = (CONFIG.tennis_sharp_provider or "").strip().lower()
    if "betsapi" not in mode and "pinnacle" not in mode:
        # smarkets-only (or unrecognised) → old Smarkets path unchanged (§9.6)
        return "legacy"
    streamable = []
    if "betsapi" in mode and CONFIG.betsapi_token:
        streamable.append("betsapi")
    if "pinnacle" in mode and CONFIG.pinnacle_rapidapi_key:
        streamable.append("pinnacle")
    if not streamable or not CONFIG.polymarket_rtds_ws_url:
        logger.warning(
            f"Tennis: stream requested (provider={mode}, RTDS on) but creds/URL "
            f"incomplete (betsapi_token={bool(CONFIG.betsapi_token)}, "
            f"pinnacle_key={bool(CONFIG.pinnacle_rapidapi_key)}, "
            f"rtds_ws_url={bool(CONFIG.polymarket_rtds_ws_url)}) — "
            f"falling back to legacy scan loop"
        )
        return "legacy"
    return "stream"


def _tennis_stream_loop():
    """Run the event-driven streaming engine on a dedicated asyncio loop.

    Lives on its own daemon thread (like the scanner loop) so it doesn't
    contend with Strategy #1's main asyncio task.
    """
    global _tennis_strategy, _tennis_engine
    if _tennis_strategy is None:
        _init_tennis_strategy()

    from src.tennis.tennis_arb import build_tennis_stream_engine

    engine = build_tennis_stream_engine(
        _tennis_strategy, on_signals=telegram_bot.send_tennis_signals
    )
    _tennis_engine = engine
    logger.info("Tennis arb streaming engine started")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _supervise():
        engine_task = asyncio.create_task(engine.run())
        # Watch the cross-thread shutdown Event and stop the engine cleanly.
        while not _shutdown_event.is_set() and not engine_task.done():
            await asyncio.sleep(1.0)
        engine.stop()
        engine_task.cancel()
        try:
            await engine_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    try:
        loop.run_until_complete(_supervise())
    except Exception as e:  # noqa: BLE001
        logger.error(f"Tennis streaming engine crashed: {e}")
        telegram_bot.send_message(f"[TENNIS] Streaming engine crashed: <code>{e}</code>")
    finally:
        loop.close()


# -- Scheduler --

def _scheduler_loop():
    """Run Strategy #2 daily at the configured SGT time."""
    last_run_date = None

    while not _shutdown_event.is_set():
        now = datetime.now(SGT)
        today = now.date()

        # Check if it's time to run
        target_time = now.replace(hour=CONFIG.schedule_hour_sgt,
                                   minute=CONFIG.schedule_minute_sgt,
                                   second=0, microsecond=0)

        if (now >= target_time and last_run_date != today):
            last_run_date = today
            logger.info(f"Scheduled run triggered at {now.strftime('%H:%M SGT')}")

            target_date = datetime(
                (today + timedelta(days=CONFIG.days_in_advance)).year,
                (today + timedelta(days=CONFIG.days_in_advance)).month,
                (today + timedelta(days=CONFIG.days_in_advance)).day,
            )

            try:
                signals = run_strategy2(target_date)
                telegram_bot.send_strategy2_signals(
                    signals, target_date.strftime("%Y-%m-%d")
                )
            except Exception as e:
                logger.error(f"Scheduled run failed: {e}")
                telegram_bot.send_message(f"Scheduled run failed: <code>{e}</code>")

        # Sleep 30s between checks
        _shutdown_event.wait(30)


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
    """Main entry point — runs all enabled strategies."""
    parser = argparse.ArgumentParser(description="Unified Trading Bot")
    parser.add_argument("--once", action="store_true",
                        help="Run Strategy #2 once and exit")
    parser.add_argument("--date", type=str, default=None,
                        help="Target date for --once mode (YYYY-MM-DD)")
    args = parser.parse_args()

    _setup_logging()

    cities_list = [c.strip() for c in CONFIG.cities_to_bet.split(",")]
    tennis_tournaments = [t.strip() for t in CONFIG.tennis_tournaments.split(",")]

    logger.info("=" * 60)
    logger.info("  Polymarket Trading Bot (Unified Python)")
    logger.info(f"  Strategy #1 (Copy Trading): {'ENABLED' if CONFIG.strategy1_enabled else 'DISABLED'}")
    logger.info(f"  Strategy #2 (Weather):      {'ENABLED' if CONFIG.strategy2_enabled else 'DISABLED'}")
    logger.info(f"  Strategy #3 (Tennis Arb):   {'ENABLED' if CONFIG.strategy3_enabled else 'DISABLED'}")
    logger.info(f"  Preview mode: {CONFIG.preview_mode}")
    logger.info(f"  Schedule: {CONFIG.schedule_hour_sgt:02d}:{CONFIG.schedule_minute_sgt:02d} SGT daily")
    logger.info(f"  Cities: {', '.join(cities_list)}")
    logger.info(f"  Days ahead: {CONFIG.days_in_advance}")
    if CONFIG.strategy3_enabled:
        logger.info(f"  Tennis scan interval: {CONFIG.tennis_scan_interval}s")
        logger.info(f"  Tennis min divergence: {CONFIG.tennis_min_divergence:.0%}")
        logger.info(f"  Tennis take-profit ratio: ×{CONFIG.tennis_take_profit_ratio:g}")
        logger.info(f"  Tennis tournaments: {', '.join(tennis_tournaments)}")
    logger.info("=" * 60)

    # Single run mode
    if args.once:
        if args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d")
        else:
            today = datetime.now(SGT).date()
            td = today + timedelta(days=CONFIG.days_in_advance)
            target_date = datetime(td.year, td.month, td.day)

        signals = run_strategy2(target_date)
        if telegram_bot.is_configured():
            telegram_bot.send_strategy2_signals(
                signals, target_date.strftime("%Y-%m-%d")
            )
        return

    # Register prediction callback for telegram
    telegram_bot.on_predict_request = run_strategy2

    # Register tennis scan callback for telegram
    telegram_bot.on_tennis_scan_request = run_strategy3
    # /tennis_pnl runs the paper-book resolve loop on demand so the report
    # picks up matches that settled between scheduled resolve ticks.
    telegram_bot.on_tennis_resolve_request = force_resolve_tennis
    # Register CLOB-client refresher so /setkey can rotate the in-memory
    # private key and have the change apply immediately to live trading.
    telegram_bot.on_refresh_clob_client = refresh_tennis_clob_client

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
        "<b>Bot Started (Unified Python)</b>\n"
        f"Strategy #1 (Copy): {'ON' if CONFIG.strategy1_enabled else 'OFF'}\n"
        f"Strategy #2 (Weather): {'ON' if CONFIG.strategy2_enabled else 'OFF'}\n"
        f"Strategy #3 (Tennis): {'ON' if CONFIG.strategy3_enabled else 'OFF'}\n"
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}\n"
        f"Schedule: {CONFIG.schedule_hour_sgt:02d}:{CONFIG.schedule_minute_sgt:02d} SGT\n"
        f"Cities: {', '.join(cities_list)}"
    )

    # Start Strategy #2 scheduler in a thread
    if CONFIG.strategy2_enabled:
        scheduler_thread = threading.Thread(
            target=_scheduler_loop, daemon=True, name="scheduler"
        )
        scheduler_thread.start()
        logger.info("Strategy #2 scheduler started")

    # Start Strategy #3 in a thread — event-driven stream when fully
    # configured, otherwise the proven legacy scan loop (fail-safe).
    if CONFIG.strategy3_enabled:
        mode = _tennis_stream_mode()
        if mode == "stream":
            tennis_thread = threading.Thread(
                target=_tennis_stream_loop, daemon=True, name="tennis-stream"
            )
            tennis_thread.start()
            logger.info(
                f"Tennis arb streaming engine started (provider={CONFIG.tennis_sharp_provider})"
            )
        else:
            tennis_thread = threading.Thread(
                target=_tennis_scanner_loop, daemon=True, name="tennis-scanner"
            )
            tennis_thread.start()
            logger.info("Tennis arb scanner started (legacy scan loop)")
    else:
        logger.info("Strategy #3 disabled, skipping tennis arb scanner")

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
            # Run copy trading as the main async task; it blocks until shutdown
            # Meanwhile, Strategy #2 and #3 run in daemon threads
            await run_copy_trading()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception(f"Strategy #1 crashed: {e}")
            telegram_bot.send_message(f"Strategy #1 crashed: <code>{e}</code>\n<i>Bot continues — Strategies #2/#3 still running.</i>")
            s1_crashed = True
    else:
        logger.info("Strategy #1 disabled, skipping copy-trader bot")

    # Keep alive whenever Strategy #1 isn't the main task — either it's
    # disabled, or it crashed. Strategies #2 and #3 run in daemon threads
    # and need the main thread to stay up so the container doesn't exit.
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
