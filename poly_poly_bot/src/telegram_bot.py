"""Unified Telegram bot for all three strategies.

Commands:
  /predict 11 Apr    — Run prediction for a specific date (Strategy #2)
  /predict           — Run prediction for default date (today + days_in_advance)
  /status            — Show bot status for all strategies
  /pnl               — Show P&L: realized + unrealized (all strategies)
  /history           — Show last 10 copy trades (Strategy #1)
  /takeprofit        — Close all positions with unrealized PnL > 30%
  /tennis            — Show current tennis divergences (Strategy #3)
  /tennis_pnl        — Tennis paper-book PnL with breakdown by event
  /help              — Show available commands
"""

import os
import re
import json
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

import requests

from src.config import CONFIG

logger = logging.getLogger("telegram")

SGT = timezone(timedelta(hours=8))

# Take-profit threshold: close when unrealized PnL > this % of cost
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.30"))

# Polymarket fee (2%)
POLYMARKET_FEE = float(os.getenv("POLYMARKET_FEE", "0.02"))


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TELEGRAM_API = "https://api.telegram.org/bot{token}"

_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()

# Callbacks set by main.py
on_predict_request = None   # Callable[[datetime], list[dict]]
on_sell_positions = None    # Callable[[list[dict]], list[dict]]
on_tennis_scan_request = None  # Callable[[], list[dict]]
on_tennis_resolve_request = None  # Callable[[], None] — force-resolve paper positions before /tennis_pnl
on_refresh_clob_client = None  # Callable[[], None] — rebuild CLOB client after /setkey


def is_configured() -> bool:
    """Check if Telegram bot is configured."""
    return bool(CONFIG.telegram_bot_token) and bool(CONFIG.telegram_chat_id)


def send_message(text: str, parse_mode: str = "HTML"):
    """Send a message to the configured Telegram chat."""
    if not is_configured():
        return
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": CONFIG.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }, timeout=10)
        if not resp.ok:
            logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")


def _send_chunked(text: str, parse_mode: str = "HTML", chunk_size: int = 3800):
    """Send a potentially long message as multiple Telegram messages.

    Splits on newline boundaries. We rely on the convention that HTML tags
    used here (<b>, <code>, <i>) open and close on the same line, so a split
    between lines won't tear a tag.
    """
    if len(text) <= chunk_size:
        send_message(text, parse_mode=parse_mode)
        return

    buf: list[str] = []
    cur = 0
    for line in text.split("\n"):
        ln = len(line) + 1  # +1 for the newline we re-insert
        if buf and cur + ln > chunk_size:
            send_message("\n".join(buf), parse_mode=parse_mode)
            buf = []
            cur = 0
        buf.append(line)
        cur += ln
    if buf:
        send_message("\n".join(buf), parse_mode=parse_mode)


def send_strategy2_signals(signals: list[dict], target_date: str):
    """Send Strategy #2 prediction results to Telegram."""
    if not signals:
        send_message(
            f"<b>Strategy #2 — Weather</b>\n"
            f"Target: {target_date}\n"
            f"No signals above {CONFIG.min_edge:.0%} edge threshold."
        )
        return

    lines = [
        f"<b>Strategy #2 — Weather Prediction</b>",
        f"Target: <b>{target_date}</b>",
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}",
        f"Edge threshold: {CONFIG.min_edge:.0%} | Bet: ${CONFIG.bet_size:.0f}",
        "",
    ]

    total_ev = 0
    for s in signals:
        deg = "\u00b0F" if s.get("unit") == "fahrenheit" else "\u00b0C"
        emoji = "\U0001f7e2" if s["edge"] >= 0.10 else "\U0001f7e1"
        bucket = _esc(s['bucket_label'])
        lines.append(
            f"{emoji} <b>{_esc(s['city_name'])}</b> {bucket}{deg}\n"
            f"   Model: {s['model_prob']:.1%}  Market: {s['market_price']:.1%}  "
            f"Edge: <b>{s['edge']:+.1%}</b>  EV: ${s.get('expected_pnl', 0):.2f}"
        )
        total_ev += s.get("expected_pnl", 0)

    lines.append(f"\nTotal signals: {len(signals)} | Total EV: ${total_ev:.2f}")
    send_message("\n".join(lines))


def send_tennis_signals(signals: list[dict]):
    """Send Strategy #3 tennis arb signals to Telegram."""
    if not signals:
        return

    preview = signals[0].get("preview", True) if signals else True
    lines = [
        f"<b>{'[PREVIEW] ' if preview else ''}Strategy #3 — Tennis Arb</b>",
        f"Signals: {len(signals)} | Threshold: {CONFIG.tennis_min_divergence:.0%}",
        "",
    ]

    for s in signals:
        outcome = s.get("outcome_label") or s.get("target_player") or ""
        event_title = s.get("event_title") or s.get("tournament", "")
        question = s.get("polymarket_question", "")
        url = s.get("polymarket_url", "")
        match_time = s.get("match_time", "") or ""
        match_time_short = match_time.replace("T", " ")[:16] if match_time else ""

        # Take-profit events skip the divergence-signal layout — there's no
        # new bet, just a fix-profit close on an existing position.
        if s.get("paper_action") == "TAKE_PROFIT":
            realized = s.get("paper_realized_pnl_usd")
            realized_str = (
                f" — realized <b>${realized:+.2f}</b>" if realized is not None else ""
            )
            entry = float(s.get("entry_price") or 0.0)
            exitp = float(s.get("exit_price") or 0.0)
            ratio = s.get("ratio") or (exitp / entry if entry > 0 else 0.0)
            block = [
                f"[TENNIS] 🎯 <b>Take-profit: {_esc(outcome)}</b>"
                + (f"  ({_esc(match_time_short)} UTC)" if match_time_short else ""),
                f"  Tournament: {_esc(s.get('tournament', ''))}",
                f"  PM event: <b>{_esc(event_title)}</b>",
                f"  Closed YES @ {exitp:.1%} (entry {entry:.1%}, ×{ratio:.2f})"
                f"{realized_str}",
            ]
            if url:
                block.append(f'  <a href="{_esc(url)}">Polymarket link</a>')
            lines.append("\n".join(block))
            lines.append("")
            continue

        block = [
            f"[TENNIS] <b>{_esc(s['player_a'])} vs {_esc(s['player_b'])}</b>"
            + (f"  ({_esc(match_time_short)} UTC)" if match_time_short else ""),
            f"  Tournament: {_esc(s.get('tournament', ''))}",
            f"  PM event: <b>{_esc(event_title)}</b>",
        ]
        if question:
            block.append(f"  Resolves: {_esc(question)}")
        block.append(
            f"  Bet: <b>{s['side']} {_esc(outcome)}</b> @ "
            f"${s['bet_size']:.0f} (price {s['polymarket_price']:.1%})"
        )
        block.append(
            f"  Sharp: {s['sharp_prob']:.1%}  |  PM: {s['polymarket_price']:.1%}  |  "
            f"Edge: <b>{s['divergence']:+.1%}</b>"
        )
        if url:
            block.append(f'  <a href="{_esc(url)}">Polymarket link</a>')

        # Live-order status (set by tennis_arb.py for every signal). Surfaces
        # whether the real CLOB order was placed, skipped, or failed so the
        # alert isn't ambiguous about what actually hit the exchange.
        live_status = s.get("live_status")
        if live_status == "placed":
            block.append(
                f"  🟢 LIVE: BUY YES {s.get('live_shares', 0)}@"
                f"{(s.get('live_order_price') or 0):.4f} "
                f"order=<code>{_esc(str(s.get('live_order_id', ''))[:16])}</code>"
            )
        elif live_status == "preview":
            block.append("  🟡 LIVE: skipped — preview mode")
        elif isinstance(live_status, str) and live_status.startswith("skipped:"):
            block.append(f"  🟡 LIVE: {_esc(live_status)}")
        elif isinstance(live_status, str) and live_status.startswith("failed:"):
            block.append(f"  ❌ LIVE: {_esc(live_status)}")

        # Paper-book note: shows what the book did with this signal
        # (OPEN a fresh position, FLIP-close the previous one and re-enter
        # on the other side, or HOLD because we're already long it).
        paper_action = s.get("paper_action")
        if paper_action == "OPEN":
            block.append(
                f"  📒 Paper book: OPEN — long {_esc(outcome)} YES "
                f"@ {s['polymarket_price']:.1%} ${s['bet_size']:.2f}"
            )
        elif paper_action == "FLIP":
            realized = s.get("paper_realized_pnl_usd")
            realized_str = (
                f" — realized <b>${realized:+.2f}</b>" if realized is not None else ""
            )
            block.append(
                f"  📒 Paper book: FLIP — closed previous YES{realized_str}, "
                f"now long {_esc(outcome)} YES @ {s['polymarket_price']:.1%} "
                f"${s['bet_size']:.2f}"
            )
        elif paper_action == "HOLD":
            block.append("  📒 Paper book: HOLD (already long this side)")

        lines.append("\n".join(block))
        lines.append("")

    send_message("\n".join(lines).rstrip())


def _load_s3_trades() -> list[dict]:
    """Load Strategy #3 tennis trade history."""
    history_path = os.path.join(CONFIG.data_dir, "tennis_trades.jsonl")
    if not os.path.exists(history_path):
        return []
    trades = []
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return trades


# --- Live price fetching ---

def _fetch_midpoint(token_id: str) -> float | None:
    """Fetch current midpoint price for a YES token from CLOB API."""
    try:
        resp = requests.get(
            f"{CONFIG.clob_api_url}/midpoint",
            params={"token_id": token_id},
            timeout=5,
        )
        if resp.ok:
            data = resp.json()
            mid = data.get("mid")
            if mid is not None:
                return float(mid)
    except Exception as e:
        logger.debug(f"Midpoint fetch failed for {token_id[:20]}...: {e}")
    return None


def _load_s2_trades() -> list[dict]:
    """Load Strategy #2 trade history."""
    history_path = os.path.join(CONFIG.data_dir, "weather_trades.jsonl")
    if not os.path.exists(history_path):
        return []
    trades = []
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return trades


def _load_s1_trades() -> list[dict]:
    """Load Strategy #1 copy trading trade history."""
    history_path = os.path.join(CONFIG.data_dir, "trade-history.jsonl")
    if not os.path.exists(history_path):
        return []
    trades = []
    with open(history_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return trades


def _enrich_with_live_prices(trades: list[dict]) -> list[dict]:
    """Add current_price and unrealized PnL to each trade."""
    for t in trades:
        token_id = t.get("clob_token_yes")
        entry_price = t.get("market_price") or 0
        cost = t.get("cost") or (t.get("bet_size", CONFIG.bet_size) * (1 + POLYMARKET_FEE))
        bet_size = t.get("bet_size", CONFIG.bet_size)

        if entry_price > 0:
            shares = bet_size / entry_price
        else:
            shares = 0

        t["shares"] = round(shares, 2)
        t["entry_price"] = entry_price
        t["cost"] = cost

        # Fetch live price
        current_price = None
        if token_id:
            current_price = _fetch_midpoint(token_id)

        if current_price is not None:
            t["current_price"] = current_price
            # If we sold now: revenue = shares * current_price, minus sell fee
            sell_revenue = shares * current_price * (1 - POLYMARKET_FEE)
            t["unrealized_pnl"] = round(sell_revenue - cost, 2)
            t["unrealized_pct"] = round((sell_revenue - cost) / cost, 4) if cost > 0 else 0
        else:
            t["current_price"] = None
            t["unrealized_pnl"] = None
            t["unrealized_pct"] = None

    return trades


# --- Command handlers ---

def _parse_date_from_text(text: str) -> datetime | None:
    """Parse date from telegram command text like '11 Apr' or '2026-04-11'."""
    text = text.strip()

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
    }

    m = re.match(r'(\d{1,2})\s+([A-Za-z]+)', text)
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()
        month = month_map.get(month_str)
        if month:
            now = datetime.now(SGT)
            year = now.year
            try:
                dt = datetime(year, month, day)
                if dt.date() < now.date():
                    dt = datetime(year + 1, month, day)
                return dt
            except ValueError:
                pass

    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    return None


def _handle_command(text: str):
    """Process a telegram command."""
    text = text.strip()

    if text.startswith("/predict"):
        _handle_predict(text)
    elif text.startswith("/tennis_pnl"):
        # /tennis_pnl must come BEFORE /tennis because startswith matches.
        _handle_tennis_pnl()
    elif text.startswith("/tennis"):
        _handle_tennis()
    elif text.startswith("/history"):
        _handle_history()
    elif text.startswith("/status"):
        _handle_status()
    elif text.startswith("/pnl"):
        _handle_pnl()
    elif text.startswith("/takeprofit"):
        _handle_takeprofit()
    elif text.startswith("/mode"):
        _handle_mode()
    elif text.startswith("/live"):
        _handle_live(text)
    elif text.startswith("/preview"):
        _handle_preview(text)
    elif text.startswith("/check"):
        _handle_check()
    elif text.startswith("/test-live"):
        _handle_test_live()
    elif text.startswith("/setkey"):
        _handle_setkey(text)
    elif text.startswith("/shutdown"):
        _handle_shutdown(text)
    elif text.startswith("/help") or text.startswith("/start"):
        _handle_help()
    else:
        return


def _handle_predict(text: str):
    """Handle /predict command."""
    parts = text.split(maxsplit=1)
    if len(parts) > 1:
        target_date = _parse_date_from_text(parts[1])
        if not target_date:
            send_message(f"Could not parse date: <code>{parts[1]}</code>\nFormat: <code>/predict 11 Apr</code>")
            return
    else:
        today = datetime.now(SGT).date()
        target_date = datetime(
            (today + timedelta(days=CONFIG.days_in_advance)).year,
            (today + timedelta(days=CONFIG.days_in_advance)).month,
            (today + timedelta(days=CONFIG.days_in_advance)).day,
        )

    date_str = target_date.strftime("%Y-%m-%d")
    send_message(f"Running prediction for <b>{date_str}</b>...")

    if on_predict_request:
        try:
            signals = on_predict_request(target_date)
            send_strategy2_signals(signals, date_str)
        except Exception as e:
            logger.exception("Prediction failed")
            send_message(f"Prediction failed: <code>{_esc(str(e))}</code>")
    else:
        send_message("Prediction handler not configured.")


def _handle_status():
    """Handle /status command — show status for all three strategies."""
    from src import runtime_state

    now = datetime.now(SGT)
    cities_list = [c.strip() for c in CONFIG.cities_to_bet.split(",")]
    tennis_tournaments = [t.strip() for t in CONFIG.tennis_tournaments.split(",")]
    modes = runtime_state.all_modes()

    lines = [
        f"<b>Bot Status</b>",
        f"Time: {now.strftime('%Y-%m-%d %H:%M SGT')}",
        f"Mode: #1 {'PREVIEW' if modes.get(1, True) else 'LIVE'} | "
        f"#2 {'PREVIEW' if modes.get(2, True) else 'LIVE'} | "
        f"#3 {'PREVIEW' if modes.get(3, True) else 'LIVE'}",
        "",
    ]

    # Strategy #1 — Copy Trading
    lines.append(f"<b>Strategy #1 — Copy Traders</b>")
    if CONFIG.strategy1_enabled:
        lines.append("Status: \U0001f7e2 ENABLED")
        lines.append(f"Wallets tracked: {len(CONFIG.user_addresses)}")
        lines.append(f"Copy strategy: {CONFIG.copy_strategy}")
        lines.append(f"Copy size: ${CONFIG.copy_size:.0f}")
        # Try to show balance
        s1_trades = _load_s1_trades()
        if s1_trades:
            total_cost = sum((t.get("cost") or 0) for t in s1_trades)
            lines.append(f"Total deployed: ${total_cost:.2f}")
            lines.append(f"Total trades: {len(s1_trades)}")
    else:
        lines.append("Status: \u26aa DISABLED")

    lines.append("")
    lines.append(f"<b>Strategy #2 — Weather Betting</b>")
    if CONFIG.strategy2_enabled:
        lines.append("Status: \U0001f7e2 ENABLED")
        lines.append(f"Cities: {', '.join(cities_list)}")
        lines.append(f"Days ahead: {CONFIG.days_in_advance}")
        lines.append(f"Min edge: {CONFIG.min_edge:.0%} | Bet: ${CONFIG.bet_size:.0f}")
    else:
        lines.append("Status: \u26aa DISABLED")

    lines.append("")
    lines.append(f"<b>Strategy #3 — Tennis Arb</b>")
    if CONFIG.strategy3_enabled:
        lines.append("Status: \U0001f7e2 ENABLED")
        lines.append(f"Tournaments: {', '.join(tennis_tournaments)}")
        lines.append(f"Min divergence: {CONFIG.tennis_min_divergence:.0%}")
        lines.append(f"Scan interval: {CONFIG.tennis_scan_interval}s")
        lines.append(f"Max bet: ${CONFIG.tennis_max_bet_size:.0f}")
        tennis_trades = _load_s3_trades()
        if tennis_trades:
            lines.append(f"Total signals: {len(tennis_trades)}")
    else:
        lines.append("Status: \u26aa DISABLED")

    signals_dir = CONFIG.results_dir
    if os.path.isdir(signals_dir):
        signal_files = sorted(
            [f for f in os.listdir(signals_dir) if f.startswith("signals_")],
            reverse=True,
        )[:3]
        if signal_files:
            lines.append(f"\nRecent signals: {', '.join(signal_files)}")

    send_message("\n".join(lines))


def _handle_pnl():
    """Handle /pnl command — unified P&L report across all strategies."""
    lines = ["\U0001f4ca <b>P&amp;L Report</b>", ""]

    # Track totals for the summary
    grand_realized = 0.0
    grand_unrealized = 0.0
    grand_open_bets = 0

    # -- Strategy #1 (Copy Traders) --
    lines.append("<b>Strategy #1 — Copy Traders</b>")
    if CONFIG.strategy1_enabled:
        s1_trades = _load_s1_trades()
        s1_realized = sum((t.get("pnl") or 0) for t in s1_trades) if s1_trades else 0.0
        grand_realized += s1_realized
        lines.append(f"  Realized:    ${s1_realized:+.2f}")
        lines.append(f"  Unrealized:  $0.00")
        lines.append(f"  Open bets:   0")
    else:
        lines.append("  [disabled]")

    lines.append("")

    # -- Strategy #2 (Weather Betting) --
    lines.append("<b>Strategy #2 — Weather Betting</b>")
    trades = _load_s2_trades()

    if CONFIG.strategy2_enabled:
        if trades:
            send_message("\n".join(lines) + "\nFetching live prices...")

            # Enrich with live prices
            trades = _enrich_with_live_prices(trades)

            resolved = [t for t in trades if t.get("resolved")]
            open_positions = [t for t in trades if not t.get("resolved")]

            s2_realized = sum((t.get("pnl") or 0) for t in resolved)
            s2_unrealized = sum((t.get("unrealized_pnl") or 0) for t in open_positions
                                if t.get("unrealized_pnl") is not None)
            s2_open = len(open_positions)

            grand_realized += s2_realized
            grand_unrealized += s2_unrealized
            grand_open_bets += s2_open

            # Rebuild lines after interim message
            lines = ["\U0001f4ca <b>P&amp;L Report</b>", ""]

            # Re-add Strategy #1
            lines.append("<b>Strategy #1 \u2014 Copy Traders</b>")
            if CONFIG.strategy1_enabled:
                s1_trades_re = _load_s1_trades()
                s1_re = sum((t.get("pnl") or 0) for t in s1_trades_re) if s1_trades_re else 0.0
                lines.append(f"  Realized:    ${s1_re:+.2f}")
                lines.append("  Unrealized:  $0.00")
                lines.append("  Open bets:   0")
            else:
                lines.append("  [disabled]")
            lines.append("")

            lines.append("<b>Strategy #2 \u2014 Weather Betting</b>")
            lines.append(f"  Realized:    ${s2_realized:+.2f}")
            lines.append(f"  Unrealized:  ${s2_unrealized:+.2f}")
            lines.append(f"  Open bets:   {s2_open}")

            tp_candidates = sum(1 for t in open_positions
                                if t.get("unrealized_pct") is not None
                                and t.get("unrealized_pct") >= TAKE_PROFIT_PCT)
            if tp_candidates > 0:
                lines.append(f"  \U0001f3af {tp_candidates} position(s) above {TAKE_PROFIT_PCT:.0%} \u2014 /takeprofit")
        else:
            lines.append("  Realized:    $0.00")
            lines.append("  Unrealized:  $0.00")
            lines.append("  Open bets:   0")
    else:
        lines.append("  [disabled]")

    lines.append("")

    # -- Strategy #3 (Tennis Arb) --
    lines.append("<b>Strategy #3 \u2014 Tennis Arb</b>")
    if CONFIG.strategy3_enabled:
        tennis_trades = _load_s3_trades()
        if tennis_trades:
            total_bet = sum(t.get("bet_size", 0) for t in tennis_trades)
            preview_count = sum(1 for t in tennis_trades if t.get("preview"))
            live_count = len(tennis_trades) - preview_count
            avg_edge = sum(t.get("divergence", 0) for t in tennis_trades) / len(tennis_trades)

            lines.append(f"  Realized:    $0.00")
            lines.append(f"  Unrealized:  $0.00")
            lines.append(f"  Open bets:   {len(tennis_trades)} ({live_count} live, {preview_count} preview)")
            lines.append(f"  Total bet:   ${total_bet:.2f}")
            lines.append(f"  Avg edge:    {avg_edge:.1%}")

            grand_open_bets += len(tennis_trades)
        else:
            lines.append("  Realized:    $0.00")
            lines.append("  Unrealized:  $0.00")
            lines.append("  Open bets:   0")
    else:
        lines.append("  [disabled]")

    # -- Grand Total --
    lines.append("")
    lines.append("\u2500" * 14)
    lines.append("<b>TOTAL:</b>")
    lines.append(f"  Realized:    ${grand_realized:+.2f}")
    lines.append(f"  Unrealized:  ${grand_unrealized:+.2f}")
    lines.append(f"  Open bets:   {grand_open_bets}")
    net_pnl = grand_realized + grand_unrealized
    lines.append(f"  Net P&amp;L:     ${net_pnl:+.2f}")

    if CONFIG.preview_mode:
        lines.append(f"\n<i>PREVIEW MODE \u2014 positions are simulated</i>")

    send_message("\n".join(lines))


def _handle_history():
    """Handle /history command — show last 10 copy trades (Strategy #1)."""
    if not CONFIG.strategy1_enabled:
        send_message("Strategy #1 (Copy Trading) is disabled.")
        return

    trades = _load_s1_trades()
    if not trades:
        send_message("<b>Strategy #1 — Copy Trading History</b>\nNo trades yet.")
        return

    recent = trades[-10:]
    lines = [
        f"<b>Strategy #1 — Last {len(recent)} Copy Trades</b>",
        "",
    ]

    for t in reversed(recent):
        ts = t.get("timestamp", "?")
        if isinstance(ts, str) and len(ts) > 16:
            ts = ts[:16]
        market = _esc(t.get("market_question", t.get("market", "?"))[:40])
        side = t.get("side", "?")
        size = t.get("size_usd", t.get("cost", 0))
        price = t.get("price", 0)
        status = t.get("status", "?")
        pnl = t.get("pnl")

        pnl_str = f" | PnL: ${pnl:+.2f}" if pnl is not None else ""
        lines.append(
            f"<code>{ts}</code> {side} ${size:.1f} @ {price:.1%}\n"
            f"  {market}\n"
            f"  Status: {status}{pnl_str}"
        )

    send_message("\n".join(lines))


def _handle_takeprofit():
    """Close all positions with unrealized PnL > TAKE_PROFIT_PCT of cost."""
    trades = _load_s2_trades()
    open_positions = [t for t in trades if not t.get("resolved")]

    if not open_positions:
        send_message("No open positions to close.")
        return

    send_message(f"Checking {len(open_positions)} open position(s) for take-profit...")

    open_positions = _enrich_with_live_prices(open_positions)

    # Find candidates
    candidates = []
    for t in open_positions:
        unr_pct = t.get("unrealized_pct")
        if unr_pct is not None and unr_pct >= TAKE_PROFIT_PCT:
            candidates.append(t)

    if not candidates:
        send_message(
            f"No positions above {TAKE_PROFIT_PCT:.0%} take-profit threshold.\n\n"
            + _format_position_summary(open_positions)
        )
        return

    # Report what we'd close
    lines = [
        f"<b>Take Profit \u2014 {len(candidates)} position(s)</b>",
        f"Threshold: {TAKE_PROFIT_PCT:.0%} of cost",
        "",
    ]

    total_revenue = 0
    sell_orders = []
    for t in candidates:
        deg = "\u00b0F" if t.get("unit") == "fahrenheit" else "\u00b0C"
        bucket = _esc(t.get("bucket_label", "?"))
        city = _esc(t.get("city_name", t.get("city", "?")))
        current = t.get("current_price", 0)
        shares = t.get("shares", 0)
        cost = t.get("cost", 0)
        unr_pnl = t.get("unrealized_pnl", 0)
        unr_pct = t.get("unrealized_pct", 0)
        revenue = shares * current * (1 - POLYMARKET_FEE)
        total_revenue += revenue

        lines.append(
            f"\U0001f3af {city} {bucket}{deg} ({t.get('target_date', '?')})\n"
            f"   {shares:.1f} shares @ {t.get('entry_price', 0):.1%} \u2192 "
            f"{current:.1%} | PnL: ${unr_pnl:+.2f} ({unr_pct:+.0%})"
        )

        sell_orders.append({
            "tokenId": t.get("clob_token_yes"),
            "price": current,
            "size": shares,
            "side": "SELL",
            "meta": {
                "city": t.get("city_name", t.get("city")),
                "date": t.get("target_date"),
                "bucket": t.get("bucket_label"),
                "entry_price": t.get("entry_price"),
                "unrealized_pct": unr_pct,
            },
        })

    lines.append(f"\nTotal revenue: ~${total_revenue:.2f}")

    if CONFIG.preview_mode:
        lines.append(f"\n<i>PREVIEW MODE \u2014 orders NOT placed</i>")
        lines.append("Set PREVIEW_MODE=false to enable live selling.")
        # Still save the sell orders for reference
        orders_path = os.path.join(CONFIG.data_dir, "pending_sells.json")
        os.makedirs(CONFIG.data_dir, exist_ok=True)
        with open(orders_path, "w") as f:
            json.dump(sell_orders, f, indent=2)
        lines.append(f"Sell orders saved to pending_sells.json")
    else:
        # Live mode: trigger sell via callback
        if on_sell_positions and sell_orders:
            try:
                results = on_sell_positions(sell_orders)
                lines.append(f"\n\u2705 {len(results)} sell order(s) placed!")
            except Exception as e:
                lines.append(f"\n\u274c Sell failed: <code>{_esc(str(e))}</code>")
        else:
            # Write sell orders for execution
            orders_path = os.path.join(CONFIG.data_dir, "pending_sells.json")
            os.makedirs(CONFIG.data_dir, exist_ok=True)
            with open(orders_path, "w") as f:
                json.dump(sell_orders, f, indent=2)
            lines.append(f"\n\U0001f4dd {len(sell_orders)} sell order(s) written to pending_sells.json")
            lines.append("Execute via bot or manually.")

    send_message("\n".join(lines))


def _format_position_summary(positions: list[dict]) -> str:
    """Format a brief summary of current positions."""
    lines = ["Current positions:"]
    for t in positions:
        deg = "\u00b0F" if t.get("unit") == "fahrenheit" else "\u00b0C"
        bucket = _esc(t.get("bucket_label", "?"))
        city = _esc(t.get("city_name", t.get("city", "?")))
        unr_pct = t.get("unrealized_pct")
        pct_str = f"{unr_pct:+.0%}" if unr_pct is not None else "?"
        lines.append(f"  {city} {bucket}{deg}: {pct_str}")
    return "\n".join(lines)


def _handle_tennis():
    """Handle /tennis command — trigger a tennis arb scan and show results."""
    if not CONFIG.strategy3_enabled:
        send_message("Strategy #3 (Tennis Arb) is disabled.")
        return

    send_message("Scanning tennis divergences...")

    if on_tennis_scan_request:
        try:
            signals = on_tennis_scan_request()
            if signals:
                send_tennis_signals(signals)
            else:
                tennis_tournaments = [t.strip() for t in CONFIG.tennis_tournaments.split(",")]
                send_message(
                    "<b>Strategy #3 — Tennis Arb</b>\n"
                    f"No divergences above {CONFIG.tennis_min_divergence:.0%} threshold.\n"
                    f"Tournaments: {', '.join(tennis_tournaments)}"
                )
        except Exception as e:
            logger.exception("Tennis scan failed")
            send_message(f"Tennis scan failed: <code>{_esc(str(e))}</code>")
    else:
        send_message("Tennis scan handler not configured.")


STALE_OPEN_DAYS = 3


def _strip_tournament_prefix(s: str) -> str:
    """Drop the leading tournament tag from event/outcome strings.

    PM titles are formatted like ``"Internazionali BNL d'Italia: Aryna
    Sabalenka vs Sorana Cirstea"``; for the PnL report we only want the
    tail ("Aryna Sabalenka vs Sorana Cirstea") so the message stays
    skimmable.
    """
    if not s:
        return ""
    return s.split(": ", 1)[-1] if ": " in s else s


def _handle_tennis_pnl():
    """Handle /tennis_pnl — concise PnL summary + open positions list.

    Format:

        🎾 Tennis Paper Book — PnL
        Mode: LIVE/PREVIEW

        Realized overall: $X.XX
        Realized today: $X.XX
        Realized yesterday: $X.XX
        Unrealized: $X.XX

        Open positions
        • Sabalenka vs Cirstea — $13.07 on Sabalenka @ 88.5% → 92.0%

    Day boundaries are SGT (matches the codebase's other scheduled-job
    convention). In LIVE mode (preview=False) only ``live=True`` paper
    rows are counted; in PREVIEW everything counts.
    """
    if not CONFIG.strategy3_enabled:
        send_message("Strategy #3 (Tennis Arb) is disabled.")
        return

    try:
        from src.tennis.paper_book import TennisPaperBook
    except Exception as exc:
        send_message(f"Paper book not available: <code>{_esc(str(exc))}</code>")
        return

    # Opportunistic settlement before reporting. The strategy's scheduled
    # resolve tick runs every ~5 min; calling it on demand here means a
    # report fired right after a match ends shows the resolution rather
    # than a stale OPEN row.
    if on_tennis_resolve_request:
        try:
            on_tennis_resolve_request()
        except Exception:
            logger.exception("Tennis resolve before /tennis_pnl failed")

    book = TennisPaperBook(data_dir=CONFIG.data_dir)
    # Belt-and-braces: anything still open many days later is treated as
    # voided.
    book.void_stale_open_positions(max_age_days=STALE_OPEN_DAYS)

    from src import runtime_state
    live_only = not runtime_state.is_preview(3)

    def _live_match(p: dict) -> bool:
        return (not live_only) or bool(p.get("live"))

    open_positions = [p for p in book.open_positions() if _live_match(p)]
    closed_positions = [p for p in book.closed_positions() if _live_match(p)]

    # Mark-to-market: best-effort YES midpoint per open token.
    current_prices: dict[str, float] = {}
    for pos in open_positions:
        tid = pos.get("token_id") or ""
        if not tid:
            continue
        mid = _fetch_midpoint(tid)
        if mid is not None:
            current_prices[tid] = mid

    # Day buckets in SGT — matches the user's wall-clock day.
    now_sgt = datetime.now(SGT)
    today_start = now_sgt.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    realized_overall = 0.0
    realized_today = 0.0
    realized_yesterday = 0.0
    for p in closed_positions:
        pnl = float(p.get("realized_pnl_usd") or 0.0)
        realized_overall += pnl
        ca = p.get("closed_at") or ""
        if not ca:
            continue
        try:
            d = datetime.fromisoformat(ca)
        except ValueError:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        d_sgt = d.astimezone(SGT)
        if d_sgt >= today_start:
            realized_today += pnl
        elif d_sgt >= yesterday_start:
            realized_yesterday += pnl

    unrealized = 0.0
    for pos in open_positions:
        cur = current_prices.get(pos.get("token_id"))
        if cur is None:
            continue
        shares = float(pos.get("shares") or 0.0)
        entry = float(pos.get("entry_price") or 0.0)
        unrealized += shares * (float(cur) - entry)

    mode_label = "LIVE" if live_only else "PREVIEW"

    lines = [
        "🎾 <b>Tennis Paper Book — PnL</b>",
        f"<i>Mode: {mode_label}</i>",
        "",
        f"Realized overall: <b>${realized_overall:+.2f}</b>",
        f"Realized today: <b>${realized_today:+.2f}</b>",
        f"Realized yesterday: <b>${realized_yesterday:+.2f}</b>",
        f"Unrealized: <b>${unrealized:+.2f}</b>",
    ]

    if open_positions:
        lines.append("")
        lines.append(f"<b>Open positions ({len(open_positions)})</b>")
        for pos in open_positions:
            match = _esc(_strip_tournament_prefix(pos.get("event_title") or "?"))
            bet_on = _esc(_strip_tournament_prefix(pos.get("outcome_player") or "?"))
            size = float(pos.get("size_usd") or 0.0)
            entry = float(pos.get("entry_price") or 0.0)
            cur = current_prices.get(pos.get("token_id"))
            cur_str = f" → {cur:.1%}" if cur is not None else " → ?"
            lines.append(
                f"• {match} — ${size:.2f} on {bet_on} @ {entry:.1%}{cur_str}"
            )

    _send_chunked("\n".join(lines))


def _handle_mode():
    """Handle /mode — show preview/live mode per strategy."""
    from src import runtime_state

    modes = runtime_state.all_modes()
    s3_mode = modes.get(3, True)
    from src.config import get_private_key
    wallet_ok = bool(get_private_key())

    lines = [
        "<b>Strategy Modes</b>",
        f"  #1 Copy:    {'PREVIEW' if modes.get(1, True) else 'LIVE'}",
        f"  #2 Weather: {'PREVIEW' if modes.get(2, True) else 'LIVE'}",
        f"  #3 Tennis:  <b>{'PREVIEW' if s3_mode else 'LIVE'}</b>",
        "",
        f"Wallet (PRIVATE_KEY): {'configured' if wallet_ok else '<b>NOT configured</b>'}",
        "",
        "<i>Toggle Strategy #3:</i>",
        "<code>/live 3 CONFIRM</code> — switch to live (real orders)",
        "<code>/preview 3</code> — switch back to preview",
    ]
    send_message("\n".join(lines))


def _handle_live(text: str):
    """Handle /live N CONFIRM — switch a strategy to live."""
    from src import runtime_state

    parts = text.split()
    if len(parts) < 3 or parts[1] != "3" or parts[2] != "CONFIRM":
        send_message(
            "Usage: <code>/live 3 CONFIRM</code>\n"
            "Only Strategy #3 (Tennis) supports live toggle.\n"
            "<code>CONFIRM</code> token required to prevent fat-finger."
        )
        return

    runtime_state.set_preview(3, False)
    from src.config import get_private_key
    wallet_ok = bool(get_private_key())
    warn = "" if wallet_ok else "\n<b>Warning:</b> PRIVATE_KEY is empty — orders won't actually post until wallet is configured."
    send_message(f"Strategy #3 switched to <b>LIVE</b>. Real orders will be placed on next scan.{warn}")
    logger.warning("Strategy #3 switched to LIVE via Telegram /live command")


def _handle_preview(text: str):
    """Handle /preview N — switch a strategy back to preview."""
    from src import runtime_state

    parts = text.split()
    if len(parts) < 2 or parts[1] != "3":
        send_message(
            "Usage: <code>/preview 3</code>\n"
            "Only Strategy #3 (Tennis) supports preview/live toggle."
        )
        return

    runtime_state.set_preview(3, True)
    send_message("Strategy #3 switched to <b>PREVIEW</b>. No real orders will be placed.")
    logger.info("Strategy #3 switched to PREVIEW via Telegram /preview command")


def _handle_setkey(text: str):
    """Handle /setkey <hex|clear> CONFIRM — rotate or wipe the in-memory key.

    Safety lever to immediately disable signed orders if /preview 3 is
    insufficient. Change is in-memory only; on container restart the .env
    value reloads.
    """
    from src.config import set_private_key

    parts = text.split()
    # /setkey <hex|clear> CONFIRM  (3 tokens)
    if len(parts) != 3 or parts[2] != "CONFIRM":
        send_message(
            "Usage:\n"
            "<code>/setkey clear CONFIRM</code> — wipe in-memory key (no orders signable)\n"
            "<code>/setkey 0xABCD... CONFIRM</code> — replace key in memory\n"
            "Change is in-memory only; container restart reloads .env."
        )
        return

    arg = parts[1]
    if arg.lower() == "clear":
        set_private_key("")
        if on_refresh_clob_client:
            try:
                on_refresh_clob_client()
            except Exception as e:
                logger.exception("Refresh CLOB client failed")
                send_message(f"Key cleared but refresh failed: <code>{_esc(str(e))}</code>")
                return
        send_message(
            "🛑 Private key <b>cleared</b> in memory. "
            "CLOB client invalidated; tennis live trading cannot sign orders. "
            "Restart will reload the .env key."
        )
        logger.warning("PRIVATE_KEY cleared in memory via /setkey")
        return

    try:
        new_key = set_private_key(arg)
    except ValueError as e:
        send_message(f"Invalid key: <code>{_esc(str(e))}</code>")
        return

    if on_refresh_clob_client:
        try:
            on_refresh_clob_client()
        except Exception as e:
            logger.exception("Refresh CLOB client failed")
            send_message(f"Key updated but CLOB rebuild failed: <code>{_esc(str(e))}</code>")
            return

    # Derive EOA so user can sanity-check that the new key matches what
    # they intended. We do NOT echo the key itself.
    try:
        from web3 import Web3
        eoa = Web3().eth.account.from_key(f"0x{new_key}").address
    except Exception:
        eoa = "<unknown>"
    send_message(
        f"🔑 Private key <b>updated</b> in memory. New EOA: <code>{eoa}</code>. "
        "Restart will reload the .env key."
    )
    logger.warning(f"PRIVATE_KEY rotated in memory via /setkey (EOA={eoa})")


def _handle_shutdown(text: str):
    """Handle /shutdown CONFIRM — graceful process exit.

    Docker is configured with --restart unless-stopped, so the container
    will come back up automatically — but on restart it reloads from .env
    where PREVIEW_MODE=true is the default. To physically stop the
    container, SSH the VM and ``docker stop poly-poly-bot``.
    """
    parts = text.split()
    if len(parts) != 2 or parts[1] != "CONFIRM":
        send_message(
            "Usage: <code>/shutdown CONFIRM</code>\n"
            "Exits the bot process. Docker will restart it within seconds; "
            "the restart will read PREVIEW_MODE from .env (currently true). "
            "For permanent stop, SSH the VM and run "
            "<code>docker stop poly-poly-bot</code>."
        )
        return

    send_message("👋 Shutting down. Container will restart per Docker policy.")
    logger.warning("Bot shutdown requested via /shutdown")
    # Kick off the asyncio shutdown path used by SIGTERM. _shutdown_event is
    # the same flag the SIGTERM handler sets, so the rest of the cleanup
    # path runs as designed.
    import os
    import threading
    def _delayed_exit():
        # small delay so the Telegram send_message above gets flushed
        import time
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=_delayed_exit, daemon=True).start()


def _handle_check():
    """Handle /check — read-only verification of trading setup.

    Runs through PRIVATE_KEY, PROXY_WALLET, CLOB auth, USDC balance, and
    on-chain approvals on both Polymarket exchanges. Posts nothing on chain
    and submits no orders.
    """
    from src.config import CONFIG, get_private_key

    lines: list[str] = ["🔧 <b>Setup Check</b>", ""]
    ok_all = True

    # 1. Private key + derived EOA
    pk = get_private_key()
    eoa = ""
    if not pk:
        lines.append("❌ <b>PRIVATE_KEY</b>: not configured")
        send_message("\n".join(lines))
        return
    try:
        from web3 import Web3
        eoa = Web3().eth.account.from_key(f"0x{pk}").address
        lines.append(f"✅ PRIVATE_KEY → EOA <code>{eoa}</code>")
    except Exception as e:
        lines.append(f"❌ PRIVATE_KEY invalid: <code>{_esc(str(e))}</code>")
        send_message("\n".join(lines))
        return

    # 2. PROXY_WALLET
    proxy = CONFIG.proxy_wallet
    if not proxy:
        lines.append("❌ <b>PROXY_WALLET</b>: not set in .env")
        ok_all = False
    else:
        lines.append(f"✅ PROXY_WALLET <code>{proxy}</code>")

    # 3. SIGNATURE_TYPE
    sig_type = CONFIG.signature_type
    sig_label = {0: "EOA (no proxy)", 1: "POLY_PROXY (email login)", 2: "POLY_GNOSIS_SAFE (browser wallet)"}.get(sig_type, f"unknown({sig_type})")
    lines.append(f"   SIGNATURE_TYPE: {sig_type} — {sig_label}")

    # 4. USDC balance on proxy
    if proxy:
        try:
            from src.constants import ERC20_BALANCE_ABI, USDC_ADDRESS
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url))
            usdc = w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS),
                abi=ERC20_BALANCE_ABI,
            )
            raw = usdc.functions.balanceOf(Web3.to_checksum_address(proxy)).call()
            usdc_bal = raw / 1_000_000
            mark = "✅" if usdc_bal > 0 else "⚠️"
            lines.append(f"{mark} USDC balance: <b>${usdc_bal:.2f}</b>")
            if usdc_bal == 0:
                lines.append("   <i>Proxy is empty — fund it before going live.</i>")
                ok_all = False
        except Exception as e:
            lines.append(f"❌ USDC balance lookup failed: <code>{_esc(str(e))}</code>")
            ok_all = False

    # 5. CLOB authentication (read-only — derives API creds from L1 sig)
    clob_client = None
    try:
        from src.copy_trading.clob_client import create_clob_client
        clob_client = create_clob_client()
        if clob_client is None:
            lines.append("❌ CLOB client: not created (private key issue?)")
            ok_all = False
        else:
            lines.append("✅ CLOB client authenticated")
    except Exception as e:
        lines.append(f"❌ CLOB auth failed: <code>{_esc(str(e))}</code>")
        ok_all = False

    # 6. On-chain approvals (read-only)
    if proxy:
        try:
            from src.constants import (
                CTF_CONTRACT,
                CTF_EXCHANGE,
                ERC1155_APPROVAL_ABI,
                ERC20_APPROVE_ABI,
                NEG_RISK_CTF_EXCHANGE,
                USDC_ADDRESS,
            )
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(CONFIG.rpc_url))
            usdc = w3.eth.contract(
                address=Web3.to_checksum_address(USDC_ADDRESS),
                abi=ERC20_APPROVE_ABI,
            )
            ctf = w3.eth.contract(
                address=Web3.to_checksum_address(CTF_CONTRACT),
                abi=ERC1155_APPROVAL_ABI,
            )
            threshold = 10**6 * 10**6  # 1M USDC
            owner = Web3.to_checksum_address(proxy)
            for name, exchange in [("CTF", CTF_EXCHANGE), ("NegRisk", NEG_RISK_CTF_EXCHANGE)]:
                addr = Web3.to_checksum_address(exchange)
                allowance = usdc.functions.allowance(owner, addr).call()
                approved = ctf.functions.isApprovedForAll(owner, addr).call()
                u_ok = "✅" if allowance >= threshold else "❌"
                c_ok = "✅" if approved else "❌"
                lines.append(f"   {name}: USDC {u_ok}  CTF {c_ok}")
                if allowance < threshold or not approved:
                    ok_all = False
        except Exception as e:
            lines.append(f"❌ Approval check failed: <code>{_esc(str(e))}</code>")
            ok_all = False

    # 7. Authenticated CLOB read — confirms creds work end-to-end
    if clob_client is not None and proxy:
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            ba = clob_client.get_balance_allowance(params)
            lines.append(f"✅ CLOB /balance-allowance OK: {ba}")
        except Exception as e:
            lines.append(f"⚠️ CLOB authed read failed: <code>{_esc(str(e))}</code>")

    lines.append("")
    lines.append("<b>READY</b> ✅" if ok_all else "<b>NOT READY</b> ❌ — fix items above before /live 3 CONFIRM")
    _send_chunked("\n".join(lines))


def _handle_test_live():
    """Handle /test-live — fire a small live BUY on a soon-to-resolve geopolitics market.

    Smoke-tests the live trading path end-to-end: market discovery, CLOB
    auth, order construction, and order submission. Picks a binary
    geopolitics market with a side priced ≥90% and resolution within 48h
    so the round-trip P&L is bounded. The bet always posts in live mode
    regardless of the Strategy #3 preview flag — this is a deliberate
    test command, not a strategy signal.
    """
    from src.copy_trading.clob_client import create_clob_client
    from src.test_live import (
        DEFAULT_BET_SIZE_USD,
        MIN_FAVOURITE_PRICE,
        RESOLUTION_WINDOW_HOURS,
        find_test_market,
        place_test_bet,
    )

    send_message(
        f"🧪 <b>/test-live</b>: searching geopolitics markets resolving "
        f"in ≤{RESOLUTION_WINDOW_HOURS}h with a side ≥{MIN_FAVOURITE_PRICE:.0%}..."
    )

    candidate = find_test_market()
    if candidate is None:
        send_message(
            "🧪 <b>/test-live</b>: no eligible market found.\n"
            "Try again in a few minutes — geopolitics markets resolve all the time."
        )
        return

    clob_client = create_clob_client()
    if clob_client is None:
        send_message(
            "🧪 <b>/test-live</b>: ❌ CLOB client not available — set PRIVATE_KEY first."
        )
        return

    lines = [
        "🧪 <b>/test-live</b> — picked market:",
        f"  Event: <b>{_esc(candidate.event_title)}</b>",
        f"  Question: {_esc(candidate.question)}",
        f"  Resolves: <code>{_esc(candidate.end_iso)}</code>",
        f"  Side: <b>{candidate.favourite_side}</b> @ {candidate.favourite_price:.1%} "
        f"(ask {candidate.best_ask:.4f})",
    ]
    if candidate.polymarket_url:
        lines.append(f'  <a href="{_esc(candidate.polymarket_url)}">Polymarket link</a>')
    lines.append(f"  Posting <b>${DEFAULT_BET_SIZE_USD:.2f}</b> BUY now...")
    send_message("\n".join(lines))

    result = place_test_bet(clob_client=clob_client, candidate=candidate)
    status = result.get("status", "")

    if status == "placed":
        send_message(
            "🧪 <b>/test-live</b>: 🟢 <b>LIVE order placed</b>\n"
            f"  Order ID: <code>{_esc(str(result.get('order_id', '')))}</code>\n"
            f"  Shares: {result.get('shares', 0)}\n"
            f"  Limit price: {(result.get('order_price') or 0):.4f}\n"
            f"  Side: BUY {candidate.favourite_side}\n"
            f"  Token: <code>{_esc(candidate.favourite_token_id[:20])}...</code>"
        )
    elif status.startswith("skipped:"):
        send_message(f"🧪 <b>/test-live</b>: 🟡 skipped — <code>{_esc(status)}</code>")
    elif status.startswith("failed:"):
        send_message(f"🧪 <b>/test-live</b>: ❌ failed — <code>{_esc(status)}</code>")
    else:
        send_message(f"🧪 <b>/test-live</b>: unknown status — <code>{_esc(status)}</code>")


def _handle_help():
    """Handle /help command."""
    send_message(
        "<b>Polymarket Trading Bot \u2014 Commands</b>\n\n"
        "<b>Strategy #1 \u2014 Copy Trading</b>\n"
        "<code>/status</code> \u2014 Bot status, balance, positions\n"
        "<code>/pnl</code> \u2014 Unified P&amp;L across all strategies\n"
        "<code>/history</code> \u2014 Last 10 copy trades\n\n"
        "<b>Strategy #2 \u2014 Weather Betting</b>\n"
        "<code>/predict 11 Apr</code> \u2014 Run prediction for Apr 11\n"
        "<code>/predict</code> \u2014 Run prediction for default date\n"
        "<code>/takeprofit</code> \u2014 Close positions with &gt;30% profit\n\n"
        "<b>Strategy #3 \u2014 Tennis Arb</b>\n"
        "<code>/tennis</code> \u2014 Show current tennis divergences\n"
        "<code>/tennis_pnl</code> \u2014 Paper-book PnL with breakdown by event\n\n"
        "<b>Mode controls</b>\n"
        "<code>/mode</code> \u2014 Show preview/live mode per strategy\n"
        "<code>/live 3 CONFIRM</code> \u2014 Switch Strategy #3 to live trading\n"
        "<code>/preview 3</code> \u2014 Switch Strategy #3 back to preview\n"
        "<code>/check</code> \u2014 Verify trading setup (read-only)\n"
        "<code>/test-live</code> \u2014 Fire $5 live BUY on a 90%+ geopolitics market (smoke test)\n\n"
        "<b>Safety levers</b>\n"
        "<code>/setkey clear CONFIRM</code> \u2014 Wipe in-memory private key\n"
        "<code>/setkey 0xHEX CONFIRM</code> \u2014 Replace key in memory\n"
        "<code>/shutdown CONFIRM</code> \u2014 Graceful exit (container will restart)\n\n"
        "<code>/help</code> \u2014 Show this message\n\n"
        f"Strategy #1: {'ON' if CONFIG.strategy1_enabled else 'OFF'}\n"
        f"Strategy #2: {'ON' if CONFIG.strategy2_enabled else 'OFF'}\n"
        f"Strategy #3: {'ON' if CONFIG.strategy3_enabled else 'OFF'}\n"
        f"Take-profit threshold: {TAKE_PROFIT_PCT:.0%}"
    )


# --- Polling ---

def _process_update(update: dict) -> None:
    """Filter, parse, and dispatch a single Telegram getUpdates entry.

    Extracted from ``_poll_loop`` so the chat-id filter, command-prefix
    filter, and exception wrapper are unit-testable without standing up
    a polling thread. The wrapper is the kill-switch's safety net: if a
    handler raises, we log it and surface the error to the user instead
    of letting the exception kill the polling thread (and with it, all
    future Telegram control of the bot).
    """
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")

    if chat_id != CONFIG.telegram_chat_id:
        return

    if not text.startswith("/"):
        return

    logger.info(f"Telegram command: {text}")
    try:
        _handle_command(text)
    except Exception as e:
        logger.exception(f"Command handler error: {e}")
        send_message(f"Error: <code>{_esc(str(e))}</code>")


def _poll_loop():
    """Poll Telegram for new messages."""
    last_update_id = 0

    # Flush stale updates
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/getUpdates"
        resp = requests.get(url, params={"offset": -1, "timeout": 0}, timeout=10)
        if resp.ok:
            data = resp.json()
            results = data.get("result", [])
            if results:
                last_update_id = results[-1]["update_id"] + 1
    except Exception:
        pass

    logger.info("Telegram polling started")

    while not _stop_event.is_set():
        try:
            url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/getUpdates"
            resp = requests.get(url, params={
                "offset": last_update_id,
                "timeout": 10,
                "allowed_updates": '["message"]',
            }, timeout=15)

            if not resp.ok:
                time.sleep(5)
                continue

            data = resp.json()
            for update in data.get("result", []):
                last_update_id = update["update_id"] + 1
                _process_update(update)

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.warning(f"Telegram poll error: {e}")
            time.sleep(5)


def _register_bot_menu():
    """Register all bot commands in the Telegram UI menu."""
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/setMyCommands"
        requests.post(url, json={
            "commands": [
                {"command": "predict", "description": "Run weather prediction (e.g. /predict 11 Apr)"},
                {"command": "tennis", "description": "Show current tennis divergences"},
                {"command": "tennis_pnl", "description": "Tennis paper-book PnL with breakdown by event"},
                {"command": "mode", "description": "Show preview/live mode per strategy"},
                {"command": "live", "description": "Switch a strategy to live (e.g. /live 3 CONFIRM)"},
                {"command": "preview", "description": "Switch a strategy back to preview (e.g. /preview 3)"},
                {"command": "check", "description": "Verify trading setup (read-only, no orders)"},
                {"command": "test-live", "description": "Fire $5 live BUY on a 90%+ geopolitics market (smoke test)"},
                {"command": "setkey", "description": "Rotate/clear in-memory private key (e.g. /setkey clear CONFIRM)"},
                {"command": "shutdown", "description": "Graceful shutdown (Docker restarts container)"},
                {"command": "status", "description": "Balance, positions, daily limits"},
                {"command": "pnl", "description": "Unified P&L across all strategies"},
                {"command": "history", "description": "Last 10 copy trades"},
                {"command": "takeprofit", "description": "Close positions with >30% profit"},
                {"command": "help", "description": "Show all commands"},
            ],
        }, timeout=10)
    except Exception:
        pass  # non-critical -- menu just won't update


def start_polling():
    """Start telegram polling in a background thread."""
    global _poll_thread
    if not is_configured():
        logger.info("Telegram not configured, skipping poll")
        return
    _register_bot_menu()
    _stop_event.clear()
    _poll_thread = threading.Thread(target=_poll_loop, daemon=True, name="telegram-poll")
    _poll_thread.start()
    logger.info("Telegram polling thread started")


def stop_polling():
    """Stop telegram polling."""
    _stop_event.set()
    if _poll_thread:
        _poll_thread.join(timeout=15)
    logger.info("Telegram polling stopped")
