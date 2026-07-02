"""Telegram bot for the copy-trading strategy (Strategy #1).

Commands:
  /status            — Show bot status (balance, positions, daily limits)
  /pnl               — Show P&L: realized + unrealized
  /history           — Show last 10 copy trades
  /check             — Verify trading setup (read-only, no orders)
  /setkey            — Rotate/clear the in-memory private key
  /shutdown          — Graceful shutdown (Docker restarts the container)
  /help              — Show available commands

The Weather (#2) and Tennis Arb (#3) strategies were decommissioned on
2026-06-17; see DECOMMISSIONED.md to restore them from git history.
"""

import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

import requests

from src.config import CONFIG
from src.copy_trading import promotion_state

logger = logging.getLogger("telegram")

SGT = timezone(timedelta(hours=8))


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TELEGRAM_API = "https://api.telegram.org/bot{token}"

# Commands registered in the Telegram popup menu (setMyCommands).
# Names must match ^[a-z0-9_]{1,32}$ — Telegram rejects the entire batch
# otherwise. Every name listed here MUST also be dispatched in
# ``_handle_command``; the parity is enforced by
# ``tests/test_telegram_handlers.py::test_bot_menu_matches_dispatcher``.
BOT_MENU_COMMANDS: list[dict] = [
    {"command": "start", "description": "Show all commands"},
    {"command": "help", "description": "Show all commands"},
    {"command": "status", "description": "Balance, positions, daily limits"},
    {"command": "pnl", "description": "P&L by strategy: realized + unrealized + total"},
    {"command": "wallets", "description": "Top wallets overall + best/worst per strategy (deduped)"},
    {"command": "gate", "description": "LLM wallet-gate: admit/reject mix + per-theory + recent rejects"},
    {"command": "history", "description": "Last 10 copy trades"},
    {"command": "check", "description": "Verify trading setup (read-only, no orders)"},
    {"command": "setkey", "description": "Rotate/clear in-memory private key (e.g. /setkey clear CONFIRM)"},
    {"command": "reset", "description": "Zero all P&L + risk/spend state (archives first; needs CONFIRM)"},
    {"command": "promote", "description": "Promote a paper-validated wallet to System A (tier 1b, paper)"},
    {"command": "shutdown", "description": "Graceful shutdown (Docker restarts container)"},
]

_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()

# Callbacks set by main.py
on_refresh_clob_client = None  # Callable[[], None] — rebuild CLOB client after /setkey


def is_configured() -> bool:
    """Check if Telegram bot is configured."""
    return bool(CONFIG.telegram_bot_token) and bool(CONFIG.telegram_chat_id)


def send_message(text: str, parse_mode: str = "HTML", reply_markup: dict | None = None) -> bool:
    """Send a message to the configured Telegram chat.

    ``reply_markup`` attaches an inline keyboard (tap-to-act buttons). Returns
    True iff the message was actually delivered, so callers that must not repeat
    on failure (e.g. a one-time promote offer) can gate on it."""
    if not is_configured():
        return False
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/sendMessage"
        payload = {
            "chat_id": CONFIG.telegram_chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            logger.warning(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
        return bool(resp.ok)
    except Exception as e:
        logger.warning(f"Telegram send error: {e}")
        return False


def _answer_callback(callback_query_id: str, text: str = "") -> None:
    """Acknowledge a button tap so Telegram stops the client-side spinner."""
    if not is_configured() or not callback_query_id:
        return
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/answerCallbackQuery"
        requests.post(url, json={"callback_query_id": callback_query_id,
                                 "text": text[:200]}, timeout=10)
    except Exception as e:
        logger.warning(f"Telegram answerCallbackQuery error: {e}")


def _edit_message(chat_id: str, message_id: int, text: str,
                  parse_mode: str = "HTML") -> None:
    """Replace an offer message's text (and drop its buttons) after a tap."""
    if not is_configured() or not message_id:
        return
    try:
        url = f"{TELEGRAM_API.format(token=CONFIG.telegram_bot_token)}/editMessageText"
        requests.post(url, json={
            "chat_id": chat_id, "message_id": message_id, "text": text,
            "parse_mode": parse_mode, "disable_web_page_preview": True,
        }, timeout=10)
    except Exception as e:
        logger.warning(f"Telegram editMessageText error: {e}")


def _signed_usd(x: float) -> str:
    return f"{'+' if x >= 0 else '-'}${abs(x):,.0f}"


def send_promotion_offer(wallet: str, n_closed: int, roi: float,
                         net_pnl: float, tier: str = "1b") -> bool:
    """One-tap promote offer: the paper book proved this wallet out. Tapping
    Promote adds it to System A (still PREVIEW) with no typing — no UUID to copy."""
    text = (
        "🎓 <b>Promote candidate</b> — paper book matured\n"
        f"<code>{_esc(wallet)}</code>\n"
        f"<b>{n_closed}</b> settled copies · ROI <b>{roi * 100:+.0f}%</b> · "
        f"net <b>{_signed_usd(net_pnl)}</b>\n"
        f"Tap to add to System A (tier {tier}, still PREVIEW/paper)."
    )
    keyboard = {"inline_keyboard": [[
        {"text": f"✅ Promote → {tier}", "callback_data": f"promo:{wallet}"},
        {"text": "✖ Dismiss", "callback_data": f"dism:{wallet}"},
    ]]}
    return send_message(text, reply_markup=keyboard)


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


# --- Command handlers ---

def _handle_command(text: str):
    """Process a telegram command."""
    text = text.strip()

    if text.startswith("/history"):
        _handle_history()
    elif text.startswith("/status"):
        _handle_status()
    elif text.startswith("/pnl"):
        _handle_pnl()
    elif text.startswith("/wallets"):
        _handle_wallets()
    elif text.startswith("/gate"):
        _handle_gate()
    elif text.startswith("/check"):
        _handle_check()
    elif text.startswith("/setkey"):
        _handle_setkey(text)
    elif text.startswith("/reset"):
        _handle_reset(text)
    elif text.startswith("/promote"):
        _handle_promote(text)
    elif text.startswith("/shutdown"):
        _handle_shutdown(text)
    elif text.startswith("/help") or text.startswith("/start"):
        _handle_help()
    else:
        return


def _handle_status():
    """Handle /status command — show Strategy #1 status."""
    now = datetime.now(SGT)

    lines = [
        f"<b>Bot Status</b>",
        f"Time: {now.strftime('%Y-%m-%d %H:%M SGT')}",
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}",
        "",
    ]

    # Strategy #1 — Copy Trading
    lines.append(f"<b>Strategy #1 — Copy Traders</b>")
    if CONFIG.strategy1_enabled:
        lines.append("Status: \U0001f7e2 ENABLED")
        lines.append(f"Wallets tracked: {len(CONFIG.user_addresses)}")
        lines.append(f"Copy strategy: {CONFIG.copy_strategy}")
        lines.append(f"Copy size: ${CONFIG.copy_size:.0f}")
        s1_trades = _load_s1_trades()
        if s1_trades:
            total_cost = sum((t.get("cost") or 0) for t in s1_trades)
            lines.append(f"Total deployed: ${total_cost:.2f}")
            lines.append(f"Total trades: {len(s1_trades)}")
    else:
        lines.append("Status: ⚪ DISABLED")

    send_message("\n".join(lines))


def _short_wallet(w: str) -> str:
    """0x1234…cdef — compact wallet address for leaderboard lines."""
    w = w or ""
    return f"{w[:6]}…{w[-4:]}" if len(w) > 12 else (w or "—")


def _mark_open_paper(positions, fetch_mid) -> None:
    """Mark open (non-dust) near-term paper copies to market in place, on-read.

    ``fetch_mid(token_id) -> float | None``. Only currently-open positions are
    priced, so the network cost scales with the live book, not the ledger's full
    history. Pure aside from the single mid fetch per open; never persists."""
    from src.copy_trading.copy_paper import is_dust_fill

    for p in positions:
        if not p.closed and not is_dust_fill(p):
            mid = fetch_mid(p.token_id)
            if mid is not None and mid > 0:
                p.mark(float(mid))


def _compute_unified():
    """Build the unified per-strategy / per-wallet P&L across both copy systems.

    System A = tiered executor (``realized-pnl.jsonl`` + open inventory marked to
    midpoint, attributed by tier/trader). System B = the paper-copy harness
    ledger (attributed by ``target`` wallet + discovery theories). Returns
    ``(unified, a_wallets, b_wallets, n_unpriced)`` so /pnl and /wallets share
    one computation.
    """
    from src.copy_trading import inventory
    from src.copy_trading import pnl as s1pnl
    from src.copy_trading import pnl_unified as u
    from src.copy_trading.copy_paper import PaperCopyLedger
    from src.copy_trading.copy_paper_live import load_watchlist_flagged_by
    from src.copy_trading.strategy_config import get_wallet_tier

    # System A — tiered executor
    realized_rows = s1pnl.load_realized()
    positions = inventory.get_positions()
    open_pos = s1pnl.value_open_positions(positions, _fetch_midpoint, fee=0.0)
    n_unpriced = sum(1 for p in open_pos if p.unrealized_pnl is None)
    a_wallets = u.aggregate_system_a(realized_rows, open_pos, tier_of=get_wallet_tier)

    # System B — paper-copy harness
    try:
        ledger = PaperCopyLedger(CONFIG.copy_paper_ledger)
        paper_positions = list(ledger.positions.values())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"copy-paper ledger load failed: {e}")
        paper_positions = []
    # Mark open near-term copies to market on-read, exactly like the System-A
    # opens priced above. Deliberately here and NOT in the 60s harness cycle: a
    # per-cycle mark would fire a full ledger re-serialize every minute and burst
    # N synchronous CLOB fetches that stall trade detection. This mutates the
    # freshly-loaded positions in memory only (never persisted) and touches the
    # network solely when the owner asks for /pnl.
    _mark_open_paper(paper_positions, _fetch_midpoint)
    flagged_now = load_watchlist_flagged_by(CONFIG.copy_paper_watchlist)
    b_wallets = u.aggregate_system_b(paper_positions, flagged_now)

    # Strategy 4 — long-horizon paper book (its own ledger, marked to market).
    # Appended to the System-B wallet list as the distinct "S4" track so a
    # dual-membership wallet shows its near-term copier track and its long-horizon
    # track side by side. Absent/empty when Strategy 4 is off.
    if CONFIG.strategy_4_enabled:
        try:
            s4_ledger = PaperCopyLedger(CONFIG.strategy_4_paper_ledger)
            s4_positions = list(s4_ledger.positions.values())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"s4 paper ledger load failed: {e}")
            s4_positions = []
        b_wallets = b_wallets + u.aggregate_strategy4(s4_positions)

    unified = u.build_unified(a_wallets, b_wallets)
    return unified, a_wallets, b_wallets, n_unpriced


def _handle_pnl():
    """Handle /pnl — unified P&L: overall total + per-strategy breakdown.

    Strategy labels are ``A:1a``/``A:1b``/``A:1c`` (executor tiers) and
    ``B:1a``..``B:1j`` (discovery theories the paper-copied wallet was flagged
    by), plus ``untagged-*`` for un-attributed positions."""
    from src.copy_trading import pnl_unified as u

    unified, a_wallets, b_wallets, n_unpriced = _compute_unified()

    all_w = a_wallets + b_wallets
    total_open = sum(w.n_open for w in all_w)
    total_closed = sum(w.n_closed for w in all_w)
    wins = sum(w.wins for w in all_w)
    losses = sum(w.losses for w in all_w)

    lines = ["\U0001f4ca <b>P&amp;L Report</b>", ""]
    lines.append("<b>TOTAL</b>")
    lines.append(f"  Realized:    <b>${unified.total_realized:+.2f}</b>")
    lines.append(f"  Unrealized:  <b>${unified.total_unrealized:+.2f}</b>")
    lines.append(f"  Net:         <b>${unified.total_net:+.2f}</b>")
    lines.append(f"  Open bets:   <b>{total_open}</b>")
    if total_closed:
        hit = wins / total_closed if total_closed else 0.0
        lines.append(f"  Record:      <b>{wins}W/{losses}L</b> ({hit:.0%} hit)")
    # Honest open-exposure footer: the paper-copy book (System B) opens are marked
    # to market when a live mid is available; disclose how much open capital is at
    # risk and how much of it is unpriced (so the Unrealized above isn't mistaken
    # for the whole picture). System A unpriced opens are counted separately.
    b_open = sum(w.n_open for w in b_wallets)
    if b_open:
        b_open_cost = sum(w.open_cost for w in b_wallets)
        b_unmarked = b_open - sum(w.n_open_marked for w in b_wallets)
        line = f"  Paper open:  <b>${b_open_cost:,.0f}</b> in {b_open} position(s)"
        if b_unmarked:
            line += f" (⚠ {b_unmarked} unpriced, not in Unrealized)"
        lines.append(line)
    if n_unpriced:
        lines.append(f"  ⚠ {n_unpriced} System-A position(s) unpriced (no live quote)")

    lines.append("")
    lines.append("<b>By strategy</b>  <i>(🧊/🌱/✅ settled | net | r/u | ROI | wallets | closed/open | hit lo)</i>")
    if not unified.strategies:
        lines.append("  (no positions yet)")
    for sp in unified.strategies:
        roi = sp.roi
        roi_str = f"ROI {roi:+.0%}" if roi is not None else "ROI n/a"
        # Show realized + unrealized for System A and any System-B/S4 strategy that
        # has marked-to-market opens; strategies with no live mark show realized only.
        if sp.system == "A" or sp.unrealized_pnl:
            pnl_str = f"r ${sp.realized_pnl:+.0f}/u ${sp.unrealized_pnl:+.0f}"
        else:
            pnl_str = f"r ${sp.realized_pnl:+.0f}"
        # Maturity glyph + Wilson hit-rate lower bound so a tiny-n fluke (common
        # for the freshly-enabled 1a/1e/1j) doesn't read as a proven edge.
        tag = u.maturity_tag(sp.n_closed)
        lo = u.wilson_lower_bound(sp.wins, sp.wins + sp.losses)
        hit_str = ""
        if lo is not None:
            hit_str = f" · hit {sp.wins / (sp.wins + sp.losses):.0%} (lo {lo:.0%})"
        lines.append(
            f"{tag} <b>{_esc(sp.label)}</b>  <b>${sp.net_pnl:+.2f}</b>  "
            f"({pnl_str}, <b>{roi_str}</b>)  "
            f"— {sp.n_wallets}w {sp.n_closed}c/{sp.n_open}o{hit_str}"
        )

    lines.append("")
    lines.append("<i>/wallets — top wallets overall + best/worst per strategy</i>")
    if CONFIG.preview_mode:
        lines.append("<i>PREVIEW MODE — positions are simulated</i>")

    _send_chunked("\n".join(lines))


def _wallet_line(w, *, tags=None, strategies=None) -> str:
    """One leaderboard row: maturity glyph, addr, net P&L, ROI, win/loss record,
    and — for paper (System B) wallets — a PROMOTE-READY/HOLD verdict that gates
    the manual promote-to-real-money call on settled sample size + positive PnL.

    ``tags`` annotates *why* a wallet is notable within a strategy (e.g.
    ``▲PnL ▲ROI``); ``strategies`` lists the strategy labels a wallet spans (used
    in the cross-strategy top section)."""
    from src.copy_trading import pnl_unified as u

    roi = w.roi
    roi_str = f"ROI {roi:+.0%}" if roi is not None else "ROI n/a"
    rec = f", {w.wins}W/{w.losses}L" if (w.wins + w.losses) else ""
    tag = u.maturity_tag(w.n_closed)
    verdict = ""
    if w.system == "B":
        v, reason = u.promotion_verdict(w.net_pnl, w.n_closed)
        verdict = f" → <b>{v}</b>: {reason}"
    line = (f"{tag} <code>{_short_wallet(w.wallet)}</code> "
            f"<b>${w.net_pnl:+.2f}</b> ({roi_str}{rec}){verdict}")
    if strategies:
        line += f"  <i>[{_esc(', '.join(strategies))}]</i>"
    elif tags:
        line += f"  <i>{_esc(' '.join(tags))}</i>"
    return line


def _handle_wallets():
    """Handle /wallets — a readable promote/drop leaderboard.

    Part 1 is the top wallets *across all strategies* (the best overall promotion
    candidates, each shown once with the strategies it spans). Part 2 is a
    per-strategy breakdown that lists each wallet **once**, tagged with whether it
    led/trailed on PnL and/or ROI — replacing the old four overlapping best/worst
    lists that printed the same wallet several times."""
    from src.copy_trading import pnl_unified as u

    unified, a_w, b_w, _n = _compute_unified()
    if not unified.strategies:
        send_message("\U0001f3c5 <b>Wallet leaderboard</b>\nNo positions yet.")
        return

    lines = [
        "\U0001f3c5 <b>Wallet leaderboard</b> <i>(promotion / removal candidates)</i>",
        "",
        "<b>\U0001f3c6 Top wallets — all strategies</b>",
    ]
    top = u.top_wallets(a_w, b_w, k=3)
    if top:
        for w in top:
            lines.append("  " + _wallet_line(w, strategies=list(w.strategies)))
    else:
        lines.append("  <i>(no profitable wallets yet)</i>")

    lines.append("")
    lines.append("<b>By strategy</b>  <i>(▲/▼ = top/bottom by PnL / ROI)</i>")
    lines.append("")

    for sp in unified.strategies:
        lines.append(f"<b>{_esc(sp.label)}</b>  ({sp.n_wallets}w)")
        for h in u.strategy_highlights(sp.wallets, k=3):
            lines.append("  " + _wallet_line(h.wallet, tags=h.tags))
        lines.append("")

    _send_chunked("\n".join(lines))


def _gate_history_path() -> str:
    """gate-history.jsonl lives beside the discovery state file."""
    return os.path.join(os.path.dirname(CONFIG.wallet_discovery_state), "gate-history.jsonl")


def _handle_gate():
    """Handle /gate — the LLM wallet-gate admit/reject picture.

    Surfaces what used to need a prod-log trawl: the accept/reject mix, the mix
    sliced by which theory qualified each wallet (so a theory the gate rejects
    wholesale is obvious), and the most recent rejection reasons."""
    from src.copy_trading import gate_history

    # Bounded read: gate-history.jsonl is append-only; cap the /gate summary to the
    # most recent decisions so the command stays fast and memory-bounded no matter
    # how long the log has grown (gate reviews accrue slowly, so this is ~years).
    rows = gate_history.load(_gate_history_path(), limit=5000)
    if not rows:
        _send_chunked("\U0001f6aa <b>LLM Gate</b>\n\n(no gate decisions logged yet)")
        return
    s = gate_history.summarize(rows)
    total, adm, rej = s["total"], s["admitted"], s["rejected"]
    adm_pct = adm / total if total else 0.0

    lines = ["\U0001f6aa <b>LLM Gate</b>", ""]
    lines.append(f"Decisions: <b>{total}</b>   admitted <b>{adm}</b> ({adm_pct:.0%})   "
                 f"rejected <b>{rej}</b>")

    if s["per_theory"]:
        lines.append("")
        lines.append("<b>By qualifying theory</b>  <i>(admit/total)</i>")
        # busiest theories first
        for tid, c in sorted(s["per_theory"].items(),
                             key=lambda kv: -(kv[1]["admit"] + kv[1]["reject"])):
            n = c["admit"] + c["reject"]
            lines.append(f"  <b>{_esc(tid)}</b>  {c['admit']}/{n} admitted")

    if s["recent_rejections"]:
        lines.append("")
        lines.append("<b>Recent rejections</b>")
        for r in reversed(s["recent_rejections"]):
            w = _short_wallet(r.get("wallet") or "")
            conf = r.get("confidence")
            conf_s = f" ({conf:.0%})" if isinstance(conf, (int, float)) else ""
            reason = _esc((r.get("reasoning") or "")[:160])
            lines.append(f"  <b>{w}</b>{conf_s}: {reason}")

    _send_chunked("\n".join(lines))


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


def _handle_setkey(text: str):
    """Handle /setkey <hex|clear> CONFIRM — rotate or wipe the in-memory key.

    Safety lever to immediately invalidate signed orders. Change is in-memory
    only; on container restart the .env value reloads. Strategy #1's running
    loops hold the CLOB client obtained at startup, so a rotated key fully
    takes effect on the next restart.
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
            "CLOB client invalidated; live trading cannot sign new orders. "
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


def _handle_reset(text: str):
    """Handle /reset CONFIRM — zero all P&L + risk/spend state (archives first).

    Clears both copy systems' ledgers/state and the executor's in-memory
    counters. The paper-copy harness holds its ledger in memory in a daemon
    thread, so to fully clear System B you must restart: this prompts a
    /shutdown so the container comes back up on the empty ledger. For a
    guaranteed-clean reset, run ``python -m scripts.reset_pnl --confirm`` on the
    VM with the bot stopped.
    """
    parts = text.split()
    if len(parts) != 2 or parts[1] != "CONFIRM":
        send_message(
            "Usage: <code>/reset CONFIRM</code>\n"
            "Zeroes <b>all</b> P&amp;L + risk/spend state for both copy systems "
            "(archives a timestamped backup first). Open/unredeemed bets are dropped.\n"
            "After it runs, send <code>/shutdown CONFIRM</code> so the paper "
            "harness restarts on the empty ledger."
        )
        return

    from src.copy_trading.reset_pnl import reset_pnl

    res = reset_pnl(
        CONFIG.data_dir, confirm=True,
        copy_paper_ledger=CONFIG.copy_paper_ledger,
        s4_paper_ledger=CONFIG.strategy_4_paper_ledger,
    )
    logger.warning("P&L reset via /reset CONFIRM")
    send_message(
        "🧹 <b>P&amp;L reset</b> — " + _esc(res.summary()) + ".\n"
        "Executor + risk/spend state zeroed and backed up to <code>data/archive/</code>.\n"
        "The paper-copy harness keeps its ledger in memory — send "
        "<code>/shutdown CONFIRM</code> now to restart it on the empty ledger "
        "(Docker brings the container back automatically)."
    )


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
    # Kick off a delayed hard exit so the Telegram send_message above flushes.
    def _delayed_exit():
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
            from py_clob_client_v2 import BalanceAllowanceParams, AssetType
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            ba = clob_client.get_balance_allowance(params)
            lines.append(f"✅ CLOB /balance-allowance OK: {ba}")
        except Exception as e:
            lines.append(f"⚠️ CLOB authed read failed: <code>{_esc(str(e))}</code>")

    lines.append("")
    lines.append("<b>READY</b> ✅" if ok_all else "<b>NOT READY</b> ❌ — fix items above before going live (PREVIEW_MODE=false)")
    _send_chunked("\n".join(lines))


def _handle_help():
    """Handle /help command."""
    send_message(
        "<b>Polymarket Copy-Trading Bot — Commands</b>\n\n"
        "<b>Strategy #1 — Copy Trading</b>\n"
        "<code>/status</code> — Bot status, balance, positions\n"
        "<code>/pnl</code> — P&amp;L by strategy: realized + unrealized + total\n"
        "<code>/wallets</code> — Top wallets overall + best/worst per strategy\n"
        "<code>/gate</code> — LLM wallet-gate: admit/reject mix + per-theory + recent rejects\n"
        "<code>/history</code> — Last 10 copy trades\n"
        "<code>/check</code> — Verify trading setup (read-only)\n\n"
        "<b>Safety levers</b>\n"
        "<code>/setkey clear CONFIRM</code> — Wipe in-memory private key\n"
        "<code>/setkey 0xHEX CONFIRM</code> — Replace key in memory\n"
        "<code>/reset CONFIRM</code> — Zero all P&amp;L + risk/spend state (archives first)\n"
        "<code>/shutdown CONFIRM</code> — Graceful exit (container will restart)\n\n"
        "<code>/help</code> — Show this message\n\n"
        f"Strategy #1: {'ON' if CONFIG.strategy1_enabled else 'OFF'}\n"
        f"Mode: {'PREVIEW' if CONFIG.preview_mode else 'LIVE'}"
    )


# --- Promote (one-tap wallet -> System A) ---

def _default_promote_tier() -> str:
    t = (CONFIG.promote_default_tier or "1b").lower()
    return t if t in promotion_state.VALID_TIERS else "1b"


def _resolve_promote_target(query: str) -> str | None:
    """Map a /promote argument to a wallet address.

    Accepts a full 0x address, or a prefix that uniquely matches a wallet we've
    offered for promotion (so the owner never has to paste a whole UUID). Returns
    None when nothing — or more than one thing — matches."""
    q = (query or "").strip().lower()
    if not q:
        return None
    if q.startswith("0x") and len(q) == 42:
        return q
    matches = {}
    for rec in promotion_state.offers_map().values():
        w = rec.get("wallet") or ""
        if w and w.lower().startswith(q):
            matches[w.lower()] = w
    vals = list(matches.values())
    return vals[0] if len(vals) == 1 else None


def _handle_promote(text: str) -> None:
    """/promote <wallet-or-prefix> — add a paper-validated wallet to System A.

    The primary path is the one-tap button on a promote offer; this command is a
    typed fallback that still avoids pasting the full address (a prefix works)."""
    parts = text.split()
    tier = _default_promote_tier()
    if len(parts) < 2:
        send_message(
            "Usage: <code>/promote &lt;wallet-or-prefix&gt;</code>\n"
            f"Adds a paper-validated wallet to System A (tier {tier}, still PREVIEW/paper).\n"
            "Tip: just tap the <b>✅ Promote</b> button on a promote offer."
        )
        return
    wallet = _resolve_promote_target(parts[1])
    if wallet is None:
        send_message(
            f"No unique promote candidate matches <code>{_esc(parts[1])}</code>. "
            "Use the full 0x address or a longer prefix."
        )
        return
    promotion_state.add_promoted(wallet, tier=tier, source="telegram-cmd")
    promotion_state.record_offer(wallet, status="accepted")
    send_message(
        f"✅ <b>Promoted</b> <code>{_esc(wallet)}</code> → tier {tier} "
        "(System A, still PREVIEW/paper). It now also trades there; flip "
        "PREVIEW_MODE off to go live."
    )


def _handle_callback(data: str) -> tuple[str, str | None]:
    """Process an inline-button tap. Returns (toast, edited_message_text|None)."""
    if data.startswith("promo:"):
        wallet = data[len("promo:"):]
        tier = _default_promote_tier()
        promotion_state.add_promoted(wallet, tier=tier, source="telegram")
        promotion_state.record_offer(wallet, status="accepted")
        return (
            f"Promoted → {tier}",
            f"✅ <b>Promoted</b> <code>{_esc(wallet)}</code> → tier {tier} "
            "(System A, still PREVIEW/paper).",
        )
    if data.startswith("dism:"):
        wallet = data[len("dism:"):]
        promotion_state.record_offer(wallet, status="dismissed")
        return ("Dismissed", f"✖ Dismissed <code>{_esc(wallet)}</code> — not promoted.")
    return ("Unknown action", None)


def _process_callback(cq: dict) -> None:
    """Filter, dispatch, and acknowledge a single callback_query (button tap)."""
    chat_id = str(cq.get("message", {}).get("chat", {}).get("id", ""))
    if chat_id != CONFIG.telegram_chat_id:
        return
    data = cq.get("data", "") or ""
    cq_id = cq.get("id", "")
    message_id = cq.get("message", {}).get("message_id")
    logger.info(f"Telegram callback: {data[:60]}")
    try:
        toast, edited = _handle_callback(data)
    except Exception as e:
        logger.exception(f"Callback handler error: {e}")
        _answer_callback(cq_id, "Error")
        return
    _answer_callback(cq_id, toast)
    if edited and message_id:
        _edit_message(chat_id, message_id, edited)


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
    cq = update.get("callback_query")
    if cq:
        try:
            _process_callback(cq)
        except Exception as e:
            logger.exception(f"Callback dispatch error: {e}")
        return

    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")

    if chat_id != CONFIG.telegram_chat_id:
        return

    if not text:
        return

    if text.startswith("/"):
        logger.info(f"Telegram command: {text}")
        try:
            _handle_command(text)
        except Exception as e:
            logger.exception(f"Command handler error: {e}")
            send_message(f"Error: <code>{_esc(str(e))}</code>")
        return


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
                "allowed_updates": '["message","callback_query"]',
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
    """Register all bot commands in the Telegram UI menu.

    Telegram rejects the entire batch (HTTP 200 with ok=false) if any single
    command name violates ^[a-z0-9_]{1,32}$. We surface that rejection in
    logs and on Telegram so a typo doesn't silently wipe the popup menu.

    Telegram resolves the popup menu per chat by picking the most-specific
    scope that has commands set: chat_member > chat_administrators > chat >
    all_chat_administrators > all_private_chats / all_group_chats > default.
    A stale list on any narrower scope hides our default-scope list — so
    before we register the default, we clear every broader-than-default
    scope we ever might have set. (Per-chat scopes can only be set by
    explicit chat_id and aren't touched here.)
    """
    base = TELEGRAM_API.format(token=CONFIG.telegram_bot_token)

    # Wipe scoped command lists that would shadow the default scope.
    for scope in (
        {"type": "all_private_chats"},
        {"type": "all_group_chats"},
        {"type": "all_chat_administrators"},
    ):
        try:
            r = requests.post(f"{base}/deleteMyCommands", json={"scope": scope}, timeout=10)
            if not (r.ok and r.json().get("ok")):
                logger.warning(f"deleteMyCommands {scope['type']} failed: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"deleteMyCommands {scope['type']} error: {e}")

    try:
        resp = requests.post(f"{base}/setMyCommands", json={"commands": BOT_MENU_COMMANDS}, timeout=10)
        body = {}
        try:
            body = resp.json()
        except Exception:
            pass
        if resp.ok and body.get("ok"):
            logger.info("Telegram menu: registered %d commands", len(BOT_MENU_COMMANDS))
        else:
            err = body.get("description") or f"HTTP {resp.status_code}"
            logger.error(f"Telegram setMyCommands rejected: {err}")
            try:
                send_message(f"⚠️ Telegram menu update failed: <code>{_esc(err)}</code>")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Telegram setMyCommands error: {e}")


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
